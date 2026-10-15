-- TraceMind AI - unified event store schema (MVP reference).
-- The Phase 2 pipeline writes JSONL; this schema is provided for the later
-- phases that persist incidents and evaluation results in PostgreSQL.

CREATE TABLE IF NOT EXISTS normalized_events (
    event_id            TEXT PRIMARY KEY,
    event_time          TIMESTAMPTZ NOT NULL,
    ingestion_time      TIMESTAMPTZ NOT NULL,
    source_type         TEXT NOT NULL,
    event_type          TEXT NOT NULL,
    service_name        TEXT,
    trace_id            TEXT,
    span_id             TEXT,
    parent_span_id      TEXT,
    severity            TEXT NOT NULL,
    message             TEXT,
    duration_ms         DOUBLE PRECISION,
    status_code         INTEGER,
    metric_name         TEXT,
    metric_value        DOUBLE PRECISION,
    deployment_id       TEXT,
    evidence_quality    TEXT NOT NULL,
    is_late             BOOLEAN NOT NULL DEFAULT FALSE,
    clock_skew_suspected BOOLEAN NOT NULL DEFAULT FALSE,
    attributes          JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_reference    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_time ON normalized_events (event_time);
CREATE INDEX IF NOT EXISTS idx_events_trace ON normalized_events (trace_id);
CREATE INDEX IF NOT EXISTS idx_events_service ON normalized_events (service_name);

CREATE TABLE IF NOT EXISTS quarantined_events (
    id               BIGSERIAL PRIMARY KEY,
    source_reference TEXT NOT NULL,
    reasons          TEXT[] NOT NULL,
    raw              JSONB NOT NULL,
    quarantined_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
