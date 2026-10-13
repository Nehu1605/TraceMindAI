"""Correlation pipeline CLI.

Reads the normalized event stream produced by Phase 2 and writes the
evidence graph plus incident/alert-grouping output.

    python -m correlation.pipeline \\
        --events data/processed/incident-001/normalized_events.jsonl \\
        --out-dir data/processed/incident-001
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ingestion.schema import NormalizedEvent

from .builder import correlate_events


def load_events(path: Path) -> list[NormalizedEvent]:
    events: list[NormalizedEvent] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                events.append(NormalizedEvent.from_json(line))
    return events


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the TraceMind correlation graph.")
    parser.add_argument(
        "--events",
        default="data/processed/incident-001/normalized_events.jsonl",
        help="Path to normalized_events.jsonl from the ingestion pipeline.",
    )
    parser.add_argument(
        "--out-dir",
        default="data/processed/incident-001",
        help="Directory for graph and incident output.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    events = load_events(Path(args.events))
    result = correlate_events(events)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result.graph.save(out_dir / "graph.json")
    (out_dir / "incidents.json").write_text(
        json.dumps(result.alert_grouping.to_dict(), indent=2), encoding="utf-8"
    )
    log_reduction = result.log_reduction
    (out_dir / "log_reduction.json").write_text(
        json.dumps(log_reduction.to_dict(), indent=2), encoding="utf-8"
    )
    with (out_dir / "reduced_logs.jsonl").open("w", encoding="utf-8") as handle:
        for event in log_reduction.kept_events:
            handle.write(event.to_json() + "\n")
    summary = result.summary()
    (out_dir / "correlation_summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )

    print("=== Correlation summary ===")
    print(f"  events correlated : {summary['event_count']}")
    print(f"  graph             : {result.graph_stats['nodes']} nodes, "
          f"{result.graph_stats['edges']} edges")
    print(f"  link quality      : {result.correlation_counts}")
    print(f"  service CALLS     : {result.graph_stats['service_dependencies']}")
    print(f"  raw alerts        : {result.alert_grouping.raw_alert_count}")
    print(f"  incident groups   : {result.alert_grouping.incident_count}")
    print(f"  alert reduction   : {result.alert_grouping.reduction_ratio}x")
    print(f"  log templates     : {log_reduction.template_count} templates from "
          f"{log_reduction.unique_lines} unique / {log_reduction.log_count_total} lines "
          f"({log_reduction.template_reduction_pct}% fewer distinct)")
    print(f"  logs kept         : {log_reduction.log_count_retained}/"
          f"{log_reduction.log_count_total} "
          f"({log_reduction.log_reduction_pct}% fewer)")
    print(f"  log bytes         : {log_reduction.bytes_reduction_pct}% fewer")
    print(f"  output            : {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
