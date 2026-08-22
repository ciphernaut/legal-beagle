from pathlib import Path

from sqlalchemy import select

from src.graph.models import (
    Act,
    Case,
    Edge,
    EdgeKind,
    Extraction,
    Paragraph,
    Provision,
)
from src.graph.seed import seed_reference_data
from src.ingestion.sources.oalc import load_oalc, short_name

FIXTURE = Path(__file__).parent.parent / "fixtures" / "oalc_sample.jsonl"
ARGS = {"sources": {"federal_register_of_legislation", "high_court_of_australia"},
        "jurisdictions": {"commonwealth"}}


def test_short_name():
    assert short_name("Corporations Act 2001") == "Corporations Act"
    assert short_name("Commonwealth of Australia Constitution Act") == "Commonwealth of Australia Constitution Act"


def test_loads_acts_and_cases_and_is_idempotent(db_session):
    seed_reference_data(db_session)
    stats = load_oalc(db_session, FIXTURE, **ARGS)
    db_session.commit()
    assert (stats.acts, stats.cases, stats.skipped) == (1, 1, 1)

    act = db_session.scalar(select(Act))
    assert act.title == "Commonwealth of Australia Constitution Act"
    assert act.source_licence == "CC-BY-4.0"
    idents = set(db_session.scalars(select(Provision.identifier)).all())
    assert {"preamble", "s51", "s51(xx)", "s109"} <= idents

    case = db_session.scalar(select(Case))
    assert case.neutral_citation == "[1992] HCA 23"
    assert case.name == "Mabo v Queensland (No 2)"
    assert case.court.code == "HCA"
    para2 = db_session.scalar(select(Paragraph).where(Paragraph.number == 2))
    assert para2.text.startswith("Under s 109")

    again = load_oalc(db_session, FIXTURE, **ARGS)
    db_session.commit()
    assert (again.acts, again.cases) == (0, 0)
    assert len(db_session.scalars(select(Act)).all()) == 1
    assert len(db_session.scalars(select(Case)).all()) == 1


def test_provenance_on_provisions_and_edges(db_session):
    seed_reference_data(db_session)
    load_oalc(db_session, FIXTURE, **ARGS)
    db_session.commit()

    act = db_session.scalar(select(Act))
    version = act.versions[0]
    for prov in db_session.scalars(select(Provision)).all():
        assert prov.source_url == version.source_url
        assert prov.source_licence == act.source_licence
        assert prov.extraction == Extraction.parsed

    case = db_session.scalar(select(Case))
    in_juris = db_session.scalar(select(Edge).where(Edge.kind == EdgeKind.IN_JURISDICTION))
    assert (in_juris.source_url, in_juris.source_licence) == (act.source_url, act.source_licence)
    decided_by = db_session.scalar(select(Edge).where(Edge.kind == EdgeKind.DECIDED_BY))
    assert (decided_by.source_url, decided_by.source_licence) == (
        case.source_url, case.source_licence)
