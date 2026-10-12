from __future__ import annotations

import json
import logging

from common.logging_config import JsonFormatter


def test_json_formatter_emits_correlation_fields():
    formatter = JsonFormatter("payment-service", "test")
    record = logging.LogRecord(
        name="app",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="database %s",
        args=("timeout",),
        exc_info=None,
    )

    payload = json.loads(formatter.format(record))

    assert payload["service"] == "payment-service"
    assert payload["severity"] == "ERROR"
    assert payload["message"] == "database timeout"
    assert "trace_id" in payload
    assert "span_id" in payload
    assert payload["timestamp"].endswith("Z")
