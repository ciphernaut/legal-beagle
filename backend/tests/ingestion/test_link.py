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
