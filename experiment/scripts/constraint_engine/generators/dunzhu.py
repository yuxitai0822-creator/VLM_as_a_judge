"""
Rule 2 — Rounded Rectangles (Dunzhu):
  Contains (n) rounded rectangle(s) arranged horizontally with spacing (s),
  each (w) wide, (h) tall, corner radius (r).

Produces:
  - 1 count constraint
  - 1 distance constraint (center-center, x-axis, top view)
  - 3 size constraints (width x, height y, corner_radius)
"""

from __future__ import annotations

from constraint_engine.schema import Constraint, count_constraint, distance_constraint, size_constraint

ENTITY_TYPE = "Dunzhu"
GEOMETRY_TYPE = "rounded_rectangle"


def generate(
    count: int,
    spacing: float,
    width: float,
    height: float,
    corner_radius: float,
) -> list[Constraint]:
    constraints: list[Constraint] = []

    # Count — arranged horizontally, so rows=1 cols=count
    constraints.append(
        count_constraint(
            view="top",
            entity_type=ENTITY_TYPE,
            geometry_type=GEOMETRY_TYPE,
            rows=1,
            cols=count,
            value=count,
        )
    )

    # Distance (center-center horizontal spacing)
    if count > 1:
        constraints.append(
            distance_constraint(
                view="top",
                world_axis="x",
                entity_type=ENTITY_TYPE,
                geometry_type=GEOMETRY_TYPE,
                value=spacing,
            )
        )

    # Size: width (x)
    constraints.append(
        size_constraint(
            view="top",
            world_axis="x",
            entity_type=ENTITY_TYPE,
            geometry_type=GEOMETRY_TYPE,
            dimension="width",
            value=width,
        )
    )

    # Size: height (y)
    constraints.append(
        size_constraint(
            view="top",
            world_axis="y",
            entity_type=ENTITY_TYPE,
            geometry_type=GEOMETRY_TYPE,
            dimension="height",
            value=height,
        )
    )

    # Size: corner radius (no specific world axis)
    constraints.append(
        size_constraint(
            view="top",
            world_axis="x",
            entity_type=ENTITY_TYPE,
            geometry_type=GEOMETRY_TYPE,
            dimension="corner_radius",
            value=corner_radius,
        )
    )

    return constraints
