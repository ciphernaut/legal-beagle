from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.graph.models import EdgeKind, NodeType
from src.graph.traversal import neighbours, node_ref
from src.ingestion.embed import Embedder

RRF_K = 60


@dataclass
class Hit:
    type: NodeType
    id: int
    label: str
    text: str
    score: float
    via: str


_FTS_SQL = text("""
    SELECT kind, row_id, txt, rank FROM (
      SELECT 'provision' AS kind, p.id AS row_id, p.text AS txt, ts_rank_cd(p.tsv, q) AS rank
      FROM provisions p, websearch_to_tsquery('english', :q) q WHERE p.tsv @@ q
      UNION ALL
      SELECT 'paragraph', pa.id, pa.text, ts_rank_cd(pa.tsv, q)
      FROM paragraphs pa, websearch_to_tsquery('english', :q) q WHERE pa.tsv @@ q
    ) s ORDER BY rank DESC LIMIT :n
""")

_VEC_SQL = text("""
    SELECT kind, row_id, txt, dist FROM (
      SELECT 'provision' AS kind, p.id AS row_id, p.text AS txt,
             p.embedding <=> CAST(:v AS vector) AS dist
      FROM provisions p WHERE p.embedding IS NOT NULL
      UNION ALL
      SELECT 'paragraph', pa.id, pa.text, pa.embedding <=> CAST(:v AS vector)
      FROM paragraphs pa WHERE pa.embedding IS NOT NULL
    ) s ORDER BY dist ASC LIMIT :n
""")

_PARA_CASE_SQL = text("""
    SELECT c.id FROM paragraphs pa JOIN judgments j ON pa.judgment_id = j.id
    JOIN cases c ON j.case_id = c.id WHERE pa.id = :pid
""")


def _to_node(session: Session, kind: str, row_id: int) -> tuple[NodeType, int]:
    if kind == "provision":
        return NodeType.provision, row_id
    return NodeType.case, session.execute(_PARA_CASE_SQL, {"pid": row_id}).scalar_one()


def search(session: Session, query: str, embedder: Embedder, *, k: int = 10,
           expand: bool = True) -> list[Hit]:
    n = k * 2
    fused: dict[tuple[str, int], dict] = {}

    def accumulate(rows, via: str) -> None:
        for rank, (kind, row_id, txt, _) in enumerate(rows):
            entry = fused.setdefault((kind, row_id), {"text": txt, "score": 0.0, "via": set()})
            entry["score"] += 1.0 / (RRF_K + rank + 1)
            entry["via"].add(via)

    accumulate(session.execute(_FTS_SQL, {"q": query, "n": n}).all(), "fts")
    vec = embedder.embed([query])[0]
    literal = "[" + ",".join(repr(float(x)) for x in vec) + "]"
    accumulate(session.execute(_VEC_SQL, {"v": literal, "n": n}).all(), "vector")

    ranked = sorted(fused.items(), key=lambda kv: kv[1]["score"], reverse=True)[:k]
    hits: list[Hit] = []
    seen: set[tuple[NodeType, int]] = set()
    for (kind, row_id), entry in ranked:
        ntype, nid = _to_node(session, kind, row_id)
        ref = node_ref(session, ntype, nid)
        if ref is None or (ntype, nid) in seen:
            continue
        via = "both" if len(entry["via"]) == 2 else next(iter(entry["via"]))
        hits.append(Hit(ntype, nid, ref.label, entry["text"], entry["score"], via))
        seen.add((ntype, nid))

    if expand:
        for h in list(hits):
            if h.type != NodeType.provision:
                continue
            for nb in neighbours(session, NodeType.provision, h.id, [EdgeKind.INTERPRETS], "in"):
                key = (nb.node.type, nb.node.id)
                if key not in seen:
                    seen.add(key)
                    hits.append(Hit(nb.node.type, nb.node.id, nb.node.label, nb.node.label,
                                    h.score * 0.5, "graph"))
    return hits
