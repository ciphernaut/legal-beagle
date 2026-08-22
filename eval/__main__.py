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
                print(
                    f"{r['neutral_citation']:<18} precision={r['precision']:.2f} "
                    f"recall={r['recall']:.2f}"
                )
    if not rows:
        print("no cases scored")
        return
    mp = sum(r["precision"] for r in rows) / len(rows)
    mr = sum(r["recall"] for r in rows) / len(rows)
    print(f"\nmean precision={mp:.3f} mean recall={mr:.3f} (n={len(rows)})")
    sys.exit(0 if mp >= 0.95 else 1)


if __name__ == "__main__":
    main()
