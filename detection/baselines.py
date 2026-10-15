"""Per-service baselines for anomaly detection (improvement I8).

A single global threshold ("latency above X") either fires constantly on busy
services or misses slow drift. The plan asks for each service to be judged
against *its own* behaviour: a rolling median with a spread measure (MAD), or
an exponentially weighted average. Both are provided here.

``robust_z`` is deliberately based on the median and MAD, not the mean and
standard deviation, so a few large spikes do not inflate the spread and hide
themselves.
"""

from __future__ import annotations

from collections import deque
from statistics import median


class RollingBaseline:
    """Rolling median + MAD baseline over a bounded window of values."""

    def __init__(self, window: int = 60) -> None:
        self._values: deque[float] = deque(maxlen=window)

    def update(self, value: float) -> None:
        self._values.append(float(value))

    def extend(self, values: list[float]) -> None:
        for value in values:
            self.update(value)

    @property
    def count(self) -> int:
        return len(self._values)

    @property
    def median(self) -> float:
        return median(self._values) if self._values else 0.0

    @property
    def mad(self) -> float:
        if len(self._values) < 2:
            return 0.0
        med = self.median
        return median(abs(value - med) for value in self._values)

    def robust_z(self, value: float) -> float:
        """Modified z-score: ``0.6745 * (value - median) / MAD``.

        The 0.6745 factor makes the score comparable to a standard z-score for
        normally distributed data. When the MAD is zero (a perfectly flat
        baseline) any deviation is reported as a large finite score instead of
        infinity, so callers get a usable magnitude.
        """

        mad = self.mad
        if mad == 0.0:
            deviation = value - self.median
            if deviation == 0.0:
                return 0.0
            return 50.0 if deviation > 0 else -50.0
        return 0.6745 * (value - self.median) / mad


class EwmaBaseline:
    """Exponentially weighted mean/variance baseline (a second opinion)."""

    def __init__(self, alpha: float = 0.4) -> None:
        self.alpha = alpha
        self._mean: float | None = None
        self._var = 0.0

    def update(self, value: float) -> None:
        value = float(value)
        if self._mean is None:
            self._mean = value
            self._var = 0.0
            return
        delta = value - self._mean
        self._mean += self.alpha * delta
        self._var = (1 - self.alpha) * (self._var + self.alpha * delta * delta)

    @property
    def mean(self) -> float:
        return self._mean if self._mean is not None else 0.0

    @property
    def std(self) -> float:
        return self._var**0.5

    def zscore(self, value: float) -> float:
        std = self.std
        if std == 0.0:
            deviation = value - self.mean
            if deviation == 0.0:
                return 0.0
            return 50.0 if deviation > 0 else -50.0
        return (value - self.mean) / std
