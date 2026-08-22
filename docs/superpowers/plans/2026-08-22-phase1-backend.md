# Phase 1 Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A FastAPI backend that ingests Commonwealth Acts and High Court judgments into Postgres, retrieves relevant provisions/paragraphs, runs the Reverse Engineering reasoning mode over a local LLM, and verifies every citation in the output against the corpus.

**Architecture:** Single Postgres 16 + pgvector database holding documents, a generic `edges` table for the authority graph, tsvector full-text and vector embeddings. Batch ingestion from the Open Australian Legal Corpus (OALC) populates it offline. Request path is: retrieval → graph expansion → LLM (LiteLLM, streamed) → citation verifier → SSE to client. Sync SQLAlchemy for DB (FastAPI runs it in a threadpool); async only for the LLM.

**Tech Stack:** Python 3.12, uv, FastAPI, SQLAlchemy 2.x, Alembic, psycopg 3, pgvector, sentence-transformers (`BAAI/bge-small-en-v1.5`, 384 dims), LiteLLM, httpx, sse-starlette, pytest, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-08-22-legal-introspection-tool-design.md` — this plan implements §10 Phase 1, backend half. The frontend (tree view, disclaimer, reasoning panel) is a separate plan.

**Deviation from spec:** Phase 1 ingests from OALC only (it contains both FRL Acts and HCA judgments with licence metadata). A live `frl_odata.py` sync is deferred to Phase 2. `hca.py` is likewise deferred — OALC's `high_court_of_australia` source covers it.

## Global Constraints

- Python `>=3.12`; package manager is `uv`; all commands run as `uv run ...` from `backend/`.
- Database is PostgreSQL 16 with the `pgvector` extension. Image: `pgvector/pgvector:pg16`.
- Embedding dimension is **384** everywhere (`BAAI/bge-small-en-v1.5`).
- LLM endpoint: `LLM_MODEL=qwen3.8-27b-fp8`, `LLM_API_BASE=http://localhost:7080/v1`, accessed via LiteLLM with the `openai/` prefix and `acompletion`.
- Every node and edge row carries `source_url`, `source_licence`, `extraction` (one of `curated | parsed | llm_extracted`).
- Node type strings used in `edges` and the API are exactly: `jurisdiction`, `court`, `act`, `provision`, `case`, `principle`.
- Edge kinds are exactly: `IN_JURISDICTION`, `DECIDED_BY`, `APPEALS_TO`, `AUTHORISED_BY`, `AMENDS`, `INTERPRETS`, `CITES`, `HELD_INCONSISTENT`, `ESTABLISHES`, `APPLIES`, `EVOLVED_INTO`, `CODIFIES`.
- Tests run against a real Postgres at `TEST_DATABASE_URL` (default `postgresql+psycopg://legal:legal@localhost:5432/legal_test`). No mocking of the database.
- Commit after every task with a conventional-commit message and the trailer `Claude-Session: https://claude.ai/code/session_01Cvr8NCUwUhq3rZT4BjdgGm`.
- No AustLII or Jade.io access, ever.

---

## File Structure

```
backend/
├── pyproject.toml
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── versions/
│       ├── 0001_initial.py
│       └── 0002_search.py
├── src/
│   ├── __init__.py
│   ├── main.py                      # FastAPI app factory
│   ├── config.py                    # Settings (pydantic-settings)
│   ├── db.py                        # engine + session factory
│   ├── graph/
│   │   ├── __init__.py
│   │   ├── models.py                # SQLAlchemy ORM, all tables
│   │   ├── seed.py                  # jurisdictions + courts reference data
│   │   ├── curated.py               # curated AUTHORISED_BY edges from YAML
│   │   ├── curated_edges.yaml
│   │   └── traversal.py             # neighbour + authority-chain queries
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── parsers/
│   │   │   ├── __init__.py
│   │   │   ├── citation_parser.py   # pure: regex → Citation dataclasses
│   │   │   ├── act_parser.py        # pure: Act text → section tree
│   │   │   └── judgment_parser.py   # pure: judgment text → paragraphs
│   │   ├── sources/
│   │   │   ├── __init__.py
│   │   │   └── oalc.py              # OALC jsonl → DB upserts
│   │   ├── link.py                  # CITES / INTERPRETS edges from citations
│   │   ├── embed.py                 # Embedder protocol + sentence-transformers impl
│   │   └── run.py                   # CLI: python -m src.ingestion.run
│   ├── retrieval/
│   │   ├── __init__.py
│   │   └── hybrid.py                # FTS + vector + RRF + 1-hop expansion
│   ├── reasoning/
│   │   ├── __init__.py
│   │   ├── llm/
│   │   │   ├── __init__.py
│   │   │   └── client.py            # LLMClient protocol + LiteLLM impl + Fake
│   │   ├── frameworks/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   └── common_law.py
│   │   ├── modes/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   └── reverse_engineering.py
│   │   └── verifier.py              # citation verification
│   └── api/
│       ├── __init__.py
│       ├── deps.py
│       ├── nodes.py                 # GET /nodes/{type}/{id}
│       ├── tree.py                  # GET /tree
│       └── reason.py                # POST /reason/reverse (SSE)
└── tests/
    ├── conftest.py
    ├── fixtures/
    │   ├── act_sample.txt
    │   ├── judgment_sample.txt
    │   └── oalc_sample.jsonl
    ├── test_smoke.py
    ├── graph/   (test_models, test_seed, test_curated, test_traversal)
    ├── ingestion/ (test_citation_parser, test_act_parser, test_judgment_parser, test_oalc, test_link, test_embed)
    ├── retrieval/ (test_hybrid)
    ├── reasoning/ (test_verifier, test_common_law, test_reverse_engineering)
    └── api/       (test_nodes, test_tree, test_reason)
eval/
├── __init__.py
├── __main__.py
├── score.py
└── gold/hca.yaml
.github/workflows/ci.yml
docker-compose.yml
.env.example
docs/runbooks/ingest.md
```

---

### Task 1: Backend scaffold, Postgres, test harness

**Files:**
- Create: `docker-compose.yml`, `.env.example`, `.gitignore`, `backend/pyproject.toml`, `backend/src/__init__.py`, `backend/src/config.py`, `backend/src/db.py`, `backend/src/main.py`, `backend/alembic.ini`, `backend/alembic/env.py`, `backend/src/graph/__init__.py`, `backend/src/graph/models.py` (placeholder), `backend/tests/conftest.py`, `backend/tests/test_smoke.py`

**Interfaces:**
- Produces: `src.config.Settings` with fields `database_url`, `llm_model`, `llm_api_base`, `embed_model` (all `str`); `src.config.get_settings() -> Settings` (lru_cached)
- Produces: `src.db.Base` (DeclarativeBase), `src.db.get_engine() -> Engine`, `src.db.SessionLocal` (sessionmaker), `src.db.configure_sessions(engine)`
- Produces: `src.main.create_app() -> FastAPI`; `GET /health` → `{"status":"ok"}`
- Produces: pytest fixtures `engine` (session-scoped, migrates to head), `db_session` (Session; all tables truncated after each test), `client` (FastAPI `TestClient`)

- [ ] **Step 1: Write docker-compose.yml, .env.example, .gitignore**

`docker-compose.yml`:
```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: legal
      POSTGRES_PASSWORD: legal
      POSTGRES_DB: legal
    ports: ["5432:5432"]
    volumes: [pgdata:/var/lib/postgresql/data]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U legal"]
      interval: 5s
      retries: 10
volumes:
  pgdata:
```

`.env.example`:
```env
DATABASE_URL=postgresql+psycopg://legal:legal@localhost:5432/legal
TEST_DATABASE_URL=postgresql+psycopg://legal:legal@localhost:5432/legal_test
LLM_MODEL=qwen3.8-27b-fp8
LLM_API_BASE=http://localhost:7080/v1
EMBED_MODEL=BAAI/bge-small-en-v1.5
```

`.gitignore`:
```
.env
.venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
backend/data/
```

- [ ] **Step 2: Start Postgres and create the test database**

Run from repo root:
```bash
docker compose up -d postgres
until docker compose exec postgres pg_isready -U legal; do sleep 1; done
docker compose exec postgres psql -U legal -c "CREATE DATABASE legal_test;"
docker compose exec postgres psql -U legal -d legal -c "CREATE EXTENSION IF NOT EXISTS vector;"
docker compose exec postgres psql -U legal -d legal_test -c "CREATE EXTENSION IF NOT EXISTS vector;"
```
Expected: `CREATE DATABASE`, then `CREATE EXTENSION` twice.

- [ ] **Step 3: Write pyproject.toml**

`backend/pyproject.toml`:
```toml
[project]
name = "legal-beagle-backend"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "sqlalchemy>=2.0",
    "alembic>=1.13",
    "psycopg[binary]>=3.2",
    "pgvector>=0.3",
    "pydantic-settings>=2.4",
    "litellm>=1.50",
    "httpx>=0.27",
    "sse-starlette>=2.1",
    "pyyaml>=6.0",
    "sentence-transformers>=3.0",
    "huggingface-hub[cli]>=0.24",
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "ruff>=0.6",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
asyncio_mode = "auto"

[tool.ruff]
line-length = 100
```

- [ ] **Step 4: Write config.py and db.py**

`backend/src/__init__.py`: empty file.

`backend/src/config.py`:
```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://legal:legal@localhost:5432/legal"
    llm_model: str = "qwen3.8-27b-fp8"
    llm_api_base: str = "http://localhost:7080/v1"
    embed_model: str = "BAAI/bge-small-en-v1.5"


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

`backend/src/db.py`:
```python
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from src.config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)


SessionLocal = sessionmaker(bind=None, expire_on_commit=False)


def configure_sessions(engine: Engine) -> None:
    SessionLocal.configure(bind=engine)
```

- [ ] **Step 5: Write main.py with /health**

`backend/src/main.py`:
```python
from fastapi import FastAPI

from src.db import configure_sessions, get_engine


def create_app() -> FastAPI:
    app = FastAPI(title="Legal Beagle API")
    configure_sessions(get_engine())

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 6: Initialise Alembic**

Run from `backend/`:
```bash
uv sync
uv run alembic init alembic
```

Replace `backend/alembic/env.py` with:
```python
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from src.db import Base
import src.graph.models  # noqa: F401  (registers tables)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option(
    "sqlalchemy.url",
    os.environ.get("ALEMBIC_DATABASE_URL")
    or os.environ.get("DATABASE_URL")
    or "postgresql+psycopg://legal:legal@localhost:5432/legal",
)
target_metadata = Base.metadata


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
```

Create `backend/src/graph/__init__.py` (empty) and a placeholder `backend/src/graph/models.py` containing only:
```python
from src.db import Base  # noqa: F401
```

In `backend/alembic.ini`: set `script_location = alembic`, delete the `sqlalchemy.url` line (env.py sets it), and add `prepend_sys_path = .` if not present.

- [ ] **Step 7: Write conftest.py and the smoke test**

`backend/tests/conftest.py`:
```python
import os

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

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
    from src.config import get_settings

    get_settings.cache_clear()
    from src.main import create_app

    return TestClient(create_app())
```

`backend/tests/test_smoke.py`:
```python
from sqlalchemy import text


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_db_connects(db_session):
    assert db_session.execute(text("SELECT 1")).scalar() == 1
```

- [ ] **Step 8: Run tests**

Run: `cd backend && uv run pytest -v`
Expected: 2 passed.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat: backend scaffold with postgres, alembic and test harness"
```

---

### Task 2: Data model and initial migration

**Files:**
- Modify: `backend/src/graph/models.py`
- Create: `backend/alembic/versions/0001_initial.py` (autogenerated then checked), `backend/tests/graph/__init__.py`, `backend/tests/graph/test_models.py`

**Interfaces:**
- Produces ORM classes in `src.graph.models`: `Jurisdiction`, `Court`, `Act`, `ActVersion`, `Provision`, `Case`, `Judgment`, `Paragraph`, `Principle`, `Edge`; enums `Extraction` (`curated|parsed|llm_extracted`), `NodeType` (six node types), `EdgeKind` (twelve kinds); constant `EMBED_DIM = 384`.
- `Edge(src_type, src_id, dst_type, dst_id, kind, treatment: str|None, source_url, extraction, confidence: float, evidence_case_id: int|None)`; unique on `(src_type, src_id, dst_type, dst_id, kind)`.

- [ ] **Step 1: Write the failing test**

`backend/tests/graph/__init__.py`: empty.

`backend/tests/graph/test_models.py`:
```python
from datetime import date

from src.graph.models import (
    Act, ActVersion, Case, Court, Edge, EdgeKind, Extraction, Judgment,
    Jurisdiction, NodeType, Paragraph, Provision,
)


def test_round_trip_act_case_edge(db_session):
    cth = Jurisdiction(code="CTH", name="Commonwealth", level="Commonwealth")
    hca = Court(code="HCA", name="High Court of Australia", jurisdiction=cth, tier=1)
    act = Act(title="Corporations Act 2001", short_name="Corporations Act", year=2001,
              jurisdiction=cth, status="in_force", source_url="https://example/act",
              source_licence="CC-BY-4.0", extraction=Extraction.parsed)
    ver = ActVersion(act=act, version_id="C2004A00818", in_force_from=date(2001, 7, 15),
                     source_url="https://example/act/v1")
    s1 = Provision(act_version=ver, identifier="s1", heading="Short title", text="This Act…")
    case = Case(name="Example v Example", neutral_citation="[2020] HCA 1", court=hca,
                decided_on=date(2020, 1, 1), source_url="https://example/case",
                source_licence="Crown", extraction=Extraction.parsed)
    j = Judgment(case=case, judges="Kiefel CJ", disposition="majority")
    p = Paragraph(judgment=j, number=1, text="Para one.")
    db_session.add_all([cth, hca, act, ver, s1, case, j, p])
    db_session.flush()

    e = Edge(src_type=NodeType.case, src_id=case.id, dst_type=NodeType.provision,
             dst_id=s1.id, kind=EdgeKind.INTERPRETS, extraction=Extraction.parsed,
             confidence=1.0)
    db_session.add(e)
    db_session.commit()

    got = db_session.get(Edge, e.id)
    assert got.kind == EdgeKind.INTERPRETS
    assert got.src_id == case.id
    assert db_session.get(Provision, s1.id).act_version.act.short_name == "Corporations Act"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/graph/test_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'Act'`.

- [ ] **Step 3: Write the models**

`backend/src/graph/models.py`:
```python
from __future__ import annotations

from datetime import date
from enum import StrEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import Date, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db import Base

EMBED_DIM = 384


class Extraction(StrEnum):
    curated = "curated"
    parsed = "parsed"
    llm_extracted = "llm_extracted"


class NodeType(StrEnum):
    jurisdiction = "jurisdiction"
    court = "court"
    act = "act"
    provision = "provision"
    case = "case"
    principle = "principle"


class EdgeKind(StrEnum):
    IN_JURISDICTION = "IN_JURISDICTION"
    DECIDED_BY = "DECIDED_BY"
    APPEALS_TO = "APPEALS_TO"
    AUTHORISED_BY = "AUTHORISED_BY"
    AMENDS = "AMENDS"
    INTERPRETS = "INTERPRETS"
    CITES = "CITES"
    HELD_INCONSISTENT = "HELD_INCONSISTENT"
    ESTABLISHES = "ESTABLISHES"
    APPLIES = "APPLIES"
    EVOLVED_INTO = "EVOLVED_INTO"
    CODIFIES = "CODIFIES"


class ProvenanceMixin:
    source_url: Mapped[str | None] = mapped_column(Text)
    source_licence: Mapped[str | None] = mapped_column(String(64))
    extraction: Mapped[Extraction] = mapped_column(String(16), default=Extraction.parsed)


