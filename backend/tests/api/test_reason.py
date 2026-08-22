import json
from pathlib import Path

from sqlalchemy import select

from src.graph.models import Case
from src.graph.seed import seed_reference_data
from src.ingestion.embed import FakeEmbedder, embed_pending
from src.ingestion.link import link_case_citations
from src.ingestion.sources.oalc import load_oalc

FIXTURE = Path(__file__).parent.parent / "fixtures" / "oalc_sample.jsonl"


def _parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        kind, data = None, None
        for line in block.splitlines():
            if line.startswith("event:"):
                kind = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:].strip())
        if kind:
            events.append((kind, data))
    return events


def test_frameworks_list(client):
    assert client.get("/reason/frameworks").json() == ["common_law"]


def test_reverse_stream(client, db_session):
    seed_reference_data(db_session)
    load_oalc(db_session, FIXTURE,
              sources={"federal_register_of_legislation", "high_court_of_australia"},
              jurisdictions={"commonwealth"})
    link_case_citations(db_session)
    embed_pending(db_session, FakeEmbedder())
    db_session.commit()
    mabo = db_session.scalar(select(Case))

    with client.stream("POST", "/reason/reverse",
                       json={"node_type": "case", "node_id": mabo.id,
                             "framework": "common_law"}) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        body = "".join(r.iter_text())
    events = _parse_sse(body)
    kinds = [k for k, _ in events]
    assert kinds[0] == "context" and kinds[-2] == "verification" and kinds[-1] == "done"
    assert abs(events[-2][1]["precision"] - 2 / 3) < 1e-9


def test_reverse_unknown_node(client, db_session):
    r = client.post("/reason/reverse",
                    json={"node_type": "case", "node_id": 999999, "framework": "common_law"})
    assert r.status_code == 404


def test_reverse_unknown_framework(client, db_session):
    r = client.post("/reason/reverse",
                    json={"node_type": "case", "node_id": 1, "framework": "nope"})
    assert r.status_code == 422


def test_reverse_stream_emits_terminal_error(client, db_session, monkeypatch):
    seed_reference_data(db_session)
    load_oalc(db_session, FIXTURE,
              sources={"federal_register_of_legislation", "high_court_of_australia"},
              jurisdictions={"commonwealth"})
    link_case_citations(db_session)
    embed_pending(db_session, FakeEmbedder())
    db_session.commit()
    mabo = db_session.scalar(select(Case))
    monkeypatch.setenv("LLM", "fake-error:partial prose citing [1992] HCA 23")

    with client.stream("POST", "/reason/reverse",
                       json={"node_type": "case", "node_id": mabo.id,
                             "framework": "common_law"}) as r:
        assert r.status_code == 200
        body = "".join(r.iter_text())
    events = _parse_sse(body)
    kinds = [k for k, _ in events]
    assert kinds[-1] == "error"
    assert "done" not in kinds and "verification" not in kinds
    assert events[-1][1] == {
        "message": "reasoning failed before verification completed", "verified": False
    }
    assert "token" in kinds  # unverified prose was emitted before the failure
