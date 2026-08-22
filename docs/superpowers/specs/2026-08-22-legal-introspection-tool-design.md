# Australian Legal Introspection Tool - Design Specification

**Date:** 2026-08-22  
**Status:** Draft v2 - Revised after review  
**Repo:** `legal-beagle-the-third`

---

## Executive Summary

A web-based legal reasoning and visualisation tool for Australian law that traces authority from common law foundations through the Constitution to current legislation and case law. Every piece of LLM reasoning is grounded in, and verified against, a locally-held corpus of primary legal materials — the tool never presents a citation it cannot resolve to a real document.

The tool supports reasoning **modes** (workflows) built on pluggable reasoning **frameworks** (prompt structures), and three visualisation views (layered map, interactive tree, timeline). It is built as a vertical slice first (Commonwealth + High Court, one view, one mode) and expanded from there.

**Primary Audience:** Citizens/researchers, law students, academics  
**Secondary Audience:** Legal professionals

**Non-negotiable design constraints:**

1. **Citation grounding.** The LLM reasons only over documents retrieved from the local corpus. Every citation in its output is parsed and resolved to a graph node; unresolved citations are visibly flagged, never silently shown.
2. **Not legal advice.** A persistent disclaimer is part of the UI, not a future enhancement.
3. **Provenance on everything.** Every node and edge records where it came from (`source_url`, `source_licence`, `extraction: curated | parsed | llm_extracted`).

---

## 1. System Architecture

### High-Level Design

```
┌─────────────────────────────────────────────────────────────┐
│                    Vite + React Frontend                     │
│  (Interactive Tree | Layered Map | Timeline)                 │
│  Disclaimer banner · Citation verification badges            │
└─────────────────────────┬───────────────────────────────────┘
                          │ HTTP + SSE (streamed LLM output)
┌─────────────────────────▼───────────────────────────────────┐
│                   FastAPI Backend Service                     │
│  ┌───────────────┐ ┌───────────────┐ ┌────────────────────┐ │
│  │ Retrieval     │ │ Reasoning     │ │ Citation Verifier  │ │
│  │ (FTS+vector)  │ │ Engine        │ │ (resolve→graph)    │ │
│  └───────────────┘ └───────────────┘ └────────────────────┘ │
└─────────────────────────┬───────────────────────────────────┘
                          │
          ┌───────────────┴───────────────┐
          ▼                               ▼
┌──────────────────────────┐   ┌──────────────────────────────┐
│  PostgreSQL 16           │   │  Ingestion (batch, offline)  │
│  - documents + provisions│   │  - legislation.gov.au OData  │
│  - graph tables (edges)  │   │  - Open Australian Legal     │
│  - pgvector embeddings   │   │    Corpus (bulk)             │
│  - tsvector full-text    │   │  - hcourt.gov.au (HCA)       │
│  - query/LLM cache       │   │  - State legislation sites   │
└──────────────────────────┘   │  - ParlInfo/Hansard (later)  │
                               └──────────────────────────────┘
                                              │
                               ┌──────────────▼───────────────┐
                               │  Local LLM (LiteLLM)         │
                               │  qwen3.8-27b-fp8 @ :7080     │
                               └──────────────────────────────┘
```

### Key Decisions

- **Bounded corpus, ingested up front.** The Australian primary-law corpus is finite and bulk-available. Ingestion is a batch job, not a request-path activity. The LLM can only cite what is in the corpus, so the corpus must be complete for the jurisdictions the tool claims to cover.
- **Single database for v1.** PostgreSQL handles documents, graph edges (recursive CTEs), full-text search, vector retrieval (pgvector) and caching. A dedicated graph DB (Neo4j) is only introduced if a real traversal query proves too slow — the data model is designed so that migration is mechanical. Redis is not needed until there is a second backend instance.
- **Retrieval is a first-class component.** Hybrid full-text + vector search over provisions and judgment paragraphs feeds the reasoning engine. Nothing reaches the LLM that did not come from retrieval.
- **Local LLM via LiteLLM:** qwen3.8-27b-fp8 at localhost:7080, OpenAI-compatible. Provider is swappable via config.
- **SSE for streaming.** LLM output is one-directional; SSE is simpler than WebSocket.
- **Deployment:** Docker Compose for development. Production config deferred.

