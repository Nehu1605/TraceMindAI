# Phase 3 - Correlation & Event/Causality Graph

This phase connects the clean events from Phase 2 into a **typed, directed
evidence graph**. Nodes are telemetry entities; edges are evidence links that
each carry a confidence label, so later phases can reason about *how strongly*
two things are connected rather than treating every link as equal.

It also delivers the correlation halves of two improvement-plan items:

* **I6** - when a log has no trace id, it is linked by service + time window +
  error signature and marked `inferred` / `time_only` instead of being
  discarded.
* **I10** - raw alerts are grouped into incidents, with an alert-reduction
  ratio.
* **I7** (partial) - a sliding-window iterator so correlation runs over the
  last N seconds instead of waiting for a fixed batch.

## Deliverables

| Item | Location |
|---|---|
| Graph vocabulary (node/edge types, evidence weights) | `correlation/constants.py` |
| Event graph (serializable NetworkX wrapper) | `correlation/graph.py` |
| Correlators (span/log/metric/deployment/alert) | `correlation/correlators.py` |
| Alert grouping into incidents (I10) | `correlation/alerting.py` |
| Sliding windows (I7) | `correlation/windowing.py` |
| Orchestration | `correlation/builder.py` |
| Pipeline CLI | `correlation/pipeline.py` |
| Postgres schema (reference) | `correlation/sql/schema.sql` |
| Tests | `tests/unit`, `tests/integration`, `tests/scenarios` |

## Graph model

Nodes: `Service`, `Trace`, `TraceSpan`, `LogEvent`, `MetricSample`,
`Deployment`, `Commit`, `Alert`, `Incident`.

Edges (directed, typed, weighted by evidence quality):

| Edge | Meaning | Evidence |
|---|---|---|
| `PART_OF` | span belongs to a trace | direct |
| `PARENT_OF` | parent span -> child span | direct |
| `CALLS` | service -> downstream service (aggregated count) | direct |
| `GENERATED` | producer -> produced event (span/service -> log, service -> metric) | direct / inferred / time_only |
| `OBSERVED_DURING` | alert/incident -> service | time_only |
| `DEPLOYED_TO` | deployment -> service | time_only |
| `MODIFIED` | deployment -> commit | direct |
| `PRECEDED` | span -> later span in the same trace | direct |
| `GROUPED_INTO` | alert -> incident | time_only |

Evidence weights: `direct` 1.0, `inferred` 0.6, `time_only` 0.3, `unknown` 0.0
(`correlation/constants.py`).

## Log-to-span correlation (I6 fallback)

1. **Direct** - the log shares a trace id; it attaches to the error span (or
   the closest span) in that trace.
2. **Inferred** - no trace id, but the log is an error in the same service
   within `CORRELATION_WINDOW_SECONDS` of an error span: a service + time +
   error-signature match.
3. **Time only** - no trace id and no signature agreement; linked by service +
   time window.
4. If nothing matches, the log is attached to its service node so it is never
   lost from the graph.

The confidence label travels on the edge, so a later scoring phase can
discount `time_only` links.

## Alert grouping (I10)

Alerts are grouped into one incident when they share a time window
(`ALERT_GROUP_WINDOW_SECONDS`) *and* their services are connected within
`ALERT_GROUP_MAX_HOPS` in the `CALLS` graph. Each incident becomes a node with
`GROUPED_INTO` edges from its alerts.

On the demo incident this collapses 7 raw alerts from three services into
**1 incident (7x reduction)**; a decoy alert on an unconnected service stays
in its own incident.

## Run the pipeline

```bash
# 1. generate + ingest (Phase 2)
python -m simulator.generate_telemetry --out-dir data/synthetic/incident-001 --degrade none
python -m ingestion.pipeline --raw-dir data/synthetic/incident-001 --out-dir data/processed/incident-001

# 2. correlate (Phase 3)
python -m correlation.pipeline \
    --events data/processed/incident-001/normalized_events.jsonl \
    --out-dir data/processed/incident-001
```

Outputs written to `--out-dir`:

* `graph.json` - nodes, edges, node/edge type counts, service dependencies.
* `incidents.json` - incident groups + alert-reduction ratio.
* `correlation_summary.json` - correlation counts and graph stats.

## Tests

```bash
pytest -q
```

* `tests/unit/test_correlation_graph.py` - graph add/query/serialize.
* `tests/unit/test_correlation_correlators.py` - span/log/metric/deployment/alert links and fallback quality.
* `tests/unit/test_correlation_alerting.py` - grouping by window, hops, topology.
* `tests/unit/test_correlation_windowing.py` - sliding-window coverage/overlap.
* `tests/integration/test_correlation_pipeline.py` - generate -> ingest -> correlate.
* `tests/scenarios/test_alert_grouping_scenario.py` - incident collapse vs decoy.

## Acceptance criteria

- Traces, spans, logs, metrics, deployments, commits and alerts all appear as
  typed nodes; parent/child, service-call and trace relationships are edges.
- Logs without trace ids are still linked, with `inferred`/`time_only`
  confidence (I6), not dropped.
- Alerts from one injected fault collapse into a single incident, and an
  unrelated decoy does not get merged (I10), with the reduction ratio reported.
- `python -m correlation.pipeline` runs end-to-end and writes `graph.json`,
  `incidents.json` and `correlation_summary.json`.

## Deferred to later phases

- Anomaly detection against per-service baselines (I8 -> P4).
- RCA ranking, baselines B1-B4, commit attribution (I2/I9 -> P5).
- Evidence-cited LLM report and remediation (I4/I11/I12/I13 -> P6).
- Grouping-quality metrics against ground truth and throughput figures
  (P7).
