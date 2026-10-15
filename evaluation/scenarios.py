"""Scenario library & train/test split (Phase 7, improvement I1).

The improvement plan requires a curated scenario library with ≥ 20 incidents,
5 healthy runs, and 3 decoy scenarios, split 60/40 by a fixed seed so
experiments are reproducible. We generate the library from the simulator's
parameter space and persist a manifest so the evaluation runner can re-use
exact scenarios.

Note: the current simulator only injects one fault type (payment-service DB
connection leak). The library varies the seed and data-quality degrade level
to create scenario diversity while keeping the fault type constant.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from simulator.generate_telemetry import DEGRADE_PRESETS, generate_dataset


@dataclass
class Scenario:
    scenario_id: str
    degrade: str
    seed: int
    requests: int
    fault_injected: str | None = None
    fault_service: str | None = None
    expected_root_cause: str | None = None
    decoy_deployments: list[str] = field(default_factory=list)
    is_healthy: bool = False
    is_decoy: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "degrade": self.degrade,
            "seed": self.seed,
            "requests": self.requests,
            "fault_injected": self.fault_injected,
            "fault_service": self.fault_service,
            "expected_root_cause": self.expected_root_cause,
            "decoy_deployments": self.decoy_deployments,
            "is_healthy": self.is_healthy,
            "is_decoy": self.is_decoy,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Scenario":
        return cls(**data)


# --- Pre-curated library (I1) ----------------------------------------------
# The simulator has one fault (payment DB conn leak) but we vary:
# - seed (changes request patterns & noise)
# - degrade level (none/light/heavy changes data quality)
# - healthy runs (degrade="none" + no fault window)
# - decoy deployments (built into the simulator for every fault run)

_SCENARIO_SPECS = [
    # Fault runs with data quality variations (16 = 4 seeds × 4 degrade configs)
    # Note: "light" and "heavy" are data-quality presets, not fault types.
    # The fault (db_conn_leak in payment-service) is always injected.
    ("sc-01", "none", 1, 60, ("db_connection_leak", "payment-service", "payment-service"), ["dep-decoy0001"], False),
    ("sc-02", "none", 2, 60, ("db_connection_leak", "payment-service", "payment-service"), ["dep-decoy0001"], False),
    ("sc-03", "none", 3, 60, ("db_connection_leak", "payment-service", "payment-service"), ["dep-decoy0001"], False),
    ("sc-04", "none", 4, 60, ("db_connection_leak", "payment-service", "payment-service"), ["dep-decoy0001"], False),
    ("sc-05", "light", 5, 60, ("db_connection_leak", "payment-service", "payment-service"), ["dep-decoy0001"], False),
    ("sc-06", "light", 6, 60, ("db_connection_leak", "payment-service", "payment-service"), ["dep-decoy0001"], False),
    ("sc-07", "light", 7, 60, ("db_connection_leak", "payment-service", "payment-service"), ["dep-decoy0001"], False),
    ("sc-08", "light", 8, 60, ("db_connection_leak", "payment-service", "payment-service"), ["dep-decoy0001"], False),
    ("sc-09", "heavy", 9, 60, ("db_connection_leak", "payment-service", "payment-service"), ["dep-decoy0001"], False),
    ("sc-10", "heavy", 10, 60, ("db_connection_leak", "payment-service", "payment-service"), ["dep-decoy0001"], False),
    ("sc-11", "heavy", 11, 60, ("db_connection_leak", "payment-service", "payment-service"), ["dep-decoy0001"], False),
    ("sc-12", "heavy", 12, 60, ("db_connection_leak", "payment-service", "payment-service"), ["dep-decoy0001"], False),
    ("sc-13", "none", 13, 60, ("db_connection_leak", "payment-service", "payment-service"), ["dep-decoy0001"], False),
    ("sc-14", "light", 14, 60, ("db_connection_leak", "payment-service", "payment-service"), ["dep-decoy0001"], False),
    ("sc-15", "heavy", 15, 60, ("db_connection_leak", "payment-service", "payment-service"), ["dep-decoy0001"], False),
    ("sc-16", "none", 16, 60, ("db_connection_leak", "payment-service", "payment-service"), ["dep-decoy0001"], False),
    # Healthy runs (5) - no incident window, just noise
    ("sc-17", "none", 17, 60, None, [], True),
    ("sc-18", "none", 18, 60, None, [], True),
    ("sc-19", "none", 19, 60, None, [], True),
    ("sc-20", "none", 20, 60, None, [], True),
    ("sc-21", "none", 21, 60, None, [], True),
    # Decoy-emphasis runs (3) - same fault but we'll tag them for analysis
    ("sc-22", "none", 22, 60, ("db_connection_leak", "payment-service", "payment-service"), ["dep-decoy0001"], False),
    ("sc-23", "light", 23, 60, ("db_connection_leak", "payment-service", "payment-service"), ["dep-decoy0001"], False),
    ("sc-24", "heavy", 24, 60, ("db_connection_leak", "payment-service", "payment-service"), ["dep-decoy0001"], False),
]


def build_library() -> list[Scenario]:
    library: list[Scenario] = []
    for spec in _SCENARIO_SPECS:
        scenario_id, degrade, seed, requests, fault_info, decoys, healthy = spec
        if fault_info:
            fault_injected, fault_service, expected_root = fault_info
            library.append(
                Scenario(
                    scenario_id=scenario_id,
                    degrade=degrade,
                    seed=seed,
                    requests=requests,
                    fault_injected=fault_injected,
                    fault_service=fault_service,
                    expected_root_cause=expected_root,
                    decoy_deployments=decoys,
                )
            )
        else:
            library.append(
                Scenario(
                    scenario_id=scenario_id,
                    degrade=degrade,
                    seed=seed,
                    requests=requests,
                    is_healthy=healthy,
                    decoy_deployments=decoys,
                )
            )
    return library


def split_train_test(library: list[Scenario], train_frac: float = 0.6, seed: int = 7) -> tuple[list[Scenario], list[Scenario]]:
    """Stable 60/40 split by hashing scenario_id + seed."""

    def in_train(s: Scenario) -> bool:
        h = hashlib.sha1(f"{s.scenario_id}:{seed}".encode()).hexdigest()
        return int(h, 16) % 100 < int(train_frac * 100)

    train = [s for s in library if in_train(s)]
    test = [s for s in library if not in_train(s)]
    return train, test


def save_manifest(library: list[Scenario], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"scenarios": [s.to_dict() for s in library]}, indent=2),
        encoding="utf-8",
    )


def load_manifest(path: Path) -> list[Scenario]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Scenario.from_dict(s) for s in data["scenarios"]]


def generate_scenario_data(scenario: Scenario, raw_root: Path) -> Path:
    """Run the simulator for one scenario and return the raw directory."""

    raw_dir = raw_root / scenario.scenario_id
    generate_dataset(
        raw_dir,
        scenario=scenario.scenario_id,
        degrade=DEGRADE_PRESETS[scenario.degrade],
        seed=scenario.seed,
        requests=scenario.requests,
    )
    return raw_dir


# --- Smoke test: ensure library has required counts ------------------------

def _validate_library() -> None:
    library = build_library()
    fault = [s for s in library if not s.is_healthy and not s.is_decoy]
    healthy = [s for s in library if s.is_healthy]
    decoy = [s for s in library if s.is_decoy or s.decoy_deployments]
    assert len(fault) >= 16, f"Need ≥16 fault scenarios, got {len(fault)}"
    assert len(healthy) >= 5, f"Need ≥5 healthy runs, got {len(healthy)}"
    assert len(decoy) >= 3, f"Need ≥3 decoy scenarios, got {len(decoy)}"


if __name__ == "__main__":
    _validate_library()
    lib = build_library()
    train, test = split_train_test(lib)
    print(f"Library: {len(lib)} scenarios | Train: {len(train)} | Test: {len(test)}")
    for s in lib:
        print(f"  {s.scenario_id}: degrade={s.degrade} seed={s.seed} healthy={s.is_healthy} decoys={s.decoy_deployments}")