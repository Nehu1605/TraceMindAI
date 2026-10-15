"""Integration test: evaluation pipeline (I1/I2/I3/I6/I7/I10)."""

from __future__ import annotations

from evaluation.pipeline import main as eval_main
from evaluation.scenarios import build_library, split_train_test


def test_library_validation():
    library = build_library()
    fault = [s for s in library if not s.is_healthy]
    healthy = [s for s in library if s.is_healthy]
    decoy = [s for s in library if s.decoy_deployments]
    assert len(fault) >= 16
    assert len(healthy) >= 5
    assert len(decoy) >= 3


def test_split_train_test():
    library = build_library()
    train, test = split_train_test(library)
    assert len(train) + len(test) == len(library)
    # No overlap
    train_ids = {s.scenario_id for s in train}
    test_ids = {s.scenario_id for s in test}
    assert train_ids.isdisjoint(test_ids)