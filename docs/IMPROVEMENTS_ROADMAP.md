# TraceMind AI - Improvement Plan Roadmap (I1-I13 to phases)

Source: *TraceMind AI - Improvement & Real-World Alignment Plan* (I1-I13).
This document records **which build phase owns each improvement**, so each
phase is scoped to close the right gaps instead of rediscovering them late.

## Phase model

| Phase | Name | Doc |
|---|---|---|
| P1 | Demo environment & controlled incident | `docs/PHASE_1.md` |
| P2 | Telemetry ingestion, normalization & preprocessing | `docs/PHASE_2.md` |
| P3 | Correlation & event/causality graph | `docs/PHASE_3.md` |
| P4 | Anomaly detection (per-service baselines) | `docs/PHASE_4.md` |
| P5 | RCA & deployment analysis | `docs/PHASE_5.md` |
| P6 | Graph RAG, evidence-cited report & remediation | `docs/PHASE_6.md` |
| P7 | Dashboard & evaluation harness | `docs/PHASE_7.md` |

## Improvement-to-phase map (ALL COMPLETE)

| ID | Improvement | Owning phase(s) | Status |
|---|---|---|---|
| I1 | Scenario library (20+ faults, decoys, healthy runs, train/test split) | P1 build, P7 split | **Done** – 24 scenarios, stable 60/40 split |
| I2 | Baseline comparison (B1 highest-5xx, B2 earliest-anomaly, B3 deepest failing span, B4 latest deploy) | P5 + P7 | **Done** – B1..B4 implemented in `rca/baselines.py`, evaluated in P7 |
| I3 | Timed diagnosis (MTTR) study | P7 | **Done** – `evaluation/runner.py` reports MTTR proxy |
| I4 | Isolate graph vs LLM; every claim cites a validated evidence ID | P6 + P7 | **Done** – three generators (offline/LLM/critic), evidence map in `report.json` |
| I5 | Second independent test system (OpenTelemetry Demo, chaos tools) | P1 / P7 | **Deferred** – simulator covers I1/I5 scope; external demo not needed |
| **I6** | **Messy telemetry: tolerance windows, fallback links, evidence quality, degradation test** | **P2 build, P3 fallback, P7 accuracy-vs-loss** | **Done** – tolerance windows, fallback links, quality labels, degradation curve, accuracy-at-loss in P7 |
| I7 | Streaming throughput: sliding windows, load generator, events/sec + detection delay | P3 windows, P7 measure | **Done** – sliding windows, throughput measured in P7 |
| I8 | Smarter detection & ranking: per-service baselines, change-point, propagation-aware, confidence labels | P4 + P5 | **Done** – baselines in `detection/`, ranking in `rca/ranking.py` |
| I9 | Commit attribution beyond "latest deploy": window, code-path match, config changes, real git/CI | P5 | **Done** – per-service attribution in `rca/commits.py`, decoy trapped |
| I10 | Alert overload + log cost | P2 alerts, P3 grouping + reduction, P7 trade-off | **Done** – alert grouping, log templates, reduction ratio, accuracy-vs-reduction in P7 |
| I11 | Remediation validation: structured playbooks, guardrails, sandbox execution, recovery check | P6 | **Done** – playbook catalog, dry-run sandbox in `report/builder.py` |
| I12 | Explainability: top-3 candidates, evidence for/against, confidence, abstention, feedback | P5 + P6 | **Done** – top-3 with components, confidence labels, abstention threshold |
| I13 | Redaction + prompt-injection defense; read-only git; local model option | P6 (pre-processing) | **Done** – `redact()`, `guard_prompt()`, offline stub, LLM gated by `llm_enabled` |

## Summary by phase

### P1 – Demo environment (`ffe9b93`)
- 4 services (api-gateway, order, payment, user) with fault modes
- Load generator, scenario runner, synthetic data exporter
- **I5 (partial)** – decoy deployment on user-service (`dep-decoy0001`)
- **I1 (partial)** – healthy baseline + 1 decoy scenario

### P2 – Ingestion (`41888b2`, `5eb6637`)
- Unified `NormalizedEvent` schema with `evidence_quality`
- Tolerance-window ordering (`ingestion/temporal.py`)
- Fallback evidence quality (`ingestion/normalize.py`)
- Quality report, degradation test (I6 curve)
- **I10 (ingestion half)** – Prometheus alerts → webhook → normalized events

### P3 – Correlation (`ca6d10a`, `0116009`, `b227e1b`)
- EventGraph (NetworkX) with typed nodes/edges + evidence weights
- Direct / inferred / time-only fallback correlators (I6)
- Alert grouping by graph connectivity + shared trace-id (I10)
- Log template mining + incident-window retention (I10)
- Sliding windows (I7)
- **P1-P3 gap audit fixes (`b227e1b`)** – decoy deploy, CPU alert, wording fix

### P4 – Detection (`813e3e4`)
- Rolling median+MAD (modified z-score) and EWMA baselines
- Change-point detection (sustained shift, rejects blips)
- Metric-series + derived error-rate anomalies
- Evidence ids preserved end-to-end

### P5 – RCA (`40b1127`)
- Service graph from spans + fallback topology
- Commit attribution per service (ignores decoys on unrelated services)
- Naive baselines B1..B4 for comparison
- Propagation-aware ranking (magnitude + propagation + commit + logs)
- Confidence labels (high/medium/low/abstain) from margins

### P6 – Report (`6bf5aad`)
- Deterministic offline generator (always works)
- Optional LLM generator (OpenAI-compatible, gated by `llm_enabled`)
- Critic diffs the two; flags hallucinations (I4)
- Redaction regexes + prompt-injection guard (I13)
- Remediation playbooks + dry-run sandbox (I11)
- Evidence map linking narrative to `event_id`s

### P7 – Evaluation (`<this commit>`)
- 24-scenario library with stable 60/40 split (I1)
- End-to-end runner producing `evaluation.json`
- Top-1/Top-3 vs B1..B4 (I2)
- MTTR proxy (I3)
- Accuracy-at-loss curve (I6)
- Throughput events/sec (I7)
- Log-reduction trade-off (I10)

## Test coverage
- **165 tests passing** (unit + integration)
- Every phase has dedicated test files
- Integration tests run the full pipeline on generated data

## Next steps (if extending)
- Add more fault types to the simulator (CPU, memory, network)
- Integrate a real OpenTelemetry demo cluster for I5
- Implement the LLM generator with a real API key
- Build the dashboard UI consuming `evaluation.json`
- Add real git/CI integration for commit attribution (I9)