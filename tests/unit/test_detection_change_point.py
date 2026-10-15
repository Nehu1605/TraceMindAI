"""Unit tests for change-point detection (I8)."""

from __future__ import annotations

from detection.change_point import detect_change_point


def test_detects_sustained_upward_shift():
    values = [10, 10, 11, 10, 10, 10, 50, 52, 49, 51, 50]

    change = detect_change_point(values, z_threshold=4.0, min_points=4)

    assert change is not None
    assert change.direction == "up"
    assert change.index == 6  # first sustained spike


def test_detects_sustained_downward_shift():
    values = [50, 50, 51, 50, 50, 50, 2, 1, 3, 2, 2]

    change = detect_change_point(values, z_threshold=4.0, min_points=4)

    assert change is not None
    assert change.direction == "down"


def test_ignores_single_sample_blip():
    values = [10, 10, 11, 10, 10, 10, 40, 10, 10, 10, 10]

    change = detect_change_point(values, z_threshold=4.0, min_points=4, confirm=2)

    assert change is None


def test_flat_series_has_no_change_point():
    assert detect_change_point([5, 5, 5, 5, 5, 5, 5, 5], min_points=4) is None


def test_short_series_returns_none():
    assert detect_change_point([1, 2], min_points=4) is None
