# TraceMind AI
## Distributed OpenTelemetry Log-Trace Correlation & Autonomous RCA Engine

## 1. Problem Statement

Cloud-native systems generate large volumes of distributed traces, application logs, and metrics. During an outage, SREs must manually connect alerts, trace IDs, logs, metrics, service dependencies, and recent deployments. This is slow and error-prone.

TraceMind AI aims to correlate telemetry, construct an event/causality graph, rank likely root causes, connect incidents to relevant code or infrastructure changes, and produce evidence-grounded explanations and remediation recommendations.

## 2. Goals

- Ingest OpenTelemetry traces, application logs, Prometheus metrics, and deployment/change events.
- Normalize events into a common schema with timestamps and service context.
- Correlate events using trace IDs, span relationships, time, service dependencies, and error patterns.
- Construct and update a dynamic event graph.
- Detect latency spikes, HTTP 5xx increases, and other configured anomalies.
- Rank root-cause hypotheses and show supporting evidence.
- Correlate incidents with GitHub/GitLab commits and deployment events when evidence supports the link.
- Use Graph Retrieval-Augmented Generation (Graph RAG) to provide relevant context to an LLM.
- Generate an incident summary, timeline, impact radius, and remediation recommendation.
- Require human approval before remediation.
- Evaluate results against known synthetic ground truth.

### MVP non-goals

The first version does not need every commercial observability integration, a custom-trained LLM, guaranteed causal discovery, or autonomous production remediation.

## 3. Key Features

1. Unified telemetry ingestion and normalization.
2. Trace-to-log correlation using trace/span context.
3. Temporal, dependency, and error-pattern correlation.
4. Dynamic graph of services, spans, logs, metric anomalies, deployments, commits, and incidents.
5. Rule/threshold-based anomaly detection.
6. Evidence-based root-cause ranking and impact analysis.
7. Git/deployment correlation.
8. Graph retrieval and LLM-generated incident explanation.
9. Remediation playbooks with human approval.
10. Dashboard with incident status, causal graph, timeline, evidence, and action status.
11. Test, evaluation, and audit logs.

## 4. Proposed Architecture

```text
Demo Microservices
(API Gateway, Order, Payment, User, Database)
                  |
       OpenTelemetry instrumentation
                  |
        +---------+---------+
        |         |         |
      Traces     Logs     Metrics
        |         |         |
        +---------+---------+
                  |
       OpenTelemetry Collector
                  |
       Ingestion, validation, normalization
                  |
           Unified event store
                  |
           Correlation engine
                  |
       Event / causality graph
                  |
       +----------+-----------+
       |                      |
  Anomaly detection      Git/deployment data
       |                      |
       +----------+-----------+
                  |
           RCA ranking engine
                  |
         Graph evidence retrieval
                  |
             Graph RAG + LLM
                  |
       +----------+-----------+
       |          |           |
   RCA report  Impact radius  Remediation
       +----------+-----------+
                  |
             SRE dashboard
                  |
        Human approval (MVP)
                  |
       Simulated action + checks
```

### Architecture principles

- Correlate and retrieve evidence before asking the LLM to explain.
- The LLM must not be the sole root-cause decision-maker.
- Important claims should reference source events, spans, metrics, or change records.
- Temporal proximity is evidence to investigate, not proof of causality.
- Preserve invalid records or quarantine them with a clear reason.
- Use synthetic incidents and simulated remediation before real integrations.

## 5. End-to-End Workflow

1. Instrument demo services and generate traces, structured logs, and metrics.
2. Ingest telemetry and deployment records.
3. Validate fields, normalize timestamps to UTC, standardize service names, and enrich trace/span context.
4. Correlate parent/child spans, logs sharing trace IDs, metric anomalies, service dependencies, and candidate deployment events.
5. Build a graph with typed nodes/edges and source evidence.
6. Detect an incident using thresholds or baseline comparisons.
7. Rank candidate causes using temporal, trace, dependency, error, metric, and change evidence.
8. Retrieve relevant deployment and commit metadata.
9. Retrieve the graph neighborhood and supporting telemetry.
10. Generate a structured, evidence-grounded incident report with an LLM.
11. Calculate the impact radius using service dependencies and observed degradation.
12. Recommend a playbook for human review.
13. Simulate the action, check recovery metrics, and record evaluation results.

