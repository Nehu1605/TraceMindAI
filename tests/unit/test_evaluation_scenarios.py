"""Unit tests for the evaluation scenario library (I1)."""

from __future__ import annotations

from evaluation.scenarios import Scenario, build_library, split_train_test


def test_library_has_required_counts():
    library = build_library()

    fault = [s for s in library if not s.is_healthy]
    healthy = [s for s in library if s.is_healthy]
    decoy = [s for s in library if s.decoy_deployments]

    assert len(fault) >= 16, f"Need ≥16 fault scenarios, got {len(fault)}"
    assert len(healthy) >= 5, f"Need ≥5 healthy runs, got {len(healthy)}"
    assert len(decoy) >= 3, f"Need ≥3 decoy scenarios, got {len(decoy)}"


def test_split_is_deterministic_and_60_40():
    library = build_library()
    train1, test1 = split_train_test(library, train_frac=0.6, seed=7)
    train2, test2 = split_train_test(library, train_frac=0.6, seed=7)

    assert len(train1) == len(train2)
    assert {s.scenario_id for s in train1} == {s.scenario_id for s in train2}
    # Roughly 60/40
    total = len(library)
    assert abs(len(train1) / total - 0.6) < 0.15


def test_split_is_different_with_different_seed():
    library = build_library()
    train_a, _ = split_train_test(library, train_frac=0.6, seed=7)
    train_b, _ = split_train_test(library, train_frac=0.6, seed=42)

    # With different seeds the splits should differ (very high probability)
    assert {s.scenario_id for s in train_a} != {s.scenario_id for s in train_b}


def test_scenario_serialization_roundtrip():
    library = build_library()
    s = library[0]
    data = s.to_dict()
    restored = Scenario.from_dict(data)
    assert restored.scenario_id == s.scenario_id
    assert restored.seed == s.seed
    assert restored.expected_root_cause == s.expected_root_cause