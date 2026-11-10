import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import catalog, main
from app.database import Base, get_db
from app.routes import conversations


@pytest.fixture
def session_factory():
    url = os.getenv("TEST_DATABASE_URL")
    if url:
        # Isolate every test in its own schema. Never drop user tables.
        schema = f"synapse_test_{uuid.uuid4().hex}"
        admin = create_engine(url)
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    else:
        engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def foreign_keys(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()
    if url:
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def client(session_factory, monkeypatch):
    monkeypatch.delenv("SYNAPSE_CONTAINER", raising=False)
    async def empty_catalog(*args, **kwargs):
        return [], False
    monkeypatch.setattr(catalog, "fetch_catalog", empty_catalog)
    monkeypatch.setattr(catalog, "_cache", {})
    monkeypatch.setattr(main, "initialize_database", lambda: None)
    monkeypatch.setattr(main, "engine", session_factory.kw["bind"])
    monkeypatch.setattr(conversations, "SessionLocal", session_factory)

    def override_db():
        with session_factory() as db:
            yield db

    main.app.dependency_overrides[get_db] = override_db
    for name in ("OPENAI", "ANTHROPIC", "GEMINI", "XAI", "OLLAMA", "LMSTUDIO"):
        for suffix in ("API_KEY", "API_BASE", "MODELS"):
            monkeypatch.delenv(f"{name}_{suffix}", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret-never-return")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-secret-never-return")
    with TestClient(main.app) as test_client:
        yield test_client
    main.app.dependency_overrides.clear()
