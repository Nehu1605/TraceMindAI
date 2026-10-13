"""The ingestion pipeline: raw telemetry in, clean events out.

Steps:

1. discover and parse raw telemetry files
2. normalize each record into a ``NormalizedEvent``
3. annotate timing quality and validate; quarantine invalid records
4. detect broken trace links across the batch
5. order events with a clock tolerance
6. write normalized events, quarantined records and a quality report

Run it with::

    python -m ingestion.pipeline --raw-dir data/synthetic/incident-001 \\
        --out-dir data/processed/incident-001
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from common.config import Settings, get_settings

from .constants import CANONICAL_SERVICES
from .parsers import parse_raw_directory
from .quality import QualityReport, build_quality_report
from .schema import NormalizedEvent, SourceType
from .store import UnifiedEventStore
from .temporal import sort_events
from .validation import (
    REASON_MISSING_REQUIRED_FIELD,
    EventValidator,
    QuarantineRecord,
    detect_broken_trace_links,
)


@dataclass
class PipelineResult:
    events: list[NormalizedEvent]
    quarantined: list[QuarantineRecord]
    quality_report: QualityReport
    out_dir: Path
    counts_by_source: dict[str, int] = field(default_factory=dict)


def run_ingestion(
    raw_dir: Path,
    out_dir: Path,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> PipelineResult:
    settings = settings or get_settings()
    raw_dir = Path(raw_dir)
    out_dir = Path(out_dir)

    validator = EventValidator(
        known_services=set(CANONICAL_SERVICES),
        late_threshold_seconds=settings.late_event_threshold_seconds,
        clock_skew_threshold_ms=settings.clock_skew_threshold_ms,
    )

    parsed = parse_raw_directory(raw_dir, now)

    events: list[NormalizedEvent] = []
    quarantined: list[QuarantineRecord] = []
    for record in parsed:
        if record.event is None:
            quarantined.append(
                QuarantineRecord(
                    source_reference=record.source_reference,
                    reasons=record.reasons or [REASON_MISSING_REQUIRED_FIELD],
                    raw=record.raw,
                )
            )
            continue
        reasons = validator.check(record.event)
        if reasons:
            quarantined.append(
                QuarantineRecord(
                    source_reference=record.source_reference,
                    reasons=reasons,
                    raw=record.raw,
                )
            )
        else:
            events.append(record.event)

    detect_broken_trace_links(events)
    events = sort_events(events, settings.event_time_tolerance_ms)

    report = build_quality_report(events, quarantined, total_raw=len(parsed))

    store = UnifiedEventStore(out_dir)
    store.write_events(events)
    store.write_quarantine(quarantined)
    store.write_json("quality_report.json", report.to_dict())
    store.write_json(
        "summary.json",
        {
            "raw_dir": str(raw_dir),
            "events": len(events),
            "quarantined": len(quarantined),
            "by_source_type": report.by_source_type,
            "error_events": sum(
                1 for e in events if e.severity.value in {"ERROR", "FATAL"}
            ),
            "alert_events": sum(
                1 for e in events if e.source_type == SourceType.ALERT
            ),
            "deployment_events": sum(
                1 for e in events if e.source_type == SourceType.DEPLOYMENT
            ),
        },
    )

    counts: dict[str, int] = {}
    for event in events:
        counts[event.source_type.value] = counts.get(event.source_type.value, 0) + 1

    return PipelineResult(
        events=events,
        quarantined=quarantined,
        quality_report=report,
        out_dir=out_dir,
        counts_by_source=counts,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the TraceMind ingestion pipeline.")
    parser.add_argument("--raw-dir", required=True, help="Directory of raw telemetry files.")
    parser.add_argument("--out-dir", required=True, help="Directory for normalized output.")
    parser.add_argument(
        "--now",
        default=None,
        help="Optional ISO timestamp to use as ingestion 'now' (for reproducible runs).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    now = None
    if args.now:
        from .normalize import parse_timestamp

        now = parse_timestamp(args.now)

    result = run_ingestion(Path(args.raw_dir), Path(args.out_dir), now=now)

    print("=== Ingestion summary ===")
    print(f"  valid events      : {len(result.events)}")
    print(f"  quarantined       : {len(result.quarantined)}")
    print(f"  by source type    : {result.counts_by_source}")
    print(f"  quarantine reasons: {result.quality_report.quarantine_reasons}")
    print(f"  missing trace id  : {result.quality_report.missing_trace_id_rate:.1%}")
    print(f"  late events       : {result.quality_report.late_events}")
    print(f"  clock skew likely : {result.quality_report.clock_skew_suspected}")
    print(f"  broken trace links: {result.quality_report.broken_trace_links}")
    print(f"  output            : {result.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
