"""
Constraint Engine — deterministic text-to-constraint compiler.

Usage:
    from constraint_engine.parser import parse_text, parse_file

    constraints = parse_text(text_string)
    constraints = parse_file("data/positive/sample_001/text.txt")
"""

from __future__ import annotations

import json
from pathlib import Path

from constraint_engine.schema import Constraint
from constraint_engine import templates
from constraint_engine.generators import baseplate, dunzhu, zhuangji, height


def parse_text(text: str) -> list[Constraint]:
    """Parse a full 6-line templated text into structured constraints."""
    constraints: list[Constraint] = []
    lines = text.strip().splitlines()

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Rule 1 — Base plate
        bp = templates.extract_baseplate(line)
        if bp:
            constraints.extend(baseplate.generate(bp["width"], bp["height"]))
            continue

        # Rule 2 — Rounded rectangles (Dunzhu)
        rr = templates.extract_rounded_rect(line)
        if rr:
            constraints.extend(dunzhu.generate(
                count=rr["count"],
                spacing=rr["spacing"],
                width=rr["width"],
                height=rr["height"],
                corner_radius=rr["corner_radius"],
            ))
            continue

        # Rule 3 — Circles (Zhuangji)
        ci = templates.extract_circle(line)
        if ci:
            constraints.extend(zhuangji.generate(
                count=ci["count"],
                rows=ci["rows"],
                cols=ci["cols"],
                h_spacing=ci["h_spacing"],
                v_spacing=ci["v_spacing"],
                radius=ci["radius"],
            ))
            continue

        # Rule 4a — Dunzhu height
        dh = templates.extract_dunzhu_height(line)
        if dh is not None:
            constraints.append(height.generate("dunzhu", dh))
            continue

        # Rule 4b — Chengtai height
        ch = templates.extract_chengtai_height(line)
        if ch is not None:
            constraints.append(height.generate("chengtai", ch))
            continue

        # Rule 4c — Zhuangji height
        zh = templates.extract_zhuangji_height(line)
        if zh is not None:
            constraints.append(height.generate("zhuangji", zh))
            continue

    return constraints


def parse_file(path: str | Path) -> list[Constraint]:
    """Read a text.txt file and return constraints."""
    return parse_text(Path(path).read_text(encoding="utf-8"))


def to_json(constraints: list[Constraint], indent: int = 2) -> str:
    return json.dumps(constraints, indent=indent, ensure_ascii=False)
