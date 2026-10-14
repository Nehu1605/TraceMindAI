"""Report pipeline CLI (Phase 6).

    python -m report.pipeline \\
        --events data/processed/incident-001/normalized_events.jsonl \\
        --out-dir data/processed/incident-001
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ingestion.schema import NormalizedEvent
from rca.engine import RCAEngine
from report.builder import build_report


def load_events(path: Path) -> list[NormalizedEvent]:
    events: list[NormalizedEvent] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                events.append(NormalizedEvent.from_json(line))
    return events


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate an incident report.")
    parser.add_argument("--events", default="data/processed/incident-001/normalized_events.jsonl")
    parser.add_argument("--out-dir", default="data/processed/incident-001")
    parser.add_argument("--incident-id", default="incident-001")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--no-playbook", action="store_true", default=False)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    events = load_events(Path(args.events))
    rca = RCAEngine().analyze(events)
    report = build_report(
        incident_id=args.incident_id,
        rca=rca,
        run_playbook_flag=not args.no_playbook,
        dry_run=args.dry_run,
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    (out_dir / "report.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("=== Incident report (I4/I11/I13) ===")
    print(f"  incident: {args.incident_id}")
    print(f"  narrative: {report.narrative[:120]}...")
    print(f"  generators: {list(report.generators.keys())}")
    print(f"  critic agree: {report.critic['agree']}")
    if report.playbook:
        print(f"  playbook: {report.playbook.playbook} (dry_run={report.playbook.dry_run})")
    print(f"  output: {out_dir / 'report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())