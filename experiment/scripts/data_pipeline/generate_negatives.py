"""Generate negative samples from all positive samples (25 × 3 = 75)."""

import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(__file__))

from perturb import generate_all_negatives
from render_from_params import render_three_view

POSITIVE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "positive")
NEGATIVE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "negative")


def main():
    pos_dir = os.path.normpath(POSITIVE_DIR)
    neg_dir = os.path.normpath(NEGATIVE_DIR)

    samples = sorted([d for d in os.listdir(pos_dir) if d.startswith("sample_")])
    print(f"Found {len(samples)} positive samples")

    for sample_name in samples:
        param_path = os.path.join(pos_dir, sample_name, "parameter.json")
        text_path = os.path.join(pos_dir, sample_name, "text.txt")

        with open(param_path, encoding="utf-8") as f:
            params = json.load(f)

        sample_id = int(sample_name.split("_")[1])
        negatives = generate_all_negatives(params, seed=sample_id)

        for ptype, neg_params in negatives.items():
            neg_name = f"{sample_name}_{ptype}"
            neg_sample_dir = os.path.join(neg_dir, neg_name)
            os.makedirs(neg_sample_dir, exist_ok=True)

            # parameter.json (with _perturbation field)
            with open(os.path.join(neg_sample_dir, "parameter.json"), "w", encoding="utf-8") as f:
                json.dump(neg_params, f, indent=2, ensure_ascii=False)

            # text.txt — unchanged copy from positive
            shutil.copy2(text_path, os.path.join(neg_sample_dir, "text.txt"))

            # render.png — rendered from perturbed params
            render_three_view(neg_params, os.path.join(neg_sample_dir, "render.png"))

        print(f"  {sample_name} → 3 negatives generated")

    total = len(samples) * 3
    print(f"\nDone. {total} negative samples in {neg_dir}")


if __name__ == "__main__":
    main()
