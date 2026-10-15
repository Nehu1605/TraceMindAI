"""Evaluation & dashboard (Phase 7)."""

from .runner import (
    EvaluationSummary,
    ScenarioResult,
    accuracy_at_loss,
    compute_summary,
    run_scenario,
)
from .scenarios import Scenario, build_library, generate_scenario_data, load_manifest, save_manifest, split_train_test

__all__ = [
    "EvaluationSummary",
    "Scenario",
    "ScenarioResult",
    "accuracy_at_loss",
    "build_library",
    "compute_summary",
    "generate_scenario_data",
    "load_manifest",
    "run_scenario",
    "save_manifest",
    "split_train_test",
]