## 6. Suggested Technology Stack

| Layer | Suggested technology | Purpose |
|---|---|---|
| Demo services | Python, FastAPI | Reproducible service calls and failures |
| Tracing | OpenTelemetry SDK | Distributed traces and spans |
| Telemetry receiver | OpenTelemetry Collector | Receive/export telemetry |
| Metrics | Prometheus | Metric collection and queries |
| Trace UI | Jaeger or Grafana Tempo | Inspect traces |
| Logs | Structured JSON; optional Loki/OpenSearch | Search and correlate logs |
| Event processing | Python first; Kafka/Redpanda if needed | Process event streams |
| Graph | NetworkX first; optional Neo4j | Store/query event relationships |
| Persistence | PostgreSQL | Incidents, events, and test results |
| Git integration | GitLab/GitHub API or fixture files | Commit/deployment metadata |
| RCA | Python | Detection, scoring, impact analysis |
| Graph RAG | Graph retriever + LLM | Evidence-grounded explanation |
| Dashboard | Streamlit | Incident investigation UI |
| Testing | pytest | Unit/integration/scenario tests |
| Local runtime | Docker Compose | Reproducible services |
| CI | GitLab CI/CD | Automated checks |

Start with FastAPI, OpenTelemetry, Prometheus, Python, NetworkX, PostgreSQL, Streamlit, and pytest. Add Kafka or Neo4j only when needed.

## 7. Suggested Repository Structure

```text
tracemind-ai/
├── services/
│   ├── api_gateway/
│   ├── order_service/
│   ├── payment_service/
│   └── user_service/
├── telemetry/
│   ├── otel-collector-config.yaml
│   ├── prometheus.yml
│   └── logging_config.py
├── ingestion/
├── correlation/
├── graph/
├── rca/
├── integrations/
├── ai/
├── dashboard/
│   └── app.py
├── simulator/
├── data/
│   └── synthetic/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── scenarios/
├── docs/
├── docker-compose.yml
├── .env.example
├── requirements.txt
└── README.md
```

This is a proposed structure; adapt it to the actual implementation.

## 8. Data Model

A normalized event can use this schema:

```json
{
  "event_id": "evt-001",
  "event_time": "2026-10-11T10:02:31Z",
  "ingestion_time": "2026-10-11T10:02:32Z",
  "source_type": "log",
  "event_type": "DB_CONNECTION_TIMEOUT",
  "service_name": "payment-service",
  "trace_id": "trace-incident-001",
  "span_id": "span-123",
  "severity": "ERROR",
  "message": "Database connection acquisition timeout",
  "attributes": {},
  "source_reference": "logs.csv:8"
}
```

Keep event time separate from ingestion time to handle late events. Do not invent missing fields.

Suggested graph nodes: `Service`, `TraceSpan`, `LogEvent`, `MetricAnomaly`, `Deployment`, `Commit`, `Incident`, `RemediationAction`.

Suggested graph edges: `CALLS`, `PARENT_OF`, `GENERATED`, `OBSERVED_DURING`, `PRECEDED`, `DEPLOYED_TO`, `MODIFIED`, `AFFECTED`, `SUPPORTS_HYPOTHESIS`.

Record provenance and distinguish observed relationships from inferred hypotheses.

## 9. Root-Cause Analysis

### Anomaly detection

Start with configurable thresholds and baseline comparisons for request latency, HTTP 5xx rate, failure counts, database connection utilization, CPU, and memory.

### Candidate scoring

An initial ranking score may be:

