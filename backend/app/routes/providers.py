import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import llm
from ..catalog import discover_models
from ..config import PROVIDERS, provider_config, provider_views
from ..database import get_db
from ..schemas import StrictModel
from pydantic import Field

router = APIRouter(prefix="/api/providers", tags=["providers"])


class TestRequest(StrictModel):
    model: str = Field(min_length=1, max_length=200)


@router.get("")
def list_providers(db: Session = Depends(get_db)):
    return provider_views(db)


@router.get("/{provider}/models")
async def list_models(provider: str, refresh: bool = False, db: Session = Depends(get_db)):
    if provider not in PROVIDERS:
        raise HTTPException(404, "Provider not found")
    config = provider_config(db, provider)
    return await discover_models(provider, config, refresh=refresh)


@router.post("/{provider}/test")
async def test_provider(provider: str, body: TestRequest, db: Session = Depends(get_db)):
    if provider not in PROVIDERS:
        raise HTTPException(404, "Provider not found")
    try:
        options = llm.completion_options(db, provider, body.model)
    except ValueError as error:
        raise HTTPException(400, str(error)) from None
    # A real, small completion also checks model access. It may incur provider cost.
    options["max_tokens"] = 16
    try:
        async with asyncio.timeout(30):
            async for _ in llm.stream_completion(options, [{"role": "user", "content": "Reply with OK."}]):
                pass
        return {"ok": True, "message": "Connected. Model responded successfully."}
    except Exception as error:
        return {"ok": False, "message": llm.safe_error(error)}
