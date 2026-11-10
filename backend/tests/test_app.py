import asyncio
import json
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app import llm
from app.memory import build_context
from app.models import Message
from app.routes.conversations import generate
from app.schemas import Generate


def conversation(client):
    response = client.post("/api/conversations", json={})
    assert response.status_code == 201
    return response.json()["id"]


def user_message(client, cid, content="Hello", mid=None):
    response = client.post(f"/api/conversations/{cid}/messages", json={"id": mid or str(uuid.uuid4()), "content": content})
    assert response.status_code == 201
    return response.json()


def generation(client, cid, provider="openai", model="test-model", **kwargs):
    return client.post(f"/api/conversations/{cid}/generate", json={"id": str(uuid.uuid4()), "provider": provider, "model": model, **kwargs})


def events(response):
    result = []
    for frame in response.text.strip().split("\n\n"):
        lines = frame.splitlines()
        result.append((lines[0].removeprefix("event: "), json.loads(lines[1].removeprefix("data: "))))
    return result


def mock_llm(monkeypatch, calls=None, content="A helpful answer."):
    async def stream(options, messages):
        if calls is not None:
            calls.append((options, messages))
        for part in (content[:5], content[5:]):
            yield part
    monkeypatch.setattr(llm, "stream_completion", stream)


def test_health_and_crud(client):
    assert client.get("/api/health").json()["database"] == "connected"
    cid = conversation(client)
    assert client.get(f"/api/conversations/{cid}").json()["title"] == "New conversation"
    assert client.patch(f"/api/conversations/{cid}", json={"title": "My project"}).status_code == 200
    user_message(client, cid)
    assert len(client.get(f"/api/conversations/{cid}/messages").json()) == 1
    assert client.get("/api/conversations").json()[0]["title"] == "My project"
    assert client.delete(f"/api/conversations/{cid}").status_code == 204
    assert client.get(f"/api/conversations/{cid}").status_code == 404


def test_message_retries_are_idempotent(client):
    cid = conversation(client)
    mid = str(uuid.uuid4())
    assert user_message(client, cid, mid=mid)["id"] == user_message(client, cid, mid=mid)["id"]
    assert len(client.get(f"/api/conversations/{cid}/messages").json()) == 1
    assert client.post(f"/api/conversations/{cid}/messages", json={"id": mid, "content": "different"}).status_code == 409


def test_streaming_cross_provider_context_and_retry(client, monkeypatch):
    calls = []
    mock_llm(monkeypatch, calls)
    cid = conversation(client)
    user_message(client, cid, "I am building a Python app.")
    mid = str(uuid.uuid4())
    response = generation(client, cid, id=mid)
    assert [e[0] for e in events(response)] == ["context", "delta", "delta", "done"]
    assert generation(client, cid, id=mid).text.count("event: done") == 1
    assert len(calls) == 1
    user_message(client, cid, "Expand the database layer.")
    response = generation(client, cid, provider="anthropic", model="another-model")
    assert events(response)[-1][0] == "done"
    assert calls[1][0]["model"] == "anthropic/another-model"
    assert [m["role"] for m in calls[1][1]] == ["system", "user", "assistant", "user"]
    assert calls[1][1][1]["content"] == "I am building a Python app."
    stored = client.get(f"/api/conversations/{cid}/messages").json()
    assert len(stored) == 4 and stored[-1]["provider"] == "anthropic"
    assert [m["sequence"] for m in stored] == [1, 2, 3, 4]


def test_memories_crud_and_injection(client, monkeypatch):
    calls = []
    mock_llm(monkeypatch, calls)
    memory = client.post("/api/memories", json={"content": "I prefer PostgreSQL."}).json()
    cid = conversation(client)
    user_message(client, cid)
    generation(client, cid)
    assert "I prefer PostgreSQL." in calls[-1][1][0]["content"]
    assert client.patch(f"/api/memories/{memory['id']}", json={"content": "I prefer concise answers.", "enabled": False}).status_code == 200
    generation(client, cid, regenerate=True)
    assert "concise answers" not in calls[-1][1][0]["content"]
    client.patch(f"/api/memories/{memory['id']}", json={"enabled": True})
    prefs = client.get("/api/settings").json()["preferences"]
    client.patch("/api/settings", json={"preferences": {**prefs, "memory_enabled": False}})
    generation(client, cid, regenerate=True)
    assert "concise answers" not in calls[-1][1][0]["content"]
    assert client.delete(f"/api/memories/{memory['id']}").status_code == 204
    client.post("/api/memories", json={"content": "Another memory"})
    assert client.delete("/api/memories").status_code == 204
    assert client.get("/api/memories").json() == []