class Jurisdiction(Base):
    __tablename__ = "jurisdictions"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(8), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    level: Mapped[str] = mapped_column(String(16))  # Commonwealth|State|Territory


class Court(Base):
    __tablename__ = "courts"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)  # neutral-citation abbreviation
    name: Mapped[str] = mapped_column(String(128))
    jurisdiction_id: Mapped[int] = mapped_column(ForeignKey("jurisdictions.id"))
    tier: Mapped[int] = mapped_column(Integer)  # 1 = apex
    parent_court_id: Mapped[int | None] = mapped_column(ForeignKey("courts.id"))
    jurisdiction: Mapped[Jurisdiction] = relationship()
    parent_court: Mapped[Court | None] = relationship(remote_side=[id])


class Act(ProvenanceMixin, Base):
    __tablename__ = "acts"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    short_name: Mapped[str] = mapped_column(String(256), index=True)
    year: Mapped[int | None] = mapped_column(Integer)
    jurisdiction_id: Mapped[int] = mapped_column(ForeignKey("jurisdictions.id"))
    status: Mapped[str] = mapped_column(String(16), default="in_force")
    jurisdiction: Mapped[Jurisdiction] = relationship()
    versions: Mapped[list[ActVersion]] = relationship(back_populates="act")
    __table_args__ = (UniqueConstraint("title", "jurisdiction_id", name="uq_act_title_juris"),)


class ActVersion(Base):
    __tablename__ = "act_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    act_id: Mapped[int] = mapped_column(ForeignKey("acts.id"))
    version_id: Mapped[str] = mapped_column(String(64), unique=True)  # source's id
    in_force_from: Mapped[date | None] = mapped_column(Date)
    in_force_to: Mapped[date | None] = mapped_column(Date)
    source_url: Mapped[str | None] = mapped_column(Text)
    act: Mapped[Act] = relationship(back_populates="versions")
    provisions: Mapped[list[Provision]] = relationship(back_populates="act_version")


class Provision(Base):
    __tablename__ = "provisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    act_version_id: Mapped[int] = mapped_column(ForeignKey("act_versions.id"))
    identifier: Mapped[str] = mapped_column(String(64))  # "s51(xx)"
    heading: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    parent_provision_id: Mapped[int | None] = mapped_column(ForeignKey("provisions.id"))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM))
    tsv: Mapped[str | None] = mapped_column(TSVECTOR)
    act_version: Mapped[ActVersion] = relationship(back_populates="provisions")
    parent: Mapped[Provision | None] = relationship(remote_side=[id])
    __table_args__ = (
        UniqueConstraint("act_version_id", "identifier", name="uq_provision_ident"),
        Index("ix_provisions_tsv", "tsv", postgresql_using="gin"),
    )


class Case(ProvenanceMixin, Base):
    __tablename__ = "cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    neutral_citation: Mapped[str] = mapped_column(String(64), unique=True)
    court_id: Mapped[int] = mapped_column(ForeignKey("courts.id"))
    decided_on: Mapped[date | None] = mapped_column(Date)
    summary: Mapped[str | None] = mapped_column(Text)
    court: Mapped[Court] = relationship()
    judgments: Mapped[list[Judgment]] = relationship(back_populates="case")


class Judgment(Base):
    __tablename__ = "judgments"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"))
    judges: Mapped[str | None] = mapped_column(Text)
    disposition: Mapped[str] = mapped_column(String(16), default="majority")
    case: Mapped[Case] = relationship(back_populates="judgments")
    paragraphs: Mapped[list[Paragraph]] = relationship(back_populates="judgment")


class Paragraph(Base):
    __tablename__ = "paragraphs"
    id: Mapped[int] = mapped_column(primary_key=True)
    judgment_id: Mapped[int] = mapped_column(ForeignKey("judgments.id"))
    number: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM))
    tsv: Mapped[str | None] = mapped_column(TSVECTOR)
    judgment: Mapped[Judgment] = relationship(back_populates="paragraphs")
    __table_args__ = (
        UniqueConstraint("judgment_id", "number", name="uq_paragraph_number"),
        Index("ix_paragraphs_tsv", "tsv", postgresql_using="gin"),
    )


class Principle(ProvenanceMixin, Base):
    __tablename__ = "principles"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(256), unique=True)
    statement: Mapped[str] = mapped_column(Text)


class Edge(Base):
    __tablename__ = "edges"
    id: Mapped[int] = mapped_column(primary_key=True)
    src_type: Mapped[NodeType] = mapped_column(String(16))
    src_id: Mapped[int] = mapped_column(Integer)
    dst_type: Mapped[NodeType] = mapped_column(String(16))
    dst_id: Mapped[int] = mapped_column(Integer)
    kind: Mapped[EdgeKind] = mapped_column(String(24))
    treatment: Mapped[str | None] = mapped_column(String(16))
    source_url: Mapped[str | None] = mapped_column(Text)
    extraction: Mapped[Extraction] = mapped_column(String(16), default=Extraction.parsed)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    evidence_case_id: Mapped[int | None] = mapped_column(ForeignKey("cases.id"))
    __table_args__ = (
        UniqueConstraint("src_type", "src_id", "dst_type", "dst_id", "kind", name="uq_edge"),
        Index("ix_edges_src", "src_type", "src_id"),
        Index("ix_edges_dst", "dst_type", "dst_id"),
    )
```

- [ ] **Step 4: Generate and check the migration**

Run from `backend/`:
```bash
ALEMBIC_DATABASE_URL=postgresql+psycopg://legal:legal@localhost:5432/legal uv run alembic revision --autogenerate -m "initial" --rev-id 0001
```
Open `backend/alembic/versions/0001_initial.py` and confirm: (a) it creates all 10 tables; (b) the `embedding` columns use `pgvector.sqlalchemy.Vector(384)` — add `import pgvector.sqlalchemy` at the top if autogen omitted it; (c) add `op.execute("CREATE EXTENSION IF NOT EXISTS vector")` as the first line of `upgrade()`.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/graph/test_models.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: graph data model and initial migration"
```

---

### Task 3: Seed reference data (jurisdictions and courts)

**Files:**
- Create: `backend/src/graph/seed.py`, `backend/tests/graph/test_seed.py`

**Interfaces:**
- Produces: `seed_reference_data(session: Session) -> None` — idempotent; inserts jurisdictions CTH, NSW, VIC, QLD, SA, WA, TAS, ACT, NT and Commonwealth courts HCA (tier 1), FCAFC (tier 2, parent HCA), FCA (tier 3, parent FCAFC), FedCFamC1G (tier 3, parent FCAFC), plus `APPEALS_TO` edges.
- Produces: `get_court_by_code(session, code: str) -> Court | None`.

- [ ] **Step 1: Write the failing test**

`backend/tests/graph/test_seed.py`:
```python
from sqlalchemy import select

from src.graph.models import Edge, EdgeKind, Jurisdiction
from src.graph.seed import get_court_by_code, seed_reference_data


def test_seed_is_idempotent_and_builds_hierarchy(db_session):
    seed_reference_data(db_session)
    seed_reference_data(db_session)
    db_session.commit()

    cth = db_session.scalar(select(Jurisdiction).where(Jurisdiction.code == "CTH"))
    assert cth.level == "Commonwealth"
    assert len(db_session.scalars(select(Jurisdiction)).all()) == 9
    fca = get_court_by_code(db_session, "FCA")
    hca = get_court_by_code(db_session, "HCA")
    assert fca.parent_court.code == "FCAFC"
    assert fca.parent_court.parent_court_id == hca.id
    appeals = db_session.scalars(select(Edge).where(Edge.kind == EdgeKind.APPEALS_TO)).all()
    assert len(appeals) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/graph/test_seed.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.graph.seed'`.

- [ ] **Step 3: Write seed.py**

`backend/src/graph/seed.py`:
```python
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.graph.models import Court, Edge, EdgeKind, Extraction, Jurisdiction, NodeType

JURISDICTIONS = [
    ("CTH", "Commonwealth", "Commonwealth"),
    ("NSW", "New South Wales", "State"),
    ("VIC", "Victoria", "State"),
    ("QLD", "Queensland", "State"),
    ("SA", "South Australia", "State"),
    ("WA", "Western Australia", "State"),
    ("TAS", "Tasmania", "State"),
    ("ACT", "Australian Capital Territory", "Territory"),
    ("NT", "Northern Territory", "Territory"),
]

# (code, name, jurisdiction_code, tier, parent_code)
COURTS = [
    ("HCA", "High Court of Australia", "CTH", 1, None),
    ("FCAFC", "Federal Court of Australia (Full Court)", "CTH", 2, "HCA"),
    ("FCA", "Federal Court of Australia", "CTH", 3, "FCAFC"),
    ("FedCFamC1G", "Federal Circuit and Family Court (Div 1)", "CTH", 3, "FCAFC"),
]


def get_court_by_code(session: Session, code: str) -> Court | None:
    return session.scalar(select(Court).where(Court.code == code))


def _upsert_edge(session: Session, src_type, src_id, dst_type, dst_id, kind) -> None:
    exists = session.scalar(
        select(Edge).where(
            Edge.src_type == src_type, Edge.src_id == src_id,
            Edge.dst_type == dst_type, Edge.dst_id == dst_id, Edge.kind == kind,
        )
    )
    if not exists:
        session.add(Edge(src_type=src_type, src_id=src_id, dst_type=dst_type, dst_id=dst_id,
                         kind=kind, extraction=Extraction.curated, confidence=1.0))


def seed_reference_data(session: Session) -> None:
    by_code: dict[str, Jurisdiction] = {}
    for code, name, level in JURISDICTIONS:
        j = session.scalar(select(Jurisdiction).where(Jurisdiction.code == code))
        if j is None:
            j = Jurisdiction(code=code, name=name, level=level)
            session.add(j)
        by_code[code] = j
    session.flush()

    courts: dict[str, Court] = {}
    for code, name, jcode, tier, _parent in COURTS:
        c = get_court_by_code(session, code)
        if c is None:
            c = Court(code=code, name=name, jurisdiction_id=by_code[jcode].id, tier=tier)
            session.add(c)
        courts[code] = c
    session.flush()
    for code, _, _, _, parent in COURTS:
        if parent:
            courts[code].parent_court_id = courts[parent].id
            _upsert_edge(session, NodeType.court, courts[code].id,
                         NodeType.court, courts[parent].id, EdgeKind.APPEALS_TO)
    session.flush()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/graph/test_seed.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: seed jurisdictions and commonwealth court hierarchy"
```

---

### Task 4: Citation parser (pure)

**Files:**
- Create: `backend/src/ingestion/__init__.py`, `backend/src/ingestion/parsers/__init__.py`, `backend/src/ingestion/parsers/citation_parser.py`, `backend/tests/ingestion/__init__.py`, `backend/tests/ingestion/test_citation_parser.py`

**Interfaces:**
- Produces:
  ```python
  NEUTRAL_RE: re.Pattern  # reused by judgment_parser
  @dataclass(frozen=True) class NeutralCitation: year: int; court: str; number: int; raw: str
  @dataclass(frozen=True) class ReportedCitation: year: int; volume: int; series: str; page: int; raw: str
  @dataclass(frozen=True) class SectionRef: section: str; act_hint: str | None; raw: str   # section like "51(xx)"; raw like "s 51(xx) of the Constitution"
  @dataclass class Citations: neutral: list[NeutralCitation]; reported: list[ReportedCitation]; sections: list[SectionRef]
  def parse_citations(text: str) -> Citations
  ```
  Dedupes by `raw`, order of first appearance preserved.

- [ ] **Step 1: Write the failing tests**

`backend/tests/ingestion/__init__.py`: empty.

`backend/tests/ingestion/test_citation_parser.py`:
```python
from src.ingestion.parsers.citation_parser import parse_citations


def test_neutral_citation():
    c = parse_citations("See Mabo v Queensland (No 2) [1992] HCA 23 at [5].")
    assert len(c.neutral) == 1
    assert (c.neutral[0].year, c.neutral[0].court, c.neutral[0].number) == (1992, "HCA", 23)
    assert c.neutral[0].raw == "[1992] HCA 23"


def test_reported_citation():
    c = parse_citations("(1992) 175 CLR 1 and (2006) 229 CLR 1")
    assert [(r.volume, r.series, r.page) for r in c.reported] == [(175, "CLR", 1), (229, "CLR", 1)]


def test_section_refs_with_and_without_act_hint():
    c = parse_citations(
        "Under s 51(xx) of the Constitution, and ss 9 and 12 of the Corporations Act 2001 (Cth), and section 109."
    )
    secs = [(s.section, s.act_hint) for s in c.sections]
    assert ("51(xx)", "Constitution") in secs
    assert ("9", "Corporations Act 2001") in secs
    assert ("12", "Corporations Act 2001") in secs
    assert ("109", None) in secs
    assert any(s.raw == "s 51(xx) of the Constitution" for s in c.sections)


def test_dedupe_preserves_order():
    c = parse_citations("[2020] HCA 1 ... [2019] HCA 2 ... [2020] HCA 1")
    assert [n.raw for n in c.neutral] == ["[2020] HCA 1", "[2019] HCA 2"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/ingestion/test_citation_parser.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the parser**

`backend/src/ingestion/__init__.py` and `backend/src/ingestion/parsers/__init__.py`: empty.

`backend/src/ingestion/parsers/citation_parser.py`:
```python
from __future__ import annotations

import re
from dataclasses import dataclass, field

NEUTRAL_RE = re.compile(r"\[(\d{4})\]\s+([A-Z][A-Za-z]{1,9})\s+(\d+)")
REPORTED_RE = re.compile(
    r"\((\d{4})\)\s+(\d+)\s+(CLR|ALR|ALJR|FCR|FLR|NSWLR|VR|Qd R|SASR|WAR|Tas R)\s+(\d+)"
)

# "s 51(xx)", "ss 9 and 12", "section 109" — captures a list of section ids.
SECTION_LIST_RE = re.compile(
    r"\b(?:ss?\.?|sections?)\s+"
    r"(\d+[A-Z]{0,3}(?:\([^)\s]{1,6}\))*"
    r"(?:(?:,\s*|\s+and\s+)\d+[A-Z]{0,3}(?:\([^)\s]{1,6}\))*)*)"
)
# "of the Corporations Act 2001 (Cth)" or "of the Constitution" right after a section list
ACT_HINT_RE = re.compile(r"^\s*of\s+the\s+((?:[A-Z][\w'’\-]*\s+)*(?:Act\s+\d{4}|Constitution))")
SECTION_SPLIT_RE = re.compile(r",\s*|\s+and\s+")


@dataclass(frozen=True)
class NeutralCitation:
    year: int
    court: str
    number: int
    raw: str


@dataclass(frozen=True)
class ReportedCitation:
    year: int
    volume: int
    series: str
    page: int
    raw: str


@dataclass(frozen=True)
class SectionRef:
    section: str
    act_hint: str | None
    raw: str


@dataclass
class Citations:
    neutral: list[NeutralCitation] = field(default_factory=list)
    reported: list[ReportedCitation] = field(default_factory=list)
    sections: list[SectionRef] = field(default_factory=list)


def _dedupe(items):
    seen, out = set(), []
    for it in items:
        if it.raw not in seen:
            seen.add(it.raw)
            out.append(it)
    return out


