from sqlalchemy import select

from src.graph.models import Edge, EdgeKind, Jurisdiction
from src.graph.seed import get_court_by_code, seed_reference_data


def test_seed_is_idempotent_and_builds_hierarchy(db_session):
    seed_reference_data(db_session)
    seed_reference_data(db_session)
    db_session.commit()

    cth = db_session.scalar(select(Jurisdiction).where(Jurisdiction.code == "CTH"))
    assert cth.level == "Commonwealth"
    assert len(db_session.scalars(select(Jurisdiction)).all()) == 9
    fca = get_court_by_code(db_session, "FCA")
    hca = get_court_by_code(db_session, "HCA")
    assert fca.parent_court.code == "FCAFC"
    assert fca.parent_court.parent_court_id == hca.id
    appeals = db_session.scalars(select(Edge).where(Edge.kind == EdgeKind.APPEALS_TO)).all()
    assert len(appeals) == 3
