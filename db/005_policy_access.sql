-- Access levels for policy documents, and the keys that grant them.
-- Idempotent; compose mounts it as 05-policy-access.sql, 'python -m app.cli
-- migrate' applies it.
--
-- Every document is public or internal (its front matter); its child chunks
-- and parent sections carry that level, and every search query filters on
-- it in SQL, before ranking. Access comes only from the caller's key.

ALTER TABLE policy_chunks   ADD COLUMN IF NOT EXISTS level TEXT NOT NULL DEFAULT 'public';
ALTER TABLE policy_sections ADD COLUMN IF NOT EXISTS level TEXT NOT NULL DEFAULT 'public';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'policy_chunks_level_check') THEN
        ALTER TABLE policy_chunks ADD CONSTRAINT policy_chunks_level_check CHECK (level IN ('public', 'internal'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'policy_sections_level_check') THEN
        ALTER TABLE policy_sections ADD CONSTRAINT policy_sections_level_check CHECK (level IN ('public', 'internal'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_policy_chunks_level ON policy_chunks(level);

-- Policy-access keys: 'pk_' + 32 random bytes, stored as SHA-256 only.
-- 'python -m app.cli policy-keys create <name> --levels public,internal'.
CREATE TABLE IF NOT EXISTS policy_access_keys (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    key_hash    TEXT NOT NULL UNIQUE,
    levels      TEXT[] NOT NULL CHECK (levels <@ ARRAY['public', 'internal'] AND cardinality(levels) > 0),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at  TIMESTAMPTZ
);
