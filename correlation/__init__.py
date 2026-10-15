"""Phase 3 correlation and event/causality graph.

Consumes the clean event stream from Phase 2 and produces a typed evidence
graph:

* trace/span relationships (``PART_OF``, ``PARENT_OF``, ``PRECEDED``),
* service dependency edges (``CALLS``),
* log-to-span links using trace ids where present and a service + time +
  error-signature fallback where they are not (I6),
* deployment/commit and alert attachments,
* alert grouping into incidents (I10) with an alert-reduction ratio and
  grouping-quality measurement,
* log-template mining and incident-windowed log reduction with a
  bytes-retained measurement (I10 log cost).
"""

from .alerting import AlertGroupingResult, group_alerts, grouping_quality
from .builder import CorrelationResult, correlate_events
from .graph import EventGraph
from .log_reduction import (
    LogReductionResult,
    mine_templates,
    reduce_logs,
    template_of,
)
from .windowing import sliding_windows

__all__ = [
    "AlertGroupingResult",
    "CorrelationResult",
    "EventGraph",
    "LogReductionResult",
    "correlate_events",
    "group_alerts",
    "grouping_quality",
    "mine_templates",
    "reduce_logs",
    "sliding_windows",
    "template_of",
]
