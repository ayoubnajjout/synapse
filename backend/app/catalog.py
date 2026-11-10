"""Discover provider catalogs without sending prompts or exposing credentials."""

import asyncio
import hashlib
import json
import os
import time

import httpx

from .config import PROVIDERS, resolve_api_base
from .schemas import ProviderConfig

DEFAULT_BASES = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
    "xai": "https://api.x.ai/v1",
}
# Cached in this process only. Successful catalogs remain available during outages.
_cache: dict[tuple[str, str, str], tuple[float, list[str], bool]] = {}


def chat_model(id: str) -> bool:
    # Catalogs do not consistently expose capabilities. Only exclude clearly
    # non-chat families; unknown/future IDs stay available, as do custom IDs.
    return not any(part in id.lower() for part in (
        "embed", "dall-e", "gpt-image", "whisper", "moderation", "tts-", "transcribe", "sora-", "realtime",
    ))


async def fetch_catalog(provider: str, base: str, key: str) -> tuple[list[str], bool]:
    headers = {"Accept": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    if provider == "anthropic":
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "Accept": "application/json"}
    elif provider == "gemini":
        headers = {"x-goog-api-key": key, "Accept": "application/json"}
    path = "/api/tags" if provider == "ollama" else "/language-models" if provider == "xai" else "/models"
    if provider == "anthropic" and not base.endswith("/v1"):
        base += "/v1"
    if provider == "gemini" and not base.endswith(("/v1beta", "/v1")):
        base += "/v1beta"
    models: set[str] = set()
    params: dict[str, str | int] = {}
    if provider == "anthropic":
        params["limit"] = 100
    if provider == "gemini":
        params["pageSize"] = 100
    seen_cursors: set[str] = set()
    async with asyncio.timeout(15), httpx.AsyncClient(timeout=6, follow_redirects=False, trust_env=provider not in ("ollama", "lmstudio")) as client:
        for _ in range(10):
            async with client.stream("GET", base.rstrip("/") + path, headers=headers, params=params) as response:
                if response.status_code == 404 and provider == "xai" and path == "/language-models":
                    path = "/models"
                    continue
                response.raise_for_status()
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > 2 * 1024 * 1024:
                        raise ValueError("Catalog response too large")
            data = json.loads(content)
            entries = data.get("models", data.get("data", [])) if provider in ("ollama", "gemini", "xai") else data.get("data", [])
            if not isinstance(entries, list):
                raise ValueError("Invalid catalog")
            for entry in entries:
                if not isinstance(entry, dict) or entry.get("lifecycle") == "retired":
                    continue
                if provider == "gemini" and "generateContent" not in entry.get("supportedGenerationMethods", []):
                    continue
                capabilities = (entry.get("capabilities") or []) if provider == "ollama" else []
                can_chat = "completion" in capabilities or "chat" in capabilities
                if "embedding" in capabilities and not can_chat:
                    continue
                id = entry.get("name") if provider in ("ollama", "gemini") else entry.get("id")
                if provider == "ollama":
                    id = id or entry.get("model")
                if isinstance(id, str):
                    id = id.removeprefix("models/") if provider == "gemini" else id
                    id = id.strip()
                    if id and len(id) <= 200 and (can_chat or chat_model(id)):
                        models.add(id)
                if len(models) >= 1000:
                    return sorted(models), True
            cursor = data.get("nextPageToken") if provider == "gemini" else data.get("last_id") if data.get("has_more") else None
            if not cursor:
                return sorted(models), False
            if not isinstance(cursor, str) or cursor in seen_cursors:
                raise ValueError("Invalid catalog pagination")
            seen_cursors.add(cursor)
            params["pageToken" if provider == "gemini" else "after_id" if provider == "anthropic" else "after"] = cursor
    return sorted(models), True


async def discover_models(provider: str, config: ProviderConfig, refresh=False) -> dict:
    _, env, _, local = PROVIDERS[provider]
    key = os.getenv(f"{env}_API_KEY", "")
    base = resolve_api_base(provider, config.api_base) or DEFAULT_BASES.get(provider, "")
    identity = (provider, base, hashlib.sha256(key.encode()).hexdigest())
    cached = _cache.get(identity)
    warning = None
    live: list[str] = []
    truncated = False
    source = "saved"
    if not base or (not local and not key):
        warning = "Connect this provider to load its available models."
    elif cached and not refresh and time.monotonic() - cached[0] < 60:
        _, live, truncated = cached
        source = "cached"
    else:
        try:
            live, truncated = await fetch_catalog(provider, base, key)
            if len(_cache) >= 64:
                _cache.pop(next(iter(_cache)))
            _cache[identity] = (time.monotonic(), live, truncated)
            source = "live"
            if not live:
                warning = "Connected, but no installed chat models were found. Download a chat model in your local model server, then refresh." if local else "No chat models found. Check your provider access."
        except Exception as error:
            # Provider responses and exceptions can contain secrets. Never relay them.
            warning = "Could not load models. Check your connection and credentials, then refresh. Your saved models are still available."
            if local:
                if isinstance(error, httpx.HTTPStatusError) and error.response.status_code in (401, 403):
                    warning = "The local server rejected access. Check its authentication settings and the server API key configured in Synapse."
                elif isinstance(error, httpx.HTTPStatusError) and error.response.status_code == 404:
                    warning = "The server has no model-list endpoint at this address. Check the selected provider and server address."
                else:
                    warning = "Cannot reach the local model server from Synapse. Make sure it is running and accepts connections from Docker. Your saved model choices are still available."
            if cached:
                _, live, truncated = cached
                source = "cached"
    models = sorted(set(live + config.models + ([config.default_model] if config.default_model else [])))
    return {"models": models, "default_model": config.default_model, "source": source if models or source == "live" else "unavailable", "warning": warning, "truncated": truncated}
