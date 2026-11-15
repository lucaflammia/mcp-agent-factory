-- Migration 002: RAG-05 embedder versioning and dual-write cutover
-- Adds support for multiple embedder versions in a single index with
-- content_hash-based deduplication during backfill.
--
-- Run once against the target Postgres instance after 001:
--   psql $DATABASE_URL -f migrations/002_rag05_embedder_versioning.sql

-- Add embedder_id and content_hash columns to chunks table
ALTER TABLE chunks
    ADD COLUMN IF NOT EXISTS embedder_id TEXT NOT NULL DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS content_hash TEXT;

-- Populate content_hash from existing chunk_id if empty (backward compatibility)
UPDATE chunks
SET content_hash = chunk_id
WHERE content_hash IS NULL;

-- Make content_hash NOT NULL after backfill
ALTER TABLE chunks
    ALTER COLUMN content_hash SET NOT NULL;

-- Create index on (owner_id, embedder_id) for efficient version-specific queries
CREATE INDEX IF NOT EXISTS idx_chunks_owner_embedder_id
    ON chunks (owner_id, embedder_id);

-- Create composite index on (owner_id, embedder_id, embedding) for version-specific ANN
CREATE INDEX IF NOT EXISTS idx_chunks_owner_embedder_embedding
    ON chunks USING ivfflat (embedding vector_cosine_ops)
    WHERE embedder_id IS NOT NULL;

-- Create unique constraint on (owner_id, embedder_id, content_hash) for deduplication
ALTER TABLE chunks
    ADD CONSTRAINT IF NOT EXISTS uq_chunks_owner_embedder_hash
    UNIQUE (owner_id, embedder_id, content_hash);

-- Add updated_at timestamp for tracking when each version was added
ALTER TABLE chunks
    ADD COLUMN IF NOT EXISTS version_added_at TIMESTAMPTZ NOT NULL DEFAULT now();
