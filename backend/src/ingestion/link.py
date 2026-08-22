from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.graph.models import (
    Act,
    ActVersion,
    Case,
    Edge,
    EdgeKind,
    Extraction,
    NodeType,
    Paragraph,
    Provision,
)
from src.ingestion.parsers.citation_parser import parse_citations
from src.ingestion.sources.oalc import short_name


def resolve_neutral(session: Session, raw: str) -> Case | None:
    return session.scalar(select(Case).where(Case.neutral_citation == raw))


def resolve_section(session: Session, section: str, act_hint: str | None) -> Provision | None:
    ident = f"s{section}"
    q = (
        select(Provision)
        .join(ActVersion, Provision.act_version_id == ActVersion.id)
        .join(Act, ActVersion.act_id == Act.id)
        .where(Provision.identifier == ident)
        .order_by(ActVersion.in_force_from.desc().nulls_last())
    )
    if act_hint is None:
        rows = session.scalars(q).all()
        acts = {r.act_version.act_id for r in rows}
        return rows[0] if len(acts) == 1 else None
    if act_hint.lower() == "constitution":
        q = q.where(Act.title.ilike("%Constitution Act%"))
    else:
        q = q.where(Act.short_name.ilike(f"{short_name(act_hint)}%"))
    return session.scalars(q).first()


def edge_exists(session: Session, src_type, src_id, dst_type, dst_id, kind) -> bool:
    n = session.scalar(
        select(func.count()).select_from(Edge).where(
            Edge.src_type == src_type, Edge.src_id == src_id,
            Edge.dst_type == dst_type, Edge.dst_id == dst_id, Edge.kind == kind,
        )
    )
    return n > 0


def link_case_citations(session: Session) -> tuple[int, int]:
    cites = interprets = 0
    for para in session.scalars(select(Paragraph)).all():
        case = para.judgment.case
        c = parse_citations(para.text)
        for n in c.neutral:
            target = resolve_neutral(session, n.raw)
            if target and target.id != case.id and not edge_exists(
                session, NodeType.case, case.id, NodeType.case, target.id, EdgeKind.CITES
            ):
                session.add(Edge(src_type=NodeType.case, src_id=case.id, dst_type=NodeType.case,
                                 dst_id=target.id, kind=EdgeKind.CITES, treatment=None,
                                 extraction=Extraction.parsed, confidence=1.0,
                                 source_url=case.source_url))
                cites += 1
        for s in c.sections:
            prov = resolve_section(session, s.section, s.act_hint)
            if prov and not edge_exists(
                session, NodeType.case, case.id, NodeType.provision, prov.id, EdgeKind.INTERPRETS
            ):
                session.add(Edge(src_type=NodeType.case, src_id=case.id,
                                 dst_type=NodeType.provision, dst_id=prov.id,
                                 kind=EdgeKind.INTERPRETS, extraction=Extraction.parsed,
                                 confidence=1.0, source_url=case.source_url))
                interprets += 1
        session.flush()
    return cites, interprets
