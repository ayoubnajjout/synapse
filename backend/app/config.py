import os
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from .models import Setting
from .schemas import Preferences, ProviderConfig

# Models are editable, never a hard-coded allowlist. Keys stay in the process environment.
PROVIDERS = {
    "openai": ("OpenAI", "OPENAI", "openai", False),
    "anthropic": ("Anthropic", "ANTHROPIC", "anthropic", False),
    "gemini": ("Google Gemini", "GEMINI", "gemini", False),
    "xai": ("xAI", "XAI", "xai", False),
    "ollama": ("Ollama", "OLLAMA", "ollama_chat", True),
    "lmstudio": ("LM Studio", "LMSTUDIO", "openai", True),
}


def resolve_api_base(provider: str, base: str | None) -> str | None:
    """Use the same local server address for discovery and model requests."""
    if not base or provider not in ("ollama", "lmstudio"):
        return base
    url = urlsplit(base.rstrip("/"))
    path = url.path
    if provider == "ollama":
        # Accept copied native/OpenAI endpoint URLs as well as the server root.
        for suffix in ("/v1/chat/completions", "/api/generate", "/api/chat", "/api/tags", "/v1/models", "/api", "/v1"):
            if path.endswith(suffix):
                path = path[:-len(suffix)]
                break
    else:
        for suffix in ("/chat/completions", "/models"):
            if path.endswith(suffix):
                path = path[:-len(suffix)]
                break
        path = path or "/v1"
    host = url.netloc
    if os.getenv("SYNAPSE_CONTAINER") == "1" and url.hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        host = "host.docker.internal" + (f":{url.port}" if url.port else "")
    return url._replace(netloc=host, path=path).geturl().rstrip("/")


def preferences(db: Session) -> Preferences:
    stored = db.get(Setting, "preferences")
    return Preferences.model_validate(stored.value if stored else {})


def provider_config(db: Session, name: str) -> ProviderConfig:
    _, env, _, _ = PROVIDERS[name]
    saved = db.get(Setting, f"provider:{name}")
    if saved:
        return ProviderConfig.model_validate(saved.value)
    models = [m.strip() for m in os.getenv(f"{env}_MODELS", "").split(",") if m.strip()]
    return ProviderConfig(api_base=os.getenv(f"{env}_API_BASE") or None, models=models, default_model=models[0] if models else None)


def provider_views(db: Session) -> list[dict]:
    result = []
    for name, (label, env, _, local) in PROVIDERS.items():
        config = provider_config(db, name)
        key_set = bool(os.getenv(f"{env}_API_KEY"))
        result.append({
            "id": name, "name": label, "local": local,
            "configured": bool(config.api_base) if local else key_set,
            "key_configured": key_set, "saved_models": config.models, **config.model_dump(),
        })
    return result


def save_setting(db: Session, key: str, value: dict) -> None:
    row = db.get(Setting, key)
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))
