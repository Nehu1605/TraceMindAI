"""Persistence for normalized events.

For the MVP the unified event store is a set of JSONL/JSON files: easy to
inspect, diff and test. A PostgreSQL schema is provided in ``sql/schema.sql``
for the later phases that need incident and evaluation persistence.
"""

from __future__ import annotations

import json
from pathlib import Path

from .schema import NormalizedEvent
from .validation import QuarantineRecord


class UnifiedEventStore:
    def __init__(self, out_dir: Path) -> None:
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)

    @property
    def events_path(self) -> Path:
        return self.out_dir / "normalized_events.jsonl"

    @property
    def quarantine_path(self) -> Path:
        return self.out_dir / "quarantined.jsonl"

    @property
    def quality_path(self) -> Path:
        return self.out_dir / "quality_report.json"

    def write_events(self, events: list[NormalizedEvent]) -> Path:
        with self.events_path.open("w", encoding="utf-8") as handle:
            for event in events:
                handle.write(event.to_json() + "\n")
        return self.events_path

    def write_quarantine(self, quarantined: list[QuarantineRecord]) -> Path:
        with self.quarantine_path.open("w", encoding="utf-8") as handle:
            for record in quarantined:
                handle.write(
                    json.dumps(
                        {
                            "source_reference": record.source_reference,
                            "reasons": record.reasons,
                            "raw": record.raw,
                        },
                        default=str,
                    )
                    + "\n"
                )
        return self.quarantine_path

    def write_json(self, name: str, payload: dict) -> Path:
        path = self.out_dir / name
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return path
