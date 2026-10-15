# TraceMind AI - Improvement Plan Roadmap (I1-I13 to phases)

Source: *TraceMind AI - Improvement & Real-World Alignment Plan* (I1-I13).
This document records **which build phase owns each improvement**, so each
phase is scoped to close the right gaps instead of rediscovering them late.

## Phase model

| Phase | Name | Doc |
|---|---|---|
| P1 | Demo environment & controlled incident | `docs/PHASE_1.md` |
| P2 | Telemetry ingestion, normalization & preprocessing | `docs/PHASE_2.md` |
| P3 | Correlation & event/causality graph | (planned) |
| P4 | Anomaly detection | (planned) |
| P5 | RCA & change/deployment analysis | (planned) |
| P6 | Graph RAG, evidence-cited report & remediation | (planned) |
| P7 | Dashboard & evaluation harness | (planned) |

## Improvement-to-phase map

| ID | Improvement | Owning phase(s) | Status |
|---|---|---|---|
| I1 | Scenario library (20+ faults, decoys, healthy runs, train/test split) | P1 build, P7 split | Deferred |
| I2 | Baseline comparison (B1 highest-5xx, B2 earliest-anomaly, B3 deepest failing span, B4 latest deploy) | P5 + P7 | Deferred |
| I3 | Timed diagnosis (MTTR) study | P7 | Deferred |
| I4 | Isolate graph vs LLM; every claim cites a validated evidence ID | P6 + P7 | Partly enabled: events already carry `event_id` + `source_reference` |
| I5 | Second independent test system (OpenTelemetry Demo, chaos tools) | P1 / P7 | Deferred |
| **I6** | **Messy telemetry: tolerance windows, fallback links, evidence quality, degradation test** | **P2** | **Done** |
| I7 | Streaming throughput: sliding windows, load generator, events/sec + detection delay | P2/P3 ingest, P7 measure | Partial (per-event ingest; throughput deferred) |
| I8 | Smarter detection & ranking: per-service baselines, change-point, propagation-aware, confidence labels | P4 + P5 | Deferred |
| I9 | Commit attribution beyond "latest deploy": window, code-path match, config changes, real git/CI | P5 | Deferred |
| I10 | Alert overload + log cost | Alerts P2; grouping P3; log-template reduction P2/P3; measure P7 | Alerts done; grouping/reduction deferred |
| I11 | Remediation validation: structured playbooks, guardrails, sandbox execution, recovery check | P6 | Deferred |
| I12 | Explainability: top-3 candidates, evidence for/against, confidence, abstention, feedback | P6 + P7 | Deferred |
| I13 | Redaction + prompt-injection defense; read-only git; local model option | P6 (pre-processing) | Deferred |

## Phase 2 scope (this phase): I6 + I10 (alert ingestion)

**I6 - messy telemetry, closed in P2:**

1. *Tolerance windows instead of exact timestamp comparison* -
   `ingestion/temporal.py::sort_events` buckets `event_time` into fixed
   tolerance windows and orders within a window by ingestion time.
2. *Fallback when a log has no trace id, marked lower confidence* -
   `ingestion/normalize.py::evidence_quality_for` labels events `direct` /
   `time_only` / `unknown`; missing-trace-id events are kept and labelled
   `time_only` so P3 can link them by service + time window + error signature.
3. *Evidence-quality value per link* - carried on every `NormalizedEvent` and
   aggregated in `quality_report.json`.
4. *Degradation test* - `simulator/degradation_test.py` runs the incident at
   0/10/20/30% data loss (dropped spans, missing trace ids, 200 ms skew) and
   reports the robustness curve:
   ingest success stays 100% while direct-link coverage falls slowly
   (81.8% -> 68.0%) and `time_only` coverage absorbs the difference.

**I10 - alert overload, the ingestion half closed in P2:**

1. Realistic Prometheus alert rules per service/metric (`telemetry/alerts.yml`)
   plus Alertmanager grouping config (`telemetry/alertmanager.yml`).
2. Raw alerts are ingested into the same unified event stream as every other
   source, so P3 can group them and P7 can measure the alert-reduction ratio.
3. The gateway exposes `POST /alerts` to receive Alertmanager webhooks.

Deferred from I10 to later phases: grouping alerts into incidents and
measuring reduction (P3/P7); collapsing repeated log lines into templates and
measuring bytes retained (P2/P3 build, P7 measure).

## Handoff notes for upcoming phases

- **P3 (correlation/graph):** consume `NormalizedEvent`, use
  `evidence_quality` to weight links, use `temporal.precedes`/`in_window`
  for windows, and group raw alerts by time + service graph (rest of I10).
- **P4/P5 (detection/RCA):** use per-service baselines (I8), implement
  baselines B1-B4 (I2), rank deployments with code-path evidence (I9).
- **P6 (RAG/remediation):** cite `event_id`/`source_reference` for every claim
  (I4), redact before the LLM (I13), structured sandbox-validated playbooks
  (I11), confidence + abstention (I12).
- **P7 (evaluation):** scenario split, held-out runs, MTTR study (I3),
  degradation + throughput runs (I6/I7), alert/log reduction figures (I10).
