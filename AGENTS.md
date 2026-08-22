# AGENTS.md — Legal Beagle

Guidance for AI agents (and humans) working in this repository.

## What this project is

An Australian legal reasoning and visualisation tool. It ingests primary law (Commonwealth Acts,
High Court judgments) into Postgres, builds an authority graph (Constitution → heads of power →
Acts → provisions → interpreting cases), retrieves relevant material, reasons over it with a
local LLM, and **verifies every citation in the LLM's output against the corpus**. Nothing the
model says is shown as authoritative unless it resolves to a real document.

Read these first:

- `docs/superpowers/specs/2026-08-22-legal-introspection-tool-design.md` — the binding design.
  Where a plan or code disagrees with the spec, the spec wins.
- `docs/superpowers/plans/2026-08-22-phase1-backend.md` — the current implementation plan
  (Phase 1 backend, 20 tasks with full code and tests).

## Non-negotiable constraints

1. **Citation grounding.** The LLM only sees retrieved documents; every citation it emits is parsed
   and resolved to a graph node. Unresolved citations are flagged, never hidden.
2. **Not legal advice.** Every user-facing surface carries a disclaimer; the system prompt says so too.
3. **Provenance.** Every node and edge row carries `source_url`, `source_licence`, and
   `extraction` (`curated | parsed | llm_extracted`).
4. **No AustLII or Jade.io access, ever.** Their terms prohibit it. Sources are the Federal Register
   of Legislation (CC-BY-4.0), the Open Australian Legal Corpus, hcourt.gov.au, and state
   legislation sites.
5. **Real database in tests.** Tests run against a live Postgres; the database is never mocked.
6. Embedding dimension is **384** (`BAAI/bge-small-en-v1.5`). LLM access is via LiteLLM with the
   `openai/<model>` prefix and `acompletion`, streaming.
7. Node type strings: `jurisdiction, court, act, provision, case, principle`. Edge kinds:
   `IN_JURISDICTION, DECIDED_BY, APPEALS_TO, AUTHORISED_BY, AMENDS, INTERPRETS, CITES,
   HELD_INCONSISTENT, ESTABLISHES, APPLIES, EVOLVED_INTO, CODIFIES`.

## Layout

```
backend/            FastAPI + SQLAlchemy 2 + Alembic; run everything with `uv run` from here
  src/graph/        ORM models, seed data, curated edges, traversal
  src/ingestion/    parsers (pure), OALC loader, citation linking, embeddings, CLI
  src/retrieval/    hybrid FTS + vector search with graph expansion
  src/reasoning/    LLM client, frameworks (prompt structures), modes (workflows), verifier
  src/api/          /nodes, /tree, /reason (SSE)
  tests/            pytest; fixtures in tests/fixtures/
eval/               gold set + scorecard (`python -m eval`)
docs/               specs, plans, runbooks
scratch/            git-ignored local scratch (rootless Postgres lives here on this machine)
.superpowers/       git-ignored process artifacts (SDD ledger, briefs, reports)
```

## Environment

- Python ≥ 3.12, `uv`. Always `cd backend && uv run ...`.
- Postgres 16 + pgvector on `localhost:5432`, user/password `legal`/`legal`.
  - Preferred: `docker compose up -d postgres` (image `pgvector/pgvector:pg16`); `infrastructure/postgres-init.sql` runs on first start and creates `legal_test` plus the `vector` extension in both databases.
  - On this dev box Docker needs `sg docker -c '...'`; a rootless cluster is already running from
    `scratch/pg.sh start|stop|status` (data in `scratch/pgdata`). Databases `legal`, `legal_test`,
    and `legal_test_a..d` (for parallel test runs) exist with the `vector` extension.
- Local LLM: `LLM_MODEL=qwen3.8-27b-fp8` at `LLM_API_BASE=http://localhost:7080/v1`.
- Do not create `backend/.env` in automated runs; `config.py` defaults point at the local DB.
- Torch is pinned to the CPU-only index in `pyproject.toml` — don't remove that.

## Commands

```bash
cd backend
uv sync                                   # first time; pulls CPU torch + sentence-transformers
uv run alembic upgrade head
uv run pytest -q                          # TEST_DATABASE_URL defaults to .../legal_test
uv run ruff check .
uv run fastapi dev src/main.py
uv run python -m src.ingestion.run --oalc data/corpus.jsonl [--no-embed]
PYTHONPATH=.:.. uv run python -m eval     # reasoning scorecard
```

## How to work here

- **Follow the plan task-by-task with TDD**: write the failing test, see it fail, implement, see it
  pass, commit. The plan contains the exact code; treat deviations as exceptions to be reported.
- **Process**: this repo is executed with the Superpowers subagent-driven-development workflow.
  The ledger at `.superpowers/sdd/<plan-name>/progress.md` records completed tasks and every
  ruling made; resume from it rather than re-doing finished tasks. `git log` is the backup record.
- **Commits**: conventional-commit subject, one task per commit (or per parallel sub-batch), with
  the trailer `Claude-Session: <session url>` when made by an agent session.
- **Branches**: never implement on `master`; current work is on `phase1-backend`.
- **Tests must be pristine** — no warnings in output. Fix the cause or add a justified
  `filterwarnings` entry.
- **Parallel agents** share one working tree: touch only your task's listed files, never run git
  yourself unless your dispatch says so; the controller commits.
- **Keep files focused**; follow the plan's file structure. If a file is outgrowing its intent,
  report it rather than restructuring on your own.
- **Don't overbuild.** Caching, Neo4j, Redis, treatment extraction, the frontend, and live FRL
  sync are all deliberately deferred — see the spec's phasing.

## Things an agent should not do without asking

- Merge to or push `master`; publish anything externally.
- Delete `scratch/pgdata` or any database.
- Change the spec's constraints above, the data model's node/edge vocabularies, or the
  embedding dimension.
- Download the full OALC corpus (several GB) unless the task explicitly calls for it (Task 20).
