# Phase 4 - Anomaly Detection (Baselines + Change Points)

Phase 3 turns raw events into a graph of what happened. Phase 4 answers the
next question: **what looks wrong?** Improvement I8 asks for anomaly detection
that does not rely on a single hand-tuned global threshold.

## Why per-service baselines

A global rule ("latency > 300 ms is bad") either drowns a busy service in false
positives or misses degradation on a service whose normal latency is already
high. Instead every service is compared against **its own** recent behaviour.

Two baselines are provided:

| Baseline | Measure | Used for |
| --- | --- | --- |
| `RollingBaseline` | rolling **median** + **MAD** | primary detector |
| `EwmaBaseline` | exponentially weighted mean/variance | second opinion |

The primary score is the *modified z-score*:

```
robust_z = 0.6745 * (value - median) / MAD
```

The 0.6745 constant makes it comparable to a plain z-score on normal data. The
median and MAD (not mean/stdev) mean a few large spikes cannot inflate the
spread and hide themselves. When a baseline is perfectly flat (MAD = 0) a real
deviation is reported as `+/-50` instead of `inf`, and the **sign is kept** so
drops are detected as reliably as spikes.

## Change points

`detection/change_point.py` reports the first index where the level moves and
*stays* moved (`confirm=2` consecutive points beyond threshold). This rejects
one-sample blips and gives each anomaly a defensible **onset time**.

## Detector

`AnomalyDetector.detect()` produces anomalies from two signal families:

1. **Metric series** - numeric samples bucketed per `(service, metric)`:
   `db_connections_in_use`, `http_request_duration_ms`, `http_5xx_rate`,
   `cpu_percent`, `memory_percent`.
2. **Derived error series** - error-log counts and 5xx span counts bucketed per
   service on a **full time grid**, so a service that only reveals problems
   through logs/traces (e.g. `order-service`) still becomes a candidate. The
   leading zero-count buckets are essential: without them a series that starts
   only when errors begin looks flat and no change point is found.

Each `Anomaly` records `service`, `metric`, `direction`, `magnitude`, `onset_time`,
`end_time`, `observed_peak`, `baseline_median` and the `evidence_ids` that
produced it - the audit trail Phase 5's RCA and Phase 6's report depend on.

## Run it

```powershell
python -m simulator.generate_telemetry --out-dir data/synthetic/incident-001 --degrade none
python -m ingestion.pipeline --raw-dir data/synthetic/incident-001 --out-dir data/processed/incident-001
python -m detection.pipeline --events data/processed/incident-001/normalized_events.jsonl `
    --out-dir data/processed/incident-001
```

Output: `anomalies.json`.

### Reference run (payment DB-connection-leak fault)

```
anomalies : 8
services  : ['api-gateway', 'order-service', 'payment-service', 'postgres']
  10:00:10  api-gateway      error_rate             up  z=50.0
  10:00:10  order-service    error_rate             up  z=50.0
  10:00:10  payment-service  error_rate             up  z=50.0
  10:00:10  postgres         error_rate             up  z=50.0
  10:00:12  api-gateway      http_5xx_rate          up  z=50.0
  10:00:12  payment-service  db_connections_in_use  up  z=50.0
  10:00:12  payment-service  http_5xx_rate          up  z=50.0
  10:00:12  payment-service  http_request_duration_ms up z=50.0
```

The fault is injected in `payment-service`; detection correctly fires there and
traces the cascade outward to `order-service`, `api-gateway` and the DB.

## Tests

- `tests/unit/test_detection_baselines.py`
- `tests/unit/test_detection_change_point.py`
- `tests/unit/test_detection_detector.py`
- `tests/integration/test_detection_pipeline.py`

## Config

| Setting | Default | Meaning |
| --- | --- | --- |
| `baseline_warmup_points` | 3 | points used to seed a baseline |
| `anomaly_z_threshold` | 4.0 | robust z that opens an anomaly |
| `ewma_alpha` | 0.4 | EWMA smoothing |
| `change_point_min_points` | 4 | minimum points before trusting a change |
