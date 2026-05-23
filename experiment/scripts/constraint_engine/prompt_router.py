"""
Prompt Template Router — selects and fills task-specific verification prompts.

constraint -> classify type -> select template -> fill placeholders -> ready for VLM
"""

from __future__ import annotations

from pathlib import Path
from string import Template

from constraint_engine.schema import Constraint

TEMPLATES_DIR = Path(__file__).parent / "prompt_templates"


def _entity_desc(c: Constraint) -> str:
    return f"{c['entity']['entity_type']} ({c['entity']['geometry_type']})"


def _classify(c: Constraint) -> str:
    """Map constraint to template name."""
    if c["constraint_type"] == "count":
        return "count"
    if c["constraint_type"] == "distance":
        return "distance"
    # Size with dimension=radius gets its own specialized template
    if c["constraint_type"] == "size" and c.get("dimension") == "radius":
        return "radius"
    if c["constraint_type"] == "size":
        return "size"
    raise ValueError(f"Unknown constraint_type: {c['constraint_type']}")


def _get_entity(c: Constraint) -> dict:
    """Extract entity dict — top-level for size/count, from anchors for distance."""
    if c["constraint_type"] == "distance":
        return c["anchors"][0]["entity"]
    return c["entity"]


def _build_context(c: Constraint) -> dict[str, str]:
    """Extract placeholder values from a constraint."""
    ent = _get_entity(c)
    val = c["value"]
    ctx: dict[str, str] = {
        "entity_type": ent["entity_type"],
        "geometry_type": ent["geometry_type"],
        "view": c.get("view", ""),
        "value": str(int(val) if val == int(val) else val),
        "world_axis": c.get("world_axis", ""),
    }

    if c["constraint_type"] == "size":
        ctx["dimension"] = c.get("dimension", "")
    elif c["constraint_type"] == "distance":
        ctx["distance_type"] = c.get("distance_type", "center-center")
    elif c["constraint_type"] == "count":
        layout = c.get("layout", {})
        ctx["rows"] = str(layout.get("rows", ""))
        ctx["cols"] = str(layout.get("cols", ""))

    return ctx


# Cache loaded templates
_template_cache: dict[str, Template] = {}


def _load_template(name: str) -> Template:
    if name not in _template_cache:
        path = TEMPLATES_DIR / f"{name}.txt"
        _template_cache[name] = Template(path.read_text(encoding="utf-8"))
    return _template_cache[name]


def template_router(c: Constraint) -> str:
    """Classify constraint, select template, fill placeholders → ready-to-use prompt."""
    template_name = _classify(c)
    tmpl = _load_template(template_name)
    ctx = _build_context(c)
    return tmpl.safe_substitute(ctx)
