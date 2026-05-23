"""
Evaluation pipeline for CAD-VLM-as-a-Judge.

Loads samples, runs the VLM judge, computes accuracy metrics, and writes CSV results.
"""

import csv
import json
from pathlib import Path
from typing import Any

from PIL import Image


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_samples(data_dir: str | Path) -> list[dict]:
    """
    Load all samples from data_dir (positive/ and negative/ subdirs).

    Each sample is a directory containing:
      - parameter.json
      - render.png
      - text.txt

    Returns list of dicts with keys:
      sample_id, text, image_path, label, perturbation
    """
    data_dir = Path(data_dir)
    samples = []

    for label, subdir in [("positive", "positive"), ("negative", "negative")]:
        category_dir = data_dir / subdir
        if not category_dir.exists():
            continue

        for sample_path in sorted(category_dir.iterdir()):
            if not sample_path.is_dir():
                continue

            text_file = sample_path / "text.txt"
            render_file = sample_path / "render.png"
            params_file = sample_path / "parameter.json"

            text = text_file.read_text(encoding="utf-8").strip() if text_file.exists() else ""

            perturbation = None
            if params_file.exists():
                params = json.loads(params_file.read_text(encoding="utf-8"))
                perturbation = params.get("_perturbation")

            samples.append({
                "sample_id": f"{subdir}/{sample_path.name}",
                "text": text,
                "image_path": str(render_file) if render_file.exists() else None,
                "label": label,
                "perturbation": perturbation,
            })

    return samples


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_metrics(results: list[dict]) -> dict:
    """
    Compute accuracy metrics from judge results.

    Each result dict should have:
      sample_id, label, perturbation, match, predicted_error_type, reason

    Returns dict with:
      overall_accuracy, positive_accuracy, negative_accuracy,
      per_error_type: {error_type: {total, correct, accuracy}}
    """
    if not results:
        return {"overall_accuracy": 0.0, "positive_accuracy": 0.0,
                "negative_accuracy": 0.0, "per_error_type": {}}

    total = len(results)
    correct = 0
    pos_total = pos_correct = 0
    neg_total = neg_correct = 0
    per_type: dict[str, dict] = {}

    for r in results:
        label = r["label"]
        predicted_match = r["match"]

        # Ground truth: positive => match=True, negative => match=False
        gt_match = label == "positive"
        is_correct = predicted_match == gt_match

        if is_correct:
            correct += 1
        total_val = total

        if label == "positive":
            pos_total += 1
            if is_correct:
                pos_correct += 1
        else:
            neg_total += 1
            if is_correct:
                neg_correct += 1

            # Per error-type accuracy (only for negatives)
            etype = r.get("perturbation") or r.get("predicted_error_type", "unknown")
            if etype not in per_type:
                per_type[etype] = {"total": 0, "correct": 0}
            per_type[etype]["total"] += 1
            if is_correct:
                per_type[etype]["correct"] += 1

    metrics = {
        "total_samples": total,
        "overall_accuracy": correct / total if total else 0.0,
        "overall_correct": correct,
        "positive_accuracy": pos_correct / pos_total if pos_total else 0.0,
        "positive_correct": pos_correct,
        "positive_total": pos_total,
        "negative_accuracy": neg_correct / neg_total if neg_total else 0.0,
        "negative_correct": neg_correct,
        "negative_total": neg_total,
    }

    per_type_metrics = {}
    for etype, counts in per_type.items():
        per_type_metrics[etype] = {
            "total": counts["total"],
            "correct": counts["correct"],
            "accuracy": counts["correct"] / counts["total"] if counts["total"] else 0.0,
        }
    metrics["per_error_type"] = per_type_metrics

    return metrics


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def save_results_csv(results: list[dict], path: str | Path) -> None:
    """Save per-sample results to CSV."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "sample_id", "label", "perturbation",
        "predicted_match", "predicted_error_type", "reason", "correct",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            gt_match = r["label"] == "positive"
            writer.writerow({
                "sample_id": r["sample_id"],
                "label": r["label"],
                "perturbation": r.get("perturbation", ""),
                "predicted_match": r.get("match", ""),
                "predicted_error_type": r.get("predicted_error_type", ""),
                "reason": r.get("reason", ""),
                "correct": r.get("match") == gt_match,
            })


def save_metrics_json(metrics: dict, path: str | Path) -> None:
    """Save aggregate metrics to JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def print_metrics(metrics: dict) -> None:
    """Pretty-print metrics to stdout."""
    print("\n" + "=" * 60)
    print("EVALUATION RESULTS")
    print("=" * 60)
    print(f"Total samples:       {metrics.get('total_samples', 0)}")
    print(f"Overall accuracy:    {metrics.get('overall_accuracy', 0):.2%} "
          f"({metrics.get('overall_correct', 0)}/{metrics.get('total_samples', 0)})")
    print(f"Positive accuracy:   {metrics.get('positive_accuracy', 0):.2%} "
          f"({metrics.get('positive_correct', 0)}/{metrics.get('positive_total', 0)})")
    print(f"Negative accuracy:   {metrics.get('negative_accuracy', 0):.2%} "
          f"({metrics.get('negative_correct', 0)}/{metrics.get('negative_total', 0)})")

    per_type = metrics.get("per_error_type", {})
    if per_type:
        print("\nPer error-type accuracy:")
        for etype, info in per_type.items():
            print(f"  {etype:20s}  {info['accuracy']:.2%} "
                  f"({info['correct']}/{info['total']})")

    print("=" * 60)
