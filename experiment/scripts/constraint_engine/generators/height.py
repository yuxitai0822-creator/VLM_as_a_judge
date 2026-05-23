"""
Rule 4 — Height constraints for Dunzhu, Chengtai, and Zhuangji.

Each height line produces a single size constraint (view=front, world_axis=z, dimension=height).
"""

from __future__ import annotations

from constraint_engine.schema import Constraint, size_constraint

ENTITY_MAP = {
    "dunzhu": ("Dunzhu", "rounded_rectangle"),
    "chengtai": ("Chengtai", "rectangle"),
    "zhuangji": ("Zhuangji", "circle"),
}


def generate(entity_key: str, value: float) -> Constraint:
    entity_type, geometry_type = ENTITY_MAP[entity_key]
    return size_constraint(
        view="front",
        world_axis="z",
        entity_type=entity_type,
        geometry_type=geometry_type,
        dimension="height",
        value=value,
    )
