from __future__ import annotations

from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.graph.models import Act, Edge, EdgeKind, Extraction, NodeType
from src.ingestion.link import edge_exists, resolve_section

DEFAULT_PATH = Path(__file__).parent / "curated_edges.yaml"


def load_curated_edges(session: Session, path: Path | None = None) -> int:
    data = yaml.safe_load((path or DEFAULT_PATH).read_text())
    added = 0
    for item in data.get("authorised_by", []):
        act = session.scalars(select(Act).where(Act.short_name.ilike(f"{item['act']}%"))).first()
        if act is None:
            continue
        for head in item["heads_of_power"]:
            prov = resolve_section(session, head, "Constitution")
            if prov is None or edge_exists(session, NodeType.act, act.id, NodeType.provision,
                                           prov.id, EdgeKind.AUTHORISED_BY):
                continue
            session.add(Edge(src_type=NodeType.act, src_id=act.id, dst_type=NodeType.provision,
                             dst_id=prov.id, kind=EdgeKind.AUTHORISED_BY,
                             extraction=Extraction.curated, confidence=1.0,
                             source_url=f"curated:{item.get('note', '')}"))
            added += 1
    session.flush()
    return added
