from pathlib import Path

from sqlalchemy import select

from src.graph.models import Case, NodeType, Provision
from src.graph.seed import seed_reference_data
from src.ingestion.sources.oalc import load_oalc
from src.reasoning.verifier import CitationStatus, verify

FIXTURE = Path(__file__).parent.parent / "fixtures" / "oalc_sample.jsonl"


def test_verify_classifies_three_ways(db_session):
    seed_reference_data(db_session)
    load_oalc(db_session, FIXTURE,
              sources={"federal_register_of_legislation", "high_court_of_australia"},
              jurisdictions={"commonwealth"})
    db_session.commit()
    mabo = db_session.scalar(select(Case))
    s109 = db_session.scalar(select(Provision).where(Provision.identifier == "s109"))

    answer = ("Mabo v Queensland (No 2) [1992] HCA 23 applied s 109 of the Constitution. "
              "Contrast [1988] HCA 69 and (1992) 175 CLR 1.")
    v = verify(db_session, answer, context_nodes={(NodeType.case, mabo.id)})
    by_raw = {c.raw: c for c in v.citations}
    assert by_raw["[1992] HCA 23"].status == CitationStatus.resolved
    assert by_raw["s 109 of the Constitution"].status == CitationStatus.resolved_outside_context
    assert by_raw["s 109 of the Constitution"].node.id == s109.id
    assert by_raw["[1988] HCA 69"].status == CitationStatus.unresolved
    assert by_raw["(1992) 175 CLR 1"].status == CitationStatus.unresolved
    assert v.precision == 0.5


def test_no_citations_is_precision_one(db_session):
    assert verify(db_session, "No citations here.", set()).precision == 1.0
