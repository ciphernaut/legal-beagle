from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.graph.models import Case, NodeType, Provision
from src.graph.traversal import neighbours, node_ref

router = APIRouter(prefix="/nodes", tags=["nodes"])


def _text(session: Session, type: NodeType, id: int) -> str:
    if type == NodeType.provision:
        return session.get(Provision, id).text
    if type == NodeType.case:
        return session.get(Case, id).summary or ""
    return ""


@router.get("/{type}/{id}")
def get_node(type: NodeType, id: int, session: Session = Depends(get_db)) -> dict:  # noqa: B008
    ref = node_ref(session, type, id)
    if ref is None:
        raise HTTPException(404, "node not found")
    out = []
    for n in neighbours(session, type, id):
        direction = "out" if (n.edge.src_type == type and n.edge.src_id == id) else "in"
        out.append({
            "kind": n.edge.kind, "direction": direction, "treatment": n.edge.treatment,
            "extraction": n.edge.extraction, "confidence": n.edge.confidence,
            "node": {"type": n.node.type.value, "id": n.node.id, "label": n.node.label},
        })
    return {"type": ref.type.value, "id": ref.id, "label": ref.label,
            "text": _text(session, type, id), "neighbours": out}
