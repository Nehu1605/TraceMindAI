# Phase 3 - Correlation & Event/Causality Graph

This phase connects the clean events from Phase 2 into a **typed, directed
evidence graph**. Nodes are telemetry entities; edges are evidence links that
each carry a confidence label, so later phases can reason about *how strongly*
two things are connected rather than treating every link as equal.

It also delivers the correlation halves of the improvement-plan items:

* **I6** - when a log has no trace id, it is linked by service + time window +
  error signature and marked `inferred` / `time_only` instead of being
  discarded; every edge carries an evidence-quality value for scoring.
* **I10** (both halves) - raw alerts are grouped into incidents with an
  alert-reduction ratio and a grouping-quality measure, and log volume is
  reduced by template mining (Drain-style key) plus incident-windowed
  retention, reporting bytes retained against bytes ingested.
* **I7** (partial) - a sliding-window iterator so correlation runs over the
  last N seconds instead of waiting for a fixed batch.

## Deliverables

| Item | Location |
|---|---|
| Graph vocabulary (node/edge types, evidence weights) | `correlation/constants.py` |
| Event graph (serializable NetworkX wrapper) | `correlation/graph.py` |
| Correlators (span/log/metric/deployment/alert) | `correlation/correlators.py` |
| Alert grouping + grouping quality (I10) | `correlation/alerting.py` |
| Log-template mining + log reduction (I10) | `correlation/log_reduction.py` |
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
(`ALERT_GROUP_WINDOW_SECONDS`) *and* either their services are connected
within `ALERT_GROUP_MAX_HOPS` in the `CALLS` graph **or** they share a trace id
(the two criteria named in the plan). Each incident becomes a node with
`GROUPED_INTO` edges from its alerts.

On the demo incident this collapses 7 raw alerts from three services into
**1 incident (7x reduction)**; a decoy alert on an unconnected service stays
in its own incident.

**Grouping quality** (`grouping_quality(incidents, fault_by_service)`) reports
`purity` (share of alerts whose incident is dominated by their own fault) and
`impure_incidents` (incidents that merged more than one fault). On the demo the
injected fault and the decoy are separate faults with **purity 1.0 and
0 impure incidents**. The full accuracy-vs-reduction trade-off is measured in
P7 (it needs the RCA phase).

## Log-volume reduction (I10, log cost)

`correlation/log_reduction.py` does two things the plan asks for:

1. **Template mining** (`template_of`, `mine_templates`) - a Drain-style key
   replaces timestamps, ids, addresses and numbers with placeholders, so
   `... order=ORD-0007 ...` and `... order=ORD-0042 ...` collapse to one
   template with a count and byte total.
2. **Incident-windowed retention** (`reduce_logs`) - full logs are kept for the
   incident time windows (padded), error/fatal logs are always kept, and the
   rest is sampled (`LOG_SAMPLE_RATE`, default 0.0 = dropped). Non-log events
   are never dropped.

On the demo incident: **145 log lines collapse to 6 templates (95.9% fewer
distinct lines)**. Byte retention is small on this dataset (~0.3%) because it
is a single all-error incident whose window spans the whole run - the win comes
from template collapse and from dropping background logs in busier datasets.
The reduced stream is written to `reduced_logs.jsonl` and the measurement to
`log_reduction.json`.

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
* `log_reduction.json` - templates, distinct-line and byte reduction figures.
* `reduced_logs.jsonl` - the retained log stream after reduction.
* `correlation_summary.json` - correlation counts, graph stats, alert grouping
  and log-reduction summary.

## Tests

```bash
pytest -q
```

* `tests/unit/test_correlation_graph.py` - graph add/query/serialize.
* `tests/unit/test_correlation_correlators.py` - span/log/metric/deployment/alert links and fallback quality.
* `tests/unit/test_correlation_alerting.py` - grouping by window, hops, topology, shared trace id; grouping quality.
* `tests/unit/test_correlation_log_reduction.py` - template keys, mining counts, retention policy, determinism, byte/line reduction.
* `tests/unit/test_correlation_windowing.py` - sliding-window coverage/overlap.
* `tests/integration/test_correlation_pipeline.py` - generate -> ingest -> correlate.
* `tests/scenarios/test_alert_grouping_scenario.py` - incident collapse vs decoy.

## Acceptance criteria

- Traces, spans, logs, metrics, deployments, commits and alerts all appear as
  typed nodes; parent/child, service-call and trace relationships are edges.
- Logs without trace ids are still linked, with `inferred`/`time_only`
  confidence (I6), not dropped.
- Alerts from one injected fault collapse into a single incident, and an
  unrelated decoy does not get merged (I10), with the reduction ratio and
  grouping quality (purity, impure incidents) reported.
- Repeated log lines collapse into templates and non-incident logs are dropped,
  with bytes/line reduction reported (I10 log cost).
- `python -m correlation.pipeline` runs end-to-end and writes `graph.json`,
  `incidents.json`, `log_reduction.json`, `reduced_logs.jsonl` and
  `correlation_summary.json`.

## Deferred to later phases

- Anomaly detection against per-service baselines, using the sliding windows
  (I8 -> P4).
- RCA ranking, baselines B1-B4, commit attribution; this is where the edge
  evidence weights are consumed by scoring (I2/I9 -> P5).
- The accuracy-vs-reduction trade-off (does RCA accuracy hold when reduced logs
  are used) and the I6 accuracy-at-loss curve need the RCA phase (-> P7).
- Evidence-cited LLM report and remediation (I4/I11/I12/I13 -> P6).
- Throughput figures (events/sec, detection delay) (-> P7).
