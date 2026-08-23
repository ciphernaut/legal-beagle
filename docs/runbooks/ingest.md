# Ingestion runbook

End-to-end: bring up Postgres, download the Open Australian Legal Corpus (OALC), load
Commonwealth Acts and High Court judgments, link citations, add curated edges, embed, and run the
reasoning scorecard.

## 1. Postgres

Either path works; the connection is always `postgresql+psycopg://legal:legal@localhost:5432/legal`.

- Docker (documented default):
  ```bash
  docker compose up -d postgres      # image pgvector/pgvector:pg16
  ```
  `infrastructure/postgres-init.sql` runs on first start and creates `legal_test` plus the
  `vector` extension in both databases.
- Rootless local cluster (this dev box, no Docker):
  ```bash
  scratch/pg.sh start | status | stop        # data in scratch/pgdata
  ```
  Databases `legal`, `legal_test` and `legal_test_a..d` already exist with `vector` created.
  `psql` lives at
  `scratch/pgenv/lib/python3.12/site-packages/pgserver/pginstall/bin/psql`.

## 2. Schema

```bash
cd backend && uv sync && uv run alembic upgrade head
```

## 3. Download the corpus (~9.4 GB)

```bash
cd backend && scripts/fetch_corpus.sh          # writes data/corpus.jsonl, resumable
```

`scripts/fetch_corpus.sh` pulls `corpus.jsonl` straight from the Hugging Face CDN with
`curl -C -` and up to 500 retries, and only promotes `corpus.jsonl.part` to `corpus.jsonl` once
the full 9,401,179,433 bytes have arrived. It is used in preference to
`uv run huggingface-cli download umarbutler/open-australian-legal-corpus corpus.jsonl
--repo-type dataset --local-dir data/`, which on this box died partway through the multi-hour
transfer without resuming.

## 4. Load (no embeddings)

```bash
uv run python -m src.ingestion.run --oalc data/corpus.jsonl --no-embed
```

Loads Cth Acts + HCA cases, links citations, adds curated `AUTHORISED_BY` edges. Emits a large
volume of `duplicate provision identifier ... skipped` warnings on stderr — see "Known gaps".
Redirect to a log: the pass-1 log for the numbers below was 64 MB.

## 5. Embed

```bash
uv run python -m src.ingestion.run --oalc data/corpus.jsonl
```

Re-run of the same command without `--no-embed`. The reload half is idempotent (every record is
recognised as already loaded), then `embed_pending` fills `paragraphs.embedding` first (the 164 k
HCA judgment paragraphs matter most for retrieval and are far fewer than provisions) and
`provisions.embedding` second. It commits after each batch of 64, so it is resumable and progress
is visible while it runs. To embed without re-parsing/re-loading the corpus (skips seed/load/link/
curated), pass `--embed-only` and drop `--oalc`:

```bash
uv run python -m src.ingestion.run --embed-only
```

```bash
psql -U legal -d legal -c \
  "select (select count(*) from provisions where embedding is not null),
          (select count(*) from paragraphs where embedding is not null);"
```

CPU embedding of the full corpus takes many hours. Interrupting and re-running is safe.

## 6. Scorecard

```bash
cd backend && PYTHONPATH=.:.. uv run python -m eval
```

Needs the local LLM at `http://localhost:7080/v1` (`qwen3.8-27b-fp8`). One LLM call per gold
case. Exit code 0 only if mean precision >= 0.95, so a baseline run below that exits 1.

## Observed baseline (2026-08-23)

Corpus snapshot: `corpus.jsonl`, 9,401,179,433 bytes.

Pass 1 (`--no-embed`), printed totals:

```
loaded acts=4661 cases=6591 skipped=220661 failed=0
edges cites=2712 interprets=3577
curated edges=10
```

In the database after pass 1:

| rows | count |
| --- | --- |
| acts | 4,661 |
| cases | 6,591 |
| provisions | 1,035,416 |
| paragraphs | 164,044 |
| `CITES` edges | 2,712 |
| `INTERPRETS` edges | 3,577 |
| `AUTHORISED_BY` edges (curated) | 10 |
| `DECIDED_BY` edges | 6,591 |
| `IN_JURISDICTION` edges | 4,661 |
| `APPEALS_TO` edges | 3 |

`skipped=220661` is the rest of the OALC (state/territory legislation, non-HCA courts,
secondary material) filtered out by `--sources`/`--jurisdictions`. `failed=0`.

Curated edges are 10/10 of the pairs in `src/graph/curated_edges.yaml` — full coverage.

HCA case coverage by decade (from `cases.neutral_citation`): 1900s 366, 1910s 637, 1920s 454,
1930s 500, 1940s 461, 1950s 717, 1960s 663, 1970s 564, 1980s 554, 1990s 433, 2000s 548,
2010s 485, 2020s 209. Coverage is a fairly even sample across the century rather than a complete
set: several leading cases (e.g. Pape v Federal Commissioner of Taxation [2009] HCA 23) are simply
absent from the snapshot.

## Known gaps

### Duplicate provision identifiers (parser limitation, not fixed)

`load_oalc` keeps the first provision under a given identifier within an Act version and skips
later ones, logging `duplicate provision identifier '<id>' skipped`. Pass 1 logged
**463,823** such skips across the 4,661 Acts, in two shapes:

