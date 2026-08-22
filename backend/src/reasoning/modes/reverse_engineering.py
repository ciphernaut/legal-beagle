from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.orm import Session

from src.graph.models import Case, NodeType, Provision
from src.graph.traversal import NodeRef, authority_chain, node_ref
from src.ingestion.embed import Embedder
from src.reasoning.frameworks.base import BaseFramework
from src.reasoning.llm.client import LLMClient
from src.reasoning.modes.base import BaseMode, ReasoningEvent
from src.reasoning.verifier import verify
from src.retrieval.hybrid import Hit, search


def _node_text(session: Session, ref: NodeRef) -> str:
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


def _ref_to_hit(session: Session, ref: NodeRef, via: str) -> Hit:
    return Hit(ref.type, ref.id, ref.label, _node_text(session, ref), 1.0, via)


class ReverseEngineeringMode(BaseMode):
    name = "reverse_engineering"

    async def run(self, session: Session, llm: LLMClient, framework: BaseFramework,
                  embedder: Embedder, **inputs) -> AsyncIterator[ReasoningEvent]:
        node_type: NodeType = inputs["node_type"]
        node_id: int = inputs["node_id"]
        root = node_ref(session, node_type, node_id)
        if root is None:
            raise ValueError(f"no such node {node_type}:{node_id}")

        hits: list[Hit] = [_ref_to_hit(session, root, "root")]
        seen = {(root.type, root.id)}
        for ref in authority_chain(session, node_type, node_id):
            if (ref.type, ref.id) not in seen:
                seen.add((ref.type, ref.id))
                hits.append(_ref_to_hit(session, ref, "graph"))
        for h in search(session, root.label, embedder, k=5, expand=False):
            if (h.type, h.id) not in seen:
                seen.add((h.type, h.id))
                hits.append(h)

        yield ReasoningEvent("context", {"nodes": [
            {"type": h.type.value, "id": h.id, "label": h.label, "via": h.via} for h in hits]})

        question = (f"Explain the chain of authority behind {root.label}: which constitutional "
                    f"head of power or provision authorises it, which cases interpret it, and "
                    f"what principles they establish.")
        messages = framework.build_messages(question, hits)
        parts: list[str] = []
        async for tok in llm.stream(messages):
            parts.append(tok)
            yield ReasoningEvent("token", {"text": tok})
        answer = "".join(parts)

        v = verify(session, answer, seen)
        yield ReasoningEvent("verification", {
            "precision": v.precision,
            "citations": [{
                "raw": c.raw, "status": c.status.value,
                "node": ({"type": c.node.type.value, "id": c.node.id, "label": c.node.label}
                         if c.node else None),
            } for c in v.citations],
        })
        yield ReasoningEvent("done", {"answer": answer})