def parse_citations(text: str) -> Citations:
    neutral = [
        NeutralCitation(int(m.group(1)), m.group(2), int(m.group(3)), m.group(0))
        for m in NEUTRAL_RE.finditer(text)
    ]
    reported = [
        ReportedCitation(int(m.group(1)), int(m.group(2)), m.group(3), int(m.group(4)), m.group(0))
        for m in REPORTED_RE.finditer(text)
    ]
    sections: list[SectionRef] = []
    for m in SECTION_LIST_RE.finditer(text):
        hint_m = ACT_HINT_RE.match(text[m.end():])
        hint = hint_m.group(1).strip() if hint_m else None
        for sec in SECTION_SPLIT_RE.split(m.group(1)):
            sec = sec.strip()
            if sec:
                raw = f"s {sec}" + (f" of the {hint}" if hint else "")
                sections.append(SectionRef(sec, hint, raw))
    return Citations(_dedupe(neutral), _dedupe(reported), _dedupe(sections))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/ingestion/test_citation_parser.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: citation parser for neutral, reported and section references"
```

---

### Task 5: Act parser (pure)

**Files:**
- Create: `backend/src/ingestion/parsers/act_parser.py`, `backend/tests/fixtures/act_sample.txt`, `backend/tests/ingestion/test_act_parser.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass class ParsedProvision: identifier: str; heading: str | None; text: str; children: list[ParsedProvision]
  def parse_act(text: str) -> list[ParsedProvision]   # top-level sections "s51", children "s51(xx)"; leading text as identifier "preamble"
  ```
  Heuristic: a top-level section starts at a line matching `^(\d+[A-Z]{0,3})\s{2,}(\S.*)$` (number, two+ spaces, heading). Inside a section, a line matching `^\s*\(([a-z0-9]{1,4}|[ivxlc]{1,6})\)\s+` starts a child.

- [ ] **Step 1: Write the fixture**

`backend/tests/fixtures/act_sample.txt`:
```
Commonwealth of Australia Constitution Act

An Act to constitute the Commonwealth of Australia

51  Legislative powers of the Parliament
The Parliament shall, subject to this Constitution, have power to make laws for the peace, order, and good government of the Commonwealth with respect to:
  (i)  trade and commerce with other countries, and among the States;
  (ii)  taxation; but so as not to discriminate between States or parts of States;
  (xx)  foreign corporations, and trading or financial corporations formed within the limits of the Commonwealth;

52  Exclusive powers of the Parliament
The Parliament shall, subject to this Constitution, have exclusive power to make laws.

109  Inconsistency of laws
When a law of a State is inconsistent with a law of the Commonwealth, the latter shall prevail, and the former shall, to the extent of the inconsistency, be invalid.
```

- [ ] **Step 2: Write the failing test**

`backend/tests/ingestion/test_act_parser.py`:
```python
from pathlib import Path

from src.ingestion.parsers.act_parser import parse_act

FIXTURE = Path(__file__).parent.parent / "fixtures" / "act_sample.txt"


def test_parses_sections_and_subsections():
    secs = parse_act(FIXTURE.read_text())
    assert [s.identifier for s in secs] == ["preamble", "s51", "s52", "s109"]
    s51 = secs[1]
    assert s51.heading == "Legislative powers of the Parliament"
    assert s51.text.startswith("The Parliament shall, subject to this Constitution")
    assert [c.identifier for c in s51.children] == ["s51(i)", "s51(ii)", "s51(xx)"]
    assert s51.children[2].text.startswith("foreign corporations")
    assert secs[3].text.startswith("When a law of a State")


def test_no_sections_returns_preamble_only():
    secs = parse_act("Just some text with no sections.")
    assert [s.identifier for s in secs] == ["preamble"]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/ingestion/test_act_parser.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Write the parser**

`backend/src/ingestion/parsers/act_parser.py`:
```python
from __future__ import annotations

import re
from dataclasses import dataclass, field

SECTION_RE = re.compile(r"^(\d+[A-Z]{0,3})\s{2,}(\S.*)$")
CHILD_RE = re.compile(r"^\s*\(([a-z0-9]{1,4}|[ivxlc]{1,6})\)\s+(.*)$")


@dataclass
class ParsedProvision:
    identifier: str
    heading: str | None
    text: str
    children: list[ParsedProvision] = field(default_factory=list)


def _finish(prov: ParsedProvision | None, lines: list[str]) -> None:
    if prov is not None:
        prov.text = "\n".join(lines).strip()


def parse_act(text: str) -> list[ParsedProvision]:
    out: list[ParsedProvision] = []
    current = ParsedProvision("preamble", None, "")
    cur_lines: list[str] = []
    child: ParsedProvision | None = None
    child_lines: list[str] = []

    def close_child() -> None:
        nonlocal child, child_lines
        _finish(child, child_lines)
        child, child_lines = None, []

    for raw in text.splitlines():
        m = SECTION_RE.match(raw)
        if m:
            close_child()
            _finish(current, cur_lines)
            out.append(current)
            current = ParsedProvision(f"s{m.group(1)}", m.group(2).strip(), "")
            cur_lines = []
            continue
        cm = CHILD_RE.match(raw) if current.identifier != "preamble" else None
        if cm:
            close_child()
            child = ParsedProvision(f"{current.identifier}({cm.group(1)})", None, "")
            child_lines = [cm.group(2)]
            current.children.append(child)
            continue
        if child is not None:
            child_lines.append(raw)
        else:
            cur_lines.append(raw)

    close_child()
    _finish(current, cur_lines)
    out.append(current)
    return out
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/ingestion/test_act_parser.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: heuristic act text parser producing section tree"
```

---

### Task 6: Judgment parser (pure)

**Files:**
- Create: `backend/src/ingestion/parsers/judgment_parser.py`, `backend/tests/fixtures/judgment_sample.txt`, `backend/tests/ingestion/test_judgment_parser.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass class ParsedJudgment: judges: str | None; paragraphs: list[tuple[int, str]]
  def parse_judgment(text: str) -> ParsedJudgment
  def split_case_citation(citation: str) -> tuple[str, str | None]  # ("Mabo v Queensland (No 2)", "[1992] HCA 23")
  ```
  A paragraph starts at a line matching `^\s*(?:\[(\d{1,4})\]|(\d{1,4})[.\]]?)\s+(\S.*)$`. Text before the first paragraph: the first line containing a `CJ`/`JJ`/`J` token becomes `judges`.

- [ ] **Step 1: Write the fixture**

`backend/tests/fixtures/judgment_sample.txt`:
```
HIGH COURT OF AUSTRALIA
MASON CJ, BRENNAN, DEANE, DAWSON, TOOHEY, GAUDRON AND McHUGH JJ

MABO AND OTHERS v QUEENSLAND (No 2)

1. The plaintiffs claim native title over the Murray Islands.
Second line of paragraph one.

2. In Cooper v Stuart (1889) 14 App Cas 286 the Privy Council held otherwise; see also [1988] HCA 69.

[3] The doctrine of terra nullius is rejected.
```

- [ ] **Step 2: Write the failing test**

`backend/tests/ingestion/test_judgment_parser.py`:
```python
from pathlib import Path

from src.ingestion.parsers.judgment_parser import parse_judgment, split_case_citation

FIXTURE = Path(__file__).parent.parent / "fixtures" / "judgment_sample.txt"


def test_paragraphs_and_judges():
    j = parse_judgment(FIXTURE.read_text())
    assert j.judges == "MASON CJ, BRENNAN, DEANE, DAWSON, TOOHEY, GAUDRON AND McHUGH JJ"
    assert [n for n, _ in j.paragraphs] == [1, 2, 3]
    assert j.paragraphs[0][1] == (
        "The plaintiffs claim native title over the Murray Islands.\nSecond line of paragraph one."
    )
    assert j.paragraphs[2][1] == "The doctrine of terra nullius is rejected."


def test_split_case_citation():
    assert split_case_citation("Mabo v Queensland (No 2) [1992] HCA 23") == (
        "Mabo v Queensland (No 2)", "[1992] HCA 23")
    assert split_case_citation("Unknown v Unknown") == ("Unknown v Unknown", None)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/ingestion/test_judgment_parser.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Write the parser**

`backend/src/ingestion/parsers/judgment_parser.py`:
```python
from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.ingestion.parsers.citation_parser import NEUTRAL_RE

PARA_RE = re.compile(r"^\s*(?:\[(\d{1,4})\]|(\d{1,4})[.\]]?)\s+(\S.*)$")
JUDGES_RE = re.compile(r"\b(CJ|JJ|J)\b")


@dataclass
class ParsedJudgment:
    judges: str | None
    paragraphs: list[tuple[int, str]] = field(default_factory=list)


def parse_judgment(text: str) -> ParsedJudgment:
    judges: str | None = None
    paras: list[tuple[int, list[str]]] = []
    for raw in text.splitlines():
        m = PARA_RE.match(raw)
        if m:
            num = int(m.group(1) or m.group(2))
            paras.append((num, [m.group(3)]))
            continue
        if paras:
            paras[-1][1].append(raw)
        elif judges is None and JUDGES_RE.search(raw):
            judges = raw.strip()
    return ParsedJudgment(
        judges=judges,
        paragraphs=[(n, "\n".join(lines).strip()) for n, lines in paras],
    )


def split_case_citation(citation: str) -> tuple[str, str | None]:
    m = NEUTRAL_RE.search(citation)
    if not m:
        return citation.strip(), None
    return citation[: m.start()].strip(), m.group(0)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/ingestion/test_judgment_parser.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: judgment parser producing numbered paragraphs and bench"
```

---

### Task 7: OALC loader

**Files:**
- Create: `backend/src/ingestion/sources/__init__.py`, `backend/src/ingestion/sources/oalc.py`, `backend/tests/fixtures/oalc_sample.jsonl`, `backend/tests/ingestion/test_oalc.py`

**Interfaces:**
- Consumes: `parse_act`, `parse_judgment`, `split_case_citation`, `get_court_by_code`, ORM models.
- Produces:
  ```python
  @dataclass class LoadStats: acts: int = 0; cases: int = 0; skipped: int = 0
  def load_oalc(session: Session, path: Path, *, sources: set[str], jurisdictions: set[str]) -> LoadStats
  def short_name(title: str) -> str      # "Corporations Act 2001" -> "Corporations Act"
  OALC_JURISDICTION_MAP: dict[str, str]  # "commonwealth" -> "CTH", ...
  ```
  Reads jsonl records with keys `version_id, type, jurisdiction, source, mime, date, citation, url, when_scraped, text`. `type == "primary_legislation"` → `Act`/`ActVersion`/`Provision` (+ `IN_JURISDICTION` edge); `type == "decision"` → `Case`/`Judgment`/`Paragraph` (+ `DECIDED_BY` edge). Idempotent on `version_id` (acts) and `neutral_citation` (cases). Records filtered out by `sources`/`jurisdictions`, or whose court code has no `Court` row, count as `skipped`. Already-loaded records count as nothing. `source_licence`: `"CC-BY-4.0"` for `federal_register_of_legislation`, `"Crown-HCA"` for `high_court_of_australia`.

- [ ] **Step 1: Write the fixture**

`backend/tests/fixtures/oalc_sample.jsonl` (three lines, one JSON object per line — keep each on a single line):
```json
{"version_id": "C2004Q00685", "type": "primary_legislation", "jurisdiction": "commonwealth", "source": "federal_register_of_legislation", "mime": "text/plain", "date": "2013-06-05", "citation": "Commonwealth of Australia Constitution Act", "url": "https://www.legislation.gov.au/C2004Q00685/latest/text", "when_scraped": "2024-01-01T00:00:00", "text": "Commonwealth of Australia Constitution Act\n\n51  Legislative powers of the Parliament\nThe Parliament shall have power to make laws with respect to:\n  (xx)  foreign corporations, and trading or financial corporations;\n\n109  Inconsistency of laws\nWhen a law of a State is inconsistent with a law of the Commonwealth, the latter shall prevail."}
{"version_id": "hca-1992-23", "type": "decision", "jurisdiction": "commonwealth", "source": "high_court_of_australia", "mime": "text/plain", "date": "1992-06-03", "citation": "Mabo v Queensland (No 2) [1992] HCA 23", "url": "https://eresources.hcourt.gov.au/showCase/1992/HCA/23", "when_scraped": "2024-01-01T00:00:00", "text": "MASON CJ, BRENNAN J\n\n1. The plaintiffs claim native title.\n\n2. Under s 109 of the Constitution the Commonwealth law prevails; see [1988] HCA 69."}
{"version_id": "nswca-2020-1", "type": "decision", "jurisdiction": "new_south_wales", "source": "nsw_caselaw", "mime": "text/plain", "date": "2020-01-01", "citation": "X v Y [2020] NSWCA 1", "url": "https://example/nswca", "when_scraped": "2024-01-01T00:00:00", "text": "1. Irrelevant."}
```

- [ ] **Step 2: Write the failing test**

`backend/tests/ingestion/test_oalc.py`:
```python
from pathlib import Path

from sqlalchemy import select

from src.graph.models import Act, Case, Paragraph, Provision
from src.graph.seed import seed_reference_data
from src.ingestion.sources.oalc import load_oalc, short_name

FIXTURE = Path(__file__).parent.parent / "fixtures" / "oalc_sample.jsonl"
ARGS = dict(sources={"federal_register_of_legislation", "high_court_of_australia"},
            jurisdictions={"commonwealth"})


def test_short_name():
    assert short_name("Corporations Act 2001") == "Corporations Act"
    assert short_name("Commonwealth of Australia Constitution Act") == "Commonwealth of Australia Constitution Act"


def test_loads_acts_and_cases_and_is_idempotent(db_session):
    seed_reference_data(db_session)
    stats = load_oalc(db_session, FIXTURE, **ARGS)
    db_session.commit()
    assert (stats.acts, stats.cases, stats.skipped) == (1, 1, 1)

    act = db_session.scalar(select(Act))
    assert act.title == "Commonwealth of Australia Constitution Act"
    assert act.source_licence == "CC-BY-4.0"
    idents = set(db_session.scalars(select(Provision.identifier)).all())
    assert {"preamble", "s51", "s51(xx)", "s109"} <= idents

    case = db_session.scalar(select(Case))
    assert case.neutral_citation == "[1992] HCA 23"
    assert case.name == "Mabo v Queensland (No 2)"
    assert case.court.code == "HCA"
    para2 = db_session.scalar(select(Paragraph).where(Paragraph.number == 2))
    assert para2.text.startswith("Under s 109")

    again = load_oalc(db_session, FIXTURE, **ARGS)
    db_session.commit()
    assert (again.acts, again.cases) == (0, 0)
    assert len(db_session.scalars(select(Act)).all()) == 1
    assert len(db_session.scalars(select(Case)).all()) == 1
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/ingestion/test_oalc.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Write the loader**

`backend/src/ingestion/sources/__init__.py`: empty.

