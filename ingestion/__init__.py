"""Phase 2 telemetry ingestion, normalization and validation.

The goal of this package is to turn heterogeneous raw telemetry (traces,
logs, metrics, deployments and raw alerts) into a single, clean, normalized
event stream that later phases can correlate. It also implements the
robustness work from the improvement plan:

* I6 - tolerates messy telemetry (missing trace ids, clock skew, dropped
  spans, duplicates) and records an evidence-quality label per event.
* I10 - ingests raw Prometheus alerts so alert-grouping can be measured.
"""

__all__ = ["schema", "normalize", "validation", "parsers", "pipeline"]
