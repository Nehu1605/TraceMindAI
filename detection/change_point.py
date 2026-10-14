"""Change-point detection (improvement I8).

Slow drift and sudden shifts are not the same thing: a threshold rule catches
the former badly and the latter late. This is a small, dependency-free
change-point rule built on the rolling baseline - it reports the first index
where the level visibly moves and *stays* moved, which is what "the incident
started here" means in practice.
"""

from __future__ import annotations

from dataclasses import dataclass

from .baselines import RollingBaseline


@dataclass
class ChangePoint:
    index: int
    value: float
    direction: str  # "up" or "down"
    zscore: float


def detect_change_point(
    values: list[float],
    z_threshold: float = 4.0,
    min_points: int = 4,
    confirm: int = 2,
) -> ChangePoint | None:
    """Return the first sustained level shift in ``values``.

    ``confirm`` consecutive points beyond ``z_threshold`` are required before a
    change is accepted, which rejects single-sample blips.
    """

    if len(values) < min_points:
        return None

    baseline = RollingBaseline()
    baseline.extend(values[:min_points])

    run = 0
    run_start: ChangePoint | None = None
    for index in range(min_points, len(values)):
        value = values[index]
        z = baseline.robust_z(value)
        threshold = z_threshold
        if z >= threshold:
            direction = "up"
        elif z <= -threshold:
            direction = "down"
        else:
            run = 0
            run_start = None
            baseline.update(value)
            continue

        if run == 0:
            run_start = ChangePoint(index=index, value=value, direction=direction, zscore=z)
        run += 1
        if run >= confirm and run_start is not None:
            return run_start

        baseline.update(value)

    return None
