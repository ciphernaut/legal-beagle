"""Turning graph node references into retrieval hits with real document text.

Shared by ``src.retrieval.hybrid`` (graph expansion) and
``src.reasoning.modes.reverse_engineering`` (authority chain) so both put the same
text in front of the LLM — previously the expansion path used the node's label.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.graph.models import Case, NodeType, Provision
from src.graph.traversal import NodeRef
from src.retrieval.hybrid import Hit


def node_text(session: Session, ref: NodeRef) -> str:
    """The document text a node contributes to the LLM context."""
    if ref.type == NodeType.provision:
        p = session.get(Provision, ref.id)
        return f"{p.heading or ''}\n{p.text}".strip()
    if ref.type == NodeType.case:
        c = session.get(Case, ref.id)
        if c.summary:
            return c.summary
        paras = sorted(c.judgments[0].paragraphs, key=lambda x: x.number)[:3] if c.judgments else []
        return "\n".join(p.text for p in paras) or c.name
    return ref.label


def ref_to_hit(session: Session, ref: NodeRef, via: str, score: float = 1.0) -> Hit:
    return Hit(ref.type, ref.id, ref.label, node_text(session, ref), score, via)
