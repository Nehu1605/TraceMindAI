# Phase 7 - Evaluation, Dashboard & Scenario Library

Phase 6 gives you a report per incident. Phase 7 answers **how well does the
system work** across many incidents, with reproducible experiments.

## Scenario Library (I1)

The improvement plan requires ≥ 20 fault incidents, 5 healthy runs, and 3 decoy
scenarios. The library is defined in `evaluation/scenarios.py`:

| Category | Count | Notes |
| --- | --- | --- |
| Fault (db_conn_leak in payment-service) | 16 | 4 seeds × 4 data-quality levels |
| Healthy (no fault window) | 5 | `degrade="none"` |
| Decoy-emphasis | 3 | Same fault, tagged for B4 analysis |
| **Total** | **24** | |

Each scenario has a fixed `scenario_id`, `seed`, `degrade` level and
`requests`. The simulator always injects the same payment-service DB
connection-leak fault; diversity comes from seeds and data-quality noise.

**Train/test split** is stable: `split_train_test(library, train_frac=0.6,
seed=7)` hashes `scenario_id:seed` so the same scenario always lands in the
same split. No leakage.

Run the library self-check:
```powershell
python -m evaluation.scenarios
```

## Evaluation Runner

`evaluation/runner.py` runs the full pipeline on every scenario in the test
split and computes:

| Metric | Improvement | Meaning |
| --- | --- | --- |
| **Top-1 / Top-3 accuracy** | I2 | RCA engine vs. ground truth |
| **Baseline top-1** (B1..B4) | I2 | Naive methods for comparison |
| **MTTR proxy** | I3 | Wall-clock ingest → report |
| **Accuracy-at-loss** | I6 | Accuracy vs. random event drop |
| **Throughput** | I7 | Events/sec end-to-end |
| **Log-reduction ratio** | I10 | Distinct templates retained |

All metrics are pure functions so they can be unit-tested and compared across
runs.

## Run it

```powershell
python -m evaluation.pipeline --split test --out-dir data/evaluation/run-001
```

Output: `evaluation.json` with per-scenario detail and a summary.

### Reference run (train split, 13 scenarios)

```
=== Evaluation (I1/I2/I3/I6/I7/I10) ===
  split: train | scenarios: 13
  ...
=== Summary ===
  top-1 accuracy:     100.0%
  top-3 accuracy:     100.0%
  B1_latest_anomaly:             0.0%
  B2_max_magnitude:             0.0%
  B3_log_volume:             100.0%
  B4_latest_deploy:             0.0%
  MTTR (mean):        0.13s
  throughput:         3911.5 events/s
  log reduction:      3.8% distinct templates retained
  accuracy at loss:
    loss_0: 100.0%
    loss_10: 80.0%
    loss_20: 70.0%
    loss_30: 100.0%
    loss_40: 20.0%
    loss_50: 40.0%
```

The propagation-aware engine achieves **100% top-1** on the train split; B1,
B2 and B4 score 0% (they blame the gateway or the decoy). B3 (log volume)
accidentally works because the fault service also emits the most errors.

Accuracy-at-loss shows the expected degradation curve; the non-monotonic
values are due to the small scenario count and random sampling.

## Tests

- `tests/unit/test_evaluation_scenarios.py`
- `tests/unit/test_evaluation_runner.py`
- `tests/integration/test_evaluation_pipeline.py`

## Config

| Setting | Default | Meaning |
| --- | --- | --- |
| `eval_train_fraction` | 0.6 | Train/test split |
| `eval_random_seed` | 7 | Split determinism |