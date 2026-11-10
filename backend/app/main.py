from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .database import engine, initialize_database
from .routes import conversations, memories, providers, settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield
    engine.dispose()


app = FastAPI(title="Synapse", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url="/api/openapi.json")
for router in (conversations.router, memories.router, providers.router, settings.router):
    app.include_router(router)


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, error: RequestValidationError):
    # Pydantic's default response echoes input values, which could include a key
    # accidentally submitted to an unsupported field.
    return JSONResponse({"detail": [
        {"loc": issue["loc"], "msg": issue["msg"], "type": issue["type"]}
        for issue in error.errors()
    ]}, status_code=422)


@app.middleware("http")
async def validate_requests(request: Request, call_next):
    # Mutating browser requests must originate from this installation (no CORS).
    # This also blocks cross-origin forms and DNS-rebinding Origin mismatches.
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        expected = str(request.base_url).rstrip("/")
        if origin and origin != expected:
            return JSONResponse({"detail": "Cross-origin requests are not allowed"}, status_code=403)
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "Cross-site requests are not allowed"}, status_code=403)
        # Bound actual bytes, including chunked import requests, before JSON parsing.
        chunks = []
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > 10 * 1024 * 1024:
                return JSONResponse({"detail": "Request exceeds the 10 MiB limit"}, status_code=413)
            chunks.append(chunk)
        # Cache for Starlette's downstream request replay after consuming the stream.
        request._body = b"".join(chunks)
    return await call_next(request)


@app.get("/api/health")
def health():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception:
        return JSONResponse({"status": "unhealthy", "database": "unavailable"}, status_code=503)


