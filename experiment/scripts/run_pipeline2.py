"""
Run pipeline2: constraint-based VLM judge with checkpoint/resume.

Usage:
    cd experiment
    python scripts/run_pipeline2.py                  # run or resume
    python scripts/run_pipeline2.py --reset           # clear checkpoint, start fresh
    python scripts/run_pipeline2.py --config my.yaml

Checkpoint mechanism:
    After each sample completes, result is appended to checkpoint.jsonl.
    On restart, completed sample_ids are loaded and skipped.
    Use --reset to discard checkpoint and start over.
"""

import argparse
import json
import sys
import time
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


CHECKPOINT_FILENAME = "checkpoint.jsonl"


def _checkpoint_path(output_dir: Path) -> Path:
    return output_dir / CHECKPOINT_FILENAME


def load_checkpoint(output_dir: Path) -> set[str]:
    """Load set of completed sample_ids from checkpoint file."""
    cp = _checkpoint_path(output_dir)
    if not cp.exists():
        return set()
    completed = set()
    with open(cp, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                completed.add(record["sample_id"])
            except json.JSONDecodeError:
                pass
    return completed


def append_checkpoint(output_dir: Path, record: dict) -> None:
    """Append one completed result to the checkpoint file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    cp = _checkpoint_path(output_dir)
    with open(cp, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def clear_checkpoint(output_dir: Path) -> None:
    """Delete the checkpoint file."""
    cp = _checkpoint_path(output_dir)
    if cp.exists():
        cp.unlink()
        print(f"Cleared checkpoint: {cp}")


def load_checkpoint_results(output_dir: Path) -> list[dict]:
    """Load all results from checkpoint as a list."""
    cp = _checkpoint_path(output_dir)
    if not cp.exists():
        return []
    results = []
    with open(cp, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return results


def format_duration(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s:02d}s" if m >= 1 else f"{s}s"


def run_experiment(config_path: str | Path, reset: bool = False) -> dict:
    cfg = load_config(config_path)

    base_dir = (
        Path(config_path).resolve().parent
        if Path(config_path).is_file()
        else Path(".").resolve()
    )
    data_path = base_dir / cfg.get("data_dir", "data")
    output_path = base_dir / cfg.get("output_dir", "results") / "pipeline2"

    print(f"Config:   {config_path}")
    print(f"Pipeline: 2 (constraint-based, checkpoint-enabled)")
    print(f"Mode:     {cfg.get('mode', 'api')}")
    print(f"Data:     {data_path}")
    print(f"Output:   {output_path}")

    # Handle reset
    if reset:
        clear_checkpoint(output_path)

    # Load checkpoint
    completed_ids = load_checkpoint(output_path)
    if completed_ids:
        print(f"\nCheckpoint found: {len(completed_ids)} samples already completed.")
    else:
        print("\nNo checkpoint found. Starting fresh.")

    # Load samples
    print(f"\nLoading samples from {data_path} ...")
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

    # Filter out already-completed samples
    remaining = [s for s in valid_samples if s["sample_id"] not in completed_ids]
    print(f"\nTotal valid: {len(valid_samples)} | Already done: {len(completed_ids)} | Remaining: {len(remaining)}")

    if not remaining:
        print("All samples already completed. Compiling final results...")
    else:
        # Timing estimates
        avg_constraints = 13
        cfg_api = cfg.get("api", {})
        max_conc = cfg_api.get("max_concurrency", 1)
        est_per_constraint = 5
        est_per_sample = max(est_per_constraint, (avg_constraints / max_conc) * est_per_constraint)
        est_total = len(remaining) * est_per_sample
        print(f"Estimated time for {len(remaining)} samples: ~{format_duration(est_total)}\n")

        # Initialize judge
        print("Initializing pipeline2 judge ...")
        judge = create_judge(config_path)

        print(f"Running per-constraint judgment ...\n")
        t_start = time.time()

        for i, sample in enumerate(remaining):
            t_sample_start = time.time()
            sid = sample["sample_id"]
            print(f"[{len(completed_ids) + i + 1}/{len(valid_samples)}] {sid}")

            try:
                judgment = judge.judge(sample["text"], sample["image_path"])
            except Exception as e:
                print(f"  >> SKIPPED (API error: {e})")
                # Save error result to checkpoint too, so we don't retry
                record = {
                    "sample_id": sid,
                    "label": sample["label"],
                    "perturbation": sample.get("perturbation"),
                    "match": None,
                    "predicted_error_type": "api_error",
                    "reason": str(e),
                }
                append_checkpoint(output_path, record)
                # Stop on API error — don't burn through remaining quota
                print(f"\nAPI error encountered. Checkpoint saved. Re-run to resume.")
                break

            record = {
                "sample_id": sid,
                "label": sample["label"],
                "perturbation": sample.get("perturbation"),
                "match": judgment.get("match"),
                "predicted_error_type": judgment.get("error_type"),
                "reason": judgment.get("reason"),
                "constraint_results": judgment.get("constraint_results", []),
            }
            append_checkpoint(output_path, record)

            # Progress reporting
            t_sample = time.time() - t_sample_start
            done = len(completed_ids) + i + 1
            left = len(valid_samples) - done
            elapsed = time.time() - t_start
            avg_per = elapsed / (i + 1) if i > 0 else t_sample
            eta = avg_per * left

            verdict = "MATCH" if judgment["match"] else f"MISMATCH ({judgment['error_type']})"
            print(f"  >> {verdict}  ({judgment['passed']}/{judgment['total_constraints']} constraints)")
            print(f"     [{format_duration(t_sample)}/sample]  "
                  f"ETA: {format_duration(eta)}  "
                  f"({done}/{len(valid_samples)} done, {left} left)")

    # Compile final results from checkpoint
    print("\n" + "=" * 60)
    print("Compiling final results from checkpoint ...")
    results = load_checkpoint_results(output_path)
    print(f"Total completed samples: {len(results)}")

    metrics = compute_metrics(results)
    print_metrics(metrics)

    output_path.mkdir(parents=True, exist_ok=True)
    save_results_csv(results, output_path / "per_sample_results.csv")
    save_metrics_json(metrics, output_path / "metrics.json")
    print(f"\nResults saved to {output_path}/")

    return metrics


def main():
    parser = argparse.ArgumentParser(description="Pipeline2: constraint-based VLM judge (checkpoint-enabled)")
    parser.add_argument(
        "--config",
        default=str(Path(__file__).resolve().parent.parent / "config.yaml"),
        help="Path to config.yaml",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear checkpoint and start fresh",
    )
    args = parser.parse_args()
    run_experiment(args.config, reset=args.reset)


if __name__ == "__main__":
    main()
