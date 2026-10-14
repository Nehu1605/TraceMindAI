# Phase 6 - Incident Report, Remediation & Guardrails

Phase 5 gives you a ranked, explainable RCA. Phase 6 produces a **machine-readable
report** that a human (or a dashboard) can trust:

* deterministic offline narrative (always works, no API keys)
* optional LLM generator (OpenAI-compatible, gated by `llm_enabled`)
* **critic** that compares the two and flags disagreements (I4)
* **redaction** and **prompt-injection guard** before any external call (I13)
* **remediation playbooks** with a dry-run sandbox (I11)

## Generators (I4)

| Generator | Trigger | Purpose |
| --- | --- | --- |
| **offline** | always | template-based, deterministic, evidence-cited |
| **llm** | `llm_enabled=true` | natural language, optional |
| **critic** | always | diffs the two; `agree=false` = human review required |

The offline version is the source of truth. If the LLM differs, the critic
records the disagreement and the report consumer should not auto-act on the
LLM text.

## Redaction & Prompt Guard (I13)

Before any external call the text passes through:

1. `redact()` - regexes for API keys, bearer tokens, base64 blobs, etc.
2. `guard_prompt()` - rejects "ignore previous instructions", "system: you are
   now", special tokens, markdown headers that look like prompt engineering.

Both are pure functions with no side effects; the test suite covers them.

## Playbooks & Sandbox (I11)

Built-in catalog (extensible via config):

| Playbook | Triggers | Steps (dry-run) |
| --- | --- | --- |
| `db_pool_exhaustion` | `db_connections_in_use`, `postgres`, `payment-service` | check DB configmap, restart deployment |
| `high_latency` | `http_request_duration_ms`, `cpu_percent` | scale up, check HPA |
| `error_spike` | `http_5xx_rate`, `error_rate` | list rollouts, undo |

`run_playbook(name, dry_run=True)` returns a `RemediationResult` with the
command, exit code and truncated output. `dry_run=True` (default) only echoes
the command; `dry_run=False` executes via `subprocess` with a 30-second
timeout.

## Run it

```powershell
python -m report.pipeline --events data/processed/incident-001/normalized_events.jsonl `
    --out-dir data/processed/incident-001 --incident-id incident-001
```

Output: `report.json`.

### Reference run

```
=== Incident report (I4/I11/I13) ===
  incident: incident-001
  narrative: Incident likely originated in **payment-service** (confidence: high). ...
  generators: ['offline', 'llm']
  critic agree: False
  playbook: db_pool_exhaustion (dry_run=True)
  output: data\processed\incident-001\report.json
```

The critic correctly reports `agree: False` because the LLM stub says "LLM
disabled" while the offline generator produces the full narrative.

## Tests

- `tests/unit/test_report_builder.py`
- `tests/integration/test_report_pipeline.py`

## Config

| Setting | Default | Meaning |
| --- | --- | --- |
| `llm_enabled` | false | enable OpenAI-compatible call |
| `llm_model` | gpt-4o-mini | model name |
| `llm_base_url` | https://api.openai.com/v1 | endpoint |
| `report_min_evidence_coverage` | 0.9 | unused yet; future gate |