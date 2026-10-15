"""Evaluation pipeline CLI (Phase 7).

    python -m evaluation.pipeline --out-dir data/evaluation/run-001
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from common.config import Settings, get_settings
from evaluation.runner import (
    EvaluationSummary,
    ScenarioResult,
    accuracy_at_loss,
    compute_summary,
    run_scenario,
    save_results,
)
from evaluation.scenarios import build_library, split_train_test


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the evaluation suite.")
    parser.add_argument("--out-dir", default="data/evaluation/run-001")
    parser.add_argument("--raw-root", default="data/evaluation/raw")
    parser.add_argument("--processed-root", default="data/evaluation/processed")
    parser.add_argument("--train-frac", type=float, default=0.6)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--split", choices=["train", "test", "all"], default="test")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = get_settings()

    library = build_library()
    train, test = split_train_test(library, train_frac=args.train_frac, seed=args.seed)
    scenarios = {"train": train, "test": test, "all": library}[args.split]

    raw_root = Path(args.raw_root)
    processed_root = Path(args.processed_root)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== Evaluation (I1/I2/I3/I6/I7/I10) ===")
    print(f"  split: {args.split} | scenarios: {len(scenarios)}")
    print(f"  raw: {raw_root} | processed: {processed_root} | out: {out_dir}")

    results: list[ScenarioResult] = []
    for i, scenario in enumerate(scenarios, 1):
        print(f"  [{i}/{len(scenarios)}] {scenario.scenario_id} (degrade={scenario.degrade})")
        result = run_scenario(scenario, raw_root, processed_root, settings)
        results.append(result)

    summary = compute_summary(results)
    save_results(results, summary, out_dir / "evaluation.json")

    print(f"\n=== Summary ===")
    print(f"  top-1 accuracy:     {summary.top1_accuracy:.1%}")
    print(f"  top-3 accuracy:     {summary.top3_accuracy:.1%}")
    for name, acc in summary.baseline_top1.items():
        print(f"  {name}:             {acc:.1%}")
    print(f"  MTTR (mean):        {summary.mttr_mean_s:.2f}s")
    print(f"  throughput:         {summary.throughput_eps:.1f} events/s")
    print(f"  log reduction:      {summary.log_reduction_ratio:.1%} distinct templates retained")
    print(f"  accuracy at loss:")
    for loss, acc in summary.accuracy_at_loss.items():
        print(f"    {loss}: {acc:.1%}")
    print(f"\n  output: {out_dir / 'evaluation.json'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())