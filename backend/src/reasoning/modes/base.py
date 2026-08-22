from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass

from sqlalchemy.orm import Session

from src.ingestion.embed import Embedder
from src.reasoning.frameworks.base import BaseFramework
from src.reasoning.llm.client import LLMClient


@dataclass
class ReasoningEvent:
    """One event in a reasoning stream.

    Event kinds, in the order a successful run emits them:

    - ``context``      — the retrieved nodes the LLM is allowed to see.
    - ``token``        — a chunk of raw LLM prose. **Unverified**: nothing in a ``token``
      event has been checked against the corpus, and it must not be presented as
      authoritative until a ``verification`` event arrives.
    - ``verification`` — per-citation statuses and precision for the completed answer.
    - ``done``         — terminal; carries the full answer.

    A stream may instead terminate with:

    - ``error``        — terminal; the run failed (typically before verification completed),
      so any ``token`` text already delivered stays unverified. Payload carries
      ``message`` and ``verified: False``.

    Exactly one of ``done`` or ``error`` ends a stream.
    """

    kind: str
    payload: dict


class BaseMode(ABC):
    name: str

    @abstractmethod
    def run(self, session: Session, llm: LLMClient, framework: BaseFramework,
            embedder: Embedder, **inputs) -> AsyncIterator[ReasoningEvent]: ...