---

## 2. Data Model

Implemented as Postgres tables; described here in graph terms because that is how it is queried and visualised.

### Nodes

```
Jurisdiction  {code, name, level: Commonwealth|State|Territory}
Court         {name, jurisdiction, tier, parent_court}       -- hierarchy for binding/persuasive
Act           {title, short_name, jurisdiction, year, status} -- includes Constitution Acts
ActVersion    {act_id, compilation_no, in_force_from, in_force_to, source_url}
Provision     {act_version_id, identifier (e.g. "s51(xx)"), heading, text, parent_provision}
Case          {name, neutral_citation, court_id, decided_on, summary, source_url}
Judgment      {case_id, judge(s), disposition: majority|dissent|concurring}
Paragraph     {judgment_id, number, text}                     -- retrieval unit for judgments
Principle     {name, statement, extraction: curated|llm_extracted}
Bill          {act_id, introduced_on, assented_on, debate_hours, committee_referred} -- phase 3
```

Notes:
- The Constitution is an `Act` (*Commonwealth of Australia Constitution Act 1900* (Imp)) with `Provision` rows for s.51(i)…(xxxix), s.92, s.109 etc. State constitutions are modelled the same way.
- `Provision` is the unit of authority. Cases interpret provisions, not Acts; legislative power derives from a specific head of power, not "the Constitution".
- `ActVersion` gives point-in-time law. Required for the timeline view and for "what was the law on date X".
- **Local government** (council by-laws) is out of scope.

### Edges

All edges carry `{source, extraction, confidence, evidence_case_id?}`.

```
Act        -[:IN_JURISDICTION]->  Jurisdiction
Case       -[:DECIDED_BY]->       Court
Court      -[:APPEALS_TO]->       Court
Act        -[:AUTHORISED_BY]->    Provision       -- head of power, e.g. s51(xx)
Act        -[:AMENDS]->           Act
Case       -[:INTERPRETS]->       Provision
Case       -[:CITES {treatment}]-> Case           -- treatment: followed|applied|considered|
                                                  --   distinguished|not_followed|overruled
Case       -[:HELD_INCONSISTENT {s109: true}]-> Act  -- s.109 is a judicial finding, not a property
Case       -[:ESTABLISHES]->      Principle
Case       -[:APPLIES]->          Principle
Principle  -[:EVOLVED_INTO]->     Principle
Provision  -[:CODIFIES]->         Principle
```

`CITES.treatment` is the core data for the Discovery mode ("find cases that distinguished this one"). Treatment is initially LLM-extracted from judgment text with `confidence`; curated corrections override.

### Jurisdictions (v1 scope in bold)

- **Commonwealth**
- State: NSW, VIC, QLD, SA, WA, TAS
- Territory: ACT, NT

---

## 3. Data Ingestion

### Sources

| Source | What | Access | Licence |
|---|---|---|---|
| **Federal Register of Legislation** (legislation.gov.au) | Cth Acts, compilations, regulations | OData API | CC BY 4.0 |
| **Open Australian Legal Corpus** (HuggingFace, Umar Butler) | Bulk judgments + legislation, all jurisdictions | Bulk download | Per-document licence metadata — respect it |
| **High Court of Australia** (hcourt.gov.au / eresources) | HCA judgments | HTTP, polite crawl | Crown copyright, reproduction permitted |
| **State legislation sites** (legislation.nsw.gov.au, legislation.vic.gov.au, legislation.qld.gov.au, …) | Consolidated state Acts | Varies per state; NSW has API | Mostly CC BY 4.0; check each |
| **ParlInfo / Hansard** (phase 3) | Bill passage dates, debate, committee referrals | Search API / scrape | Cth Parliament licence |

