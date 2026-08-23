import argparse
import sys
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
    ap.add_argument("--oalc", type=Path, required=False)
    ap.add_argument("--sources", default="federal_register_of_legislation,high_court_of_australia")
    ap.add_argument("--jurisdictions", default="commonwealth")
    ap.add_argument("--no-embed", action="store_true")
    ap.add_argument("--embed-only", action="store_true",
                     help="Skip seed/load/link/curated steps; only embed pending rows.")
    args = ap.parse_args()

    if args.embed_only and args.no_embed:
        ap.error("--embed-only and --no-embed are mutually exclusive")
    if not args.embed_only and args.oalc is None:
        ap.error("--oalc is required unless --embed-only is given")

    configure_sessions(get_engine())
    with SessionLocal() as session:
        try:
            if args.embed_only:
                n = embed_pending(session, SentenceTransformerEmbedder(get_settings().embed_model))
                session.commit()
                print(f"embedded rows={n}")
                return
            seed_reference_data(session)
            session.commit()
            stats = load_oalc(session, args.oalc, sources=set(args.sources.split(",")),
                              jurisdictions=set(args.jurisdictions.split(",")))
            session.commit()
            print(f"loaded acts={stats.acts} cases={stats.cases} "
                  f"skipped={stats.skipped} failed={stats.failed}")
            cites, interprets = link_case_citations(session)
            session.commit()
            print(f"edges cites={cites} interprets={interprets}")
            print(f"curated edges={load_curated_edges(session)}")
            session.commit()
            if not args.no_embed:
                n = embed_pending(session, SentenceTransformerEmbedder(get_settings().embed_model))
                session.commit()
                print(f"embedded rows={n}")
        except Exception as exc:  # noqa: BLE001 - top-level CLI guard
            session.rollback()
            print(f"ingestion failed: {exc!r}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
