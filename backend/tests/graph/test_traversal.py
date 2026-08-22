from pathlib import Path

from sqlalchemy import select

from src.graph.models import Case, EdgeKind, NodeType, Provision
from src.graph.seed import seed_reference_data
from src.graph.traversal import authority_chain, neighbours, node_ref
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


def test_node_ref_labels(db_session):
    _load(db_session)
    s109 = db_session.scalar(select(Provision).where(Provision.identifier == "s109"))
    ref = node_ref(db_session, NodeType.provision, s109.id)
    assert ref.label == "Commonwealth of Australia Constitution Act s109"
    assert node_ref(db_session, NodeType.provision, 999999) is None


def test_neighbours_and_chain(db_session):
    _load(db_session)
    mabo = db_session.scalar(select(Case))
    out = neighbours(db_session, NodeType.case, mabo.id, kinds=[EdgeKind.INTERPRETS])
    assert [n.node.type for n in out] == [NodeType.provision]
    assert out[0].node.label.endswith("s109")

    chain = authority_chain(db_session, NodeType.case, mabo.id)
    types = [c.type for c in chain]
    assert NodeType.provision in types and NodeType.act in types

    s109 = db_session.scalar(select(Provision).where(Provision.identifier == "s109"))
    back = neighbours(db_session, NodeType.provision, s109.id, direction="in")
    assert back[0].node.label.startswith("Mabo")