**Explicitly not used:**
- **AustLII** — no API, terms prohibit bulk download and caching, actively blocks scrapers. May be linked to as a human-readable reference but not ingested.
- **Jade.io** — commercial (BarNet); automation breaches ToS.
- ~~ComLaw~~ — renamed to the Federal Register of Legislation in 2016.

### Pipeline

```
backend/src/ingestion/
├── sources/
│   ├── frl_odata.py          # legislation.gov.au
│   ├── oalc.py               # Open Australian Legal Corpus loader
│   ├── hca.py                # hcourt.gov.au
│   └── state/<code>.py       # one per state, added as scope expands
├── parsers/
│   ├── act_parser.py         # Act → ActVersion → Provision tree
│   ├── judgment_parser.py    # Case → Judgment → Paragraph
│   └── citation_parser.py    # neutral + reported citations, section refs
├── extractors/
│   ├── treatment.py          # LLM: CITES.treatment from judgment text
│   └── principles.py         # LLM: ESTABLISHES/APPLIES
├── embed.py                  # pgvector embeddings for Provision + Paragraph
└── run.py                    # orchestration, idempotent, resumable
```

Ingestion is idempotent and keyed on `source_url + version`. LLM-extracted edges are marked `extraction = llm_extracted` and are never presented as authoritative without a confidence indicator.

---

## 4. Retrieval & Citation Verification

### Retrieval

Hybrid search over `Provision` and `Paragraph`:
1. Full-text (Postgres `tsvector`, legal-aware tokeniser for section refs and citations)
2. Vector (pgvector, local embedding model)
3. Graph expansion: from top hits, pull directly connected nodes (cases interpreting a provision, cases cited by a hit case) one hop out
4. Rerank and assemble a context bundle with explicit node IDs

### Citation Verifier

Runs over every LLM response before it is shown:
1. Parse citations (neutral citations `[2023] HCA 12`, reported `(1992) 175 CLR 1`, section refs `s 51(xx)`, Act titles)
2. Resolve each against the graph
3. Annotate: ✅ resolved (link to node) · ⚠️ resolved but not in the retrieved context (model drew on memory) · ❌ unresolved (treat as hallucinated)
4. Report citation precision per response; surface in UI

This is the primary quality metric for the whole system (see §9).

---

## 5. Reasoning Engine

```
backend/src/reasoning/
├── llm/
│   ├── client.py             # LiteLLM wrapper (acompletion, streaming)
│   └── cache.py              # response cache keyed on (mode, framework, context_hash)
├── frameworks/               # prompt structures — HOW to reason
│   ├── base.py
│   ├── irac.py               # Issue → Rule → Application → Conclusion
│   ├── common_law.py         # Precedent → Distinguish → Apply
│   └── dialectical.py        # Thesis → Antithesis → Synthesis
├── modes/                    # workflows — WHAT is hidden/compared
│   ├── base.py
│   ├── reverse_engineering.py
│   ├── discovery.py
│   ├── prediction.py
│   └── dialectical.py
└── verifier.py               # → §4 Citation Verifier
```

### LLM Client

```python
from litellm import acompletion

class LLMClient:
    def __init__(self, model: str, api_base: str):
        self.model = f"openai/{model}"      # OpenAI-compatible endpoint
        self.api_base = api_base

    async def reason(self, messages: list[dict], *, temperature: float = 0.2):
        return await acompletion(
            model=self.model,
            api_base=self.api_base,
            messages=messages,
            temperature=temperature,
            stream=True,
        )
```

```env
LLM_MODEL=qwen3.8-27b-fp8
LLM_API_BASE=http://localhost:7080/v1
EMBED_MODEL=<local embedding model>
```

### Frameworks vs Modes

A **framework** is a prompt structure. A **mode** is a workflow that decides what context is supplied, what is withheld, and what the output is compared against. Not every combination is meaningful; these are the supported pairings:

