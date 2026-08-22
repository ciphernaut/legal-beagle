import os
from functools import lru_cache

from src.config import get_settings
from src.db import SessionLocal
from src.ingestion.embed import Embedder, FakeEmbedder, SentenceTransformerEmbedder
from src.reasoning.llm.client import (
    FailingLLMClient,
    FakeLLMClient,
    LiteLLMClient,
    LLMClient,
)


def get_db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@lru_cache
def get_embedder() -> Embedder:
    if os.environ.get("EMBEDDER") == "fake":
        return FakeEmbedder()
    return SentenceTransformerEmbedder(get_settings().embed_model)


def get_llm() -> LLMClient:
    spec = os.environ.get("LLM", "")
    if spec.startswith("fake:"):
        return FakeLLMClient(spec[5:])
    if spec.startswith("fake-error:"):
        return FailingLLMClient(spec[11:])
    s = get_settings()
    return LiteLLMClient(s.llm_model, s.llm_api_base)
