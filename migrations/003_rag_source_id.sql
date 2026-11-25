-- Migration 003: Add source_id column for tracking document provenance
-- Extends chunks table with source_id for backup/restore and deletion workflows.

-- Add source_id column if it doesn't exist
ALTER TABLE chunks
    ADD COLUMN IF NOT EXISTS source_id TEXT;

-- Create index on (owner_id, source_id) for efficient source-based deletions
CREATE INDEX IF NOT EXISTS idx_chunks_owner_source_id
    ON chunks (owner_id, source_id);
