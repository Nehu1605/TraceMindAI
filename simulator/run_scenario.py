"""Reproduce the primary Phase 1 incident and record its ground truth.

Sequence:
    1. reset payment-service to a healthy state
    2. run warm-up (healthy) traffic
    3. deploy the buggy payment revision and record a deployment event
    4. run incident traffic until failures propagate
    5. reset to a healthy state and run recovery traffic
    6. write a ground-truth record for later evaluation

The ground truth is written to a separate file and is never fed back into
the services, so it cannot leak into the RCA logic in later phases.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

from simulator.load_generator import TrafficStats, run_traffic

BUGC_COMMIT_SHA = "c0ffee1d00m3"
BUG_CHANGED_FILES = "services/payment_service/app.py"
BUG_CHANGE_SUMMARY = "Introduce connection handling defect in payment-service"
DECOY_COMMIT_SHA = "dec0y0abc"
DECOY_CHANGED_FILES = "services/user_service/app.py"
DECOY_CHANGE_SUMMARY = "Bump user-service request logging (unrelated to the incident)"

DEFAULT_OUTPUT = "data/synthetic/scenario_ground_truth.json"
DEFAULT_DEPLOYMENTS = "data/synthetic/deployments.csv"


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _set_fault(admin_url: str, mode: str) -> dict:
    response = httpx.post(f"{admin_url}/admin/fault", json={"mode": mode}, timeout=5.0)
    response.raise_for_status()
    return response.json()


def _reset(admin_url: str) -> dict:
    response = httpx.post(f"{admin_url}/admin/reset", timeout=5.0)
    response.raise_for_status()
    return response.json()


def _append_deployment(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "deployment_id",
        "service_name",
        "timestamp",
        "commit_sha",
        "status",
        "changed_files",
        "change_summary",
    ]
    is_new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if is_new:
            writer.writeheader()
        writer.writerow(record)


def execute_scenario(
    gateway_url: str,
    payment_admin_url: str,
    warmup_seconds: float,
    incident_seconds: float,
    recovery_seconds: float,
    rps: float,
    output_path: Path,
    deployments_path: Path,
) -> dict:
    print("[1/6] Resetting payment-service to healthy state")
    _reset(payment_admin_url)

    print(f"[2/6] Warm-up traffic for {warmup_seconds}s at {rps} rps")
    baseline = run_traffic(gateway_url, warmup_seconds, rps)

    print("[3/6] Deploying buggy payment-service revision")
    incident_start = _now_iso()
    deployment = {
        "deployment_id": f"dep-{uuid.uuid4().hex[:10]}",
        "service_name": "payment-service",
        "timestamp": incident_start,
        "commit_sha": BUGC_COMMIT_SHA,
        "status": "deployed",
        "changed_files": BUG_CHANGED_FILES,
        "change_summary": BUG_CHANGE_SUMMARY,
    }
    _append_deployment(deployments_path, deployment)
    fault = _set_fault(payment_admin_url, "db_conn_leak")
    print(f"    Fault active: {fault}")

    # Decoy deployment (I1): land an unrelated deploy on a healthy service
    # immediately *after* the fault, so a "blame the latest deploy" baseline
    # (B4) is fooled and commit attribution is forced to use evidence.
    decoy = {
        "deployment_id": f"dep-{uuid.uuid4().hex[:10]}",
        "service_name": "user-service",
        "timestamp": _now_iso(),
        "commit_sha": DECOY_COMMIT_SHA,
        "status": "deployed",
        "changed_files": DECOY_CHANGED_FILES,
        "change_summary": DECOY_CHANGE_SUMMARY,
    }
    _append_deployment(deployments_path, decoy)
    print(f"    Decoy deployment recorded: {decoy['deployment_id']}")

    print(f"[4/6] Incident traffic for {incident_seconds}s at {rps} rps")
    incident = run_traffic(gateway_url, incident_seconds, rps)
    incident_end = _now_iso()

    print("[5/6] Rolling back / resetting payment-service")
    _reset(payment_admin_url)
    print(f"[6/6] Recovery traffic for {recovery_seconds}s at {rps} rps")
    recovery = run_traffic(gateway_url, recovery_seconds, rps)

    ground_truth = {
        "scenario_id": "payment-db-conn-exhaustion-001",
        "description": (
            "A buggy payment-service revision leaks database connections, "
            "exhausting the connection pool and cascading failures to "
            "order-service and api-gateway."
        ),
        "injected_cause": "db_conn_leak",
        "root_cause_service": "payment-service",
        "deployment": deployment,
        "decoy_deployments": [decoy],
        "incident_start_time": incident_start,
        "incident_end_time": incident_end,
        "affected_services": ["payment-service", "order-service", "api-gateway"],
        "expected_symptoms": [
            "database connection utilization rises to pool limit",
            "payment-service latency increases then fails",
            "order-service returns errors",
            "api-gateway returns HTTP 500",
        ],
        "healthy_baseline": _merge(baseline.to_dict()),
        "incident_traffic": _merge(incident.to_dict()),
        "recovery_traffic": _merge(recovery.to_dict()),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(ground_truth, indent=2), encoding="utf-8")
    print(f"Ground truth written to {output_path}")
    return ground_truth


def _merge(stats: dict) -> dict:
    return {
        "total": stats["total"],
        "success": stats["success"],
        "server_errors": stats["server_errors"],
        "transport_errors": stats["transport_errors"],
        "error_rate": stats["error_rate"],
        "avg_latency_ms": stats["avg_latency_ms"],
        "max_latency_ms": stats["max_latency_ms"],
        "status_counts": stats["status_counts"],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the TraceMind Phase 1 incident scenario.")
    parser.add_argument("--gateway-url", default=os.environ.get("GATEWAY_URL", "http://localhost:8000"))
    parser.add_argument(
        "--payment-admin-url",
        default=os.environ.get("PAYMENT_ADMIN_URL", "http://localhost:8002"),
    )
    parser.add_argument("--warmup-seconds", type=float, default=6.0)
    parser.add_argument("--incident-seconds", type=float, default=15.0)
    parser.add_argument("--recovery-seconds", type=float, default=6.0)
    parser.add_argument("--rps", type=float, default=5.0)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--deployments-file", default=DEFAULT_DEPLOYMENTS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = execute_scenario(
        gateway_url=args.gateway_url,
        payment_admin_url=args.payment_admin_url,
        warmup_seconds=args.warmup_seconds,
        incident_seconds=args.incident_seconds,
        recovery_seconds=args.recovery_seconds,
        rps=args.rps,
        output_path=Path(args.output),
        deployments_path=Path(args.deployments_file),
    )

    print("\n=== Scenario summary ===")
    for phase in ("healthy_baseline", "incident_traffic", "recovery_traffic"):
        stats = result[phase]
        print(
            f"{phase:18s} total={stats['total']:4d} "
            f"errors={stats['server_errors']:4d} "
            f"error_rate={stats['error_rate']:.2f} "
            f"avg_latency_ms={stats['avg_latency_ms']:.1f}"
        )

    if result["incident_traffic"]["server_errors"] == 0:
        print("WARNING: no server errors observed during the incident window.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
