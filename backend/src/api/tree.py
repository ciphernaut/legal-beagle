from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.graph.models import Act, ActVersion, Edge, EdgeKind, NodeType, Provision
from src.graph.traversal import NodeRef, neighbours, node_ref

router = APIRouter(tags=["tree"])


def _ref_dict(ref: NodeRef) -> dict:
    return {"type": ref.type.value, "id": ref.id, "label": ref.label}


def _edge_dict(edge: Edge) -> dict:
    """Provenance of the edge that put this child under its parent."""
    return {"kind": edge.kind, "extraction": edge.extraction, "confidence": edge.confidence}


def _resolve_root(session: Session, root: str) -> Act | None:
    if root == "constitution":
        return session.scalars(select(Act).where(Act.title.ilike("%Constitution Act%"))).first()
    if root.startswith("act:") and root[4:].isdigit():
        return session.get(Act, int(root[4:]))
    return None


@router.get("/tree")
def get_tree(root: str = Query(...), session: Session = Depends(get_db)) -> dict:  # noqa: B008
    act = _resolve_root(session, root)
    if act is None:
        raise HTTPException(404, "root not found")
    latest = session.scalars(
        select(ActVersion).where(ActVersion.act_id == act.id)
        .order_by(ActVersion.in_force_from.desc().nulls_last())
    ).first()
    provisions = session.scalars(
        select(Provision).where(Provision.act_version_id == latest.id,
                                Provision.parent_provision_id.is_(None),
                                Provision.identifier != "preamble")
        .order_by(Provision.id)
    ).all() if latest else []
    children = []
    for p in provisions:
        cases = [{"node": _ref_dict(n.node), "edge": _edge_dict(n.edge), "children": []}
                 for n in neighbours(session, NodeType.provision, p.id, [EdgeKind.INTERPRETS], "in")]
        # Provisions hang off their act structurally (act_version_id), not via an edge row.
        children.append({"node": _ref_dict(node_ref(session, NodeType.provision, p.id)),
                         "edge": None, "children": cases})
    return {"node": _ref_dict(node_ref(session, NodeType.act, act.id)),
            "edge": None, "children": children}
