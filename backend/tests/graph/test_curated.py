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
