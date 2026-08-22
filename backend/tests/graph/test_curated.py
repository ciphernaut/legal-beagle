from pathlib import Path

from sqlalchemy import select

from src.graph.curated import load_curated_edges
from src.graph.models import Act, Case, Edge, EdgeKind, Extraction, Jurisdiction
from src.graph.seed import get_court_by_code, seed_reference_data
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
    # The note belongs in `note`; source_url names the curated file, not the note text.
    assert e.source_url == "curated:src/graph/curated_edges.yaml"
    assert e.note == "Corporations power; NSW v Commonwealth (Work Choices) [2006] HCA 52"
    assert e.evidence_case_id is None  # [2006] HCA 52 is not in the fixture corpus
    assert load_curated_edges(db_session) == 0


def test_curated_edge_links_evidence_case_when_note_citation_resolves(db_session):
    seed_reference_data(db_session)
    load_oalc(db_session, FIXTURE, sources={"federal_register_of_legislation"},
              jurisdictions={"commonwealth"})
    cth = db_session.scalar(select(Jurisdiction).where(Jurisdiction.code == "CTH"))
    db_session.add(Act(title="Corporations Act 2001", short_name="Corporations Act", year=2001,
                       jurisdiction_id=cth.id, extraction=Extraction.parsed))
    db_session.add(Case(name="NSW v Commonwealth (Work Choices)",
                        neutral_citation="[2006] HCA 52",
                        court_id=get_court_by_code(db_session, "HCA").id,
                        extraction=Extraction.parsed))
    db_session.commit()

    assert load_curated_edges(db_session) == 1
    db_session.commit()
    e = db_session.scalar(select(Edge).where(Edge.kind == EdgeKind.AUTHORISED_BY))
    work_choices = db_session.scalar(select(Case))
    assert e.evidence_case_id == work_choices.id
