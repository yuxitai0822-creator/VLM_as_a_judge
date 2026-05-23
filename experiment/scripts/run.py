"""
CAD-VLM-as-a-Judge: Main experiment runner.

Usage:
    python scripts/run.py                        # uses config.yaml
    python scripts/run.py --config my_config.yaml

All settings (model, API key, paths, etc.) are read from config.yaml.
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
from judge_pipeline1.judge import create_judge
import yaml


def run_experiment(config_path: str | Path) -> dict:
    """
    Run the full evaluation pipeline driven by config.yaml.

    1. Load config
    2. Load samples from data_dir
    3. Create judge from config (api / local)
    4. Run judgment on each sample
    5. Compute metrics
    6. Save results and metrics
    """
    from judge_pipeline1.judge import load_config
    cfg = load_config(config_path)

    base_dir = Path(config_path).resolve().parent if Path(config_path).is_file() else Path(".").resolve()
    data_path = base_dir / cfg.get("data_dir", "data")
    output_path = base_dir / cfg.get("output_dir", "results")

    print(f"Config:  {config_path}")
    print(f"Mode:    {cfg.get('mode', 'api')}")
    print(f"Data:    {data_path}")
    print(f"Output:  {output_path}\n")

    print(f"Loading samples from {data_path} ...")
    samples = load_samples(data_path)
    print(f"Found {len(samples)} samples "
          f"(positive: {sum(1 for s in samples if s['label']=='positive')}, "
          f"negative: {sum(1 for s in samples if s['label']=='negative')})")

    if not samples:
        print("No samples found. Please add data to data/positive/ and data/negative/.")
        return {}

    valid_samples = [s for s in samples if s["text"] and s["image_path"]]
    if len(valid_samples) < len(samples):
        print(f"Skipping {len(samples) - len(valid_samples)} samples missing text or image.")

    print(f"\nInitializing judge ({cfg.get('mode', 'api')} mode) ...")
    judge = create_judge(config_path)

    print(f"Running judgment on {len(valid_samples)} samples ...\n")
    results = []
    for i, sample in enumerate(valid_samples):
        print(f"[{i+1}/{len(valid_samples)}] {sample['sample_id']}")
        judgment = judge.judge(sample["text"], sample["image_path"])

        results.append({
            "sample_id": sample["sample_id"],
            "label": sample["label"],
            "perturbation": sample.get("perturbation"),
            "match": judgment.get("match"),
            "predicted_error_type": judgment.get("error_type"),
            "reason": judgment.get("reason"),
        })

    metrics = compute_metrics(results)
    print_metrics(metrics)

    output_path.mkdir(parents=True, exist_ok=True)
    save_results_csv(results, output_path / "per_sample_results.csv")
    save_metrics_json(metrics, output_path / "metrics.json")
    print(f"\nResults saved to {output_path}/")

    return metrics


def main():
    parser = argparse.ArgumentParser(description="CAD-VLM-as-a-Judge experiment runner")
    parser.add_argument("--config", default=str(
        Path(__file__).resolve().parent.parent / "config.yaml"
    ), help="Path to config.yaml")
    args = parser.parse_args()

    run_experiment(args.config)


if __name__ == "__main__":
    main()
