from pathlib import Path

from src.graph.seed import seed_reference_data
from src.ingestion.link import link_case_citations
from src.ingestion.sources.oalc import load_oalc

FIXTURE = Path(__file__).parent.parent / "fixtures" / "oalc_sample.jsonl"


def test_tree_from_constitution(client, db_session):
    seed_reference_data(db_session)
    load_oalc(db_session, FIXTURE,
              sources={"federal_register_of_legislation", "high_court_of_australia"},
              jurisdictions={"commonwealth"})
    link_case_citations(db_session)
    db_session.commit()

    r = client.get("/tree", params={"root": "constitution"})
    assert r.status_code == 200
    tree = r.json()
    assert tree["node"]["type"] == "act"
    labels = [c["node"]["label"] for c in tree["children"]]
    assert any(lbl.endswith("s109") for lbl in labels)
    assert not any(lbl.endswith("s51(xx)") for lbl in labels)  # subsections excluded
    assert not any(lbl.endswith("preamble") for lbl in labels)
    s109 = next(c for c in tree["children"] if c["node"]["label"].endswith("s109"))
    assert s109["children"][0]["node"]["label"].startswith("Mabo")


def test_tree_bad_root(client, db_session):
    assert client.get("/tree", params={"root": "act:999999"}).status_code == 404
