"""
Parameter perturbation for generating negative CAD samples.

Works with the flat TriView2CAD parameter schema:
  rect_width, rect_height, rounded_rect_*, circle_*, dunzhu_height, etc.

Supported perturbation types:
  - count_error:    Change object count (±1–3)
  - symmetry_error: Break symmetry by altering spacing
  - scale_error:    Scale a dimension by 0.3×–2.5×
"""

import copy
import random

COUNT_FIELDS = [
    "circle_horizontal_count",
    "circle_vertical_count",
    "rounded_rect_horizontal_count",
]

DISTANCE_FIELDS = [
    "circle_horizontal_distance",
    "circle_vertical_distance",
    "rounded_rect_horizontal_distance",
]

SCALE_FIELDS = [
    "rect_width", "rect_height",
    "circle_radius",
    "rounded_rect_width", "rounded_rect_height", "rounded_rect_radius",
    "dunzhu_height", "chengtai_height", "zhuangji_height",
]

SCALE_FACTORS = [0.3, 0.5, 0.7, 1.5, 2.0, 2.5]


def perturb_count(params: dict, rng: random.Random) -> dict:
    """Change the count of a random object by ±1–3."""
    result = copy.deepcopy(params)
    field = rng.choice(COUNT_FIELDS)
    original = result[field]
    delta = rng.choice([-3, -2, -1, 1, 2, 3])
    result[field] = max(1, original + delta)
    result["_perturbation"] = "count_error"
    return result


def perturb_symmetry(params: dict, rng: random.Random) -> dict:
    """Break symmetry by scaling one distance unevenly."""
    result = copy.deepcopy(params)
    field = rng.choice(DISTANCE_FIELDS)
    factor = rng.choice(SCALE_FACTORS)
    result[field] = round(result[field] * factor)
    result["_perturbation"] = "symmetry_error"
    return result


def perturb_scale(params: dict, rng: random.Random) -> dict:
    """Scale a dimension by 0.3×–2.5×."""
    result = copy.deepcopy(params)
    field = rng.choice(SCALE_FIELDS)
    factor = rng.choice(SCALE_FACTORS)
    result[field] = round(result[field] * factor)
    result["_perturbation"] = "scale_error"
    return result


PERTURBATIONS = {
    "count_error": perturb_count,
    "symmetry_error": perturb_symmetry,
    "scale_error": perturb_scale,
}


def generate_all_negatives(params: dict, seed: int | None = None) -> dict[str, dict]:
    """Generate one negative sample per perturbation type."""
    results = {}
    for ptype, fn in PERTURBATIONS.items():
        rng = random.Random(seed)
        results[ptype] = fn(params, rng)
    return results