`backend/src/ingestion/sources/oalc.py`:
```python
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.graph.models import (
    Act, ActVersion, Case, Edge, EdgeKind, Extraction, Judgment, Jurisdiction,
    NodeType, Paragraph, Provision,
)
from src.graph.seed import get_court_by_code
from src.ingestion.parsers.act_parser import ParsedProvision, parse_act
from src.ingestion.parsers.judgment_parser import parse_judgment, split_case_citation

OALC_JURISDICTION_MAP = {
    "commonwealth": "CTH", "new_south_wales": "NSW", "victoria": "VIC", "queensland": "QLD",
    "south_australia": "SA", "western_australia": "WA", "tasmania": "TAS",
    "australian_capital_territory": "ACT", "northern_territory": "NT",
}
LICENCE_BY_SOURCE = {
    "federal_register_of_legislation": "CC-BY-4.0",
    "high_court_of_australia": "Crown-HCA",
}
YEAR_RE = re.compile(r"\b(1[89]\d{2}|20\d{2})\b")


@dataclass
class LoadStats:
    acts: int = 0
    cases: int = 0
    skipped: int = 0


def short_name(title: str) -> str:
    return re.sub(r"\s+(Act|Regulations?)\s+\d{4}.*$", r" \1", title).strip()


def _parse_date(s: str | None) -> date | None:
    try:
        return date.fromisoformat(s[:10]) if s else None
    except ValueError:
        return None


def _add_provisions(session: Session, version: ActVersion, provs: list[ParsedProvision],
                    parent: Provision | None = None) -> None:
    for p in provs:
        row = Provision(act_version=version, identifier=p.identifier, heading=p.heading,
                        text=p.text, parent=parent)
        session.add(row)
        session.flush()
        _add_provisions(session, version, p.children, row)


def _load_act(session: Session, rec: dict, juris: Jurisdiction) -> bool:
    if session.scalar(select(ActVersion).where(ActVersion.version_id == rec["version_id"])):
        return False
    title = rec["citation"].strip()
    act = session.scalar(select(Act).where(Act.title == title, Act.jurisdiction_id == juris.id))
    if act is None:
        ym = YEAR_RE.search(title)
        act = Act(title=title, short_name=short_name(title), year=int(ym.group(1)) if ym else None,
                  jurisdiction_id=juris.id, status="in_force", source_url=rec["url"],
                  source_licence=LICENCE_BY_SOURCE.get(rec["source"]),
                  extraction=Extraction.parsed)
        session.add(act)
        session.flush()
        session.add(Edge(src_type=NodeType.act, src_id=act.id, dst_type=NodeType.jurisdiction,
                         dst_id=juris.id, kind=EdgeKind.IN_JURISDICTION,
                         extraction=Extraction.parsed, confidence=1.0))
    version = ActVersion(act=act, version_id=rec["version_id"],
                         in_force_from=_parse_date(rec.get("date")), source_url=rec["url"])
    session.add(version)
    session.flush()
    _add_provisions(session, version, parse_act(rec["text"]))
    return True


def _load_case(session: Session, rec: dict) -> str:
    """Returns 'loaded', 'exists' or 'skipped'."""
    name, neutral = split_case_citation(rec["citation"])
    if neutral is None:
        return "skipped"
    court = get_court_by_code(session, neutral.split()[1])
    if court is None:
        return "skipped"
    if session.scalar(select(Case).where(Case.neutral_citation == neutral)):
        return "exists"
    parsed = parse_judgment(rec["text"])
    case = Case(name=name, neutral_citation=neutral, court_id=court.id,
                decided_on=_parse_date(rec.get("date")), source_url=rec["url"],
                source_licence=LICENCE_BY_SOURCE.get(rec["source"]), extraction=Extraction.parsed)
    session.add(case)
    session.flush()
    session.add(Edge(src_type=NodeType.case, src_id=case.id, dst_type=NodeType.court,
                     dst_id=court.id, kind=EdgeKind.DECIDED_BY, extraction=Extraction.parsed,
                     confidence=1.0))
    j = Judgment(case=case, judges=parsed.judges, disposition="majority")
    session.add(j)
    session.flush()
    session.add_all([Paragraph(judgment=j, number=n, text=t) for n, t in parsed.paragraphs])
    session.flush()
    return "loaded"


def load_oalc(session: Session, path: Path, *, sources: set[str],
              jurisdictions: set[str]) -> LoadStats:
    stats = LoadStats()
    juris_rows = {j.code: j for j in session.scalars(select(Jurisdiction)).all()}
    with path.open() as fh:
        for line in fh:
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("source") not in sources or rec.get("jurisdiction") not in jurisdictions:
                stats.skipped += 1
                continue
            juris = juris_rows[OALC_JURISDICTION_MAP[rec["jurisdiction"]]]
            if rec["type"] == "primary_legislation":
                stats.acts += int(_load_act(session, rec, juris))
            elif rec["type"] == "decision":
                outcome = _load_case(session, rec)
                stats.cases += outcome == "loaded"
                stats.skipped += outcome == "skipped"
            else:
                stats.skipped += 1
    return stats
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/ingestion/test_oalc.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: OALC jsonl loader for commonwealth acts and HCA decisions"
```

---

### Task 8: Citation linking (CITES and INTERPRETS edges)

**Files:**
- Create: `backend/src/ingestion/link.py`, `backend/tests/ingestion/test_link.py`

**Interfaces:**
- Consumes: `parse_citations`, `short_name`, ORM.
- Produces:
  ```python
  def resolve_neutral(session, raw: str) -> Case | None
  def resolve_section(session, section: str, act_hint: str | None) -> Provision | None
  def link_case_citations(session: Session) -> tuple[int, int]   # (cites_edges_added, interprets_edges_added)
  ```
  `resolve_section`: identifier is `f"s{section}"`; hint `"Constitution"` → `Act.title ILIKE '%Constitution Act%'`; other hint → `Act.short_name ILIKE f"{short_name(hint)}%"`; no hint → only if every matching provision belongs to a single act. Latest `ActVersion` wins. `link_case_citations` walks every `Paragraph`, adds `CITES` (case→case, `treatment=None`) and `INTERPRETS` (case→provision) edges, `extraction=parsed`, `confidence=1.0`, idempotent.

- [ ] **Step 1: Write the failing test**

`backend/tests/ingestion/test_link.py`:
```python
from pathlib import Path

from sqlalchemy import select

from src.graph.models import Edge, EdgeKind, NodeType
from src.graph.seed import seed_reference_data
from src.ingestion.link import link_case_citations, resolve_section
from src.ingestion.sources.oalc import load_oalc

FIXTURE = Path(__file__).parent.parent / "fixtures" / "oalc_sample.jsonl"


def _load(db_session):
    seed_reference_data(db_session)
    load_oalc(db_session, FIXTURE,
              sources={"federal_register_of_legislation", "high_court_of_australia"},
              jurisdictions={"commonwealth"})
    db_session.commit()


def test_resolve_section_by_hint(db_session):
    _load(db_session)
    assert resolve_section(db_session, "109", "Constitution").identifier == "s109"
    assert resolve_section(db_session, "51(xx)", "Constitution").identifier == "s51(xx)"
    assert resolve_section(db_session, "109", None).identifier == "s109"  # unique across acts
    assert resolve_section(db_session, "999", "Constitution") is None


def test_link_creates_interprets_but_not_unresolvable_cites(db_session):
    _load(db_session)
    cites, interprets = link_case_citations(db_session)
    db_session.commit()
    # [1988] HCA 69 is not in the corpus -> no CITES edge; s 109 of the Constitution resolves.
    assert (cites, interprets) == (0, 1)
    e = db_session.scalar(select(Edge).where(Edge.kind == EdgeKind.INTERPRETS))
    assert e.src_type == NodeType.case and e.dst_type == NodeType.provision
    assert link_case_citations(db_session) == (0, 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/ingestion/test_link.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write link.py**

`backend/src/ingestion/link.py`:
```python
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.graph.models import (
    Act, ActVersion, Case, Edge, EdgeKind, Extraction, NodeType, Paragraph, Provision,
)
from src.ingestion.parsers.citation_parser import parse_citations
from src.ingestion.sources.oalc import short_name


def resolve_neutral(session: Session, raw: str) -> Case | None:
    return session.scalar(select(Case).where(Case.neutral_citation == raw))


def resolve_section(session: Session, section: str, act_hint: str | None) -> Provision | None:
    ident = f"s{section}"
    q = (
        select(Provision)
        .join(ActVersion, Provision.act_version_id == ActVersion.id)
        .join(Act, ActVersion.act_id == Act.id)
        .where(Provision.identifier == ident)
        .order_by(ActVersion.in_force_from.desc().nulls_last())
    )
    if act_hint is None:
        rows = session.scalars(q).all()
        acts = {r.act_version.act_id for r in rows}
        return rows[0] if len(acts) == 1 else None
    if act_hint.lower() == "constitution":
        q = q.where(Act.title.ilike("%Constitution Act%"))
    else:
        q = q.where(Act.short_name.ilike(f"{short_name(act_hint)}%"))
    return session.scalars(q).first()


def edge_exists(session: Session, src_type, src_id, dst_type, dst_id, kind) -> bool:
    n = session.scalar(
        select(func.count()).select_from(Edge).where(
            Edge.src_type == src_type, Edge.src_id == src_id,
            Edge.dst_type == dst_type, Edge.dst_id == dst_id, Edge.kind == kind,
        )
    )
    return n > 0


def link_case_citations(session: Session) -> tuple[int, int]:
    cites = interprets = 0
    for para in session.scalars(select(Paragraph)).all():
        case = para.judgment.case
        c = parse_citations(para.text)
        for n in c.neutral:
            target = resolve_neutral(session, n.raw)
            if target and target.id != case.id and not edge_exists(
                session, NodeType.case, case.id, NodeType.case, target.id, EdgeKind.CITES
            ):
                session.add(Edge(src_type=NodeType.case, src_id=case.id, dst_type=NodeType.case,
                                 dst_id=target.id, kind=EdgeKind.CITES, treatment=None,
                                 extraction=Extraction.parsed, confidence=1.0,
                                 source_url=case.source_url))
                cites += 1
        for s in c.sections:
            prov = resolve_section(session, s.section, s.act_hint)
            if prov and not edge_exists(
                session, NodeType.case, case.id, NodeType.provision, prov.id, EdgeKind.INTERPRETS
            ):
                session.add(Edge(src_type=NodeType.case, src_id=case.id,
                                 dst_type=NodeType.provision, dst_id=prov.id,
                                 kind=EdgeKind.INTERPRETS, extraction=Extraction.parsed,
                                 confidence=1.0, source_url=case.source_url))
                interprets += 1
        session.flush()
    return cites, interprets
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/ingestion/test_link.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: link case citations into CITES and INTERPRETS edges"
```

---

### Task 9: Curated head-of-power edges

**Files:**
- Create: `backend/src/graph/curated_edges.yaml`, `backend/src/graph/curated.py`, `backend/tests/graph/test_curated.py`

**Interfaces:**
- Consumes: `resolve_section`, `edge_exists`.
- Produces: `load_curated_edges(session: Session, path: Path | None = None) -> int` (edges added). Creates `AUTHORISED_BY` (act → Constitution provision) with `extraction=curated`, `confidence=1.0`, `source_url="curated:<note>"`. Acts not in the corpus are silently skipped; idempotent.

- [ ] **Step 1: Write the YAML**

`backend/src/graph/curated_edges.yaml`:
```yaml
authorised_by:
  - act: "Corporations Act"
    heads_of_power: ["51(xx)"]
    note: "Corporations power; NSW v Commonwealth (Work Choices) [2006] HCA 52"
  - act: "Fair Work Act"
    heads_of_power: ["51(xx)", "51(xxxv)"]
    note: "Corporations and conciliation/arbitration powers"
  - act: "Migration Act"
    heads_of_power: ["51(xix)", "51(xxvii)"]
    note: "Aliens and immigration powers"
  - act: "Income Tax Assessment Act"
    heads_of_power: ["51(ii)"]
    note: "Taxation power"
  - act: "Competition and Consumer Act"
    heads_of_power: ["51(xx)", "51(i)"]
    note: "Corporations and trade and commerce powers"
  - act: "Marriage Act"
    heads_of_power: ["51(xxi)"]
    note: "Marriage power"
  - act: "Native Title Act"
    heads_of_power: ["51(xxvi)"]
    note: "Race power; Western Australia v Commonwealth [1995] HCA 47"
```

- [ ] **Step 2: Write the failing test**

`backend/tests/graph/test_curated.py`:
```python
from pathlib import Path

from sqlalchemy import select

from src.graph.curated import load_curated_edges
from src.graph.models import Act, Edge, EdgeKind, Extraction, Jurisdiction
from src.graph.seed import seed_reference_data
from src.ingestion.sources.oalc import load_oalc

FIXTURE = Path(__file__).parent.parent / "fixtures" / "oalc_sample.jsonl"


def test_curated_edges_resolve_to_constitution_provisions(db_session):
    seed_reference_data(db_session)
    load_oalc(db_session, FIXTURE, sources={"federal_register_of_legislation"},
              jurisdictions={"commonwealth"})
    cth = db_session.scalar(select(Jurisdiction).where(Jurisdiction.code == "CTH"))
    db_session.add(Act(title="Corporations Act 2001", short_name="Corporations Act", year=2001,
                       jurisdiction_id=cth.id, extraction=Extraction.parsed))
    db_session.commit()

    n = load_curated_edges(db_session)
    db_session.commit()
    assert n == 1  # only the Corporations Act exists and s51(xx) is in the fixture
    e = db_session.scalar(select(Edge).where(Edge.kind == EdgeKind.AUTHORISED_BY))
    assert e.extraction == Extraction.curated
    assert load_curated_edges(db_session) == 0
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/graph/test_curated.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Write curated.py**

`backend/src/graph/curated.py`:
```python
from __future__ import annotations

from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.graph.models import Act, Edge, EdgeKind, Extraction, NodeType
from src.ingestion.link import edge_exists, resolve_section

DEFAULT_PATH = Path(__file__).parent / "curated_edges.yaml"


def load_curated_edges(session: Session, path: Path | None = None) -> int:
    data = yaml.safe_load((path or DEFAULT_PATH).read_text())
    added = 0
    for item in data.get("authorised_by", []):
        act = session.scalars(select(Act).where(Act.short_name.ilike(f"{item['act']}%"))).first()
        if act is None:
            continue
        for head in item["heads_of_power"]:
            prov = resolve_section(session, head, "Constitution")
            if prov is None or edge_exists(session, NodeType.act, act.id, NodeType.provision,
                                           prov.id, EdgeKind.AUTHORISED_BY):
                continue
            session.add(Edge(src_type=NodeType.act, src_id=act.id, dst_type=NodeType.provision,
                             dst_id=prov.id, kind=EdgeKind.AUTHORISED_BY,
                             extraction=Extraction.curated, confidence=1.0,
                             source_url=f"curated:{item.get('note', '')}"))
            added += 1
    session.flush()
    return added
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/graph/test_curated.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: curated AUTHORISED_BY head-of-power edges"
```

---

### Task 10: Embeddings and full-text search

**Files:**
- Create: `backend/src/ingestion/embed.py`, `backend/alembic/versions/0002_search.py`, `backend/tests/ingestion/test_embed.py`

**Interfaces:**
- Produces:
  ```python
  class Embedder(Protocol): dim: int; def embed(self, texts: list[str]) -> list[list[float]]
  class FakeEmbedder          # deterministic hash-based 384-dim unit vectors
  class SentenceTransformerEmbedder(model_name: str)
  def embed_pending(session: Session, embedder: Embedder, batch_size: int = 64) -> int   # rows embedded
  ```
- Migration 0002: trigger-maintained `tsv` on `provisions` and `paragraphs`; HNSW cosine indexes on both `embedding` columns.

- [ ] **Step 1: Write the migration**

`backend/alembic/versions/0002_search.py`:
```python
"""search columns

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION provisions_tsv_update() RETURNS trigger AS $$
        BEGIN
          NEW.tsv := to_tsvector('english', coalesce(NEW.heading, '') || ' ' || NEW.text);
          RETURN NEW;
        END $$ LANGUAGE plpgsql;
        CREATE TRIGGER provisions_tsv BEFORE INSERT OR UPDATE OF heading, text ON provisions
          FOR EACH ROW EXECUTE FUNCTION provisions_tsv_update();
        UPDATE provisions SET text = text;

        CREATE OR REPLACE FUNCTION paragraphs_tsv_update() RETURNS trigger AS $$
        BEGIN
          NEW.tsv := to_tsvector('english', NEW.text);
          RETURN NEW;
        END $$ LANGUAGE plpgsql;
        CREATE TRIGGER paragraphs_tsv BEFORE INSERT OR UPDATE OF text ON paragraphs
          FOR EACH ROW EXECUTE FUNCTION paragraphs_tsv_update();
        UPDATE paragraphs SET text = text;

        CREATE INDEX ix_provisions_embedding ON provisions USING hnsw (embedding vector_cosine_ops);
        CREATE INDEX ix_paragraphs_embedding ON paragraphs USING hnsw (embedding vector_cosine_ops);
    """)


def downgrade() -> None:
    op.execute("""
        DROP INDEX IF EXISTS ix_paragraphs_embedding;
        DROP INDEX IF EXISTS ix_provisions_embedding;
        DROP TRIGGER IF EXISTS paragraphs_tsv ON paragraphs;
        DROP FUNCTION IF EXISTS paragraphs_tsv_update;
        DROP TRIGGER IF EXISTS provisions_tsv ON provisions;
        DROP FUNCTION IF EXISTS provisions_tsv_update;
    """)
```

