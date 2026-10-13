"""Phase 3 correlation and event/causality graph.

Consumes the clean event stream from Phase 2 and produces a typed evidence
graph:

* trace/span relationships (``PART_OF``, ``PARENT_OF``, ``PRECEDED``),
* service dependency edges (``CALLS``),
* log-to-span links using trace ids where present and a service + time +
  error-signature fallback where they are not (I6),
* deployment/commit and alert attachments,
* alert grouping into incidents (I10) with an alert-reduction ratio.
"""

from .builder import CorrelationResult, correlate_events
from .graph import EventGraph

__all__ = ["CorrelationResult", "EventGraph", "correlate_events"]