```text
score(candidate) =
    w_temporal   * temporal_evidence
  + w_dependency * trace_and_dependency_evidence
  + w_error      * error_evidence
  + w_metric     * metric_anomaly_evidence
  + w_change     * deployment_change_evidence
```

Normalize features and tune weights using labeled scenarios. Treat the result as a ranking score, not a calibrated probability unless calibration has been performed.

For each leading hypothesis, return the candidate service/event, score factors, supporting event IDs, relevant trace/span IDs, metric samples, timeline, deployment candidates, missing/contradictory evidence, and affected services.

A nearby deployment is not automatically the cause.

## 10. Graph RAG and LLM

Retrieve a compact graph neighborhood, representative spans, relevant logs, metric changes, deployment data, and RCA scoring evidence. Pass this evidence to the LLM rather than sending every raw log.

The report should include:
- Incident summary and time window
- Leading root-cause hypothesis
- Evidence and source references
- Timeline and propagation path
- Impacted services
- Candidate deployment/commit
- Recommended next steps
- Uncertainties and missing evidence

Require the LLM to distinguish observed facts from hypotheses, say “unknown” when evidence is missing, and never invent commits, metrics, logs, or causal links. Validate output against a schema.

## 11. Git and Deployment Correlation

Capture deployment ID, service, timestamp, commit SHA, deployment status, changed files, and change summary. For affected services, query deployments within a configurable lookback window, compare them with anomaly onset, retrieve commit metadata, and add candidate relationships to the graph with evidence.

Use least-privilege tokens from environment variables or a secret manager. Never commit tokens to source control.

## 12. Remediation and Safety

Examples of candidate recommendations:
- Recent deployment implicated: review and consider rollback.
- Confirmed resource saturation: consider scaling or adjusting resource limits.
- Database pool exhaustion: inspect connection leaks and pool settings.
- Confirmed cache issue: investigate cache health before taking action.

Each playbook should include evidence, preconditions, action, expected result, risks, approval, verification, and rollback/recovery steps.

**MVP policy:** recommendation only, with simulated approval/execution. Before production actions, implement least privilege, audit logs, explicit approval, idempotency where possible, timeouts, failure handling, post-action health checks, and rollback procedures.

## 13. Dashboard Requirements

- Incident overview: ID, severity, status, start time, affected services.
- Timeline: deployments, anomalies, errors, and recovery.
- Causal graph with source evidence.
- Evidence explorer for logs, spans, metrics, and commits.
- RCA report with ranking factors and uncertainty.
- Change correlation view.
- Impact radius.
- Remediation proposal, risks, approval, and verification status.
- Evaluation view for detection latency, accuracy, false positives, and evidence coverage.

## 14. Setup and Run

The following is a template; commands work only after the corresponding files and dependencies are implemented.

### Prerequisites
- Python version supported by the project
- Git
- Docker and Docker Compose
- Synthetic test data
- An LLM endpoint or local model for the explanation phase (optional initially)

```bash
git clone <your-repository-url>
cd tracemind-ai
python -m venv .venv
```

Activate the environment:

**Windows PowerShell**
```powershell
.\.venv\Scripts\Activate.ps1
```

**macOS/Linux**
```bash
source .venv/bin/activate
```

Install dependencies after `requirements.txt` exists:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Start configured services:

```bash
docker compose up --build
```

Run tests:

```bash
pytest -q
```

Start the dashboard once `dashboard/app.py` exists:

```bash
streamlit run dashboard/app.py
```

Suggested `.env.example` keys:
`OTEL_EXPORTER_OTLP_ENDPOINT`, `PROMETHEUS_URL`, `DATABASE_URL`, `GIT_PROVIDER`, `GIT_API_BASE_URL`, `LLM_PROVIDER`, `LLM_MODEL`.

Use placeholders only in `.env.example`. Keep real `.env` files and credentials out of Git.

## Dashboard

