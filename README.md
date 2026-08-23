# Legal Beagle

An Australian legal reasoning and visualisation tool. It ingests primary law (Commonwealth Acts and
High Court judgments), builds an authority graph — Constitution → heads of power → Acts →
provisions → interpreting cases — retrieves relevant material, reasons over it with a local LLM,
and **verifies every citation in the model's output against the corpus**. Nothing the model says
is shown as authoritative unless it resolves to a real document.

> **Not legal advice.** This is a research and education tool. It can be wrong.

Status: Phase 1 backend (API + ingestion + evaluation). No frontend yet. See
`docs/superpowers/specs/` for the design and `docs/superpowers/plans/` for what has been built.

## Quick start (macOS or Linux)

You need: **Docker** (Docker Desktop or [OrbStack](https://orbstack.dev) on a Mac), **uv**, and
**git**. Python is installed by `uv` automatically.

```bash
brew install uv                      # macOS; Linux: curl -LsSf https://astral.sh/uv/install.sh | sh
git clone <this repo> legal-beagle && cd legal-beagle

# 1. Database — Postgres 16 + pgvector, with `legal` and `legal_test` databases created for you
docker compose up -d postgres        # if port 5432 is busy: POSTGRES_PORT=5433 docker compose up -d postgres

# 2. Backend dependencies (CPU-only torch + sentence-transformers; ~1 GB on first run)
cd backend
uv sync

# 3. Schema
uv run alembic upgrade head

# 4. Prove it works — tests run against the real database
uv run pytest -q
```

Expect `45 passed`. If you changed the port, set `DATABASE_URL` / `TEST_DATABASE_URL`
(see below) before steps 3–4.

### Try it with the tiny fixture corpus

```bash
uv run python -m src.ingestion.run --oalc tests/fixtures/oalc_sample.jsonl --no-embed
uv run fastapi dev src/main.py       # http://127.0.0.1:8000/docs
```

Then, e.g. `curl 'http://127.0.0.1:8000/tree?root=constitution'`.

### Pointing it at an LLM

The reasoning endpoint talks to any OpenAI-compatible server via LiteLLM. Copy the example env
file into `backend/` and edit it:

```bash
cp ../.env.example .env
```

| Server | `LLM_API_BASE` | `LLM_MODEL` |
|---|---|---|
| LM Studio (Mac-friendly) | `http://localhost:1234/v1` | whatever the UI shows, e.g. `qwen2.5-14b-instruct` |
| Ollama | `http://localhost:11434/v1` | e.g. `qwen2.5:14b` |
| vLLM / llama.cpp server | `http://host:port/v1` | the served model id |

No API key is needed for local servers. The verifier is what makes the output trustworthy, not the
model, so a modest local model is fine to start. Then run the scorecard:

```bash
PYTHONPATH=.:.. uv run python -m eval    # needs the LLM running; uses the gold set in eval/gold/
```

### The real corpus (optional, 9.4 GB)

```bash
scripts/fetch_corpus.sh                          # resumable download to backend/data/corpus.jsonl
uv run python -m src.ingestion.run --oalc data/corpus.jsonl --no-embed   # ~40 min
uv run python -m src.ingestion.run --oalc data/corpus.jsonl              # + embeddings: hours on CPU
```

See `docs/runbooks/ingest.md` for observed counts, timings and known gaps.

## Configuration

All settings are environment variables (or `backend/.env`), defaults in `backend/src/config.py`:

| Variable | Default |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg://legal:legal@localhost:5432/legal` |
| `TEST_DATABASE_URL` | `postgresql+psycopg://legal:legal@localhost:5432/legal_test` |
| `LLM_API_BASE` | `http://localhost:7080/v1` |
| `LLM_MODEL` | `qwen3.8-27b-fp8` |
| `EMBED_MODEL` | `BAAI/bge-small-en-v1.5` (384 dimensions — fixed by the schema) |

## Layout

```
backend/        FastAPI + SQLAlchemy 2 + Alembic; everything runs with `uv run` from here
  src/graph/      ORM, seed data, curated edges, traversal
  src/ingestion/  parsers, corpus loader, citation linking, embeddings, CLI
  src/retrieval/  hybrid full-text + vector search with graph expansion
  src/reasoning/  LLM client, prompt frameworks, reasoning modes, citation verifier
  src/api/        /nodes, /tree, /reason/reverse (SSE)
eval/           gold set + scorecard
infrastructure/ Postgres init script used by docker compose
docs/           spec, plans, runbooks
```

## Contributing

Read `AGENTS.md` first — it states the non-negotiable constraints (citation grounding, provenance
on every row, no AustLII/Jade scraping, tests against a real database) and the workflow. Run
`uv run ruff check . ../eval` and `uv run pytest -q` before opening a PR; CI runs the same plus the
evaluation smoke test.

## Data sources and licences

Commonwealth legislation comes from the Federal Register of Legislation (CC BY 4.0) and High Court
judgments from hcourt.gov.au, both via the
[Open Australian Legal Corpus](https://huggingface.co/datasets/umarbutler/open-australian-legal-corpus)
which carries per-document licence metadata that the loader stores on every row. AustLII and
Jade.io are deliberately not used: their terms prohibit bulk access.