- [ ] **Step 2: Write the failing test**

`backend/tests/ingestion/test_embed.py`:
```python
from pathlib import Path

from sqlalchemy import func, select

from src.graph.models import Paragraph, Provision
from src.graph.seed import seed_reference_data
from src.ingestion.embed import FakeEmbedder, embed_pending
from src.ingestion.sources.oalc import load_oalc

FIXTURE = Path(__file__).parent.parent / "fixtures" / "oalc_sample.jsonl"


def test_fake_embedder_is_deterministic_unit_vectors():
    e = FakeEmbedder()
    a, b = e.embed(["hello", "hello"])
    assert a == b and len(a) == 384
    assert abs(sum(x * x for x in a) - 1.0) < 1e-6


def test_embed_pending_fills_all_rows_and_tsv_trigger_fires(db_session):
    seed_reference_data(db_session)
    load_oalc(db_session, FIXTURE,
              sources={"federal_register_of_legislation", "high_court_of_australia"},
              jurisdictions={"commonwealth"})
    db_session.commit()
    n = embed_pending(db_session, FakeEmbedder())
    db_session.commit()
    total = (db_session.scalar(select(func.count(Provision.id)))
             + db_session.scalar(select(func.count(Paragraph.id))))
    assert n == total
    assert db_session.scalar(
        select(func.count(Provision.id)).where(Provision.embedding.is_(None))) == 0
    assert embed_pending(db_session, FakeEmbedder()) == 0
    assert db_session.scalar(select(func.count(Provision.id)).where(Provision.tsv.is_(None))) == 0
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/ingestion/test_embed.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Write embed.py**

`backend/src/ingestion/embed.py`:
```python
from __future__ import annotations

import hashlib
import math
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.graph.models import EMBED_DIM, Paragraph, Provision


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FakeEmbedder:
    dim = EMBED_DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            h = hashlib.sha256(t.encode()).digest()
            vals = [((h[i % 32] + i * 31) % 251) / 251.0 - 0.5 for i in range(self.dim)]
            norm = math.sqrt(sum(v * v for v in vals))
            out.append([v / norm for v in vals])
        return out


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        self.dim = self._model.get_sentence_embedding_dimension()
        assert self.dim == EMBED_DIM, f"model dim {self.dim} != {EMBED_DIM}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, normalize_embeddings=True, batch_size=32).tolist()


def _embed_table(session: Session, model, embedder: Embedder, batch_size: int) -> int:
    done = 0
    while True:
        rows = session.scalars(
            select(model).where(model.embedding.is_(None)).limit(batch_size)).all()
        if not rows:
            return done
        texts = [(getattr(r, "heading", None) or "") + " " + r.text for r in rows]
        for row, vec in zip(rows, embedder.embed(texts)):
            row.embedding = vec
        session.flush()
        done += len(rows)


def embed_pending(session: Session, embedder: Embedder, batch_size: int = 64) -> int:
    return (_embed_table(session, Provision, embedder, batch_size)
            + _embed_table(session, Paragraph, embedder, batch_size))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/ingestion/test_embed.py -v`
Expected: 2 passed (conftest migrates to head, so 0002 is applied).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: embeddings, tsvector triggers and vector indexes"
```

---

### Task 11: Ingestion CLI

**Files:**
- Create: `backend/src/ingestion/run.py`

**Interfaces:**
- Consumes: `seed_reference_data`, `load_oalc`, `link_case_citations`, `load_curated_edges`, `embed_pending`, `SentenceTransformerEmbedder`.
- Produces: `uv run python -m src.ingestion.run --oalc PATH [--sources a,b] [--jurisdictions x,y] [--no-embed]`.

- [ ] **Step 1: Write run.py**

`backend/src/ingestion/run.py`:
```python
import argparse
from pathlib import Path

from src.config import get_settings
from src.db import SessionLocal, configure_sessions, get_engine
from src.graph.curated import load_curated_edges
from src.graph.seed import seed_reference_data
from src.ingestion.embed import SentenceTransformerEmbedder, embed_pending
from src.ingestion.link import link_case_citations
from src.ingestion.sources.oalc import load_oalc

HELP = """Ingest the Open Australian Legal Corpus.
Download first:
  uv run huggingface-cli download umarbutler/open-australian-legal-corpus corpus.jsonl \\
      --repo-type dataset --local-dir data/
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--oalc", type=Path, required=True)
    ap.add_argument("--sources", default="federal_register_of_legislation,high_court_of_australia")
    ap.add_argument("--jurisdictions", default="commonwealth")
    ap.add_argument("--no-embed", action="store_true")
    args = ap.parse_args()

    configure_sessions(get_engine())
    with SessionLocal() as session:
        seed_reference_data(session)
        session.commit()
        stats = load_oalc(session, args.oalc, sources=set(args.sources.split(",")),
                          jurisdictions=set(args.jurisdictions.split(",")))
        session.commit()
        print(f"loaded acts={stats.acts} cases={stats.cases} skipped={stats.skipped}")
        cites, interprets = link_case_citations(session)
        session.commit()
        print(f"edges cites={cites} interprets={interprets}")
        print(f"curated edges={load_curated_edges(session)}")
        session.commit()
        if not args.no_embed:
            n = embed_pending(session, SentenceTransformerEmbedder(get_settings().embed_model))
            session.commit()
            print(f"embedded rows={n}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke-run against the test fixture**

Run from `backend/`:
```bash
uv run alembic upgrade head
uv run python -m src.ingestion.run --oalc tests/fixtures/oalc_sample.jsonl --no-embed
```
Expected output:
```
loaded acts=1 cases=1 skipped=1
edges cites=0 interprets=1
curated edges=0
```
(Second run prints `acts=0 cases=0`, `cites=0 interprets=0`.)

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "feat: ingestion CLI"
```

---

### Task 12: Graph traversal queries

**Files:**
- Create: `backend/src/graph/traversal.py`, `backend/tests/graph/test_traversal.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True) class NodeRef: type: NodeType; id: int; label: str
  @dataclass class Neighbour: edge: Edge; node: NodeRef
  def node_ref(session, type: NodeType, id: int) -> NodeRef | None
  def neighbours(session, type, id, kinds: list[EdgeKind] | None = None, direction: str = "both") -> list[Neighbour]
  def authority_chain(session, type, id) -> list[NodeRef]
  ```
  Labels: act → `short_name`; provision → `"<act short_name> <identifier>"`; case → `"<name> <neutral_citation>"`; others → `name`.
  `authority_chain`: **case** → cases it CITES + provisions it INTERPRETS + those provisions' acts + those acts' AUTHORISED_BY provisions; **provision** → its act + the act's AUTHORISED_BY provisions + cases that INTERPRET it; **act** → AUTHORISED_BY provisions + cases interpreting any of its provisions. Deduped, discovery order.

- [ ] **Step 1: Write the failing test**

`backend/tests/graph/test_traversal.py`:
```python
from pathlib import Path

from sqlalchemy import select

from src.graph.models import Case, EdgeKind, NodeType, Provision
from src.graph.seed import seed_reference_data
from src.graph.traversal import authority_chain, neighbours, node_ref
from src.ingestion.link import link_case_citations
from src.ingestion.sources.oalc import load_oalc

FIXTURE = Path(__file__).parent.parent / "fixtures" / "oalc_sample.jsonl"


def _load(db_session):
    seed_reference_data(db_session)
    load_oalc(db_session, FIXTURE,
              sources={"federal_register_of_legislation", "high_court_of_australia"},
              jurisdictions={"commonwealth"})
    link_case_citations(db_session)
    db_session.commit()


def test_node_ref_labels(db_session):
    _load(db_session)
    s109 = db_session.scalar(select(Provision).where(Provision.identifier == "s109"))
    ref = node_ref(db_session, NodeType.provision, s109.id)
    assert ref.label == "Commonwealth of Australia Constitution Act s109"
    assert node_ref(db_session, NodeType.provision, 999999) is None


def test_neighbours_and_chain(db_session):
    _load(db_session)
    mabo = db_session.scalar(select(Case))
    out = neighbours(db_session, NodeType.case, mabo.id, kinds=[EdgeKind.INTERPRETS])
    assert [n.node.type for n in out] == [NodeType.provision]
    assert out[0].node.label.endswith("s109")

    chain = authority_chain(db_session, NodeType.case, mabo.id)
    types = [c.type for c in chain]
    assert NodeType.provision in types and NodeType.act in types

    s109 = db_session.scalar(select(Provision).where(Provision.identifier == "s109"))
    back = neighbours(db_session, NodeType.provision, s109.id, direction="in")
    assert back[0].node.label.startswith("Mabo")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/graph/test_traversal.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write traversal.py**

`backend/src/graph/traversal.py`:
```python
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from src.graph.models import (
    Act, Case, Court, Edge, EdgeKind, Jurisdiction, NodeType, Principle, Provision,
)

_MODEL = {
    NodeType.jurisdiction: Jurisdiction, NodeType.court: Court, NodeType.act: Act,
    NodeType.provision: Provision, NodeType.case: Case, NodeType.principle: Principle,
}


@dataclass(frozen=True)
class NodeRef:
    type: NodeType
    id: int
    label: str


@dataclass
class Neighbour:
    edge: Edge
    node: NodeRef


def _label(type: NodeType, row) -> str:
    if type == NodeType.act:
        return row.short_name
    if type == NodeType.provision:
        return f"{row.act_version.act.short_name} {row.identifier}"
    if type == NodeType.case:
        return f"{row.name} {row.neutral_citation}"
    return row.name


def node_ref(session: Session, type: NodeType, id: int) -> NodeRef | None:
    row = session.get(_MODEL[type], id)
    return NodeRef(type, id, _label(type, row)) if row else None


def neighbours(session: Session, type: NodeType, id: int,
               kinds: list[EdgeKind] | None = None, direction: str = "both") -> list[Neighbour]:
    conds = []
    if direction in ("out", "both"):
        conds.append((Edge.src_type == type) & (Edge.src_id == id))
    if direction in ("in", "both"):
        conds.append((Edge.dst_type == type) & (Edge.dst_id == id))
    q = select(Edge).where(or_(*conds))
    if kinds:
        q = q.where(Edge.kind.in_([k.value for k in kinds]))
    out = []
    for e in session.scalars(q.order_by(Edge.id)).all():
        if e.src_type == type and e.src_id == id:
            other = (NodeType(e.dst_type), e.dst_id)
        else:
            other = (NodeType(e.src_type), e.src_id)
        ref = node_ref(session, *other)
        if ref:
            out.append(Neighbour(e, ref))
    return out


def authority_chain(session: Session, type: NodeType, id: int) -> list[NodeRef]:
    seen: dict[tuple[NodeType, int], NodeRef] = {}

    def add(ref: NodeRef | None) -> None:
        if ref and (ref.type, ref.id) not in seen:
            seen[(ref.type, ref.id)] = ref

    def heads_of_power(act_id: int) -> None:
        for n in neighbours(session, NodeType.act, act_id, [EdgeKind.AUTHORISED_BY], "out"):
            add(n.node)

    def provision_context(prov_id: int) -> None:
        prov = session.get(Provision, prov_id)
        act_ref = node_ref(session, NodeType.act, prov.act_version.act_id)
        add(act_ref)
        if act_ref:
            heads_of_power(act_ref.id)

    if type == NodeType.case:
        for n in neighbours(session, type, id, [EdgeKind.CITES], "out"):
            add(n.node)
        for n in neighbours(session, type, id, [EdgeKind.INTERPRETS], "out"):
            add(n.node)
            provision_context(n.node.id)
    elif type == NodeType.provision:
        provision_context(id)
        for n in neighbours(session, type, id, [EdgeKind.INTERPRETS], "in"):
            add(n.node)
    elif type == NodeType.act:
        heads_of_power(id)
        for v in session.get(Act, id).versions:
            for p in v.provisions:
                for n in neighbours(session, NodeType.provision, p.id, [EdgeKind.INTERPRETS], "in"):
                    add(n.node)
    return list(seen.values())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/graph/test_traversal.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: graph neighbour and authority-chain traversal"
```

---

### Task 13: Hybrid retrieval

**Files:**
- Create: `backend/src/retrieval/__init__.py`, `backend/src/retrieval/hybrid.py`, `backend/tests/retrieval/__init__.py`, `backend/tests/retrieval/test_hybrid.py`

**Interfaces:**
- Consumes: `Embedder`, `neighbours`, `node_ref`.
- Produces:
  ```python
  @dataclass class Hit: type: NodeType; id: int; label: str; text: str; score: float; via: str   # "fts"|"vector"|"both"|"graph"
  def search(session, query: str, embedder: Embedder, *, k: int = 10, expand: bool = True) -> list[Hit]
  ```
  FTS top-`2k` (provisions ∪ paragraphs, `websearch_to_tsquery`, `ts_rank_cd`) and vector top-`2k` (cosine) fused by RRF (`1/(60+rank)`), top `k` kept. Paragraph hits are reported as their parent **case** (`type=case`, `id=case_id`, `text`=paragraph text). With `expand`, each provision hit adds cases that INTERPRET it (`via="graph"`, score × 0.5).

- [ ] **Step 1: Write the failing test**

`backend/tests/retrieval/__init__.py`: empty.

`backend/tests/retrieval/test_hybrid.py`:
```python
from pathlib import Path

from src.graph.models import NodeType
from src.graph.seed import seed_reference_data
from src.ingestion.embed import FakeEmbedder, embed_pending
from src.ingestion.link import link_case_citations
from src.ingestion.sources.oalc import load_oalc
from src.retrieval.hybrid import search

FIXTURE = Path(__file__).parent.parent / "fixtures" / "oalc_sample.jsonl"


def _load(db_session):
    seed_reference_data(db_session)
    load_oalc(db_session, FIXTURE,
              sources={"federal_register_of_legislation", "high_court_of_australia"},
              jurisdictions={"commonwealth"})
    link_case_citations(db_session)
    embed_pending(db_session, FakeEmbedder())
    db_session.commit()


def test_fts_finds_inconsistency_provision_and_expands_to_case(db_session):
    _load(db_session)
    hits = search(db_session, "inconsistency of laws State Commonwealth prevail",
                  FakeEmbedder(), k=5)
    assert hits[0].type == NodeType.provision and hits[0].label.endswith("s109")
    assert hits[0].via in ("fts", "both")
    graph_hits = [h for h in hits if h.via == "graph"]
    assert any(h.type == NodeType.case and h.label.startswith("Mabo") for h in graph_hits)


def test_no_expand_returns_only_direct_hits(db_session):
    _load(db_session)
    hits = search(db_session, "native title", FakeEmbedder(), k=5, expand=False)
    assert all(h.via != "graph" for h in hits)
    assert any(h.type == NodeType.case for h in hits)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/retrieval/test_hybrid.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write hybrid.py**

`backend/src/retrieval/__init__.py`: empty.

