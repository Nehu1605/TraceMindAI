"""RCA pipeline CLI (Phase 5).

    python -m rca.pipeline \\
        --events data/processed/incident-001/normalized_events.jsonl \\
        --out-dir data/processed/incident-001
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ingestion.schema import NormalizedEvent

from .engine import RCAEngine


def load_events(path: Path) -> list[NormalizedEvent]:
    events: list[NormalizedEvent] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                events.append(NormalizedEvent.from_json(line))
    return events


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Explain the incident (propagation-aware RCA).")
    parser.add_argument("--events", default="data/processed/incident-001/normalized_events.jsonl")
    parser.add_argument("--out-dir", default="data/processed/incident-001")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    events = load_events(Path(args.events))
    report = RCAEngine().analyze(events)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    (out_dir / "rca.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("=== RCA summary (I2/I8/I9/I12) ===")
    print(f"  {report.summary()}")
    print(f"  anomalous services: {payload['anomalous_services']}")
    for rank, candidate in enumerate(report.candidates, start=1):
        print(
            f"    #{rank} {candidate.service:16s} score={candidate.score:.3f} "
            f"conf={candidate.confidence}"
        )
    print("  baselines:")
    for name, ranked in payload["baselines"].items():
        print(f"    {name}: {ranked[:1] or ['-']}")
    print(f"  output: {out_dir / 'rca.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
