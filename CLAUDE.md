# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Read `AGENTS.md` first — it holds the non-negotiable constraints (citation grounding, not-legal-advice,
provenance on every row, no AustLII/Jade.io access, real-database tests, the fixed node/edge and
citation-status vocabularies) and the workflow rules (TDD from the plan, commit conventions, **no
session-identifier trailers in commit messages** — a commit-msg hook rejects them). The binding design
is `docs/superpowers/specs/2026-08-22-legal-introspection-tool-design.md`; where anything disagrees
with the spec, the spec wins.

## Commands

Backend (Python 3.12, uv; run everything from `backend/`):

```bash
cd backend
uv sync                                   # first time (CPU torch — don't remove the pytorch-cpu index)
uv run alembic upgrade head
uv run pytest -q                          # full suite vs real Postgres (TEST_DATABASE_URL → legal_test)
uv run pytest tests/ingestion/test_link.py -q        # one file; -k selects a single test
uv run ruff check . ../eval
uv run uvicorn src.main:app --reload --host 127.0.0.1 --port 8000   # NOT `fastapi dev` (CLI extra not installed)
uv run python -m src.ingestion.run --oalc data/corpus.jsonl [--no-embed|--embed-only]
PYTHONPATH=.:.. uv run python -m eval     # gold-set scorecard; needs the LLM endpoint up
```

Frontend (Node ≥22, from `frontend/`):

```bash
cd frontend
npm install
npm run dev            # :5173, proxies /api → 127.0.0.1:8000 (dev server binds ::1 — use `localhost`)
npm test               # Vitest; `npm test -- src/api/sse.test.ts` for one file
npm run build          # tsc --noEmit && vite build
```

Postgres 16 + pgvector must be on `localhost:5432` (`legal`/`legal` trust auth) with databases
`legal` and `legal_test`: `docker compose up -d postgres` creates both via
`infrastructure/postgres-init.sql`. Tests truncate every table after each test and run
`alembic downgrade base && upgrade head` per session — never point `TEST_DATABASE_URL` at a
database whose data you care about. Parallel test runs need separate databases (the extension must
be created per database).

## Architecture

The system's one invariant: **the LLM only ever sees text retrieved from the corpus, and every
citation in its output is resolved against the corpus before being shown as anything but
unverified.** Most cross-file structure exists to enforce that.

Backend request path (`backend/src/`):
`api/reason.py` (SSE endpoint) → `reasoning/modes/reverse_engineering.py` (builds context from
`graph/traversal.authority_chain` + `retrieval/hybrid.search`, streams the LLM, then runs
`reasoning/verifier.verify` over the full answer) → events `context | token | verification | done |
error` (one SSE event each, `sep="\n"`; `error` is terminal and means the text was never verified).
`reasoning/frameworks/` are prompt structures; `reasoning/modes/` are workflows — keep the
distinction. The verifier's statuses (`resolved | resolved_outside_context | unresolved |
unverifiable`) and its precision formula (unverifiable excluded from the denominator) are mirrored
in the frontend (`ReasoningPanel`) and in `eval/score.py`; change one and you must change all three.

Graph storage: one generic `edges` table (`src_type/src_id/dst_type/dst_id/kind` + provenance +
optional `treatment`/`note`/`evidence_case_id`) instead of per-relation tables. All traversal goes
through `graph/traversal.py` (`node_ref`, `neighbours`, `authority_chain`); node "labels" are built
there and are what the verifier and UI display. Documents are `Act → ActVersion → Provision` and
`Case → Judgment → Paragraph`; `Provision`/`Paragraph` carry the pgvector `embedding` (384-d, fixed)
and trigger-maintained `tsv` columns (migration 0002). Retrieval (`retrieval/hybrid.py`) is FTS +
vector fused with RRF, then one hop of graph expansion; `retrieval/context.py::node_text` is the
single definition of "what text represents a node to the LLM" — both expansion and the reasoning
mode use it.

Ingestion (`ingestion/`) is an offline batch pipeline, not request-path: pure parsers
(`parsers/` — citation regexes, Act section tree, judgment paragraphs) → `sources/oalc.py` (one
jsonl record per document, per-record savepoints so one bad record can't abort a run) →
`link.py` (regex citations → `CITES`/`INTERPRETS` edges) → `graph/curated.py` (hand-maintained
`AUTHORISED_BY` head-of-power edges from YAML) → `embed.py` (batched, commits per batch, resumable;
paragraphs before provisions). `graph/naming.py::short_name` is shared by loader, linker and
curated edges. Known parser gaps are documented in `docs/runbooks/ingest.md` — read it before
touching ingestion at corpus scale.

Frontend (`frontend/src/`): `api/` (typed client, hand-rolled SSE parser — the backend's stream is
read with fetch + ReadableStream, not EventSource, because the endpoint is a POST) → components in
feature folders. `useReverseReasoning` owns the run lifecycle (abort on cancel/selection
change/unmount; stale-run guard; `done` without `verification` is an error) — streamed text must
always be visibly marked unverified until the `verification` event, and that rule lives in
`ReasoningPanel`, not the hook. `API_BASE` honours `VITE_API_BASE` for production builds; dev relies
on the Vite proxy, so never hard-code `localhost:8000`.

Evaluation (`eval/`, repo root): a gold set of HCA cases (`eval/gold/hca.yaml`) scored by running
the real pipeline; CI runs it against the fixture corpus with a fake LLM and gates on citation
precision. If you change prompt text, retrieval, or the verifier, run `python -m eval` and compare
against the baseline recorded in `docs/runbooks/ingest.md`.

LLM access is via LiteLLM (`openai/<model>` prefix, `acompletion`, streaming) against any
OpenAI-compatible endpoint (`LLM_API_BASE`/`LLM_MODEL`, defaults in `src/config.py`); tests always
use the built-in fakes (`LLM=fake:<reply>`, `EMBEDDER=fake` env overrides in `api/deps.py`) — no
test may call a real model or mock the database.