`backend/src/retrieval/hybrid.py`:
```python
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.graph.models import EdgeKind, NodeType
from src.graph.traversal import neighbours, node_ref
from src.ingestion.embed import Embedder

RRF_K = 60


@dataclass
class Hit:
    type: NodeType
    id: int
    label: str
    text: str
    score: float
    via: str


_FTS_SQL = text("""
    SELECT kind, row_id, txt, rank FROM (
      SELECT 'provision' AS kind, p.id AS row_id, p.text AS txt, ts_rank_cd(p.tsv, q) AS rank
      FROM provisions p, websearch_to_tsquery('english', :q) q WHERE p.tsv @@ q
      UNION ALL
      SELECT 'paragraph', pa.id, pa.text, ts_rank_cd(pa.tsv, q)
      FROM paragraphs pa, websearch_to_tsquery('english', :q) q WHERE pa.tsv @@ q
    ) s ORDER BY rank DESC LIMIT :n
""")

_VEC_SQL = text("""
    SELECT kind, row_id, txt, dist FROM (
      SELECT 'provision' AS kind, p.id AS row_id, p.text AS txt,
             p.embedding <=> CAST(:v AS vector) AS dist
      FROM provisions p WHERE p.embedding IS NOT NULL
      UNION ALL
      SELECT 'paragraph', pa.id, pa.text, pa.embedding <=> CAST(:v AS vector)
      FROM paragraphs pa WHERE pa.embedding IS NOT NULL
    ) s ORDER BY dist ASC LIMIT :n
""")

_PARA_CASE_SQL = text("""
    SELECT c.id FROM paragraphs pa JOIN judgments j ON pa.judgment_id = j.id
    JOIN cases c ON j.case_id = c.id WHERE pa.id = :pid
""")


def _to_node(session: Session, kind: str, row_id: int) -> tuple[NodeType, int]:
    if kind == "provision":
        return NodeType.provision, row_id
    return NodeType.case, session.execute(_PARA_CASE_SQL, {"pid": row_id}).scalar_one()


def search(session: Session, query: str, embedder: Embedder, *, k: int = 10,
           expand: bool = True) -> list[Hit]:
    n = k * 2
    fused: dict[tuple[str, int], dict] = {}

    def accumulate(rows, via: str) -> None:
        for rank, (kind, row_id, txt, _) in enumerate(rows):
            entry = fused.setdefault((kind, row_id), {"text": txt, "score": 0.0, "via": set()})
            entry["score"] += 1.0 / (RRF_K + rank + 1)
            entry["via"].add(via)

    accumulate(session.execute(_FTS_SQL, {"q": query, "n": n}).all(), "fts")
    vec = embedder.embed([query])[0]
    accumulate(session.execute(_VEC_SQL, {"v": str(vec), "n": n}).all(), "vector")

    ranked = sorted(fused.items(), key=lambda kv: kv[1]["score"], reverse=True)[:k]
    hits: list[Hit] = []
    seen: set[tuple[NodeType, int]] = set()
    for (kind, row_id), entry in ranked:
        ntype, nid = _to_node(session, kind, row_id)
        ref = node_ref(session, ntype, nid)
        if ref is None or (ntype, nid) in seen:
            continue
        via = "both" if len(entry["via"]) == 2 else next(iter(entry["via"]))
        hits.append(Hit(ntype, nid, ref.label, entry["text"], entry["score"], via))
        seen.add((ntype, nid))

    if expand:
        for h in list(hits):
            if h.type != NodeType.provision:
                continue
            for nb in neighbours(session, NodeType.provision, h.id, [EdgeKind.INTERPRETS], "in"):
                key = (nb.node.type, nb.node.id)
                if key not in seen:
                    seen.add(key)
                    hits.append(Hit(nb.node.type, nb.node.id, nb.node.label, nb.node.label,
                                    h.score * 0.5, "graph"))
    return hits
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/retrieval/test_hybrid.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: hybrid FTS + vector retrieval with RRF and graph expansion"
```

---

### Task 14: Citation verifier

**Files:**
- Create: `backend/src/reasoning/__init__.py`, `backend/src/reasoning/verifier.py`, `backend/tests/reasoning/__init__.py`, `backend/tests/reasoning/test_verifier.py`

**Interfaces:**
- Consumes: `parse_citations`, `resolve_neutral`, `resolve_section`, `node_ref`.
- Produces:
  ```python
  class CitationStatus(StrEnum): resolved; resolved_outside_context; unresolved
  @dataclass class VerifiedCitation: raw: str; status: CitationStatus; node: NodeRef | None
  @dataclass class Verification: citations: list[VerifiedCitation]; precision: float  # (resolved + outside_context) / total; 1.0 if none
  def verify(session, answer: str, context_nodes: set[tuple[NodeType, int]]) -> Verification
  ```
  Reported citations (CLR etc.) are always `unresolved` in Phase 1 — intentional; the prompt requires neutral citations.

- [ ] **Step 1: Write the failing test**

`backend/tests/reasoning/__init__.py`: empty.

`backend/tests/reasoning/test_verifier.py`:
```python
from pathlib import Path

from sqlalchemy import select

from src.graph.models import Case, NodeType, Provision
from src.graph.seed import seed_reference_data
from src.ingestion.sources.oalc import load_oalc
from src.reasoning.verifier import CitationStatus, verify

FIXTURE = Path(__file__).parent.parent / "fixtures" / "oalc_sample.jsonl"


def test_verify_classifies_three_ways(db_session):
    seed_reference_data(db_session)
    load_oalc(db_session, FIXTURE,
              sources={"federal_register_of_legislation", "high_court_of_australia"},
              jurisdictions={"commonwealth"})
    db_session.commit()
    mabo = db_session.scalar(select(Case))
    s109 = db_session.scalar(select(Provision).where(Provision.identifier == "s109"))

    answer = ("Mabo v Queensland (No 2) [1992] HCA 23 applied s 109 of the Constitution. "
              "Contrast [1988] HCA 69 and (1992) 175 CLR 1.")
    v = verify(db_session, answer, context_nodes={(NodeType.case, mabo.id)})
    by_raw = {c.raw: c for c in v.citations}
    assert by_raw["[1992] HCA 23"].status == CitationStatus.resolved
    assert by_raw["s 109 of the Constitution"].status == CitationStatus.resolved_outside_context
    assert by_raw["s 109 of the Constitution"].node.id == s109.id
    assert by_raw["[1988] HCA 69"].status == CitationStatus.unresolved
    assert by_raw["(1992) 175 CLR 1"].status == CitationStatus.unresolved
    assert v.precision == 0.5


def test_no_citations_is_precision_one(db_session):
    assert verify(db_session, "No citations here.", set()).precision == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/reasoning/test_verifier.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write verifier.py**

`backend/src/reasoning/__init__.py`: empty.

`backend/src/reasoning/verifier.py`:
```python
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.orm import Session

from src.graph.models import NodeType
from src.graph.traversal import NodeRef, node_ref
from src.ingestion.link import resolve_neutral, resolve_section
from src.ingestion.parsers.citation_parser import parse_citations


class CitationStatus(StrEnum):
    resolved = "resolved"
    resolved_outside_context = "resolved_outside_context"
    unresolved = "unresolved"


@dataclass
class VerifiedCitation:
    raw: str
    status: CitationStatus
    node: NodeRef | None


@dataclass
class Verification:
    citations: list[VerifiedCitation]
    precision: float


def _classify(ref: NodeRef | None, context: set[tuple[NodeType, int]]) -> CitationStatus:
    if ref is None:
        return CitationStatus.unresolved
    if (ref.type, ref.id) in context:
        return CitationStatus.resolved
    return CitationStatus.resolved_outside_context