The TraceMind AI dashboard is a 5-page Streamlit application for incident investigation:

### Pages

| Page | File | Description |
|------|------|-------------|
| 1. Overview | `dashboard/app.py` | Incident summary, key metrics, affected services, leading hypothesis, quick navigation |
| 2. Timeline | `dashboard/pages/2_Timeline.py` | Interactive timeline with deployments, anomalies, errors, recovery; metrics charts |
| 3. Causal Graph | `dashboard/pages/3_Causal_Graph.py` | NetworkX graph with service dependencies, anomalies, deployments; path analysis |
| 4. Evidence Explorer | `dashboard/pages/4_Evidence_Explorer.py` | Logs, spans (with flame graph), metrics (time series + heatmap), deployments |
| 5. RCA Report | `dashboard/pages/5_RCA_Report.py` | Ranked hypotheses with factor breakdown, impact radius, remediation with approval workflow |

### Running the Dashboard

```bash
# Install dependencies (includes streamlit, plotly, networkx, streamlit-agraph)
pip install -r requirements.txt

# Generate synthetic incident data (run after starting services)
python -m simulator.run_scenario

# Start the dashboard
streamlit run dashboard/app.py
```

The dashboard opens at http://localhost:8501

### Dashboard Features

- **Page 1 - Overview**: Error rate, latency, request counts, affected services panel, root cause hypothesis with confidence
- **Page 2 - Timeline**: Plotly timeline chart with event filtering, detailed event cards, simulated metrics progression (latency, error rate, DB pool usage)
- **Page 3 - Causal Graph**: Interactive graph (hierarchical/force-directed) with 6 node types and 6 edge types, path analysis from deployment to errors, GraphML export
- **Page 4 - Evidence Explorer**: Structured logs with search/filter, span flame graphs per trace, metrics time series and heatmaps, deployment-incident correlation
- **Page 5 - RCA Report**: 3 ranked hypotheses with weighted factor scores (temporal, dependency, error, metric, change), impact radius visualization, remediation playbook with human approval (Approve/Reject/Execute), evaluation metrics

### Dashboard Screenshots

The dashboard reads from synthetic data generated by the Phase 1 simulator:
- `data/synthetic/scenario_ground_truth.json` - Incident ground truth
- `data/synthetic/deployments.csv` - Deployment records
- `data/synthetic/incident_scenarios.json` - Scenario definitions

Sample logs, spans, and metrics are generated dynamically for demonstration.

## 15. Synthetic Test Data

Use the TraceMind synthetic telemetry package before connecting real sources. It may include:

- `traces.jsonl`
- `logs.csv`
- `metrics.csv`
- `deployments.csv`
- `scenario_ground_truth.json`
- `telemetry_quality_challenges.csv`

### Primary scenario

A synthetic deployment of `payment-service` is associated with a connection-handling defect. Database connection utilization rises, payment requests time out, and failures propagate to `order-service` and `api-gateway`.

Test procedure:
1. Ingest traces, logs, metrics, and deployment records.
2. Keep ground-truth labels out of RCA inputs.
3. Normalize and validate records.
4. Correlate spans, logs, metrics, and deployments.
5. Build the graph and run detection/RCA.
6. Generate the report and recommendation.
7. Compare with ground truth only after the run.
8. Run malformed telemetry challenges separately.

This small synthetic dataset validates workflow logic, not production performance.

## 16. Testing and Evaluation

### Test types
- Unit tests for parsing, timestamps, validation, correlation, graph edges, scoring, and report validation.
- Integration tests from ingestion through RCA output.
- Scenario tests for known failures and healthy baselines.
- Data-quality tests for missing fields, invalid timestamps, duplicates, unknown services, out-of-range values, late events, and broken trace links.
- Safety tests ensuring no action executes without approval.
- Regression tests for fixed synthetic scenarios.

### Evaluation metrics

