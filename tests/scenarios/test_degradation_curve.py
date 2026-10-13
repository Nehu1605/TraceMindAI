"""Scenario test for the messy-telemetry degradation curve (I6).

Asserts the properties that make the curve a *robustness* result rather than
just a table: ingestion keeps succeeding as data is lost, and the strongest
(direct) trace-link coverage falls as noise increases instead of collapsing.
"""

from __future__ import annotations

from simulator.degradation_test import DATA_LOSS_LEVELS, run_curve


def test_degradation_curve_shape(tmp_path):
    rows = run_curve(tmp_path / "degradation", requests=40)

    assert [row["data_loss"] for row in rows] == list(DATA_LOSS_LEVELS)
    assert len(rows) == 4


def test_ingestion_stays_robust_as_data_is_lost(tmp_path):
    rows = run_curve(tmp_path / "degradation", requests=40)

    for row in rows:
        assert row["valid_events"] > 0
        # The pipeline degrades gracefully: it keeps ingesting almost
        # everything even when a third of the spans are gone.
        assert row["ingest_success_rate"] >= 0.9


def test_direct_link_coverage_falls_but_does_not_collapse(tmp_path):
    rows = run_curve(tmp_path / "degradation", requests=40)

    clean = rows[0]
    worst = rows[-1]

    assert clean["missing_trace_id_rate"] == 0.0
    assert worst["missing_trace_id_rate"] > 0.0
    # More missing ids means fewer direct links, but the stream is still usable.
    assert worst["direct_link_rate"] <= clean["direct_link_rate"]
    assert worst["direct_link_rate"] > 0.0
