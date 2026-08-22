from __future__ import annotations

from abc import ABC, abstractmethod

from src.retrieval.hybrid import Hit

MAX_CONTEXT_CHARS = 1500


class BaseFramework(ABC):
    name: str

    @abstractmethod
    def build_messages(self, question: str, context: list[Hit]) -> list[dict]: ...

    @staticmethod
    def render_context(context: list[Hit]) -> str:
        parts = []
        for h in context:
            body = h.text if len(h.text) <= MAX_CONTEXT_CHARS else h.text[:MAX_CONTEXT_CHARS] + "…"
            parts.append(f"### {h.label}\n{body}")
        return "\n\n".join(parts)
