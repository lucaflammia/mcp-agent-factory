-- Migration 001: pgvector knowledge store
-- Run once against the target Postgres instance:
--   psql $DATABASE_URL -f migrations/001_pgvector_init.sql
--
-- Requires pgvector extension (available in pgvector/pgvector Docker image
-- and Supabase/Neon/RDS with pgvector enabled).

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chunks (
    id          BIGSERIAL PRIMARY KEY,
    owner_id    TEXT        NOT NULL,
    chunk_id    TEXT        NOT NULL,
    text        TEXT        NOT NULL,
    -- embedding dimension must match your Embedder output (default: all-MiniLM-L6-v2 = 384)
    embedding   vector(384) NOT NULL,
    ts          TSVECTOR    NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Tenant isolation index: every query filters on owner_id first.
CREATE INDEX IF NOT EXISTS idx_chunks_owner_id ON chunks (owner_id);

-- Approximate nearest-neighbour index for cosine distance (pgvector IVFFlat).
-- lists=100 is a good starting point for up to ~1M rows per tenant.
-- Rebuild with larger lists when the table grows beyond that.
CREATE INDEX IF NOT EXISTS idx_chunks_embedding
    ON chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Full-text search index for hybrid retrieval.
CREATE INDEX IF NOT EXISTS idx_chunks_ts ON chunks USING GIN (ts);

-- Unique constraint so upsert (ON CONFLICT) works correctly.
ALTER TABLE chunks
    ADD CONSTRAINT IF NOT EXISTS uq_chunks_owner_chunk UNIQUE (owner_id, chunk_id);
