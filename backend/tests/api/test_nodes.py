from pathlib import Path

from sqlalchemy import select

from src.graph.models import Case
from src.graph.seed import seed_reference_data
from src.ingestion.link import link_case_citations
from src.ingestion.sources.oalc import load_oalc

FIXTURE = Path(__file__).parent.parent / "fixtures" / "oalc_sample.jsonl"


def _load(db_session):
    seed_reference_data(db_session)
    load_oalc(db_session, FIXTURE,
              sources={"federal_register_of_legislation", "high_court_of_australia"},
              jurisdictions={"commonwealth"})
    link_case_citations(db_session)
    db_session.commit()


def test_get_case_node_with_neighbours(client, db_session):
    _load(db_session)
    mabo = db_session.scalar(select(Case))
    r = client.get(f"/nodes/case/{mabo.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["label"].startswith("Mabo")
    assert {"DECIDED_BY", "INTERPRETS"} <= {n["kind"] for n in body["neighbours"]}


def test_unknown_node(client, db_session):
    assert client.get("/nodes/case/999999").status_code == 404
    assert client.get("/nodes/bogus/1").status_code == 422
