from __future__ import annotations

import asyncio
from pathlib import Path

import yaml
from sqlalchemy.orm import Session

from src.graph.models import NodeType
from src.ingestion.embed import Embedder
from src.ingestion.link import resolve_neutral
from src.reasoning.frameworks.common_law import CommonLawFramework
from src.reasoning.llm.client import LLMClient
from src.reasoning.modes.reverse_engineering import ReverseEngineeringMode


def load_gold(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text())["cases"]


async def _run(session: Session, llm: LLMClient, embedder: Embedder, case_id: int):
    answer, verification = "", {}
    async for ev in ReverseEngineeringMode().run(
        session, llm, CommonLawFramework(), embedder, node_type=NodeType.case, node_id=case_id
    ):
        if ev.kind == "verification":
            verification = ev.payload
        elif ev.kind == "done":
            answer = ev.payload["answer"]
    return answer, verification


def score_case(session: Session, llm: LLMClient, embedder: Embedder, gold: dict) -> dict | None:
    case = resolve_neutral(session, gold["neutral_citation"])
    if case is None:
        return None
    answer, ver = asyncio.run(_run(session, llm, embedder, case.id))
    resolved = {c["raw"] for c in ver["citations"] if c["status"] != "unresolved"}
    expected = set(gold.get("key_authorities", [])) | set(gold.get("key_provisions", []))
    recall = len(expected & resolved) / len(expected) if expected else 1.0
    return {
        "neutral_citation": gold["neutral_citation"],
        "precision": ver["precision"],
        "recall": recall,
        "answer": answer,
    }
