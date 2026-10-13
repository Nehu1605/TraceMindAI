-- TraceMind AI - incidents, alert groups and graph edges (Phase 3 reference).
-- The pipeline writes JSON; this schema is the PostgreSQL target for the
-- persistence phase.

CREATE TABLE IF NOT EXISTS incidents (
    incident_id   TEXT PRIMARY KEY,
    start_time    TIMESTAMPTZ NOT NULL,
    end_time      TIMESTAMPTZ NOT NULL,
    severity      TEXT NOT NULL,
    services      TEXT[] NOT NULL DEFAULT '{}',
    alert_count   INTEGER NOT NULL DEFAULT 0,
    alertnames    TEXT[] NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS incident_alerts (
    incident_id   TEXT NOT NULL REFERENCES incidents (incident_id) ON DELETE CASCADE,
    event_id      TEXT NOT NULL,
    PRIMARY KEY (incident_id, event_id)
);

CREATE TABLE IF NOT EXISTS graph_edges (
    source          TEXT NOT NULL,
    target          TEXT NOT NULL,
    edge_type       TEXT NOT NULL,
    evidence_quality TEXT NOT NULL,
    weight          DOUBLE PRECISION NOT NULL,
    attributes      JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (source, target, edge_type)
);

CREATE INDEX IF NOT EXISTS idx_graph_edges_type ON graph_edges (edge_type);
CREATE INDEX IF NOT EXISTS idx_incidents_time ON incidents (start_time);