def verify(session: Session, answer: str,
           context_nodes: set[tuple[NodeType, int]]) -> Verification:
    c = parse_citations(answer)
    out: list[VerifiedCitation] = []
    for n in c.neutral:
        case = resolve_neutral(session, n.raw)
        ref = node_ref(session, NodeType.case, case.id) if case else None
        out.append(VerifiedCitation(n.raw, _classify(ref, context_nodes), ref))
    for s in c.sections:
        prov = resolve_section(session, s.section, s.act_hint)
        ref = node_ref(session, NodeType.provision, prov.id) if prov else None
        out.append(VerifiedCitation(s.raw, _classify(ref, context_nodes), ref))
    for r in c.reported:
        out.append(VerifiedCitation(r.raw, CitationStatus.unresolved, None))
    ok = sum(1 for v in out if v.status != CitationStatus.unresolved)
    return Verification(out, ok / len(out) if out else 1.0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/reasoning/test_verifier.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: citation verifier with resolved/outside-context/unresolved statuses"
```

---

### Task 15: LLM client and Common-law framework

**Files:**
- Create: `backend/src/reasoning/llm/__init__.py`, `backend/src/reasoning/llm/client.py`, `backend/src/reasoning/frameworks/__init__.py`, `backend/src/reasoning/frameworks/base.py`, `backend/src/reasoning/frameworks/common_law.py`, `backend/tests/reasoning/test_common_law.py`

**Interfaces:**
- Produces:
  ```python
  class LLMClient(Protocol):
      def stream(self, messages: list[dict], *, temperature: float = 0.2) -> AsyncIterator[str]
  class LiteLLMClient(model: str, api_base: str)
  class FakeLLMClient(reply: str)     # yields reply in 3 chunks; records .last_messages
  class BaseFramework(ABC): name: str; def build_messages(self, question: str, context: list[Hit]) -> list[dict]
  class CommonLawFramework(BaseFramework)   # name = "common_law"
  ```
  System prompt must: state it is a research aid and **not legal advice**; require citing **only** CONTEXT materials, by neutral citation and `s N of the <Act>`; say "not in the provided materials" rather than invent; structure as Precedent → Distinguish → Apply. Context entries render as `### <label>\n<text truncated to 1500 chars>`.

- [ ] **Step 1: Write the failing test**

`backend/tests/reasoning/test_common_law.py`:
```python
from src.graph.models import NodeType
from src.reasoning.frameworks.common_law import CommonLawFramework
from src.reasoning.llm.client import FakeLLMClient
from src.retrieval.hybrid import Hit


def test_common_law_prompt_contains_constraints_and_context():
    fw = CommonLawFramework()
    hits = [Hit(NodeType.provision, 1, "Constitution s109", "When a law of a State…", 0.9, "fts"),
            Hit(NodeType.case, 2, "Mabo v Queensland (No 2) [1992] HCA 23", "x" * 2000, 0.5, "graph")]
    msgs = fw.build_messages("Does Commonwealth law prevail?", hits)
    assert msgs[0]["role"] == "system"
    sys_prompt = msgs[0]["content"]
    assert "not legal advice" in sys_prompt
    assert "ONLY" in sys_prompt and "CONTEXT" in sys_prompt
    assert "Precedent" in sys_prompt and "Distinguish" in sys_prompt and "Apply" in sys_prompt
    user = msgs[1]["content"]
    assert "### Constitution s109" in user
    assert "### Mabo v Queensland (No 2) [1992] HCA 23" in user
    assert len(user) < 4000  # truncation applied
    assert user.rstrip().endswith("Does Commonwealth law prevail?")


async def test_fake_llm_streams_and_records():
    llm = FakeLLMClient("alpha beta gamma")
    chunks = [c async for c in llm.stream([{"role": "user", "content": "hi"}])]
    assert "".join(chunks) == "alpha beta gamma"
    assert len(chunks) == 3
    assert llm.last_messages[0]["content"] == "hi"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/reasoning/test_common_law.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the LLM client**

`backend/src/reasoning/llm/__init__.py`: empty.

`backend/src/reasoning/llm/client.py`:
```python
from __future__ import annotations

from typing import AsyncIterator, Protocol


class LLMClient(Protocol):
    def stream(self, messages: list[dict], *, temperature: float = 0.2) -> AsyncIterator[str]: ...


class LiteLLMClient:
    def __init__(self, model: str, api_base: str):
        self.model = f"openai/{model}"
        self.api_base = api_base

    async def stream(self, messages: list[dict], *, temperature: float = 0.2) -> AsyncIterator[str]:
        from litellm import acompletion

        resp = await acompletion(model=self.model, api_base=self.api_base, api_key="local",
                                 messages=messages, temperature=temperature, stream=True)
        async for chunk in resp:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


class FakeLLMClient:
    def __init__(self, reply: str):
        self.reply = reply
        self.last_messages: list[dict] = []

    async def stream(self, messages: list[dict], *, temperature: float = 0.2) -> AsyncIterator[str]:
        self.last_messages = messages
        n = len(self.reply)
        for i in range(3):
            yield self.reply[i * n // 3:(i + 1) * n // 3]
```

- [ ] **Step 4: Write the frameworks**

`backend/src/reasoning/frameworks/__init__.py`: empty.

`backend/src/reasoning/frameworks/base.py`:
```python
from __future__ import annotations

from abc import ABC, abstractmethod

from src.retrieval.hybrid import Hit

MAX_CONTEXT_CHARS = 1500


class BaseFramework(ABC):
    name: str

    @abstractmethod
    def build_messages(self, question: str, context: list[Hit]) -> list[dict]: ...

    @staticmethod
    def render_context(context: list[Hit]) -> str:
        parts = []
        for h in context:
            body = h.text if len(h.text) <= MAX_CONTEXT_CHARS else h.text[:MAX_CONTEXT_CHARS] + "…"
            parts.append(f"### {h.label}\n{body}")
        return "\n\n".join(parts)
```

`backend/src/reasoning/frameworks/common_law.py`:
```python
from __future__ import annotations

from src.reasoning.frameworks.base import BaseFramework
from src.retrieval.hybrid import Hit

SYSTEM = """You are a legal research aid for Australian law. You are not a lawyer and your output is not legal advice.

Rules:
1. Cite ONLY materials that appear in the CONTEXT block. Do not rely on memory for authorities.
2. Cite cases by neutral citation exactly as given, e.g. [1992] HCA 23. Cite legislation as "s 109 of the Constitution" or "s 9 of the Corporations Act 2001".
3. If the provided materials do not support a point, say "not in the provided materials" instead of inventing authority.

Reason using the common-law method and structure your answer with these headings:
## Precedent — the authorities in the context and what they decided
## Distinguish — how the facts or provisions differ and whether each authority is binding or persuasive
## Apply — the conclusion the authorities support, and its limits
"""


class CommonLawFramework(BaseFramework):
    name = "common_law"

    def build_messages(self, question: str, context: list[Hit]) -> list[dict]:
        user = f"CONTEXT:\n\n{self.render_context(context)}\n\nQUESTION:\n{question}"
        return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/reasoning/test_common_law.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: LiteLLM streaming client and common-law reasoning framework"
```

---

### Task 16: Reverse Engineering mode

**Files:**
- Create: `backend/src/reasoning/modes/__init__.py`, `backend/src/reasoning/modes/base.py`, `backend/src/reasoning/modes/reverse_engineering.py`, `backend/tests/reasoning/test_reverse_engineering.py`

**Interfaces:**
- Consumes: `authority_chain`, `node_ref`, `search`, `BaseFramework`, `LLMClient`, `verify`.
- Produces:
  ```python
  @dataclass class ReasoningEvent: kind: str; payload: dict   # "context" | "token" | "verification" | "done"
  class BaseMode(ABC): name: str; def run(self, session, llm, framework, embedder, **inputs) -> AsyncIterator[ReasoningEvent]
  class ReverseEngineeringMode(BaseMode)   # name="reverse_engineering"; inputs node_type: NodeType, node_id: int; raises ValueError on unknown node
  ```
  Payloads: `context` → `{"nodes":[{"type","id","label","via"}]}`; `token` → `{"text"}`; `verification` → `{"precision", "citations":[{"raw","status","node":{"type","id","label"}|None}]}`; `done` → `{"answer"}`.

- [ ] **Step 1: Write the failing test**

`backend/tests/reasoning/test_reverse_engineering.py`:
```python
from pathlib import Path

from sqlalchemy import select

from src.graph.models import Case, NodeType
from src.graph.seed import seed_reference_data
from src.ingestion.embed import FakeEmbedder, embed_pending
from src.ingestion.link import link_case_citations
from src.ingestion.sources.oalc import load_oalc
from src.reasoning.frameworks.common_law import CommonLawFramework
from src.reasoning.llm.client import FakeLLMClient
from src.reasoning.modes.reverse_engineering import ReverseEngineeringMode

FIXTURE = Path(__file__).parent.parent / "fixtures" / "oalc_sample.jsonl"


async def test_reverse_engineering_emits_context_tokens_verification_done(db_session):
    seed_reference_data(db_session)
    load_oalc(db_session, FIXTURE,
              sources={"federal_register_of_legislation", "high_court_of_australia"},
              jurisdictions={"commonwealth"})
    link_case_citations(db_session)
    embed_pending(db_session, FakeEmbedder())
    db_session.commit()
    mabo = db_session.scalar(select(Case))

    llm = FakeLLMClient(
        "## Precedent\n[1992] HCA 23 applied s 109 of the Constitution. See also [1950] HCA 99.")
    events = [e async for e in ReverseEngineeringMode().run(
        db_session, llm, CommonLawFramework(), FakeEmbedder(),
        node_type=NodeType.case, node_id=mabo.id)]

    kinds = [e.kind for e in events]
    assert kinds[0] == "context" and kinds[-2] == "verification" and kinds[-1] == "done"
    assert kinds.count("token") == 3
    labels = [n["label"] for n in events[0].payload["nodes"]]
    assert any(lbl.endswith("s109") for lbl in labels)
    ver = events[-2].payload
    statuses = {c["raw"]: c["status"] for c in ver["citations"]}
    assert statuses["[1992] HCA 23"] == "resolved"
    assert statuses["s 109 of the Constitution"] == "resolved"
    assert statuses["[1950] HCA 99"] == "unresolved"
    assert abs(ver["precision"] - 2 / 3) < 1e-9
    assert "Mabo" in llm.last_messages[1]["content"]
    assert events[-1].payload["answer"].startswith("## Precedent")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/reasoning/test_reverse_engineering.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the mode**

`backend/src/reasoning/modes/__init__.py`: empty.

`backend/src/reasoning/modes/base.py`:
```python
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator

from sqlalchemy.orm import Session

from src.ingestion.embed import Embedder
from src.reasoning.frameworks.base import BaseFramework
from src.reasoning.llm.client import LLMClient


@dataclass
class ReasoningEvent:
    kind: str
    payload: dict


class BaseMode(ABC):
    name: str

    @abstractmethod
    def run(self, session: Session, llm: LLMClient, framework: BaseFramework,
            embedder: Embedder, **inputs) -> AsyncIterator[ReasoningEvent]: ...
```

`backend/src/reasoning/modes/reverse_engineering.py`:
```python
from __future__ import annotations

from typing import AsyncIterator

from sqlalchemy.orm import Session

from src.graph.models import Case, NodeType, Provision
from src.graph.traversal import NodeRef, authority_chain, node_ref
from src.ingestion.embed import Embedder
from src.reasoning.frameworks.base import BaseFramework
from src.reasoning.llm.client import LLMClient
from src.reasoning.modes.base import BaseMode, ReasoningEvent
from src.reasoning.verifier import verify
from src.retrieval.hybrid import Hit, search


def _node_text(session: Session, ref: NodeRef) -> str:
    if ref.type == NodeType.provision:
        p = session.get(Provision, ref.id)
        return f"{p.heading or ''}\n{p.text}".strip()
    if ref.type == NodeType.case:
        c = session.get(Case, ref.id)
        if c.summary:
            return c.summary
        paras = sorted(c.judgments[0].paragraphs, key=lambda x: x.number)[:3] if c.judgments else []
        return "\n".join(p.text for p in paras) or c.name
    return ref.label


def _ref_to_hit(session: Session, ref: NodeRef, via: str) -> Hit:
    return Hit(ref.type, ref.id, ref.label, _node_text(session, ref), 1.0, via)


class ReverseEngineeringMode(BaseMode):
    name = "reverse_engineering"

    async def run(self, session: Session, llm: LLMClient, framework: BaseFramework,
                  embedder: Embedder, **inputs) -> AsyncIterator[ReasoningEvent]:
        node_type: NodeType = inputs["node_type"]
        node_id: int = inputs["node_id"]
        root = node_ref(session, node_type, node_id)
        if root is None:
            raise ValueError(f"no such node {node_type}:{node_id}")

        hits: list[Hit] = [_ref_to_hit(session, root, "root")]
        seen = {(root.type, root.id)}
        for ref in authority_chain(session, node_type, node_id):
            if (ref.type, ref.id) not in seen:
                seen.add((ref.type, ref.id))
                hits.append(_ref_to_hit(session, ref, "graph"))
        for h in search(session, root.label, embedder, k=5, expand=False):
            if (h.type, h.id) not in seen:
                seen.add((h.type, h.id))
                hits.append(h)

        yield ReasoningEvent("context", {"nodes": [
            {"type": h.type.value, "id": h.id, "label": h.label, "via": h.via} for h in hits]})

        question = (f"Explain the chain of authority behind {root.label}: which constitutional "
                    f"head of power or provision authorises it, which cases interpret it, and "
                    f"what principles they establish.")
        messages = framework.build_messages(question, hits)
        parts: list[str] = []
        async for tok in llm.stream(messages):
            parts.append(tok)
            yield ReasoningEvent("token", {"text": tok})
        answer = "".join(parts)

        v = verify(session, answer, seen)
        yield ReasoningEvent("verification", {
            "precision": v.precision,
            "citations": [{
                "raw": c.raw, "status": c.status.value,
                "node": ({"type": c.node.type.value, "id": c.node.id, "label": c.node.label}
                         if c.node else None),
            } for c in v.citations],
        })
        yield ReasoningEvent("done", {"answer": answer})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/reasoning/test_reverse_engineering.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: reverse engineering reasoning mode"
```

---

### Task 17: API — nodes and tree

**Files:**
- Create: `backend/src/api/__init__.py`, `backend/src/api/deps.py`, `backend/src/api/nodes.py`, `backend/src/api/tree.py`, `backend/tests/api/__init__.py`, `backend/tests/api/test_nodes.py`, `backend/tests/api/test_tree.py`
- Modify: `backend/src/main.py`

**Interfaces:**
- `deps.get_db()` yields a Session; `deps.get_embedder()` (lru_cached; `FakeEmbedder` when env `EMBEDDER=fake`); `deps.get_llm()` (`FakeLLMClient(reply)` when env `LLM=fake:<reply>`, else `LiteLLMClient` from settings).
- `GET /nodes/{type}/{id}` → `{"type","id","label","text","neighbours":[{"kind","direction","treatment","extraction","confidence","node":{"type","id","label"}}]}`; 404 unknown id; 422 bad type.
- `GET /tree?root=constitution|act:<id>` → `{"node":{...},"children":[{"node":{...},"children":[{"node":{...},"children":[]}]}]}`: act → top-level provisions of the latest version (excluding `preamble`) → cases that INTERPRET each. 404 unknown root.

- [ ] **Step 1: Write the failing tests**

`backend/tests/api/__init__.py`: empty.

`backend/tests/api/test_nodes.py`:
```python
from pathlib import Path

from sqlalchemy import select

from src.graph.models import Case
from src.graph.seed import seed_reference_data
from src.ingestion.link import link_case_citations
from src.ingestion.sources.oalc import load_oalc

FIXTURE = Path(__file__).parent.parent / "fixtures" / "oalc_sample.jsonl"


def _load(db_session):
    seed_reference_data(db_session)
    load_oalc(db_session, FIXTURE,
              sources={"federal_register_of_legislation", "high_court_of_australia"},
              jurisdictions={"commonwealth"})
    link_case_citations(db_session)
    db_session.commit()


def test_get_case_node_with_neighbours(client, db_session):
    _load(db_session)
    mabo = db_session.scalar(select(Case))
    r = client.get(f"/nodes/case/{mabo.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["label"].startswith("Mabo")
    assert {"DECIDED_BY", "INTERPRETS"} <= {n["kind"] for n in body["neighbours"]}


def test_unknown_node(client, db_session):
    assert client.get("/nodes/case/999999").status_code == 404
    assert client.get("/nodes/bogus/1").status_code == 422
```

`backend/tests/api/test_tree.py`:
```python
from pathlib import Path

from src.graph.seed import seed_reference_data
from src.ingestion.link import link_case_citations
from src.ingestion.sources.oalc import load_oalc

FIXTURE = Path(__file__).parent.parent / "fixtures" / "oalc_sample.jsonl"


def test_tree_from_constitution(client, db_session):
    seed_reference_data(db_session)
    load_oalc(db_session, FIXTURE,
              sources={"federal_register_of_legislation", "high_court_of_australia"},
              jurisdictions={"commonwealth"})
    link_case_citations(db_session)
    db_session.commit()

    r = client.get("/tree", params={"root": "constitution"})
    assert r.status_code == 200
    tree = r.json()
    assert tree["node"]["type"] == "act"
    labels = [c["node"]["label"] for c in tree["children"]]
    assert any(lbl.endswith("s109") for lbl in labels)
    assert not any(lbl.endswith("s51(xx)") for lbl in labels)  # subsections excluded
    assert not any(lbl.endswith("preamble") for lbl in labels)
    s109 = next(c for c in tree["children"] if c["node"]["label"].endswith("s109"))
    assert s109["children"][0]["node"]["label"].startswith("Mabo")


def test_tree_bad_root(client, db_session):
    assert client.get("/tree", params={"root": "act:999999"}).status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/api -v`
Expected: FAIL (404 on every route; `/nodes/bogus/1` gives 404 not 422).

- [ ] **Step 3: Write deps.py**

`backend/src/api/__init__.py`: empty.

`backend/src/api/deps.py`:
```python
import os
from functools import lru_cache

from src.config import get_settings
from src.db import SessionLocal
from src.ingestion.embed import Embedder, FakeEmbedder, SentenceTransformerEmbedder
from src.reasoning.llm.client import FakeLLMClient, LiteLLMClient, LLMClient


def get_db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@lru_cache
def get_embedder() -> Embedder:
    if os.environ.get("EMBEDDER") == "fake":
        return FakeEmbedder()
    return SentenceTransformerEmbedder(get_settings().embed_model)


def get_llm() -> LLMClient:
    spec = os.environ.get("LLM", "")
    if spec.startswith("fake:"):
        return FakeLLMClient(spec[5:])
    s = get_settings()
    return LiteLLMClient(s.llm_model, s.llm_api_base)
```

- [ ] **Step 4: Write nodes.py**

`backend/src/api/nodes.py`:
```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.graph.models import Case, NodeType, Provision
from src.graph.traversal import neighbours, node_ref

router = APIRouter(prefix="/nodes", tags=["nodes"])


def _text(session: Session, type: NodeType, id: int) -> str:
    if type == NodeType.provision:
        return session.get(Provision, id).text
    if type == NodeType.case:
        return session.get(Case, id).summary or ""
    return ""


@router.get("/{type}/{id}")
def get_node(type: NodeType, id: int, session: Session = Depends(get_db)) -> dict:
    ref = node_ref(session, type, id)
    if ref is None:
        raise HTTPException(404, "node not found")
    out = []
    for n in neighbours(session, type, id):
        direction = "out" if (n.edge.src_type == type and n.edge.src_id == id) else "in"
        out.append({
            "kind": n.edge.kind, "direction": direction, "treatment": n.edge.treatment,
            "extraction": n.edge.extraction, "confidence": n.edge.confidence,
            "node": {"type": n.node.type.value, "id": n.node.id, "label": n.node.label},
        })
    return {"type": ref.type.value, "id": ref.id, "label": ref.label,
            "text": _text(session, type, id), "neighbours": out}
```

- [ ] **Step 5: Write tree.py**

`backend/src/api/tree.py`:
```python
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.graph.models import Act, ActVersion, EdgeKind, NodeType, Provision
from src.graph.traversal import NodeRef, neighbours, node_ref

router = APIRouter(tags=["tree"])


def _ref_dict(ref: NodeRef) -> dict:
    return {"type": ref.type.value, "id": ref.id, "label": ref.label}


def _resolve_root(session: Session, root: str) -> Act | None:
    if root == "constitution":
        return session.scalars(select(Act).where(Act.title.ilike("%Constitution Act%"))).first()
    if root.startswith("act:") and root[4:].isdigit():
        return session.get(Act, int(root[4:]))
    return None


@router.get("/tree")
def get_tree(root: str = Query(...), session: Session = Depends(get_db)) -> dict:
    act = _resolve_root(session, root)
    if act is None:
        raise HTTPException(404, "root not found")
    latest = session.scalars(
        select(ActVersion).where(ActVersion.act_id == act.id)
        .order_by(ActVersion.in_force_from.desc().nulls_last())
    ).first()
    provisions = session.scalars(
        select(Provision).where(Provision.act_version_id == latest.id,
                                Provision.parent_provision_id.is_(None),
                                Provision.identifier != "preamble")
        .order_by(Provision.id)
    ).all() if latest else []
    children = []
    for p in provisions:
        cases = [{"node": _ref_dict(n.node), "children": []}
                 for n in neighbours(session, NodeType.provision, p.id, [EdgeKind.INTERPRETS], "in")]
        children.append({"node": _ref_dict(node_ref(session, NodeType.provision, p.id)),
                         "children": cases})
    return {"node": _ref_dict(node_ref(session, NodeType.act, act.id)), "children": children}
```

- [ ] **Step 6: Register routers in main.py**

Replace `backend/src/main.py` with:
```python
from fastapi import FastAPI

from src.api import nodes, tree
from src.db import configure_sessions, get_engine


def create_app() -> FastAPI:
    app = FastAPI(title="Legal Beagle API")
    configure_sessions(get_engine())
    app.include_router(nodes.router)
    app.include_router(tree.router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/api -v`
Expected: 4 passed.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat: nodes and tree API endpoints"
```

---

### Task 18: API — reasoning endpoint (SSE)

**Files:**
- Create: `backend/src/api/reason.py`, `backend/tests/api/test_reason.py`
- Modify: `backend/src/main.py` (register router), `backend/tests/conftest.py` (`client` fixture sets `EMBEDDER=fake` and an `LLM=fake:` reply)

**Interfaces:**
- `POST /reason/reverse` body `{"node_type": "case"|"provision"|"act", "node_id": int, "framework": "common_law"}` → `text/event-stream`; each SSE event has `event: <kind>` and `data: <json payload>` exactly as produced by `ReasoningEvent`. 404 unknown node; 422 unknown framework.
- `GET /reason/frameworks` → `["common_law"]`.
- Produces `FRAMEWORKS: dict[str, type[BaseFramework]]` in `reason.py`.

- [ ] **Step 1: Update the conftest client fixture**

In `backend/tests/conftest.py` replace the `client` fixture with:
```python
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
```

- [ ] **Step 2: Write the failing test**

`backend/tests/api/test_reason.py`:
```python
import json
from pathlib import Path

from sqlalchemy import select

from src.graph.models import Case
from src.graph.seed import seed_reference_data
from src.ingestion.embed import FakeEmbedder, embed_pending
from src.ingestion.link import link_case_citations
from src.ingestion.sources.oalc import load_oalc

FIXTURE = Path(__file__).parent.parent / "fixtures" / "oalc_sample.jsonl"


def _parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        kind, data = None, None
        for line in block.splitlines():
            if line.startswith("event:"):
                kind = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:].strip())
        if kind:
            events.append((kind, data))
    return events


def test_frameworks_list(client):
    assert client.get("/reason/frameworks").json() == ["common_law"]


