"""Degradation curve for messy telemetry (improvement I6).

Re-runs the same incident at increasing levels of data loss and reports how
the ingestion pipeline copes:

* 0%   - clean input
* 10%  - 10% of spans dropped, trace ids removed from 10% of logs, 200 ms skew
* 20%  - as above at 20%
* 30%  - as above at 30%

The point is the curve, not a single number: a pipeline whose valid-ingest
rate stays high and whose *direct* trace-link coverage falls slowly is
robust to the messiness real systems produce.

Usage::

    python -m simulator.degradation_test --work-dir data/processed/degradation
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ingestion.pipeline import run_ingestion
from simulator.generate_telemetry import DegradeConfig, generate_dataset

DATA_LOSS_LEVELS = (0.0, 0.10, 0.20, 0.30)
CLOCK_SKEW_MS = 200


def run_curve(
    work_dir: Path,
    levels: tuple[float, ...] = DATA_LOSS_LEVELS,
    clock_skew_ms: int = CLOCK_SKEW_MS,
    seed: int = 123,
    requests: int = 60,
) -> list[dict]:
    work_dir = Path(work_dir)
    rows: list[dict] = []
    for level in levels:
        degrade = DegradeConfig(
            missing_trace_id_rate=level,
            drop_span_rate=level,
            clock_skew_ms=clock_skew_ms,
            duplicate_rate=0.0,
        )
        raw = work_dir / f"raw-{int(level * 100):02d}"
        out = work_dir / f"out-{int(level * 100):02d}"
        generate_dataset(raw, seed=seed, requests=requests, degrade=degrade)
        result = run_ingestion(raw, out)

        report = result.quality_report
        valid = len(result.events)
        total = valid + len(result.quarantined)
        direct = report.evidence_quality.get("direct", 0)
        time_only = report.evidence_quality.get("time_only", 0)

        rows.append(
            {
                "data_loss": level,
                "valid_events": valid,
                "quarantined": len(result.quarantined),
                "ingest_success_rate": round(valid / total, 4) if total else 0.0,
                "direct_link_rate": round(direct / valid, 4) if valid else 0.0,
                "time_only_link_rate": round(time_only / valid, 4) if valid else 0.0,
                "broken_trace_links": report.broken_trace_links,
                "missing_trace_id_rate": round(report.missing_trace_id_rate, 4),
                "clock_skew_suspected": report.clock_skew_suspected,
            }
        )
    return rows


def _print_table(rows: list[dict]) -> None:
    headers = (
        "data_loss",
        "valid_events",
        "ingest_success",
        "direct_link",
        "time_only_link",
        "broken_links",
    )
    print("  ".join(f"{h:>15}" for h in headers))
    for row in rows:
        print(
            "  ".join(
                f"{value:>15}"
                for value in (
                    f"{row['data_loss']:.0%}",
                    row["valid_events"],
                    f"{row['ingest_success_rate']:.1%}",
                    f"{row['direct_link_rate']:.1%}",
                    f"{row['time_only_link_rate']:.1%}",
                    row["broken_trace_links"],
                )
            )
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the messy-telemetry degradation curve.")
    parser.add_argument("--work-dir", default="data/processed/degradation")
    parser.add_argument("--requests", type=int, default=60)
    parser.add_argument("--seed", type=int, default=123)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    work_dir = Path(args.work_dir)
    rows = run_curve(work_dir, seed=args.seed, requests=args.requests)

    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "robustness_curve.json").write_text(
        json.dumps(rows, indent=2), encoding="utf-8"
    )

    print("=== Degradation curve (I6) ===")
    _print_table(rows)
    print(f"written: {work_dir / 'robustness_curve.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