| Mode | Default framework | Input | Output |
|---|---|---|---|
| **Reverse Engineering** (v1) | Common-law | A case or provision | Chain of authority: provision → head of power → interpreting cases → principles, each node verified |
| **Discovery** | Common-law | A case | Cases that distinguished / did not follow it (from `CITES.treatment`), plus LLM-generated distinguishing arguments grounded in those cases |
| **Dialectical** | Dialectical | A legal question + retrieved context | Plaintiff argument, defendant argument, synthesis; compared with actual court reasoning where a case is supplied |
| **Prediction** | IRAC | Facts + retrieved law, with the outcome withheld | Predicted outcome + reasoning; then reveal and diff |

**Prediction caveat:** the model has almost certainly memorised landmark cases (*Mabo*, *Tasmanian Dam*, *Cole v Whitfield*). "Blind" prediction is only honest for obscure or post-training-cutoff cases. The UI states this, and the mode optionally restricts itself to cases decided after the model's cutoff date. The Citation Verifier's ⚠️ state (cited but not in context) is the tell for memorised material.

Frameworks are plugin-based (subclass `BaseFramework`, register). User-defined frameworks via the web UI are deferred (Open Question 3).

---

## 6. Visualisation Layer

```
frontend/src/
├── components/
│   ├── tree/                 # v1: expandable authority hierarchy
│   ├── layered_map/          # phase 2: geological strata view
│   ├── timeline/             # phase 3: temporal + legislative process
│   ├── law_node/             # reusable Act/Provision/Case card
│   ├── authority_chain/      # edges between nodes
│   ├── reasoning_panel/      # streamed LLM output with citation badges
│   └── disclaimer/           # persistent, not dismissable on first visit
├── hooks/
└── stores/
```

### Interactive Tree (v1)

Root: Constitution → heads of power → Acts → Provisions → interpreting Cases → Principles. Expand/collapse, filter by jurisdiction, date (via `ActVersion`), court tier. Clicking a node opens the Reverse Engineering mode on it.

### Layered Map (phase 2)

Geological strata:
1. Common Law Stratum — English common law, reception, Australian principles
2. Constitutional Stratum (1901) — s.51 powers, s.92, s.109
3. Commonwealth Legislation — positioned under the head of power that authorises it
4. State/Territory Legislation — by jurisdiction
5. Case Law — annotated on the layer it interprets

### Timeline (phase 3) — Legislative Process View

Temporal view of Acts and their amendments (from `ActVersion`), with **neutral legislative-process metrics** from `Bill` (requires Hansard ingestion):

- Days from introduction to assent
- Recorded debate hours
- Committee referral (yes/no, which)
- Number of amendments during passage
- Whether the Act has been subject to an s.109 or constitutional challenge (from `HELD_INCONSISTENT` / `INTERPRETS`)

The tool presents the metrics and lets the user draw conclusions. It does **not** label legislation as "bad faith" — that is an editorial judgement, "constitutional overreach" is for the High Court to find, and an algorithmic label to a citizen audience would undermine the tool's credibility.

---

## 7. Caching

Single layer for v1, in Postgres:

- `llm_cache` — key `(mode, framework, model, context_hash)` → response, TTL days. Invalidated when any node in the context changes.
- `retrieval_cache` — key `(query_hash, filters)` → node IDs, TTL hours.

Redis and prefetching are deferred until there is measured need.

---

## 8. Project Structure

```
legal-beagle-the-third/
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml          # uv
│   ├── alembic/                # migrations
│   ├── src/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── api/
│   │   ├── ingestion/
│   │   ├── retrieval/
│   │   ├── reasoning/
│   │   ├── graph/              # data model + traversal queries
│   │   └── cache/
│   └── tests/
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── vite.config.ts
│   ├── src/
│   └── tests/
├── eval/                       # gold set + scoring (§9)
└── docs/
```

### Docker Compose (Development)

