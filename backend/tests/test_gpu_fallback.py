import asyncio
from types import SimpleNamespace

import pytest

from app import llm


class Stream:
    def __init__(self, error=None, partial=False):
        self.error = error
        self.partial = partial
        self.closed = False

    async def aclose(self):
        self.closed = True

    def __aiter__(self):
        return self.chunks()

    async def chunks(self):
        if not self.error or self.partial:
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="Hello"), finish_reason=None)])
        if self.error:
            raise self.error
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None), finish_reason="stop")])


def collect(options):
    async def run():
        return [chunk async for chunk in llm.stream_completion(options, [{"role": "user", "content": "Hello"}])]
    return asyncio.run(run())


def test_ollama_requests_automatic_gpu_by_default(client, session_factory):
    client.patch("/api/settings", json={"providers": {"ollama": {"api_base": "http://localhost:11434"}}}).raise_for_status()
    with session_factory() as db:
        assert llm.completion_options(db, "ollama", "local-model")["num_gpu"] == -1


@pytest.mark.parametrize("during_stream", [False, True])
def test_gpu_initialization_failure_retries_cpu_once(monkeypatch, during_stream):
    calls, streams = [], []
    async def completion(**options):
        calls.append(options)
        if len(calls) == 1:
            error = RuntimeError("CUDA allocation failed: out of memory")
            if not during_stream:
                raise error
            stream = Stream(error)
        else:
            stream = Stream()
        streams.append(stream)
        return stream
    monkeypatch.setattr(llm.litellm, "acompletion", completion)
    original = {"model": "ollama_chat/local-model", "num_gpu": -1}
    assert collect(original) == ["Hello"]
    assert [c["num_gpu"] for c in calls] == [-1, 0]
    assert original["num_gpu"] == -1
    assert all(s.closed for s in streams)


def test_gpu_failure_after_visible_output_does_not_retry(monkeypatch):
    calls = []
    stream = Stream(RuntimeError("GPU device lost"), partial=True)
    async def completion(**options):
        calls.append(options)
        return stream
    monkeypatch.setattr(llm.litellm, "acompletion", completion)
    with pytest.raises(RuntimeError, match="GPU device lost"):
        collect({"model": "ollama_chat/local-model", "num_gpu": -1})
    assert len(calls) == 1
    assert stream.closed


@pytest.mark.parametrize("model", ["openai/cloud-model", "openai/lmstudio-model"])
def test_other_providers_do_not_receive_ollama_gpu_parameters(monkeypatch, model):
    calls = []
    async def completion(**options):
        calls.append(options)
        raise RuntimeError("GPU allocation failed")
    monkeypatch.setattr(llm.litellm, "acompletion", completion)
    with pytest.raises(RuntimeError):
        collect({"model": model})
    assert len(calls) == 1
    assert "num_gpu" not in calls[0]


def test_auth_and_network_errors_do_not_trigger_cpu_retry(monkeypatch):
    calls = []
    async def completion(**options):
        calls.append(options)
        raise ConnectionError("Server unreachable")
    monkeypatch.setattr(llm.litellm, "acompletion", completion)
    with pytest.raises(ConnectionError):
        collect({"model": "ollama_chat/model", "num_gpu": -1})
    assert len(calls) == 1
    denied = RuntimeError("GPU allocation failed")
    denied.status_code = 403
    assert not llm.gpu_failure(denied)
