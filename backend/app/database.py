import os
import time
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


engine = create_engine(
    os.getenv("DATABASE_URL", "postgresql+psycopg://synapse:synapse@localhost:5432/synapse"),
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as db:
        yield db


def initialize_database() -> None:
    # Compose also checks readiness; retry here for direct and restarted deployments.
    for attempt in range(30):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            Base.metadata.create_all(engine)
            return
        except Exception:
            if attempt == 29:
                raise RuntimeError("Database unavailable after 60 seconds. Check DATABASE_URL and PostgreSQL.") from None
            time.sleep(2)
