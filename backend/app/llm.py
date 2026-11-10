import os
from collections.abc import AsyncIterator

import anyio

# Disable SDK telemetry and remote model-cost fetching before import.
os.environ.setdefault("LITELLM_TELEMETRY", "False")
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

import litellm
from sqlalchemy.orm import Session

from .config import PROVIDERS, preferences, provider_config, resolve_api_base

litellm.telemetry = False
litellm.suppress_debug_info = True


def completion_options(db: Session, provider: str, model: str) -> dict:
    _, env, prefix, local = PROVIDERS[provider]
    config = provider_config(db, provider)
    key = os.getenv(f"{env}_API_KEY")
    if local and not config.api_base:
        raise ValueError("Set this local provider's endpoint in Settings before connecting.")
    if not local and not key:
        raise ValueError(f"Set {env}_API_KEY in .env and recreate the backend container.")
    options = {
        "model": f"{prefix}/{model}", "api_key": key or "local",
        "timeout": 90, "num_retries": 0,
        "max_tokens": preferences(db).max_output_tokens, "drop_params": True,
    }
    if config.api_base:
        options["api_base"] = resolve_api_base(provider, config.api_base)
    if provider == "ollama":
        # -1 lets Ollama place as many layers on available GPUs as will fit.
        # With no usable GPU, Ollama's scheduler uses the CPU automatically.
        options["num_gpu"] = -1
    return options


def gpu_failure(error: Exception) -> bool:
    if getattr(error, "status_code", None) in (401, 403, 404, 429):
        return False
    # Inspect locally; never forward/log SDK error text, which may contain secrets.
    detail = str(error).lower()
    return any(device in detail for device in ("cuda", "gpu", "vulkan", "metal", "rocm", "hipblas")) and any(
        failure in detail for failure in ("out of memory", "failed", "not available", "not supported", "device lost", "allocation")
    )


async def stream_completion(options: dict, messages: list[dict]) -> AsyncIterator[str]:
    request_options = dict(options)
    emitted = False
    for attempt in range(2):
        response = None
        completed = False
        try:
            response = await litellm.acompletion(**request_options, messages=messages, stream=True)
            async for chunk in response:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                if choice.delta.content:
                    emitted = True
                    yield choice.delta.content
                if choice.finish_reason:
                    completed = True
            if not completed:
                raise RuntimeError("Provider stream ended without a completion marker")
            return
        except Exception as error:
            if attempt == 0 and options.get("model", "").startswith("ollama_chat/") and not emitted and request_options.get("num_gpu") != 0 and gpu_failure(error):
                request_options["num_gpu"] = 0
                continue
            raise
        finally:
            close = getattr(response, "aclose", None)
            if close:
                with anyio.CancelScope(shield=True):
                    await close()


def safe_error(error: Exception) -> str:
    # Never forward SDK errors: they may contain credentials, URLs, or prompt text.
    name = type(error).__name__.lower()
    if "authentication" in name or "permission" in name:
        return "Provider rejected the credentials. Check the API key and model permissions."
    if "ratelimit" in name:
        return "Provider rate limit or quota reached. Wait a moment or choose another provider."
    if "timeout" in name:
        return "Provider timed out. Check the endpoint or try again."
    if "badrequest" in name or "notfound" in name:
        return "Provider rejected this request. Check the model ID and context/output limits."
    return "Could not complete the response. Check the provider endpoint, model ID, and connection, then retry."
