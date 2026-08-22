"""provenance columns on provisions and edges, plus FK indexes

Spec constraint 3: every node and edge row carries source_url, source_licence and
extraction. Provisions and edges were missing part of that. Jurisdictions and courts
stay bare — they are reference data seeded from code, not ingested.

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_FK_INDEXES = [
    ("ix_courts_jurisdiction_id", "courts", "jurisdiction_id"),
    ("ix_cases_court_id", "cases", "court_id"),
    ("ix_act_versions_act_id", "act_versions", "act_id"),
    ("ix_provisions_act_version_id", "provisions", "act_version_id"),
    ("ix_paragraphs_judgment_id", "paragraphs", "judgment_id"),
    ("ix_edges_evidence_case_id", "edges", "evidence_case_id"),
]


def upgrade() -> None:
    op.add_column("edges", sa.Column("source_licence", sa.String(length=64), nullable=True))
    op.add_column("edges", sa.Column("note", sa.Text(), nullable=True))

    op.add_column("provisions", sa.Column("source_url", sa.Text(), nullable=True))
    op.add_column("provisions", sa.Column("source_licence", sa.String(length=64), nullable=True))
    op.add_column(
        "provisions",
        sa.Column("extraction", sa.String(length=16), nullable=False, server_default="parsed"),
    )
    # Backfill existing provisions from the act version / act they belong to.
    op.execute("""
        UPDATE provisions p
        SET source_url = av.source_url, source_licence = a.source_licence
        FROM act_versions av JOIN acts a ON av.act_id = a.id
        WHERE p.act_version_id = av.id
    """)

    for name, table, column in _FK_INDEXES:
        op.create_index(name, table, [column], unique=False)


def downgrade() -> None:
    for name, table, _column in reversed(_FK_INDEXES):
        op.drop_index(name, table_name=table)

    op.drop_column("provisions", "extraction")
    op.drop_column("provisions", "source_licence")
    op.drop_column("provisions", "source_url")

    op.drop_column("edges", "note")
    op.drop_column("edges", "source_licence")
