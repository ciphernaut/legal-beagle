import os

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from alembic import command
from src.db import Base, SessionLocal, configure_sessions

TEST_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://legal:legal@localhost:5432/legal_test"
)


@pytest.fixture(scope="session")
def engine():
    os.environ["ALEMBIC_DATABASE_URL"] = TEST_URL
    cfg = Config("alembic.ini")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    eng = create_engine(TEST_URL)
    configure_sessions(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db_session(engine) -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        with engine.begin() as conn:
            tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
            if tables:
                conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def client(engine, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TEST_URL)
    monkeypatch.setenv("EMBEDDER", "fake")
    monkeypatch.setenv(
        "LLM",
        "fake:## Precedent\n[1992] HCA 23 applied s 109 of the Constitution. See [1950] HCA 99.",
    )
    from src.config import get_settings

    get_settings.cache_clear()
    from src.api.deps import get_embedder

    get_embedder.cache_clear()
    from src.main import create_app

    return TestClient(create_app())
