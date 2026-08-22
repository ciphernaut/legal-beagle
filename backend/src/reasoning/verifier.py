"""Check every citation an LLM emits against the corpus.

Four outcomes are possible:

- ``resolved``                   — resolves to a node that was in the retrieved context.
- ``resolved_outside_context``   — resolves to a real corpus node the LLM was not shown.
- ``unresolved``                 — does not resolve to anything: treat as hallucinated.
- ``unverifiable``               — cannot be checked, because no reported-citation index
  exists in Phase 1. Reported citations (e.g. ``(1992) 175 CLR 1``, which is Mabo) fall
  here. They are neither credited nor blamed: precision excludes them from both the
  numerator and the denominator.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.orm import Session

from src.graph.models import NodeType
from src.graph.traversal import NodeRef, node_ref
from src.ingestion.link import resolve_neutral, resolve_section
from src.ingestion.parsers.citation_parser import parse_citations


class CitationStatus(StrEnum):
    resolved = "resolved"
    resolved_outside_context = "resolved_outside_context"
    unresolved = "unresolved"
    unverifiable = "unverifiable"


@dataclass
class VerifiedCitation:
    raw: str
    status: CitationStatus
    node: NodeRef | None


@dataclass
class Verification:
    citations: list[VerifiedCitation]
    precision: float


def _classify(ref: NodeRef | None, context: set[tuple[NodeType, int]]) -> CitationStatus:
    if ref is None:
        return CitationStatus.unresolved
    if (ref.type, ref.id) in context:
        return CitationStatus.resolved
    return CitationStatus.resolved_outside_context


def verify(session: Session, answer: str,
           context_nodes: set[tuple[NodeType, int]]) -> Verification:
    c = parse_citations(answer)
    out: list[VerifiedCitation] = []
    for n in c.neutral:
        case = resolve_neutral(session, n.raw)
        ref = node_ref(session, NodeType.case, case.id) if case else None
        out.append(VerifiedCitation(n.raw, _classify(ref, context_nodes), ref))
    for s in c.sections:
        prov = resolve_section(session, s.section, s.act_hint)
        ref = node_ref(session, NodeType.provision, prov.id) if prov else None
        out.append(VerifiedCitation(s.raw, _classify(ref, context_nodes), ref))
    for r in c.reported:
        out.append(VerifiedCitation(r.raw, CitationStatus.unverifiable, None))
    checkable = [v for v in out if v.status != CitationStatus.unverifiable]
    ok = sum(1 for v in checkable if v.status != CitationStatus.unresolved)
    return Verification(out, ok / len(checkable) if checkable else 1.0)
