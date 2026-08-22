from sqlalchemy import select
from sqlalchemy.orm import Session

from src.graph.models import Court, Edge, EdgeKind, Extraction, Jurisdiction, NodeType

JURISDICTIONS = [
    ("CTH", "Commonwealth", "Commonwealth"),
    ("NSW", "New South Wales", "State"),
    ("VIC", "Victoria", "State"),
    ("QLD", "Queensland", "State"),
    ("SA", "South Australia", "State"),
    ("WA", "Western Australia", "State"),
    ("TAS", "Tasmania", "State"),
    ("ACT", "Australian Capital Territory", "Territory"),
    ("NT", "Northern Territory", "Territory"),
]

# (code, name, jurisdiction_code, tier, parent_code)
COURTS = [
    ("HCA", "High Court of Australia", "CTH", 1, None),
    ("FCAFC", "Federal Court of Australia (Full Court)", "CTH", 2, "HCA"),
    ("FCA", "Federal Court of Australia", "CTH", 3, "FCAFC"),
    ("FedCFamC1G", "Federal Circuit and Family Court (Div 1)", "CTH", 3, "FCAFC"),
]


def get_court_by_code(session: Session, code: str) -> Court | None:
    return session.scalar(select(Court).where(Court.code == code))


def _upsert_edge(session: Session, src_type, src_id, dst_type, dst_id, kind) -> None:
    exists = session.scalar(
        select(Edge).where(
            Edge.src_type == src_type, Edge.src_id == src_id,
            Edge.dst_type == dst_type, Edge.dst_id == dst_id, Edge.kind == kind,
        )
    )
    if not exists:
        session.add(Edge(src_type=src_type, src_id=src_id, dst_type=dst_type, dst_id=dst_id,
                         kind=kind, extraction=Extraction.curated, confidence=1.0))


def seed_reference_data(session: Session) -> None:
    by_code: dict[str, Jurisdiction] = {}
    for code, name, level in JURISDICTIONS:
        j = session.scalar(select(Jurisdiction).where(Jurisdiction.code == code))
        if j is None:
            j = Jurisdiction(code=code, name=name, level=level)
            session.add(j)
        by_code[code] = j
    session.flush()

    courts: dict[str, Court] = {}
    for code, name, jcode, tier, _parent in COURTS:
        c = get_court_by_code(session, code)
        if c is None:
            c = Court(code=code, name=name, jurisdiction_id=by_code[jcode].id, tier=tier)
            session.add(c)
        courts[code] = c
    session.flush()
    for code, _, _, _, parent in COURTS:
        if parent:
            courts[code].parent_court_id = courts[parent].id
            _upsert_edge(session, NodeType.court, courts[code].id,
                         NodeType.court, courts[parent].id, EdgeKind.APPEALS_TO)
    session.flush()