def test_reverse_stream(client, db_session):
    seed_reference_data(db_session)
    load_oalc(db_session, FIXTURE,
              sources={"federal_register_of_legislation", "high_court_of_australia"},
              jurisdictions={"commonwealth"})
    link_case_citations(db_session)
    embed_pending(db_session, FakeEmbedder())
    db_session.commit()
    mabo = db_session.scalar(select(Case))

    with client.stream("POST", "/reason/reverse",
                       json={"node_type": "case", "node_id": mabo.id,
                             "framework": "common_law"}) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        body = "".join(r.iter_text())
    events = _parse_sse(body)
    kinds = [k for k, _ in events]
    assert kinds[0] == "context" and kinds[-2] == "verification" and kinds[-1] == "done"
    assert abs(events[-2][1]["precision"] - 2 / 3) < 1e-9


def test_reverse_unknown_node(client, db_session):
    r = client.post("/reason/reverse",
                    json={"node_type": "case", "node_id": 999999, "framework": "common_law"})
    assert r.status_code == 404


def test_reverse_unknown_framework(client, db_session):
    r = client.post("/reason/reverse",
                    json={"node_type": "case", "node_id": 1, "framework": "nope"})
    assert r.status_code == 422
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/api/test_reason.py -v`
Expected: FAIL with 404 on `/reason/frameworks`.

- [ ] **Step 4: Write reason.py**

`backend/src/api/reason.py`:
```python
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from src.api.deps import get_db, get_embedder, get_llm
from src.graph.models import NodeType
from src.graph.traversal import node_ref
from src.reasoning.frameworks.base import BaseFramework
from src.reasoning.frameworks.common_law import CommonLawFramework
from src.reasoning.modes.reverse_engineering import ReverseEngineeringMode

router = APIRouter(prefix="/reason", tags=["reason"])

FRAMEWORKS: dict[str, type[BaseFramework]] = {CommonLawFramework.name: CommonLawFramework}


class ReverseRequest(BaseModel):
    node_type: NodeType
    node_id: int
    framework: str = "common_law"


@router.get("/frameworks")
def list_frameworks() -> list[str]:
    return list(FRAMEWORKS)


@router.post("/reverse")
async def reverse(req: ReverseRequest, session: Session = Depends(get_db)):
    if req.framework not in FRAMEWORKS:
        raise HTTPException(422, f"unknown framework {req.framework}")
    if node_ref(session, req.node_type, req.node_id) is None:
        raise HTTPException(404, "node not found")
    mode = ReverseEngineeringMode()
    llm, embedder, framework = get_llm(), get_embedder(), FRAMEWORKS[req.framework]()

    async def gen():
        async for ev in mode.run(session, llm, framework, embedder,
                                 node_type=req.node_type, node_id=req.node_id):
            yield {"event": ev.kind, "data": json.dumps(ev.payload)}

    return EventSourceResponse(gen())
```

In `backend/src/main.py`: change the import to `from src.api import nodes, reason, tree` and add `app.include_router(reason.router)` after the tree router.

- [ ] **Step 5: Run the full suite**

Run: `cd backend && uv run pytest -v`
Expected: all tests pass (the conftest change must not break earlier suites).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: SSE reasoning endpoint for reverse engineering mode"
```

---

### Task 19: Evaluation harness, gold set, CI

**Files:**
- Create: `eval/__init__.py`, `eval/gold/hca.yaml`, `eval/score.py`, `eval/__main__.py`, `.github/workflows/ci.yml`

**Interfaces:**
- Gold YAML: `cases: [{neutral_citation, key_authorities: [neutral citations], key_provisions: [section raw strings like "s 109 of the Constitution"]}]`.
- `eval.score.load_gold(path) -> list[dict]`; `eval.score.score_case(session, llm, embedder, gold: dict) -> dict | None` → `{"neutral_citation","precision","recall","answer"}`; `None` if the case is not in the DB. `recall` = |expected ∩ resolved citation raws| / |expected| (1.0 if nothing expected).
- `python -m eval [--gold PATH]` prints per-case rows and means; exit 1 if mean precision < 0.95 and ≥1 case scored.

- [ ] **Step 1: Write the seed gold set**

`eval/gold/hca.yaml`:
```yaml
cases:
  - neutral_citation: "[1992] HCA 23"   # Mabo v Queensland (No 2)
    key_authorities: []
    key_provisions: []
  - neutral_citation: "[2006] HCA 52"   # NSW v Commonwealth (Work Choices)
    key_authorities: ["[1971] HCA 16"]   # Strickland v Rocla Concrete Pipes
    key_provisions: ["s 51(xx) of the Constitution"]
  - neutral_citation: "[1983] HCA 21"   # Commonwealth v Tasmania (Tasmanian Dam)
    key_authorities: ["[1982] HCA 27"]   # Koowarta v Bjelke-Petersen
    key_provisions: ["s 51(xxix) of the Constitution"]
  - neutral_citation: "[1988] HCA 18"   # Cole v Whitfield
    key_authorities: []
    key_provisions: ["s 92 of the Constitution"]
  - neutral_citation: "[1920] HCA 54"   # Engineers' Case
    key_authorities: []
    key_provisions: ["s 51(xxxv) of the Constitution"]
```

- [ ] **Step 2: Write score.py and __main__.py**

`eval/__init__.py`: empty.

`eval/score.py`:
```python
from __future__ import annotations

import asyncio
from pathlib import Path

import yaml
from sqlalchemy.orm import Session

from src.graph.models import NodeType
from src.ingestion.embed import Embedder
from src.ingestion.link import resolve_neutral
from src.reasoning.frameworks.common_law import CommonLawFramework
from src.reasoning.llm.client import LLMClient
from src.reasoning.modes.reverse_engineering import ReverseEngineeringMode


def load_gold(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text())["cases"]


async def _run(session: Session, llm: LLMClient, embedder: Embedder, case_id: int):
    answer, verification = "", {}
    async for ev in ReverseEngineeringMode().run(session, llm, CommonLawFramework(), embedder,
                                                 node_type=NodeType.case, node_id=case_id):
        if ev.kind == "verification":
            verification = ev.payload
        elif ev.kind == "done":
            answer = ev.payload["answer"]
    return answer, verification


def score_case(session: Session, llm: LLMClient, embedder: Embedder, gold: dict) -> dict | None:
    case = resolve_neutral(session, gold["neutral_citation"])
    if case is None:
        return None
    answer, ver = asyncio.run(_run(session, llm, embedder, case.id))
    resolved = {c["raw"] for c in ver["citations"] if c["status"] != "unresolved"}
    expected = set(gold.get("key_authorities", [])) | set(gold.get("key_provisions", []))
    recall = len(expected & resolved) / len(expected) if expected else 1.0
    return {"neutral_citation": gold["neutral_citation"], "precision": ver["precision"],
            "recall": recall, "answer": answer}
```

`eval/__main__.py`:
```python
import argparse
import sys
from pathlib import Path

from eval.score import load_gold, score_case
from src.api.deps import get_embedder, get_llm
from src.db import SessionLocal, configure_sessions, get_engine


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", type=Path, default=Path(__file__).parent / "gold" / "hca.yaml")
    args = ap.parse_args()
    configure_sessions(get_engine())
    rows = []
    with SessionLocal() as session:
        for g in load_gold(args.gold):
            r = score_case(session, get_llm(), get_embedder(), g)
            if r is None:
                print(f"SKIP {g['neutral_citation']} (not in corpus)")
            else:
                rows.append(r)
                print(f"{r['neutral_citation']:<18} precision={r['precision']:.2f} "
                      f"recall={r['recall']:.2f}")
    if not rows:
        print("no cases scored")
        return
    mp = sum(r["precision"] for r in rows) / len(rows)
    mr = sum(r["recall"] for r in rows) / len(rows)
    print(f"\nmean precision={mp:.3f} mean recall={mr:.3f} (n={len(rows)})")
    sys.exit(0 if mp >= 0.95 else 1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Smoke-run the eval on the fixture corpus with the fake LLM**

Run from `backend/` (`eval/` lives at the repo root, so add it to the path):
```bash
uv run alembic upgrade head
uv run python -m src.ingestion.run --oalc tests/fixtures/oalc_sample.jsonl --no-embed
EMBEDDER=fake LLM="fake:[1992] HCA 23 applied s 109 of the Constitution." \
  PYTHONPATH=.:.. uv run python -m eval
```
Expected: `[1992] HCA 23      precision=1.00 recall=1.00`, four `SKIP` lines, `mean precision=1.000`, exit code 0.

- [ ] **Step 4: Write the CI workflow**

`.github/workflows/ci.yml`:
```yaml
name: ci
on: [push, pull_request]
jobs:
  backend:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env: { POSTGRES_USER: legal, POSTGRES_PASSWORD: legal, POSTGRES_DB: legal_test }
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U legal" --health-interval 5s --health-retries 10
    env:
      TEST_DATABASE_URL: postgresql+psycopg://legal:legal@localhost:5432/legal_test
      DATABASE_URL: postgresql+psycopg://legal:legal@localhost:5432/legal_test
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync
      - run: uv run ruff check .
      - run: uv run pytest -q
      - name: eval smoke (fixture corpus, fake LLM)
        env:
          EMBEDDER: fake
          LLM: "fake:[1992] HCA 23 applied s 109 of the Constitution."
          PYTHONPATH: ".:.."
        run: |
          uv run alembic upgrade head
          uv run python -m src.ingestion.run --oalc tests/fixtures/oalc_sample.jsonl --no-embed
          uv run python -m eval
```

- [ ] **Step 5: Run the full suite and lint locally**

Run: `cd backend && uv run ruff check . && uv run pytest -q`
Expected: ruff clean, all tests pass.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: evaluation harness with HCA gold set and CI workflow"
```

---

### Task 20: Real-corpus ingestion baseline and gold-set expansion

**Files:**
- Modify: `eval/gold/hca.yaml`
- Create: `docs/runbooks/ingest.md`

This task proves the pipeline on real data and records what was observed. It needs the local LLM at `localhost:7080` running.

- [ ] **Step 1: Download and ingest the real corpus**

Run from `backend/`:
```bash
mkdir -p data
uv run huggingface-cli download umarbutler/open-australian-legal-corpus corpus.jsonl \
    --repo-type dataset --local-dir data/
uv run alembic upgrade head
uv run python -m src.ingestion.run --oalc data/corpus.jsonl --no-embed
uv run python -m src.ingestion.run --oalc data/corpus.jsonl
```
Expected: the first run prints non-zero `acts`, `cases`, `interprets` and `curated edges >= 5`; the second prints `acts=0 cases=0` and then `embedded rows=<n>`. Embedding on CPU is slow (hours); it is resumable, so interrupting and re-running is safe. Record all printed numbers.

If the real OALC record schema differs from the fixture (key names or `type`/`source` values), fix `oalc.py` to match and update `tests/fixtures/oalc_sample.jsonl` to the real shape — the fixture must mirror reality.

- [ ] **Step 2: Run the eval with the real LLM**

Run: `cd backend && PYTHONPATH=.:.. uv run python -m eval`
Expected: five scored lines (no SKIPs) and a mean precision/recall. Do **not** tune prompts to hit 0.95 in this task — record the baseline.

- [ ] **Step 3: Expand the gold set to 20 cases**

Candidates to add (confirm each exists before adding; drop any that don't): `[1997] HCA 25` Lange, `[1992] HCA 45` ACTV, `[1948] HCA 7` Bank Nationalisation, `[1951] HCA 5` Communist Party Case, `[1995] HCA 47` Native Title Act Case, `[1996] HCA 40` Wik, `[2009] HCA 23` Pape, `[2012] HCA 23` Williams, `[1999] HCA 30` Sue v Hill, `[2004] HCA 37` Al-Kateb, `[1994] HCA 46` Theophanous, `[1989] HCA 34` Street, `[1971] HCA 16` Strickland, `[1982] HCA 27` Koowarta, `[1936] HCA 52` Dixon in Dignan (verify).

Check existence:
```bash
docker compose exec postgres psql -U legal -d legal -c \
  "SELECT neutral_citation, left(name, 60) FROM cases WHERE neutral_citation IN ('[1997] HCA 25','[1992] HCA 45','[1948] HCA 7','[1951] HCA 5','[1995] HCA 47','[1996] HCA 40','[2009] HCA 23','[2012] HCA 23','[1999] HCA 30','[2004] HCA 37','[1994] HCA 46','[1989] HCA 34','[1971] HCA 16','[1982] HCA 27','[1936] HCA 52');"
```
For each confirmed case add an entry with at least one `key_provisions` value (the constitutional provision the case is known for).

- [ ] **Step 4: Write the runbook**

`docs/runbooks/ingest.md`:
```markdown
# Ingestion runbook

1. `docker compose up -d postgres`
2. `cd backend && uv sync && uv run alembic upgrade head`
3. Download the corpus (several GB):
   `uv run huggingface-cli download umarbutler/open-australian-legal-corpus corpus.jsonl --repo-type dataset --local-dir data/`
4. `uv run python -m src.ingestion.run --oalc data/corpus.jsonl --no-embed`
   Loads Cth Acts + HCA cases, links citations, adds curated edges.
5. `uv run python -m src.ingestion.run --oalc data/corpus.jsonl`
   Re-run to embed (resumable; the reload is a no-op).
6. `PYTHONPATH=.:.. uv run python -m eval` — baseline scorecard (needs the LLM at :7080).

## Observed baseline (YYYY-MM-DD)

acts=<n> cases=<n> skipped=<n> cites=<n> interprets=<n> curated=<n> embedded=<n>
mean precision=<x> mean recall=<y> (n=<cases scored>)
```
Fill in the numbers from Steps 1–2.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: real-corpus ingestion baseline, expanded gold set, ingest runbook"
```

---

## Self-Review

**Spec coverage (Phase 1 backend):**
- Bounded corpus, batch ingestion (§1, §3) → Tasks 7, 11, 20. Live FRL OData + hcourt clients deferred to Phase 2 (stated deviation).
- Postgres + pgvector single DB (§1) → Tasks 1, 2, 10.
- Data model with `Provision`, `ActVersion`, `Court` hierarchy, `Paragraph`, generic provenance-carrying edges (§2) → Tasks 2, 3. `Bill` is Phase 3; `Principle` table exists but extraction is Phase 2.
- s.109 as judicial finding (`HELD_INCONSISTENT`) → kind defined in Task 2; populated by Phase 2 extraction.
- Retrieval: FTS + vector + 1-hop expansion (§4) → Task 13.
- Citation Verifier, three states (§4) → Task 14; surfaced over SSE in Task 18.
- LiteLLM `acompletion`, `openai/` prefix, streaming (§5) → Task 15.
- Modes vs frameworks; Reverse Engineering + Common-law (§5) → Tasks 15, 16.
- SSE (§1) → Task 18.
- Caching (§7) — **not in this plan**. Deferred until there is a measured need; noted as a gap.
- Eval with gold set, citation precision/recall, CI (§9) → Tasks 19, 20.
- Disclaimer (§6) → frontend plan; the system prompt already states "not legal advice" (Task 15).

**Placeholder scan:** every code step has full code; Task 20 lists candidate cases with an explicit existence check rather than asserting they exist.

**Type consistency:** `Hit(type, id, label, text, score, via)` matches across Tasks 13, 15, 16. `NodeRef(type, id, label)` across 12, 14, 16, 17. `ReasoningEvent(kind, payload)` across 16, 18, 19. `resolve_section(session, section, act_hint)` / `resolve_neutral(session, raw)` / `edge_exists(...)` across 8, 9, 14, 19. `short_name` is defined in `oalc.py` and imported by `link.py`; `curated.py` imports from `link.py` — an `ingestion → graph` import direction that is acceptable for Phase 1 and worth moving into `ingestion/names.py` if it grows.
