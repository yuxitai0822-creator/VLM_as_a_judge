"""
Canonical constraint schema definitions.

Three constraint types:
  - size:      single-entity dimension (width, height, radius, corner_radius)
  - distance:  center-center spacing between two anchors of the same entity type
  - count:     number of instances with grid layout
"""

from typing import Literal, TypedDict


# --- Shared sub-schemas ---

class Entity(TypedDict):
    entity_type: str       # "Chengtai" | "Dunzhu" | "Zhuangji"
    geometry_type: str     # "rectangle" | "rounded_rectangle" | "circle"


class Anchor(TypedDict):
    entity: Entity
    anchor: str            # always "center" for now


class Layout(TypedDict, total=False):
    rows: int
    cols: int


# --- Constraint types ---

class SizeConstraint(TypedDict):
    constraint_type: Literal["size"]
    view: str              # "top" | "front" | "side"
    world_axis: str        # "x" | "y" | "z"
    entity: Entity
    dimension: str         # "width" | "height" | "radius" | "corner_radius"
    value: float


class DistanceConstraint(TypedDict):
    constraint_type: Literal["distance"]
    distance_type: str     # "center-center"
    view: str
    world_axis: str
    anchors: list[Anchor]
    value: float


class CountConstraint(TypedDict):
    constraint_type: Literal["count"]
    view: str
    entity: Entity
    layout: Layout
    value: int


Constraint = SizeConstraint | DistanceConstraint | CountConstraint


# --- Factory helpers ---

def _entity(entity_type: str, geometry_type: str) -> Entity:
    return {"entity_type": entity_type, "geometry_type": geometry_type}


def size_constraint(
    view: str,
    world_axis: str,
    entity_type: str,
    geometry_type: str,
    dimension: str,
    value: float,
) -> SizeConstraint:
    return {
        "constraint_type": "size",
        "view": view,
        "world_axis": world_axis,
        "entity": _entity(entity_type, geometry_type),
        "dimension": dimension,
        "value": value,
    }


def distance_constraint(
    view: str,
    world_axis: str,
    entity_type: str,
    geometry_type: str,
    value: float,
) -> DistanceConstraint:
    ent = _entity(entity_type, geometry_type)
    return {
        "constraint_type": "distance",
        "distance_type": "center-center",
        "view": view,
        "world_axis": world_axis,
        "anchors": [
            {"entity": ent, "anchor": "center"},
            {"entity": ent, "anchor": "center"},
        ],
        "value": value,
    }


def count_constraint(
    view: str,
    entity_type: str,
    geometry_type: str,
    rows: int,
    cols: int,
    value: int,
) -> CountConstraint:
    return {
        "constraint_type": "count",
        "view": view,
        "entity": _entity(entity_type, geometry_type),
        "layout": {"rows": rows, "cols": cols},
        "value": value,
    }