```yaml
services:
  backend:
    build: ./backend
    ports: ["8000:8000"]
    depends_on: [postgres]
    environment:
      LLM_API_BASE: http://host.docker.internal:7080/v1
  frontend:
    build: ./frontend
    ports: ["3000:3000"]
    depends_on: [backend]
  postgres:
    image: pgvector/pgvector:pg16
    ports: ["5432:5432"]
    volumes: [pgdata:/var/lib/postgresql/data]
volumes:
  pgdata:
```

---

## 9. Evaluation

There is no way to know whether the reasoning is any good without a gold set. `eval/` holds:

- **Gold cases** (20–30 to start): HCA decisions with known outcome, the provisions at issue, and the key authorities cited in the judgment.
- **Metrics:**
  - *Citation precision* — fraction of citations in LLM output that resolve (✅) — target ≥ 0.95
  - *Citation recall* — fraction of the judgment's key authorities the Reverse Engineering chain surfaces
  - *Treatment extraction accuracy* — sampled `CITES.treatment` vs. human label
  - *Prediction accuracy* — outcome match on post-cutoff cases only
- `uv run python -m eval` runs the suite and prints a scorecard; it runs in CI against a fixed corpus snapshot.

---

## 10. Phasing

**Phase 1 — Vertical slice**
- Ingest: Cth Acts + compilations (FRL OData), HCA judgments (OALC + hcourt)
- Retrieval + Citation Verifier
- Reverse Engineering mode with Common-law framework
- Interactive Tree view
- Disclaimer, eval gold set, CI

**Phase 2 — Breadth**
- Discovery and Dialectical modes; IRAC and Dialectical frameworks
- Treatment extraction for `CITES`
- Layered Map view
- First state (NSW — has an API)

**Phase 3 — Temporal**
- Hansard/ParlInfo ingestion → `Bill`
- Timeline view with legislative-process metrics
- Prediction mode (post-cutoff cases)
- Remaining states/territories

**Later**
- Neo4j if traversal performance demands it
- User accounts, saved research, PDF export
- Public API (subject to per-source licence constraints — AustLII-derived material could never be redistributed, which is one reason it is excluded)
- Content moderation model, if actually needed

---

## 11. Development Workflow

```bash
cp .env.example .env
docker compose up -d postgres
cd backend && uv sync && uv run alembic upgrade head
uv run python -m ingestion.run --source frl --source hca   # phase 1 corpus
uv run fastapi dev src/main.py
cd ../frontend && npm install && npm run dev
```

Testing:

```bash
cd backend && uv run pytest
cd frontend && npm test
uv run python -m eval        # reasoning quality scorecard
```

---

## Open Questions

1. Which local embedding model for pgvector? (Needs to handle long legal paragraphs; candidates to benchmark on the gold set.)
2. How aggressively should LLM-extracted edges (`treatment`, `principles`) be shown before curation? Proposal: shown with a confidence badge, hidden below a threshold.
3. Should reasoning frameworks be user-extensible via the web UI, or is a Python plugin sufficient for the target audience?
4. Licence audit: confirm per-state legislation licences before each state is added in phase 2/3.

---

## Changelog

- **v2 (2026-08-22):** Added citation grounding + retrieval as core components; replaced lazy scraping with bounded batch ingestion; replaced ComLaw/AustLII/Jade with FRL OData, OALC, hcourt.gov.au; collapsed Neo4j/Redis/Postgres to Postgres + pgvector; added `Provision`, `ActVersion`, `Court`, `Paragraph`, `Bill` nodes and `CITES.treatment`; made s.109 a judicial finding; dropped Local jurisdiction; renamed "bad-faith detection" to neutral legislative-process metrics; separated modes from frameworks and added the Prediction contamination caveat; fixed LiteLLM usage (`acompletion`, `openai/` prefix); SSE over WebSocket; added evaluation section and phasing; disclaimer made a v1 requirement.
- **v1 (2026-08-22):** Initial draft.
