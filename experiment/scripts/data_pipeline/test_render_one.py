"""Test: render one negative sample with simplified dimensions."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from perturb import generate_all_negatives
from render_from_params import render_three_view

POS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "positive")
NEG_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "negative")


def main():
    sample = "sample_001"
    pos_path = os.path.normpath(os.path.join(POS_DIR, sample, "parameter.json"))

    with open(pos_path, encoding="utf-8") as f:
        params = json.load(f)

    print(f"Positive params: {json.dumps(params, indent=2)}")

    sample_id = int(sample.split("_")[1])
    negatives = generate_all_negatives(params, seed=sample_id)

    ptype = "count_error"
    neg_params = negatives[ptype]
    print(f"\nNegative ({ptype}) params: {json.dumps(neg_params, indent=2)}")

    out_dir = os.path.normpath(os.path.join(NEG_DIR, f"{sample}_{ptype}"))
    os.makedirs(out_dir, exist_ok=True)

    out_path = os.path.join(out_dir, "render.png")
    print(f"\nRendering to {out_path} ...")
    render_three_view(neg_params, out_path)
    print("Done.")


if __name__ == "__main__":
    main()
