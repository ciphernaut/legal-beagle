from __future__ import annotations

import hashlib
import math
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.graph.models import EMBED_DIM, Paragraph, Provision


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FakeEmbedder:
    dim = EMBED_DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            h = hashlib.sha256(t.encode()).digest()
            vals = [((h[i % 32] + i * 31) % 251) / 251.0 - 0.5 for i in range(self.dim)]
            norm = math.sqrt(sum(v * v for v in vals))
            out.append([v / norm for v in vals])
        return out


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        # sentence-transformers >=5 renamed this; keep a fallback for older versions.
        get_dim = getattr(
            self._model,
            "get_embedding_dimension",
            self._model.get_sentence_embedding_dimension,
        )
        self.dim = get_dim()
        assert self.dim == EMBED_DIM, f"model dim {self.dim} != {EMBED_DIM}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, normalize_embeddings=True, batch_size=32).tolist()


def _embed_table(session: Session, model, embedder: Embedder, batch_size: int) -> int:
    done = 0
    while True:
        rows = session.scalars(
            select(model).where(model.embedding.is_(None)).limit(batch_size)).all()
        if not rows:
            return done
        texts = [(getattr(r, "heading", None) or "") + " " + r.text for r in rows]
        for row, vec in zip(rows, embedder.embed(texts)):
            row.embedding = vec
        session.flush()
        session.commit()
        done += len(rows)


def embed_pending(session: Session, embedder: Embedder, batch_size: int = 64) -> int:
    return (_embed_table(session, Provision, embedder, batch_size)
            + _embed_table(session, Paragraph, embedder, batch_size))