| Metric | Definition |
|---|---|
| Root-cause top-1 accuracy | Labeled incidents where the correct cause ranks first |
| Detection latency | Time from injected anomaly to detection |
| MTTR reduction | Investigation-time change versus manual baseline |
| Impact-radius accuracy | Agreement with known affected services |
| False-positive rate | Healthy windows incorrectly flagged |
| Evidence coverage | Key claims supported by retrievable evidence |
| Data-quality detection | Malformed records correctly flagged/quarantined |
| Remediation correctness | Recommendations appropriate for the scenario |

The problem statement's 85% MTTR reduction is a target, not a guaranteed result. Report measured results and limitations.

## 17. Requirement-to-Implementation Mapping

| Problem requirement | Component | Completion evidence |
|---|---|---|
| Ingest OpenTelemetry traces, logs, Prometheus metrics | Ingestion/normalization | Sample telemetry successfully ingested |
| Temporal causality graphs | Correlation/graph engine | Graph of trace, service, error, and timeline relationships |
| Link incidents to GitHub/GitLab commits and infrastructure changes | Change integration | Candidate changes linked with source evidence |
| Natural-language incident summaries | Graph RAG + LLM | Evidence-grounded report |
| Flame-graph links and log highlights | Trace/evidence dashboard | Trace details and relevant log lines accessible |
| Remediation playbooks | Remediation engine | Action, preconditions, risks, verification |
| Human-in-the-loop approval | Approval workflow | Action remains pending until approval |
| MTTR and alert-noise improvement | Evaluation | Measured baseline comparison and false-positive tests |
| Impact radius | Impact analyzer | Affected services supported by telemetry |

Only mark a requirement complete after its implementation and test evidence exist.

## 18. Development Roadmap

1. **Demo environment:** create services and a controlled incident.
2. **Telemetry:** instrument traces, logs, and metrics.
3. **Ingestion:** normalize and validate events.
4. **Correlation/graph:** connect evidence and construct the event graph.
5. **RCA/change analysis:** detect anomalies, rank hypotheses, calculate impact, correlate commits.
6. **Graph RAG/remediation:** retrieve evidence, generate reports, propose safe actions.
7. **Dashboard/evaluation:** visualize results and run tests.

A practical first estimate is six weeks, but actual duration depends on integration depth, compute, and available time.

## 19. Limitations and Future Work

Current limitations of the proposed MVP:
- Small set of synthetic failure scenarios.
- Threshold detection may miss subtle anomalies.
- Correlation does not automatically prove causality.
- Commit metadata may be incomplete.
- LLM quality depends on retrieval and model behavior.
- Production-scale throughput and reliability are not established by a local demo.

Future work:
- More telemetry backends and OTLP patterns.
- Kafka/Redpanda streaming where needed.
- Neo4j evaluation.
- Per-service baselines and improved anomaly detection.
- Calibrated RCA ranking on labeled incidents.
- More fault-injection scenarios.
- Authentication, authorization, tenancy, and audit controls.
- Carefully governed infrastructure remediation after simulation tests.
- Repeatable MTTR experiments.

## 20. Contributing

1. Create a feature branch for each change.
2. Add or update tests with each feature.
3. Keep secrets out of source control.
4. Run tests and linting before opening a merge request.
5. Document new event types, graph relationships, configuration, and limitations.
6. Merge only after review and passing checks.

## Project Success Criteria

The MVP is ready for demonstration when it can:
- Ingest and normalize synthetic traces, logs, metrics, and deployment records.
- Detect a controlled incident without alerting on the healthy baseline.
- Correlate evidence into a graph and rank a root-cause hypothesis.
- Link a relevant deployment/commit when supported by evidence.
- Generate a report whose major claims reference telemetry.
- Show affected services and a remediation recommendation.
- Require human approval before simulated action.
- Pass documented tests and report evaluation results honestly.

**Core principle:** correlate evidence first, reason over the graph second, and use the LLM to explain the investigation—not to invent the root cause.
