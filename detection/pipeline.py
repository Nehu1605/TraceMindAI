"""Detection pipeline CLI (Phase 4).

    python -m detection.pipeline \\
        --events data/processed/incident-001/normalized_events.jsonl \\
        --out-dir data/processed/incident-001
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ingestion.schema import NormalizedEvent

from .detector import AnomalyDetector


def load_events(path: Path) -> list[NormalizedEvent]:
    events: list[NormalizedEvent] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                events.append(NormalizedEvent.from_json(line))
    return events


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect anomalies per service baseline.")
    parser.add_argument("--events", default="data/processed/incident-001/normalized_events.jsonl")
    parser.add_argument("--out-dir", default="data/processed/incident-001")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    events = load_events(Path(args.events))
    result = AnomalyDetector().detect(events)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = result.to_dict()
    (out_dir / "anomalies.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )

    print("=== Detection summary (I8) ===")
    print(f"  anomalies : {payload['anomaly_count']}")
    print(f"  services  : {payload['services']}")
    for anomaly in result.anomalies:
        print(
            f"    {anomaly.onset_time.isoformat()}  {anomaly.service:16s} "
            f"{anomaly.metric:22s} {anomaly.direction:4s} z={anomaly.magnitude:.1f}"
        )
    print(f"  output    : {out_dir / 'anomalies.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
