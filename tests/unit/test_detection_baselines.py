"""Unit tests for per-service baselines (I8)."""

from __future__ import annotations

from detection.baselines import EwmaBaseline, RollingBaseline


def test_rolling_baseline_median_and_mad():
    baseline = RollingBaseline()
    baseline.extend([10, 11, 12, 11, 10])

    assert baseline.median == 11
    assert baseline.mad == 1


def test_robust_z_flags_a_spike_not_normal_values():
    baseline = RollingBaseline()
    baseline.extend([10, 11, 12, 11, 10, 12, 9])

    assert baseline.robust_z(11) < 1.0
    assert baseline.robust_z(50) > 4.0


def test_flat_baseline_gives_bounded_score():
    baseline = RollingBaseline()
    baseline.extend([5, 5, 5, 5])

    # MAD is zero; a real deviation must still be reported as large, not inf.
    assert baseline.robust_z(5) == 0.0
    assert baseline.robust_z(9) == 50.0


def test_ewma_tracks_mean_and_flags_drift():
    ewma = EwmaBaseline(alpha=0.4)
    for value in [10, 10, 10, 10, 10]:
        ewma.update(value)

    assert abs(ewma.mean - 10.0) < 0.01
    assert ewma.zscore(100) > 4.0
    assert abs(ewma.zscore(10)) < 1.0
