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
    kind: str
    payload: dict


class BaseMode(ABC):
    name: str

    @abstractmethod
    def run(self, session: Session, llm: LLMClient, framework: BaseFramework,
            embedder: Embedder, **inputs) -> AsyncIterator[ReasoningEvent]: ...
