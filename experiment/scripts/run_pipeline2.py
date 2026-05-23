"""
Run pipeline2: constraint-based VLM judge.

Usage:
    cd experiment
    python scripts/run_pipeline2.py
    python scripts/run_pipeline2.py --config config.yaml
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from evaluate_pipeline.evaluate import (
    load_samples,
    compute_metrics,
    save_results_csv,
    save_metrics_json,
    print_metrics,
)
from judge_pipeline2.judge import create_judge, load_config


def run_experiment(config_path: str | Path) -> dict:
    cfg = load_config(config_path)

    base_dir = (
        Path(config_path).resolve().parent
        if Path(config_path).is_file()
        else Path(".").resolve()
    )
    data_path = base_dir / cfg.get("data_dir", "data")
    output_path = base_dir / cfg.get("output_dir", "results") / "pipeline2"

    print(f"Config:   {config_path}")
    print(f"Pipeline: 2 (constraint-based)")
    print(f"Mode:     {cfg.get('mode', 'api')}")
    print(f"Data:     {data_path}")
    print(f"Output:   {output_path}\n")

    print(f"Loading samples from {data_path} ...")
    samples = load_samples(data_path)
    print(
        f"Found {len(samples)} samples "
        f"(positive: {sum(1 for s in samples if s['label'] == 'positive')}, "
        f"negative: {sum(1 for s in samples if s['label'] == 'negative')})"
    )

    if not samples:
        print("No samples found.")
        return {}

    valid_samples = [s for s in samples if s["text"] and s["image_path"]]
    if len(valid_samples) < len(samples):
        print(f"Skipping {len(samples) - len(valid_samples)} samples missing text or image.")

    print(f"\nInitializing pipeline2 judge ...")
    judge = create_judge(config_path)

    print(f"Running per-constraint judgment on {len(valid_samples)} samples ...\n")
    results = []
    skipped = 0
    for i, sample in enumerate(valid_samples):
        try:
            judgment = judge.judge(sample["text"], sample["image_path"])
        except Exception as e:
            print(f"  >> SKIPPED (API error: {e})")
            skipped += 1
            results.append({
                "sample_id": sample["sample_id"],
                "label": sample["label"],
                "perturbation": sample.get("perturbation"),
                "match": None,
                "predicted_error_type": "api_error",
                "reason": str(e),
            })
            break

        results.append({
            "sample_id": sample["sample_id"],
            "label": sample["label"],
            "perturbation": sample.get("perturbation"),
            "match": judgment.get("match"),
            "predicted_error_type": judgment.get("error_type"),
            "reason": judgment.get("reason"),
        })

    if skipped:
        print(f"\n{skipped} sample(s) skipped due to API errors.")

    metrics = compute_metrics(results)
    print_metrics(metrics)

    output_path.mkdir(parents=True, exist_ok=True)
    save_results_csv(results, output_path / "per_sample_results.csv")
    save_metrics_json(metrics, output_path / "metrics.json")
    print(f"\nResults saved to {output_path}/")

    return metrics


def main():
    parser = argparse.ArgumentParser(description="Pipeline2: constraint-based VLM judge")
    parser.add_argument(
        "--config",
        default=str(Path(__file__).resolve().parent.parent / "config.yaml"),
        help="Path to config.yaml",
    )
    args = parser.parse_args()
    run_experiment(args.config)


if __name__ == "__main__":
    main()
