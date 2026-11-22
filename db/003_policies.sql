-- Policy knowledge base: chunks of bank-service/policies/*.md with their
-- embeddings, for GET /policies/search. Idempotent, like 002_merchants.sql:
-- compose mounts it as 03-policies.sql, and 'python -m app.cli migrate'
-- applies it to an existing database. Filled by 'python -m app.cli
-- index-policies'.
--
-- Needs pgvector. CREATE EXTENSION needs a superuser the first time; in
-- compose the init scripts run as one. On a local Postgres, run it once as
-- a superuser: psql -d anvil_bank -c "CREATE EXTENSION IF NOT EXISTS vector;"
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS policy_chunks (
    id              TEXT PRIMARY KEY,          -- <doc_slug>:<section_slug>:<n>
    doc_slug        TEXT NOT NULL,
    doc_title       TEXT NOT NULL,
    section         TEXT NOT NULL,
    chunk_index     INT NOT NULL DEFAULT 0,    -- position within a split section
    effective_date  DATE,
    content         TEXT NOT NULL,
    -- SHA-256 of what was embedded (title, section, content) and the model,
    -- so re-indexing skips chunks that haven't changed.
    content_hash    TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    embedding       vector(1536) NOT NULL,
    indexed_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_policy_chunks_doc ON policy_chunks(doc_slug);

-- HNSW on cosine distance: no training step (unlike IVFFlat, whose lists
-- need data to be tuned), so it works from the first row. With tens of
-- chunks Postgres may well choose an exact scan anyway.
CREATE INDEX IF NOT EXISTS idx_policy_chunks_embedding
    ON policy_chunks USING hnsw (embedding vector_cosine_ops);