def test_regeneration_replaces_only_after_success(client, monkeypatch):
    mock_llm(monkeypatch, content="Original response.")
    cid = conversation(client)
    user_message(client, cid)
    generation(client, cid)
    mock_llm(monkeypatch, content="Replacement response.")
    generation(client, cid, regenerate=True)
    stored = client.get(f"/api/conversations/{cid}/messages").json()
    assert len(stored) == 2 and stored[-1]["content"] == "Replacement response."

    async def broken(options, messages):
        yield "partial"
        raise RuntimeError("secret provider error")
    monkeypatch.setattr(llm, "stream_completion", broken)
    response = generation(client, cid, regenerate=True)
    assert events(response)[-1][0] == "error"
    assert "secret provider error" not in response.text
    assert client.get(f"/api/conversations/{cid}/messages").json() == stored


def test_failed_generation_does_not_persist_partial(client, monkeypatch):
    async def broken(options, messages):
        yield "incomplete"
        raise ConnectionError("API key: do-not-expose")
    monkeypatch.setattr(llm, "stream_completion", broken)
    cid = conversation(client)
    user_message(client, cid)
    response = generation(client, cid)
    assert events(response)[-1][0] == "error"
    assert "do-not-expose" not in response.text
    assert len(client.get(f"/api/conversations/{cid}/messages").json()) == 1


def test_cancellation_rolls_back_and_closes_stream(client, session_factory, monkeypatch):
    cid = conversation(client)
    user_message(client, cid)
    closed = []

    async def cancelled(options, messages):
        try:
            yield "partial"
            raise asyncio.CancelledError()
        finally:
            closed.append(True)

    monkeypatch.setattr(llm, "stream_completion", cancelled)

    async def exercise():
        request = SimpleNamespace(is_disconnected=lambda: asyncio.sleep(0, result=False))
        with session_factory() as db:
            response = generate(uuid.UUID(cid), Generate(id=uuid.uuid4(), provider="openai", model="test-model"), request, db)
        with pytest.raises(asyncio.CancelledError):
            async for _ in response.body_iterator:
                pass

    asyncio.run(exercise())
    assert closed
    with session_factory() as db:
        assert len(list(db.scalars(select(Message)))) == 1


def test_disconnection_closes_provider_without_persisting(client, session_factory, monkeypatch):
    cid = conversation(client)
    user_message(client, cid)
    closed = []

    async def provider(options, messages):
        try:
            yield "partial"
            yield "more"
        finally:
            closed.append(True)
    monkeypatch.setattr(llm, "stream_completion", provider)

    async def exercise():
        request = SimpleNamespace(is_disconnected=lambda: asyncio.sleep(0, result=True))
        with session_factory() as db:
            response = generate(uuid.UUID(cid), Generate(id=uuid.uuid4(), provider="openai", model="test-model"), request, db)
        async for _ in response.body_iterator:
            pass
    asyncio.run(exercise())
    assert closed
    assert len(client.get(f"/api/conversations/{cid}/messages").json()) == 1


def test_context_limits_are_visible(client, monkeypatch):
    mock_llm(monkeypatch)
    cid = conversation(client)
    user_message(client, cid, "First question")
    generation(client, cid)
    user_message(client, cid, "Second question")
    prefs = client.get("/api/settings").json()["preferences"]
    client.patch("/api/settings", json={"preferences": {**prefs, "max_messages": 2}})
    response = generation(client, cid)
    context = events(response)[0][1]
    assert context["included_messages"] == 1
    assert context["excluded_messages"] == 2


def test_oversized_latest_message_is_rejected(client, monkeypatch):
    mock_llm(monkeypatch)
    cid = conversation(client)
    user_message(client, cid, "x" * 3000)
    prefs = client.get("/api/settings").json()["preferences"]
    client.patch("/api/settings", json={"preferences": {**prefs, "context_chars": 2000}})
    assert events(generation(client, cid))[-1][0] == "error"
    assert len(client.get(f"/api/conversations/{cid}/messages").json()) == 1


