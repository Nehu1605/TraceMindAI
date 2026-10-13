# Phase 2 - Telemetry Collection, Normalization & Preprocessing

This phase turns heterogeneous, messy raw telemetry into a single clean,
normalized event stream that later phases can correlate. It also delivers the
robustness work from the improvement plan that this phase was scoped to carry:
**I6 (messy telemetry)** and **I10 (raw alert ingestion)**.

There is still no correlation, RCA or LLM logic here - this phase only makes
the data trustworthy and uniformly shaped.

## Deliverables

| Item | Location |
|---|---|
| Unified event schema | `ingestion/schema.py` |
| Normalization helpers (time/service/severity/ids) | `ingestion/normalize.py`, `ingestion/constants.py` |
| Parsers (traces/logs/metrics/deployments/alerts) | `ingestion/parsers.py` |
| Validation, quarantine & broken-link detection | `ingestion/validation.py` |
| Clock-tolerant temporal utilities | `ingestion/temporal.py` |
| Data-quality reporting | `ingestion/quality.py` |
| Event store (JSONL + report) | `ingestion/store.py` |
| Pipeline + CLI | `ingestion/pipeline.py` |
| Postgres event-store schema (reference) | `ingestion/sql/schema.sql` |
| Synthetic telemetry generator (with defect injection) | `simulator/generate_telemetry.py` |
| Prometheus alert rules + Alertmanager (I10) | `telemetry/alerts.yml`, `telemetry/alertmanager.yml` |
| Tests | `tests/unit`, `tests/integration`, `tests/scenarios` |

## Unified event schema

Every raw record - span, log line, metric sample, deployment or raw alert -
becomes one `NormalizedEvent` with a common set of fields:

```
event_id, event_time, ingestion_time, source_type, event_type,
service_name, trace_id, span_id, parent_span_id, severity, message,
duration_ms, status_code, metric_name, metric_value, deployment_id,
attributes, source_reference, evidence_quality, is_late,
clock_skew_suspected
```

`event_id` is deterministic (a hash of the identifying fields), which makes
de-duplication trivial and keeps runs reproducible.

### Evidence quality

Each event is labelled with how strongly it can be linked to a request:

* `direct`    - carries a valid trace/span id,
* `inferred`  - linked by service + time window + error signature (Phase 3),
* `time_only` - only a time window links it (weakest usable),
* `unknown`   - not enough information to link at all.

This label is what keeps confidence honest when telemetry is incomplete.

## Messy telemetry handling (I6)

Real telemetry is incomplete, duplicated, out of order and sometimes wrong.
Rather than assuming clean input, the pipeline is explicitly defensive:

* **Missing trace ids** - kept, labelled `time_only` and counted in the
  quality report, so correlation can fall back to service + time window.
* **Clock skew** - timestamps are compared with a tolerance
  (`EVENT_TIME_TOLERANCE_MS`); an event whose `event_time` is ahead of its
  `ingestion_time` beyond `CLOCK_SKEW_THRESHOLD_MS` is flagged, not rejected.
* **Dropped spans** - spans whose parent is absent are flagged with
  `broken_trace_link` in `attributes`, which matters when reconstructing
  causal chains.
* **Late arrival** - an ingestion lag above
  `LATE_EVENT_THRESHOLD_SECONDS` sets `is_late`; the event is kept.
* **Duplicates** - identical deterministic `event_id`s are quarantined with
  reason `duplicate_event`.
* **Invalid records** - unparseable timestamps, out-of-range durations/status
  codes, unknown service names and malformed JSON are never silently dropped.
  They are quarantined with an explicit reason and written to
  `quarantined.jsonl`.

## Raw alert ingestion (I10)

`telemetry/alerts.yml` defines realistic Prometheus alert rules
(5xx rate, p95 latency, DB pool saturation, connection errors, app errors)
and `telemetry/alertmanager.yml` groups them. Alerts are parsed into the same
event stream, so a later phase can collapse the "wall of alerts" into a
single incident and measure the reduction.

## Run the pipeline

```bash
# 1. generate a raw dataset (optionally with planted defects)
python -m simulator.generate_telemetry --out-dir data/synthetic/incident-001 --degrade none
python -m simulator.generate_telemetry --out-dir data/synthetic/incident-001 --degrade heavy --seed 7

# 2. run ingestion
python -m ingestion.pipeline --raw-dir data/synthetic/incident-001 --out-dir data/processed/incident-001
```

Outputs written to `--out-dir`:

* `normalized_events.jsonl` - the clean event stream,
* `quarantined.jsonl` - invalid records with reasons,
* `quality_report.json` - counts, rates and defect signals,
* `summary.json` - a compact run summary.

## Quality report signals

`quality_report.json` reports `missing_trace_id_rate`, `unknown_service`,
`late_events`, `clock_skew_suspected`, `broken_trace_links`, per-source and
per-reason counts, evidence-quality distribution and ingestion-lag
percentiles. These are the metrics the degradation test asserts on.

## Tests

```bash
pytest -q
```

* `tests/unit/test_ingestion_normalize.py` - timestamp/service/severity/ids.
* `tests/unit/test_ingestion_validation.py` - validation, quarantine, skew, broken links.
* `tests/unit/test_ingestion_parsers.py` - every parser, including malformed input.
* `tests/unit/test_ingestion_quality.py` - quality-report math.
* `tests/integration/test_ingestion_pipeline.py` - end-to-end generate -> ingest.
* `tests/scenarios/test_messy_telemetry.py` - clean vs messy degradation.

## Acceptance criteria

- All five raw sources (traces, logs, metrics, deployments, alerts) parse into
  the unified schema.
- Malformed / out-of-range / unknown-service / duplicate records are
  quarantined with a clear reason, never dropped silently.
- Missing trace ids, clock skew, late events and broken links are detected and
  reported instead of corrupting the stream.
- A clean dataset produces a clean quality report; a degraded dataset produces
  the expected defect signals while still yielding usable events.
- `python -m ingestion.pipeline` runs end-to-end and writes all output files.
