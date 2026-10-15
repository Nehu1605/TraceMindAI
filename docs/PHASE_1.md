# Phase 1 - Environment Setup and Simulated Microservices

This phase delivers a **reproducible, controlled distributed system** in
which a single incident can be triggered and observed. It intentionally
contains no correlation, RCA, or LLM logic - those arrive in later phases.

## Deliverables

| Item | Location |
|---|---|
| API Gateway (FastAPI) | `services/api_gateway/` |
| Order Service | `services/order_service/` |
| Payment Service (hosts the defect) | `services/payment_service/` |
| User Service | `services/user_service/` |
| Shared config/logging/tracing/metrics/DB | `common/` |
| PostgreSQL + Collector + Jaeger + Prometheus | `docker-compose.yml`, `telemetry/` |
| Incident simulator & ground truth | `simulator/`, `data/synthetic/` |
| Tests | `tests/` |

## Primary incident

A buggy `payment-service` revision (`db_conn_leak` fault mode) leaks one
database connection per request until the connection pool is exhausted.
The observable sequence is:

```
normal operation
  -> buggy payment-service deployment
  -> database connection exhaustion
  -> payment latency increases, then payments fail (503)
  -> order requests fail (502)
  -> api-gateway returns HTTP 500
```

This is the exact scenario later phases must rediscover from telemetry
alone; the injected cause is recorded only in the ground-truth file.

## Run locally (Docker)

```bash
docker compose up --build
```

Services: gateway `:8000`, order `:8001`, payment `:8002`, user `:8003`,
Prometheus `:9090`, Jaeger `:16686`.

Reproduce the incident and write ground truth:

```bash
python -m simulator.run_scenario
```

## Run locally (no Docker, no database)

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
set DB_BACKEND=simulated
set OTEL_ENABLED=false
uvicorn services.api_gateway.app:app --port 8000
uvicorn services.order_service.app:app --port 8001
uvicorn services.payment_service.app:app --port 8002
uvicorn services.user_service.app:app --port 8003
```

## Fault control

```bash
# activate the defect
curl -X POST http://localhost:8002/admin/fault -H "Content-Type: application/json" -d "{\"mode\":\"db_conn_leak\"}"
# inspect status
curl http://localhost:8002/admin/fault
# reset to healthy
curl -X POST http://localhost:8002/admin/reset
```

## Tests

```bash
pytest -q
```

* `tests/unit` - config, connection pool, JSON logging, payment fault flow.
* `tests/integration` - full gateway -> order -> payment/user propagation.
* `tests/scenarios` - ground-truth data contract.

## Acceptance criteria

- All four services start and serve `/healthz` and `/metrics`.
- A healthy run of `POST /orders` returns `200 CONFIRMED`.
- After activating `db_conn_leak`, the gateway returns `HTTP 500`.
- `POST /admin/reset` restores healthy behavior and releases connections.
- `simulator/run_scenario.py` writes a ground-truth JSON with the injected
  cause, deployment id, timestamps, and affected services.
