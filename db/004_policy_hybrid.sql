-- Hybrid parent-child policy search. Idempotent, like 002/003: compose
-- mounts it as 04-policy-hybrid.sql; 'python -m app.cli migrate' applies it.
--
-- Children (policy_chunks, ~60 tokens) are what queries match, by vector
-- and by full-text (keyword) search; results are their parent ## sections
-- (policy_sections), each returned once.

CREATE TABLE IF NOT EXISTS policy_sections (
    id              TEXT PRIMARY KEY,          -- <doc_slug>:<section_slug>
    doc_slug        TEXT NOT NULL,
    doc_title       TEXT NOT NULL,
    section         TEXT NOT NULL,
    effective_date  DATE,
    content         TEXT NOT NULL,             -- the whole section
    content_hash    TEXT NOT NULL,
    indexed_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE policy_chunks ADD COLUMN IF NOT EXISTS parent_id TEXT;

-- Full-text search over each child, title and section name included.
ALTER TABLE policy_chunks ADD COLUMN IF NOT EXISTS search_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', doc_title || ' ' || section || ' ' || content)) STORED;
CREATE INDEX IF NOT EXISTS idx_policy_chunks_tsv ON policy_chunks USING gin (search_tsv);
CREATE INDEX IF NOT EXISTS idx_policy_chunks_parent ON policy_chunks(parent_id);
