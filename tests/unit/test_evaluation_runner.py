"""Unit tests for the evaluation runner & metrics (I2/I3/I6/I7/I10)."""

from __future__ import annotations

from rca.engine import Candidate, RCAReport
from evaluation.runner import accuracy_at_loss, compute_summary
from evaluation.scenarios import Scenario


def _make_result(top1: str | None, expected: str | None, healthy: bool = False, baseline: dict | None = None) -> "ScenarioResult":
    from dataclasses import dataclass

    @dataclass
    class ScenarioResult:
        scenario_id: str
        is_healthy: bool
        expected_root: str | None
        detected_anomalies: int
        rca_top1: str | None
        rca_top3: list[str]
        rca_confidence: str
        rca_abstained: bool
        baseline_ranks: dict[str, list[str]]
        ingest_time_s: float
        detect_time_s: float
        rca_time_s: float
        report_time_s: float
        events_ingested: int
        events_correlated: int
        templates_retained: int
        templates_total: int
        log_bytes_retained: int
        log_bytes_total: int

    return ScenarioResult(
        scenario_id="test",
        is_healthy=healthy,
        expected_root=expected,
        detected_anomalies=1,
        rca_top1=top1,
        rca_top3=[top1] if top1 else [],
        rca_confidence="high" if top1 else "none",
        rca_abstained=top1 is None,
        baseline_ranks=baseline or {"B1_latest_anomaly": ["other"], "B2_max_magnitude": ["other"], "B3_log_volume": ["other"], "B4_latest_deploy": ["other"]},
        ingest_time_s=0.01,
        detect_time_s=0.01,
        rca_time_s=0.01,
        report_time_s=0.01,
        events_ingested=100,
        events_correlated=80,
        templates_retained=10,
        templates_total=100,
        log_bytes_retained=1000,
        log_bytes_total=10000,
    )


def test_top1_top3_accuracy():
    results = [
        _make_result("payment-service", "payment-service"),
        _make_result("payment-service", "payment-service"),
        _make_result("order-service", "payment-service"),  # wrong
    ]

    summary = compute_summary(results)
    assert summary.top1_accuracy == 2 / 3
    assert summary.top3_accuracy == 2 / 3


def test_baseline_accuracies():
    results = [
        _make_result("payment-service", "payment-service", baseline={"B1_latest_anomaly": ["payment-service"], "B2_max_magnitude": ["other"]}),
        _make_result("payment-service", "payment-service", baseline={"B1_latest_anomaly": ["other"], "B2_max_magnitude": ["payment-service"]}),
    ]

    summary = compute_summary(results)
    assert summary.baseline_top1["B1_latest_anomaly"] == 0.5
    assert summary.baseline_top1["B2_max_magnitude"] == 0.5


def test_mttr_mean():
    results = [
        _make_result("payment-service", "payment-service"),
        _make_result("payment-service", "payment-service"),
    ]
    # Each has 0.04s total
    summary = compute_summary(results)
    assert abs(summary.mttr_mean_s - 0.04) < 0.01


def test_throughput():
    results = [
        _make_result("payment-service", "payment-service"),
    ]
    summary = compute_summary(results)
    # 100 events / 0.04s = 2500 eps
    assert abs(summary.throughput_eps - 2500) < 100


def test_log_reduction_ratio():
    results = [
        _make_result("payment-service", "payment-service"),
    ]
    summary = compute_summary(results)
    assert abs(summary.log_reduction_ratio - 0.1) < 0.01


def test_accuracy_at_loss():
    results = [
        _make_result("payment-service", "payment-service"),
        _make_result("payment-service", "payment-service"),
    ]
    loss_map = accuracy_at_loss(results, loss_rates=[0.0, 0.5])
    assert loss_map["loss_0"] == 1.0
    # With 50% loss and deterministic seed, both should survive or not
    assert loss_map["loss_50"] in (0.0, 0.5, 1.0)