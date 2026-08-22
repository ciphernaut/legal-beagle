from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from src.graph.models import (
    Act,
    Case,
    Court,
    Edge,
    EdgeKind,
    Jurisdiction,
    NodeType,
    Principle,
    Provision,
)

_MODEL = {
    NodeType.jurisdiction: Jurisdiction, NodeType.court: Court, NodeType.act: Act,
    NodeType.provision: Provision, NodeType.case: Case, NodeType.principle: Principle,
}


@dataclass(frozen=True)
class NodeRef:
    type: NodeType
    id: int
    label: str


@dataclass
class Neighbour:
    edge: Edge
    node: NodeRef


def _label(type: NodeType, row) -> str:
    if type == NodeType.act:
        return row.short_name
    if type == NodeType.provision:
        return f"{row.act_version.act.short_name} {row.identifier}"
    if type == NodeType.case:
        return f"{row.name} {row.neutral_citation}"
    return row.name


def node_ref(session: Session, type: NodeType, id: int) -> NodeRef | None:
    row = session.get(_MODEL[type], id)
    return NodeRef(type, id, _label(type, row)) if row else None


def neighbours(session: Session, type: NodeType, id: int,
               kinds: list[EdgeKind] | None = None, direction: str = "both") -> list[Neighbour]:
    conds = []
    if direction in ("out", "both"):
        conds.append((Edge.src_type == type) & (Edge.src_id == id))
    if direction in ("in", "both"):
        conds.append((Edge.dst_type == type) & (Edge.dst_id == id))
    q = select(Edge).where(or_(*conds))
    if kinds:
        q = q.where(Edge.kind.in_([k.value for k in kinds]))
    out = []
    for e in session.scalars(q.order_by(Edge.id)).all():
        if e.src_type == type and e.src_id == id:
            other = (NodeType(e.dst_type), e.dst_id)
        else:
            other = (NodeType(e.src_type), e.src_id)
        ref = node_ref(session, *other)
        if ref:
            out.append(Neighbour(e, ref))
    return out


def authority_chain(session: Session, type: NodeType, id: int) -> list[NodeRef]:
    seen: dict[tuple[NodeType, int], NodeRef] = {}

    def add(ref: NodeRef | None) -> None:
        if ref and (ref.type, ref.id) not in seen:
            seen[(ref.type, ref.id)] = ref

    def heads_of_power(act_id: int) -> None:
        for n in neighbours(session, NodeType.act, act_id, [EdgeKind.AUTHORISED_BY], "out"):
            add(n.node)

    def provision_context(prov_id: int) -> None:
        prov = session.get(Provision, prov_id)
        act_ref = node_ref(session, NodeType.act, prov.act_version.act_id)
        add(act_ref)
        if act_ref:
            heads_of_power(act_ref.id)

    if type == NodeType.case:
        for n in neighbours(session, type, id, [EdgeKind.CITES], "out"):
            add(n.node)
        for n in neighbours(session, type, id, [EdgeKind.INTERPRETS], "out"):
            add(n.node)
            provision_context(n.node.id)
    elif type == NodeType.provision:
        provision_context(id)
        for n in neighbours(session, type, id, [EdgeKind.INTERPRETS], "in"):
            add(n.node)
    elif type == NodeType.act:
        heads_of_power(id)
        for v in session.get(Act, id).versions:
            for p in v.provisions:
                for n in neighbours(session, NodeType.provision, p.id, [EdgeKind.INTERPRETS], "in"):
                    add(n.node)
    return list(seen.values())
