import asyncio
import uuid

import httpx
import pytest

from app import catalog, llm
from app.config import resolve_api_base


@pytest.mark.parametrize(("provider", "address", "container", "expected"), [
    ("ollama", "http://localhost:11434", True, "http://host.docker.internal:11434"),
    ("ollama", "http://127.0.0.1:11434/", True, "http://host.docker.internal:11434"),
    ("ollama", "http://[::1]:11434/api/tags", True, "http://host.docker.internal:11434"),
    ("ollama", "http://localhost:11434/v1", True, "http://host.docker.internal:11434"),
    ("ollama", "http://localhost:11434/api/chat", False, "http://localhost:11434"),
    ("ollama", "http://ollama:11434", True, "http://ollama:11434"),
    ("ollama", "http://192.168.1.5:11434/proxy/api/tags", True, "http://192.168.1.5:11434/proxy"),
    ("lmstudio", "http://localhost:1234", True, "http://host.docker.internal:1234/v1"),
    ("lmstudio", "http://localhost:1234/v1/models", True, "http://host.docker.internal:1234/v1"),
    ("lmstudio", "http://localhost:1234/v1/chat/completions", False, "http://localhost:1234/v1"),
    ("openai", "http://localhost:9000/v1", True, "http://localhost:9000/v1"),
])
def test_local_addresses(monkeypatch, provider, address, container, expected):
    monkeypatch.setenv("SYNAPSE_CONTAINER", "1" if container else "0")
    assert resolve_api_base(provider, address) == expected


@pytest.mark.parametrize(("provider", "address", "expected"), [
    ("ollama", "http://localhost:11434/v1", "http://host.docker.internal:11434"),
    ("lmstudio", "http://localhost:1234", "http://host.docker.internal:1234/v1"),
])
def test_discovery_and_generation_use_same_resolved_address(client, monkeypatch, provider, address, expected):
    monkeypatch.setenv("SYNAPSE_CONTAINER", "1")
    discovered, generated = [], []
    async def models(name, base, key):
        discovered.append(base)
        return ["local-chat"], False
    async def stream(options, messages):
        generated.append(options)
        yield "Local server works."
    monkeypatch.setattr(catalog, "fetch_catalog", models)
    monkeypatch.setattr(llm, "stream_completion", stream)
    client.patch("/api/settings", json={"providers": {provider: {"api_base": address}}}).raise_for_status()
    assert client.get(f"/api/providers/{provider}/models").json()["models"] == ["local-chat"]
    cid = client.post("/api/conversations", json={}).json()["id"]
    client.post(f"/api/conversations/{cid}/messages", json={"id": str(uuid.uuid4()), "content": "Hello"}).raise_for_status()
    response = client.post(f"/api/conversations/{cid}/generate", json={"id": str(uuid.uuid4()), "provider": provider, "model": "local-chat"})
    assert "event: done" in response.text
    assert discovered == [expected]
    assert generated[0]["api_base"] == expected
    saved = next(p for p in client.get("/api/providers").json() if p["id"] == provider)
    assert saved["api_base"] == address


def test_ollama_embedding_models_are_not_chat_choices(monkeypatch):
    original = httpx.AsyncClient
    def handler(request):
        return httpx.Response(200, json={"models": [
            {"name": "nomic-embed-text:latest"},
            {"name": "private-vector-model", "capabilities": ["embedding"]},
            {"name": "qwen3:1.7b", "capabilities": ["completion", "thinking"]},
            {"name": "chat-with-embed-support", "capabilities": ["completion", "embedding"]},
        ]})
    monkeypatch.setattr(catalog.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    assert asyncio.run(catalog.fetch_catalog("ollama", "http://models.test", "")) == (["chat-with-embed-support", "qwen3:1.7b"], False)


def test_local_connection_failure_has_actionable_error(client, monkeypatch):
    client.patch("/api/settings", json={"providers": {"ollama": {"api_base": "http://localhost:11434", "models": ["saved-model"]}}}).raise_for_status()
    async def unavailable(*args):
        raise httpx.ConnectError("secret-in-transport-error")
    monkeypatch.setattr(catalog, "fetch_catalog", unavailable)
    response = client.get("/api/providers/ollama/models?refresh=true")
    assert response.json()["models"] == ["saved-model"]
    assert "Docker" in response.json()["warning"]
    assert "secret-in-transport-error" not in response.text
