from pathlib import Path

from sqlalchemy import select

from src.graph.models import Case, NodeType
from src.graph.seed import seed_reference_data
from src.ingestion.embed import FakeEmbedder, embed_pending
from src.ingestion.link import link_case_citations
from src.ingestion.sources.oalc import load_oalc
from src.reasoning.frameworks.common_law import CommonLawFramework
from src.reasoning.llm.client import FakeLLMClient
from src.reasoning.modes.reverse_engineering import ReverseEngineeringMode

FIXTURE = Path(__file__).parent.parent / "fixtures" / "oalc_sample.jsonl"


async def test_reverse_engineering_emits_context_tokens_verification_done(db_session):
    seed_reference_data(db_session)
    load_oalc(db_session, FIXTURE,
              sources={"federal_register_of_legislation", "high_court_of_australia"},
              jurisdictions={"commonwealth"})
    link_case_citations(db_session)
    embed_pending(db_session, FakeEmbedder())
    db_session.commit()
    mabo = db_session.scalar(select(Case))

    llm = FakeLLMClient(
        "## Precedent\n[1992] HCA 23 applied s 109 of the Constitution. See also [1950] HCA 99.")
    events = [e async for e in ReverseEngineeringMode().run(
        db_session, llm, CommonLawFramework(), FakeEmbedder(),
        node_type=NodeType.case, node_id=mabo.id)]

    kinds = [e.kind for e in events]
    assert kinds[0] == "context" and kinds[-2] == "verification" and kinds[-1] == "done"
    assert kinds.count("token") == 3
    labels = [n["label"] for n in events[0].payload["nodes"]]
    assert any(lbl.endswith("s109") for lbl in labels)
    ver = events[-2].payload
    statuses = {c["raw"]: c["status"] for c in ver["citations"]}
    assert statuses["[1992] HCA 23"] == "resolved"
    assert statuses["s 109 of the Constitution"] == "resolved"
    assert statuses["[1950] HCA 99"] == "unresolved"
    assert abs(ver["precision"] - 2 / 3) < 1e-9
    assert "Mabo" in llm.last_messages[1]["content"]
    assert events[-1].payload["answer"].startswith("## Precedent")