def test_export_import_validates_and_uses_new_ids(client, monkeypatch):
    mock_llm(monkeypatch)
    cid = conversation(client)
    user_message(client, cid)
    generation(client, cid)
    exported = client.get(f"/api/conversations/{cid}/export").json()
    imported = client.post("/api/conversations/import", json=exported)
    assert imported.status_code == 201
    new_id = imported.json()[0]["id"]
    assert new_id != cid
    old = client.get(f"/api/conversations/{cid}/messages").json()
    new = client.get(f"/api/conversations/{new_id}/messages").json()
    assert len(new) == 2 and old[0]["id"] != new[0]["id"]
    assert new[-1]["provider"] == old[-1]["provider"]
    exported["conversations"][0]["messages"][0]["role"] = "system"
    assert client.post("/api/conversations/import", json=exported).status_code == 422
    assert len(client.get("/api/conversations/export").json()["conversations"]) == 2


def test_providers_settings_and_secrets(client, monkeypatch):
    providers = client.get("/api/providers")
    assert len(providers.json()) == 6
    assert "test-secret-never-return" not in providers.text
    assert "test-secret-never-return" not in client.get("/api/settings").text
    config = {"api_base": "http://localhost:11434", "models": ["custom:model"], "default_model": "custom:model"}
    assert client.patch("/api/settings", json={"providers": {"ollama": config}}).status_code == 200
    assert client.get("/api/providers/ollama/models").json()["models"] == ["custom:model"]
    calls = []
    mock_llm(monkeypatch, calls)
    assert client.post("/api/providers/ollama/test", json={"model": "custom:model"}).json()["ok"]
    assert calls[0][0]["model"] == "ollama_chat/custom:model"
    config["api_base"] = "http://user:secret@localhost:11434"
    assert client.patch("/api/settings", json={"providers": {"ollama": config}}).status_code == 422
    rejected = client.patch("/api/settings", json={"providers": {"openai": {"api_key": "secret-input-key"}}})
    assert rejected.status_code == 422
    assert "secret-input-key" not in rejected.text


def test_local_unavailable_and_missing_key(client, monkeypatch):
    cid = conversation(client)
    user_message(client, cid)
    assert generation(client, cid, provider="ollama").status_code == 400
    monkeypatch.delenv("OPENAI_API_KEY")
    assert generation(client, cid).status_code == 400
    assert generation(client, cid, provider="unknown").status_code == 422


def test_preferences_patch_preserves_other_limits(client):
    assert client.patch("/api/settings", json={"preferences": {"max_messages": 7, "context_chars": 8000}}).status_code == 200
    changed = client.patch("/api/settings", json={"preferences": {"memory_enabled": False}}).json()["preferences"]
    assert changed["memory_enabled"] is False
    assert changed["max_messages"] == 7
    assert changed["context_chars"] == 8000


def test_cross_origin_and_validation(client):
    assert client.post("/api/conversations", json={}, headers={"Origin": "https://other.example"}).status_code == 403
    assert client.post("/api/conversations", json={"title": " "}).status_code == 422
    assert client.post("/api/memories", json={"content": " "}).status_code == 422
    assert client.get("/api/does-not-exist").status_code == 404


def test_postgres_row_lock_blocks_concurrent_writes(client, session_factory):
    if session_factory.kw["bind"].dialect.name != "postgresql":
        pytest.skip("PostgreSQL required for row-lock verification")
    from app.routes.conversations import get_conversation
    cid = conversation(client)
    with session_factory() as db:
        get_conversation(db, uuid.UUID(cid), lock=True)
        assert client.patch(f"/api/conversations/{cid}", json={"title": "Concurrent edit"}).status_code == 409
    assert client.patch(f"/api/conversations/{cid}", json={"title": "After unlock"}).status_code == 200


def test_sdk_stream_requires_finish_marker_and_closes(monkeypatch):
    class FakeStream:
        closed = False
        def __aiter__(self):
            return self
        async def __anext__(self):
            if getattr(self, "sent", False):
                raise StopAsyncIteration
            self.sent = True
            return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="partial"), finish_reason=None)])
        async def aclose(self):
            self.closed = True
    fake = FakeStream()
    async def completion(**kwargs):
        return fake
    monkeypatch.setattr(llm.litellm, "acompletion", completion)
    async def exercise():
        with pytest.raises(RuntimeError, match="completion marker"):
            async for _ in llm.stream_completion({}, []):
                pass
    asyncio.run(exercise())
    assert fake.closed
