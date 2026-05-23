"""
Regex templates for each line type in the templated CAD text description.

The text always follows exactly 6 lines:
  1. A rectangular base plate with width (w) and height (h).
  2. Contains (n) rounded rectangle(s) arranged horizontally with spacing (s),
     each (w) wide, (h) tall, corner radius (r).
  3. Contains (n) circle(s) in a (rows)x(cols) grid layout, horizontal spacing (hs),
     vertical spacing (vs), radius (r), solid/dashed line style.
  4. Dunzhu (pier column) height: (h).
  5. Chengtai (bearing platform) height: (h).
  6. Zhuangji (pile foundation) height: (h).
"""

import re
from typing import Any


# --- Compiled regex patterns ---

BASEPLATE_RE = re.compile(
    r"A rectangular base plate with width (\d+(?:\.\d+)?) and height (\d+(?:\.\d+)?)."
)

ROUNDED_RECT_RE = re.compile(
    r"Contains (\d+) rounded rectangle\(s\) arranged horizontally "
    r"with spacing (\d+(?:\.\d+)?), each (\d+(?:\.\d+)?) wide, "
    r"(\d+(?:\.\d+)?) tall, corner radius (\d+(?:\.\d+)?)."
)

CIRCLE_RE = re.compile(
    r"Contains (\d+) circle\(s\) in a (\d+)x(\d+) grid layout, "
    r"horizontal spacing (\d+(?:\.\d+)?), vertical spacing (\d+(?:\.\d+)?), "
    r"radius (\d+(?:\.\d+)?), (solid|dashed) line style."
)

HEIGHT_DUNZHU_RE = re.compile(
    r"Dunzhu \(pier column\) height: (\d+(?:\.\d+)?)."
)

HEIGHT_CHENGTI_RE = re.compile(
    r"Chengtai \(bearing platform\) height: (\d+(?:\.\d+)?)."
)

HEIGHT_ZHUANJI_RE = re.compile(
    r"Zhuangji \(pile foundation\) height: (\d+(?:\.\d+)?)."
)


# --- Extractor functions (each returns a dict or None) ---

def extract_baseplate(line: str) -> dict[str, Any] | None:
    m = BASEPLATE_RE.match(line.strip())
    if not m:
        return None
    return {"width": float(m.group(1)), "height": float(m.group(2))}


def extract_rounded_rect(line: str) -> dict[str, Any] | None:
    m = ROUNDED_RECT_RE.match(line.strip())
    if not m:
        return None
    return {
        "count": int(m.group(1)),
        "spacing": float(m.group(2)),
        "width": float(m.group(3)),
        "height": float(m.group(4)),
        "corner_radius": float(m.group(5)),
    }


def extract_circle(line: str) -> dict[str, Any] | None:
    m = CIRCLE_RE.match(line.strip())
    if not m:
        return None
    return {
        "count": int(m.group(1)),
        "rows": int(m.group(2)),
        "cols": int(m.group(3)),
        "h_spacing": float(m.group(4)),
        "v_spacing": float(m.group(5)),
        "radius": float(m.group(6)),
        "line_style": m.group(7),
    }


def extract_dunzhu_height(line: str) -> float | None:
    m = HEIGHT_DUNZHU_RE.match(line.strip())
    return float(m.group(1)) if m else None


def extract_chengtai_height(line: str) -> float | None:
    m = HEIGHT_CHENGTI_RE.match(line.strip())
    return float(m.group(1)) if m else None


def extract_zhuangji_height(line: str) -> float | None:
    m = HEIGHT_ZHUANJI_RE.match(line.strip())
    return float(m.group(1)) if m else None
