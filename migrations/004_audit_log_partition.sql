-- RAG-09 S1: Partitioned PostgreSQL audit log table
-- Partitioned by month on timestamp for efficient range queries and retention management.

CREATE TABLE IF NOT EXISTS query_audit_log (
    id              BIGSERIAL,
    tenant          TEXT        NOT NULL,
    question        TEXT        NOT NULL,
    top_k           INT         NOT NULL,
    result_count    INT         NOT NULL DEFAULT 0,
    top_score       FLOAT,
    refused         BOOLEAN     NOT NULL DEFAULT FALSE,
    refusal_reason  TEXT,
    retrieval_ms    FLOAT       NOT NULL DEFAULT 0.0,
    generation_ms   FLOAT       NOT NULL DEFAULT 0.0,
    cost_tokens     FLOAT       NOT NULL DEFAULT 1.0,
    "timestamp"     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, "timestamp")
) PARTITION BY RANGE ("timestamp");

-- Create monthly partitions for the next 12 months (ops can add more as needed)
DO $$
DECLARE
    yr   INT;
    mo   INT;
    start_dt DATE;
    end_dt   DATE;
    part_name TEXT;
BEGIN
    FOR i IN 0..11 LOOP
        start_dt  := DATE_TRUNC('month', NOW()) + (i || ' months')::interval;
        end_dt    := start_dt + INTERVAL '1 month';
        yr        := EXTRACT(YEAR  FROM start_dt);
        mo        := EXTRACT(MONTH FROM start_dt);
        part_name := FORMAT('query_audit_log_%s_%s', yr, LPAD(mo::text, 2, '0'));
        IF NOT EXISTS (
            SELECT 1 FROM pg_class c
            JOIN   pg_namespace n ON n.oid = c.relnamespace
            WHERE  c.relname = part_name
        ) THEN
            EXECUTE FORMAT(
                'CREATE TABLE %I PARTITION OF query_audit_log FOR VALUES FROM (%L) TO (%L)',
                part_name, start_dt, end_dt
            );
        END IF;
    END LOOP;
END;
$$;

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_audit_tenant_ts ON query_audit_log (tenant, "timestamp" DESC);
CREATE INDEX IF NOT EXISTS idx_audit_refused   ON query_audit_log (tenant, refused) WHERE refused = TRUE;

-- Per-tenant timezone configuration
CREATE TABLE IF NOT EXISTS tenant_config (
    tenant      TEXT PRIMARY KEY,
    timezone    TEXT NOT NULL DEFAULT 'UTC',
    daily_quota  INT  NOT NULL DEFAULT 100000,
    hourly_quota INT  NOT NULL DEFAULT 10000,
    qps          FLOAT NOT NULL DEFAULT 10.0,
    burst_size   INT   NOT NULL DEFAULT 20,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE query_audit_log IS 'RAG-09: Durable partitioned query audit trail';
COMMENT ON TABLE tenant_config   IS 'RAG-09: Per-tenant quota and timezone configuration';
