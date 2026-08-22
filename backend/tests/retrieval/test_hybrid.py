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
                  FakeEmbedder(), k=1)
    assert hits[0].type == NodeType.provision and hits[0].label.endswith("s109")
    assert hits[0].via in ("fts", "both")
    graph_hits = [h for h in hits if h.via == "graph"]
    mabo = next(h for h in graph_hits if h.type == NodeType.case and h.label.startswith("Mabo"))
    # Expanded hits must carry real document text, not just their label.
    assert mabo.text != mabo.label
    assert mabo.text.startswith("The plaintiffs claim native title")


def test_no_expand_returns_only_direct_hits(db_session):
    _load(db_session)
    hits = search(db_session, "native title", FakeEmbedder(), k=5, expand=False)
    assert all(h.via != "graph" for h in hits)
    assert any(h.type == NodeType.case for h in hits)
