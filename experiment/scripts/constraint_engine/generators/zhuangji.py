"""
Rule 3 — Circles (Zhuangji):
  Contains (n) circle(s) in a (rows)x(cols) grid layout,
  horizontal spacing (hs), vertical spacing (vs), radius (r), solid/dashed line style.

Produces:
  - 1 count constraint
  - 1 distance constraint (horizontal, x-axis, front view)
  - 1 distance constraint (vertical, y-axis, side view)
  - 1 size constraint (radius, top view)
"""

from __future__ import annotations

from constraint_engine.schema import Constraint, count_constraint, distance_constraint, size_constraint

ENTITY_TYPE = "Zhuangji"
GEOMETRY_TYPE = "circle"


def generate(
    count: int,
    rows: int,
    cols: int,
    h_spacing: float,
    v_spacing: float,
    radius: float,
) -> list[Constraint]:
    constraints: list[Constraint] = []

    # Count
    constraints.append(
        count_constraint(
            view="top",
            entity_type=ENTITY_TYPE,
            geometry_type=GEOMETRY_TYPE,
            rows=rows,
            cols=cols,
            value=count,
        )
    )

    # Distance: horizontal spacing (x-axis)
    if cols > 1:
        constraints.append(
            distance_constraint(
                view="front",
                world_axis="x",
                entity_type=ENTITY_TYPE,
                geometry_type=GEOMETRY_TYPE,
                value=h_spacing,
            )
        )

    # Distance: vertical spacing (y-axis)
    if rows > 1:
        constraints.append(
            distance_constraint(
                view="side",
                world_axis="y",
                entity_type=ENTITY_TYPE,
                geometry_type=GEOMETRY_TYPE,
                value=v_spacing,
            )
        )

    # Size: radius
    constraints.append(
        size_constraint(
            view="top",
            world_axis="x",
            entity_type=ENTITY_TYPE,
            geometry_type=GEOMETRY_TYPE,
            dimension="radius",
            value=radius,
        )
    )

    return constraints
