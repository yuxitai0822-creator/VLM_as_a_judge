"""
Rule 1 — Base Plate:  A rectangular base plate with width (w) and height (h).

Produces two size constraints (width along x, height along y) in top view.
"""

from __future__ import annotations

from constraint_engine.schema import Constraint, size_constraint

ENTITY_TYPE = "Chengtai"
GEOMETRY_TYPE = "rectangle"


def generate(width: float, height: float) -> list[Constraint]:
    return [
        size_constraint(
            view="top",
            world_axis="x",
            entity_type=ENTITY_TYPE,
            geometry_type=GEOMETRY_TYPE,
            dimension="width",
            value=width,
        ),
        size_constraint(
            view="top",
            world_axis="y",
            entity_type=ENTITY_TYPE,
            geometry_type=GEOMETRY_TYPE,
            dimension="height",
            value=height,
        ),
    ]
