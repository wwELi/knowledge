"""Initial schema: pgvector extension, documents + chunks tables, HNSW index.

Mirrors the former backend/db/init.sql exactly (IF NOT EXISTS kept so the
first upgrade also succeeds on a database bootstrapped by the old script).
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

CREATE_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    filename text NOT NULL,
    filepath text NOT NULL,
    status text NOT NULL DEFAULT 'processing' CHECK (status IN ('processing','ready','failed')),
    chunk_count int NOT NULL DEFAULT 0,
    error text,
    created_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
    id bigserial PRIMARY KEY,
    document_id uuid REFERENCES documents ON DELETE CASCADE,
    content text NOT NULL,
    page int,
    embedding vector(512) NOT NULL
);

CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx
    ON chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 128);

CREATE INDEX IF NOT EXISTS chunks_document_id_idx ON chunks (document_id);
"""

DROP_SQL = """
DROP INDEX IF EXISTS chunks_document_id_idx;
DROP INDEX IF EXISTS chunks_embedding_hnsw_idx;
DROP TABLE IF EXISTS chunks;
DROP TABLE IF EXISTS documents;
DROP EXTENSION IF EXISTS vector;
"""


def upgrade() -> None:
    op.execute(CREATE_SQL)


def downgrade() -> None:
    op.execute(DROP_SQL)
