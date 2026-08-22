"""search columns

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION provisions_tsv_update() RETURNS trigger AS $$
        BEGIN
          NEW.tsv := to_tsvector('english', coalesce(NEW.heading, '') || ' ' || NEW.text);
          RETURN NEW;
        END $$ LANGUAGE plpgsql;
        CREATE TRIGGER provisions_tsv BEFORE INSERT OR UPDATE OF heading, text ON provisions
          FOR EACH ROW EXECUTE FUNCTION provisions_tsv_update();
        UPDATE provisions SET text = text;

        CREATE OR REPLACE FUNCTION paragraphs_tsv_update() RETURNS trigger AS $$
        BEGIN
          NEW.tsv := to_tsvector('english', NEW.text);
          RETURN NEW;
        END $$ LANGUAGE plpgsql;
        CREATE TRIGGER paragraphs_tsv BEFORE INSERT OR UPDATE OF text ON paragraphs
          FOR EACH ROW EXECUTE FUNCTION paragraphs_tsv_update();
        UPDATE paragraphs SET text = text;

        CREATE INDEX ix_provisions_embedding ON provisions USING hnsw (embedding vector_cosine_ops);
        CREATE INDEX ix_paragraphs_embedding ON paragraphs USING hnsw (embedding vector_cosine_ops);
    """)


def downgrade() -> None:
    op.execute("""
        DROP INDEX IF EXISTS ix_paragraphs_embedding;
        DROP INDEX IF EXISTS ix_provisions_embedding;
        DROP TRIGGER IF EXISTS paragraphs_tsv ON paragraphs;
        DROP FUNCTION IF EXISTS paragraphs_tsv_update;
        DROP TRIGGER IF EXISTS provisions_tsv ON provisions;
        DROP FUNCTION IF EXISTS provisions_tsv_update;
    """)
