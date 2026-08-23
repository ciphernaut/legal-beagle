from pathlib import Path

from sqlalchemy import func, select

from src.graph.models import Paragraph, Provision
from src.graph.seed import seed_reference_data
from src.ingestion.embed import FakeEmbedder, embed_pending
from src.ingestion.sources.oalc import load_oalc

FIXTURE = Path(__file__).parent.parent / "fixtures" / "oalc_sample.jsonl"


def test_fake_embedder_is_deterministic_unit_vectors():
    e = FakeEmbedder()
    a, b = e.embed(["hello", "hello"])
    assert a == b and len(a) == 384
    assert abs(sum(x * x for x in a) - 1.0) < 1e-6


def test_embed_pending_embeds_paragraphs_before_provisions(db_session, monkeypatch):
    seed_reference_data(db_session)
    load_oalc(db_session, FIXTURE,
              sources={"federal_register_of_legislation", "high_court_of_australia"},
              jurisdictions={"commonwealth"})
    db_session.commit()
    assert db_session.scalar(select(func.count(Paragraph.id))) > 0
    assert db_session.scalar(select(func.count(Provision.id))) > 0

    import src.ingestion.embed as embed_mod

    order: list[str] = []
    real_embed_table = embed_mod._embed_table

    def spy_embed_table(session, model, embedder, batch_size):
        order.append(model.__name__)
        return real_embed_table(session, model, embedder, batch_size)

    monkeypatch.setattr(embed_mod, "_embed_table", spy_embed_table)

    embed_mod.embed_pending(db_session, FakeEmbedder(), batch_size=1)
    db_session.commit()

    assert order == ["Paragraph", "Provision"]


def test_embed_pending_fills_all_rows_and_tsv_trigger_fires(db_session):
    seed_reference_data(db_session)
    load_oalc(db_session, FIXTURE,
              sources={"federal_register_of_legislation", "high_court_of_australia"},
              jurisdictions={"commonwealth"})
    db_session.commit()
    n = embed_pending(db_session, FakeEmbedder())
    db_session.commit()
    total = (db_session.scalar(select(func.count(Provision.id)))
             + db_session.scalar(select(func.count(Paragraph.id))))
    assert n == total
    assert db_session.scalar(
        select(func.count(Provision.id)).where(Provision.embedding.is_(None))) == 0
    assert embed_pending(db_session, FakeEmbedder()) == 0
    assert db_session.scalar(select(func.count(Provision.id)).where(Provision.tsv.is_(None))) == 0
