# Phase 5 - Propagation-Aware Root-Cause Analysis

Phase 4 tells you *what* looks wrong (anomalies per service). Phase 5 answers
**which service is the root cause** and *why*.

The naive approach picks the loudest symptom. The improvement plan (I2, I8, I9,
I12) requires a propagation-aware engine that reasons over the call graph, uses
commit/deployment attribution, and can **abstain** when evidence is thin.

## Architecture

```
detection/            (Phase 4)  -->  anomalies + evidence_ids
rca/
  topology.py         build_service_graph() from parent/child spans
  commits.py          attribute_deployment() per service; latest_deployment() baseline
  baselines.py        B1..B4 straw-men for evaluation
  ranking.py          Candidate scoring: magnitude + propagation + commit + logs
  engine.py           RCAEngine -> RCAReport (top-k, baselines, abstain)
  pipeline.py         CLI -> rca.json
```

## Ranking

Each anomalous service gets four component scores (0-1 normalized):

| Component | Weight | Meaning |
| --- | --- | --- |
| **magnitude** | 0.35 | max anomaly z-score this service owns |
| **propagation** | 0.30 | how many *other* anomalous services sit upstream |
| **commit** | 0.25 | was a deployment to this service right before onset? |
| **logs** | 0.10 | relative error-log volume |

`propagation` walks the call graph `caller -> callee` and sums
`0.7^hops` for each path from another anomalous service to the candidate. A
shared dependency (e.g. `payment-service` called by both `order-service` and
`api-gateway`) scores highest.

The combined score is `sum(weight * component)`. Every `Candidate` keeps all
components, its evidence ids and a plain-English `rationale`.

## Commit attribution (I9)

`attribute_deployment(service, onset, deployments, window_seconds)` returns the
best deployment **to that service** that landed before the anomaly onset.
The decoy deployment on `user-service` is ignored because it's not on the
candidate service.

`latest_deployment(onset, deployments, window_seconds)` is the naive
"blame the latest ship" baseline (B4) - it looks symmetrically around the
onset so the later decoy traps it.

## Confidence & Abstention (I12)

* `high`   - top score leads the runner-up by `rca_high_margin` (default 0.25)
* `medium` - lead by `rca_medium_margin` (default 0.10)
* `low`    - lead smaller than that
* `abstain` - top score below `rca_abstain_threshold` (default 0.05)

The `RCAReport.summary()` returns a human-readable string; the `abstained`
property is true when confidence is `abstain`.

## Run it

```powershell
python -m rca.pipeline --events data/processed/incident-001/normalized_events.jsonl `
    --out-dir data/processed/incident-001
```

Output: `rca.json`.

### Reference run (payment DB-connection-leak fault)

```
=== RCA summary (I2/I8/I9/I12) ===
  Most likely root cause: payment-service (confidence high, score 0.93).
    payment-service is a shared dependency of other degraded services
    (propagation 0.78); it has the strongest local anomalies (magnitude 1.00);
    commit c0ffee1d00m3 deployed 1s before onset; error logs cluster on it
    (relative 1.00)
  anomalous services: ['api-gateway', 'order-service', 'payment-service', 'postgres']
    #1 payment-service  score=0.933 conf=high
    #2 postgres         score=0.650 conf=low
    #3 order-service    score=0.587 conf=low
    #4 api-gateway      score=0.450 conf=low
  baselines:
    B1_latest_anomaly: ['api-gateway']
    B2_max_magnitude: ['api-gateway']
    B3_log_volume: ['api-gateway']
    B4_latest_deploy: ['user-service']
```

The engine picks the true root cause (`payment-service`) with **high
confidence** and cites the correct commit (`c0ffee1d00m3`). All three symptom-
based baselines (B1-B3) blame the gateway; B4 falls for the decoy.

## Tests

- `tests/unit/test_rca_topology.py`
- `tests/unit/test_rca_commits.py`
- `tests/unit/test_rca_ranking.py`
- `tests/integration/test_rca_pipeline.py`

## Config

| Setting | Default | Meaning |
| --- | --- | --- |
| `rca_high_margin` | 0.25 | top-1 vs top-2 gap for `high` |
| `rca_medium_margin` | 0.10 | top-1 vs top-2 gap for `medium` |
| `rca_abstain_threshold` | 0.05 | below this -> `abstain` |
| `rca_top_k` | 3 | candidates returned for explainability |
| `commit_window_seconds` | 900 | attribution time window |