- **140,418 top-level `sN` skips.** Overwhelmingly amending Acts, whose Schedule items are
  numbered `1`, `2`, `3`… in each Schedule and are parsed by the flat section regex as if they
  were sections, so every Schedule after the first collides with the one before. The frequency
  falls off exactly like a Schedule-item ordinal would: `s1` 13,995, `s2` 12,669, `s3` 10,910,
  `s4` 6,971, `s5` 5,716, `s6` 4,908 …
- **323,405 sub-item skips** (identifiers containing parentheses, e.g. `s24J(a)`). The child
  regex flattens paragraphs `(a)`, `(b)`… under the *section*, not under the subsection they sit
  in, so `s24J(1)(a)` and `s24J(2)(a)` both come out as `s24J(a)`.

Consequence: `provisions` holds 1,035,416 rows rather than the ~1.5 M the raw text implies. The
loss is concentrated in amending-Act Schedules and in repeated paragraph letters inside long
sections; principal Acts' section text is intact, and every Constitution provision the curated
edges and gold set rely on resolves. Fixing it means making `act_parser` Schedule- and
subsection-aware, which is deliberately out of scope for Phase 1.

The same first-wins rule applies to judgment paragraphs (`duplicate paragraph number N skipped`,
**232,109** in pass 1): multi-judgment HCA decisions restart numbering at [1] for each judge, so
only the first judge's reasons are stored for those cases.

### Constitution section numbering

The Constitution ships in the corpus in its originally enacted typography — `51.  Legislative
powers of the Parliament.` and heads of power as `(xx.)` — rather than the post-2001 consolidated
`51  Heading` / `(xx)` style. `act_parser` now tolerates the optional trailing period in both the
section and the child regex. Before that fix no Constitution sections parsed at all, so
`resolve_section(..., "Constitution")` returned `None` for every head of power and
`curated edges=0`. With the fix all 10 curated `AUTHORISED_BY` edges load.

## Observed timings (2026-08-23, this dev box: CPU-only, rootless Postgres)

| phase | duration |
| --- | --- |
| download `corpus.jsonl` (9.4 GB) via `scripts/fetch_corpus.sh` | ~30 min |
| pass 1, `--no-embed` (parse + insert 1.04 M provisions, 164 k paragraphs, link citations) | ~1 h 35 min |
| pass 2, reload half (re-stream 9.4 GB, recognise everything as already loaded) | **~57 min** — idempotent but not fast; the JSONL is re-parsed end to end |
| pass 2, embedding | ~950 provision rows/min steady state (`BAAI/bge-small-en-v1.5`, CPU, batch 64) |

At 950 rows/min the remaining 1,028,952 provisions plus 164,044 paragraphs project to
**~21 hours** of wall clock. `embed_pending` commits after every batch, so this can be stopped and
resumed at any point and completed rows survive; check progress with the query in step 5.

## Baseline scorecard (2026-08-23)

`PYTHONPATH=.:.. uv run python -m eval` against the 20-case gold set, `qwen3.8-27b-fp8` at
`localhost:7080`. Run took 31 min for 20 cases (~1.6 min/case, one LLM call each; no call
approached the 5-minute mark). **Exit code 1** — expected, the gate is mean precision >= 0.95 and
this is an untuned baseline. Prompts were deliberately not tuned.

Embeddings at eval time: **7,424 → 50,304 provision rows embedded, 0 paragraph rows** (the
embedding pass was running concurrently and is ~5% through provisions). Retrieval was therefore
carried almost entirely by FTS and graph expansion; the vector leg contributed nearly nothing.
Re-run this scorecard once embedding completes before drawing conclusions from it.

```
[1992] HCA 23      precision=0.73 recall=0.00
[2006] HCA 52      precision=0.96 recall=0.50
[1983] HCA 21      precision=0.58 recall=0.00
[1988] HCA 18      precision=0.62 recall=1.00
[1920] HCA 54      precision=0.17 recall=0.00
[1997] HCA 25      precision=0.92 recall=0.00
[1992] HCA 45      precision=0.60 recall=0.00
[1948] HCA 7       precision=0.35 recall=0.00
[1951] HCA 5       precision=0.67 recall=0.00
[1995] HCA 47      precision=0.86 recall=1.00
[1996] HCA 40      precision=0.71 recall=0.00
[2012] HCA 23      precision=0.48 recall=1.00
[1999] HCA 30      precision=0.58 recall=1.00
[2004] HCA 37      precision=1.00 recall=1.00
[1994] HCA 46      precision=0.75 recall=0.00
[1989] HCA 53      precision=0.38 recall=1.00
[1971] HCA 40      precision=0.50 recall=1.00
[1982] HCA 27      precision=0.83 recall=1.00
[1956] HCA 10      precision=0.50 recall=1.00
[1998] HCA 22      precision=0.33 recall=0.00

mean precision=0.626 mean recall=0.475 (n=20)
```

All 20 gold cases scored; no `SKIP` lines, i.e. every gold neutral citation resolves in the corpus.

`recall` here is exact-string overlap between the gold `key_authorities`/`key_provisions` and the
citations the verifier resolved, so it is brittle by construction: a case that cites
`s 51(xxix)` when the gold says `s 51(xxix) of the Constitution` scores 0. The zeros above are
worth reading as "the expected authority was not resolved *in that exact form*" rather than "the
model missed it".
