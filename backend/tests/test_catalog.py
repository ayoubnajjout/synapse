import asyncio

import httpx
import pytest

from app import catalog
from app.catalog import fetch_catalog
from app.schemas import ProviderConfig


@pytest.mark.parametrize(("provider", "path", "payload", "expected"), [
    ("openai", "/v1/models", {"data": [{"id": "future-chat-model"}, {"id": "text-embedding-3-small"}, {"id": "gpt-image-1"}]}, ["future-chat-model"]),
    ("anthropic", "/v1/models", {"data": [{"id": "claude-future"}, {"id": "claude-retired", "lifecycle": "retired"}]}, ["claude-future"]),
    ("gemini", "/v1beta/models", {"models": [{"name": "models/gemini-future", "supportedGenerationMethods": ["generateContent"]}, {"name": "models/embed", "supportedGenerationMethods": ["embedContent"]}]}, ["gemini-future"]),
    ("xai", "/v1/language-models", {"models": [{"id": "grok-future"}]}, ["grok-future"]),
    ("ollama", "/api/tags", {"models": [{"name": "local-model:latest"}, {"model": "another:8b"}]}, ["another:8b", "local-model:latest"]),
    ("lmstudio", "/v1/models", {"data": [{"id": "loaded/model"}]}, ["loaded/model"]),
])
def test_catalog_protocols(monkeypatch, provider, path, payload, expected):
    original = httpx.AsyncClient
    def handler(request):
        assert request.url.path == path
        assert "test-catalog-key" not in str(request.url)
        if provider == "gemini":
            assert request.headers["x-goog-api-key"] == "test-catalog-key"
        elif provider == "anthropic":
            assert request.headers["x-api-key"] == "test-catalog-key"
        else:
            assert request.headers["authorization"] == "Bearer test-catalog-key"
        return httpx.Response(200, json=payload)
    monkeypatch.setattr(catalog.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    base = "http://models.test" + ("/v1" if provider in ("openai", "lmstudio", "xai") else "")
    assert asyncio.run(fetch_catalog(provider, base, "test-catalog-key")) == (expected, False)


@pytest.mark.parametrize("provider", ["gemini", "anthropic"])
def test_catalog_pagination(monkeypatch, provider):
    original = httpx.AsyncClient
    calls = []
    def handler(request):
        calls.append(request)
        if provider == "gemini":
            page = {"models": [{"name": f"models/chat-{len(calls)}", "supportedGenerationMethods": ["generateContent"]}]}
            if len(calls) == 1:
                page["nextPageToken"] = "page-two"
            else:
                assert request.url.params["pageToken"] == "page-two"
        else:
            page = {"data": [{"id": f"chat-{len(calls)}"}], "has_more": len(calls) == 1, "last_id": "chat-1"}
            if len(calls) == 2:
                assert request.url.params["after_id"] == "chat-1"
        return httpx.Response(200, json=page)
    monkeypatch.setattr(catalog.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    assert asyncio.run(fetch_catalog(provider, "http://models.test", "key")) == (["chat-1", "chat-2"], False)
    assert len(calls) == 2


def test_live_discovery_cache_refresh_and_custom_fallback(client, monkeypatch):
    calls = []
    async def available(provider, base, key):
        calls.append((provider, base))
        return ["new-chat-model"], False
    monkeypatch.setattr(catalog, "fetch_catalog", available)
    response = client.get("/api/providers/openai/models")
    assert response.json()["models"] == ["new-chat-model"]
    assert response.json()["source"] == "live"
    assert client.get("/api/providers/openai/models").json()["source"] == "cached"
    assert len(calls) == 1
    assert client.get("/api/providers/openai/models?refresh=true").json()["source"] == "live"
    assert len(calls) == 2
    config = {"models": ["custom/private-model"], "default_model": "custom/private-model"}
    assert client.patch("/api/settings", json={"providers": {"openai": config}}).status_code == 200
    async def unavailable(*args):
        raise RuntimeError("DO-NOT-EXPOSE-secret-key")
    monkeypatch.setattr(catalog, "fetch_catalog", unavailable)
    failed = client.get("/api/providers/openai/models?refresh=true")
    assert failed.json()["models"] == ["custom/private-model", "new-chat-model"]
    assert failed.json()["default_model"] == "custom/private-model"
    assert failed.json()["warning"]
    assert "DO-NOT-EXPOSE" not in failed.text
    # A failed catalog call never destroys the persisted configuration.
    saved = client.get("/api/providers").json()[0]
    assert saved["models"] == ["custom/private-model"]
    assert saved["saved_models"] == ["custom/private-model"]


def test_catalog_cache_does_not_cross_endpoints_or_credentials(client, monkeypatch):
    calls = []
    async def available(provider, base, key):
        calls.append((base, key))
        return [f"model-{len(calls)}"], False
    monkeypatch.setattr(catalog, "fetch_catalog", available)
    assert client.get("/api/providers/openai/models").json()["models"] == ["model-1"]
    monkeypatch.setenv("OPENAI_API_KEY", "changed-secret")
    assert client.get("/api/providers/openai/models").json()["models"] == ["model-2"]
    client.patch("/api/settings", json={"providers": {"openai": {"api_base": "http://other.test/v1"}}})
    assert client.get("/api/providers/openai/models").json()["models"] == ["model-3"]


def test_unconfigured_provider_does_not_make_network_requests(client, monkeypatch):
    async def forbidden(*args):
        pytest.fail("Unconfigured provider attempted discovery")
    monkeypatch.setattr(catalog, "fetch_catalog", forbidden)
    assert client.get("/api/providers/ollama/models").json()["source"] == "unavailable"
    assert client.get("/api/providers/unknown/models").status_code == 404
