"""
Engineering-style dimension layout engine.

Implements a 3-tier dimension band hierarchy:
  BAND1: local feature dimensions (closest to geometry)
  BAND2: spacing between features
  BAND3: overall dimensions (outermost)

All dimensions in the same band share a common baseline.
Dimensions are organized per-view with global reference lines.
"""

import style_config as S

# Shorthand for band offsets (pixels from geometry edge)
B1 = S.BAND1_OFFSET
B2 = S.BAND2_OFFSET
B3 = S.BAND3_OFFSET


def _fmt(v):
    return str(int(v)) if v == int(v) else str(round(v, 1))


def top_view_annotations(p, sc):
    """Top/plan view: outer rect with dunzhu (rounded rects) + circles.

    Layout:
      ┌────────────────────────┐
      │  ┌──┐        ┌──┐     │
      │  │  │  ○  ○  │  │  ○  ○ │
      │  └──┘        └──┘     │
      └────────────────────────┘
      ←B1: segment widths→
      ←B2: spacing────────→
      ←B3: overall─────────→
    """
    rw = p["rect_width"] * sc
    rh = p["rect_height"] * sc
    cx0 = rw / 2
    anns = []

    rr_count = p["rounded_rect_horizontal_count"]
    rr_dist = p["rounded_rect_horizontal_distance"] * sc
    rrw = p["rounded_rect_width"] * sc
    rrh = p["rounded_rect_height"] * sc
    rrr = p["rounded_rect_radius"] * sc
    ch = p["circle_horizontal_count"]
    cv = p["circle_vertical_count"]
    dh = p["circle_horizontal_distance"] * sc
    dv = p["circle_vertical_distance"] * sc
    cr = p["circle_radius"] * sc

    y_bot = int(rh)  # bottom edge of outer rect

    # ── Horizontal BAND1: chain segment widths ─────────────────────────
    # Segments: left-edge → dunzhu-left → dunzhu-right → ... → right-edge
    edges = [0]
    for i in range(rr_count):
        cx = (i - (rr_count - 1) / 2) * rr_dist + cx0
        edges.extend([cx - rrw / 2, cx + rrw / 2])
    edges.append(rw)

    b1_y = y_bot + B1
    for i in range(0, len(edges) - 1, 2):
        x1, x2 = int(edges[i]), int(edges[i + 1])
        anns.append(("h", x1, y_bot, x2, y_bot, b1_y, _fmt((x2 - x1) / sc)))

    # ── Horizontal BAND2: dunzhu center-to-center spacing ──────────────
    if rr_count > 1:
        b2_y = y_bot + B2
        for i in range(rr_count - 1):
            cx1 = (i - (rr_count - 1) / 2) * rr_dist + cx0
            cx2 = ((i + 1) - (rr_count - 1) / 2) * rr_dist + cx0
            x1, x2 = int(cx1), int(cx2)
            anns.append(("h", x1, y_bot, x2, y_bot, b2_y,
                         _fmt((x2 - x1) / sc)))

    # ── Horizontal BAND3: overall width ────────────────────────────────
    b3_y = y_bot + B3
    anns.append(("h", 0, y_bot, int(rw), y_bot, b3_y,
                 str(p["rect_width"])))

    # ── Vertical BAND1: chain segment heights (left side) ──────────────
    b1_x = -B1
    edges_y = [0, int(rh / 2 - rrh / 2), int(rh / 2 + rrh / 2), int(rh)]
    for i in range(len(edges_y) - 1):
        y1, y2 = edges_y[i], edges_y[i + 1]
        anns.append(("v", 0, y1, 0, y2, b1_x, _fmt((y2 - y1) / sc)))

    # ── Vertical BAND3: overall height ─────────────────────────────────
    b3_x = -B3
    anns.append(("v", 0, 0, 0, int(rh), b3_x, str(p["rect_height"])))

    # ── Radius annotations (on geometry, leader-line style) ───────────
    if rrr > 0:
        for i in range(rr_count):
            cx = int((i - (rr_count - 1) / 2) * rr_dist + cx0)
            cy = int(rh / 2 - rrh / 2)
            anns.append(("r", cx, cy, int(rrr), 0, 0, f"R{int(rrr / sc)}"))

    # ── Diameter annotation (first circle) ─────────────────────────────
    dia = round(cr * 2 / sc, 1)
    dia_t = f"Ø{int(dia)}" if dia == int(dia) else f"Ø{dia}"
    ccx = int(-(ch - 1) / 2 * dh + cx0)
    ccy = int(-(cv - 1) / 2 * dv + rh / 2)
    anns.append(("r", ccx, ccy, int(cr), 0, 0, dia_t))

    return anns


def front_view_annotations(p, sc, y_base):
    """Front view: stacked zhuangji/chengtai/dunzhu below, piles below.

    Layout:
         ┌─┐   ┌─┐        B1 ← vertical: local heights
         │ │   │ │        B2 ← vertical: (if needed)
      ┌──┴─┴───┴─┴──┐
      │   chengtai   │     B1 ← horizontal: pile widths + gaps
      └─────────────┘
      ┌──┐       ┌──┐
      │  │       │  │
      └──┘       └──┘
    """
    rw = p["rect_width"] * sc
    cx0 = rw / 2
    zj = p["zhuangji_height"] * sc
    ct = p["chengtai_height"] * sc
    dz = p["dunzhu_height"] * sc
    total = zj + ct + dz
    anns = []

    # ── Vertical BAND1: local heights (left side) ─────────────────────
    b1_x = -B1
    y0 = int(y_base)
    bands = [
        (y0, int(y0 + zj), str(p["zhuangji_height"])),
        (int(y0 + zj), int(y0 + zj + ct), str(p["chengtai_height"])),
        (int(y0 + zj + ct), int(y0 + total), str(p["dunzhu_height"])),
    ]
    for y1, y2, text in bands:
        anns.append(("v", 0, y1, 0, y2, b1_x, text))

    # ── Horizontal BAND1: chain pile widths (below front view) ────────
    pile_w = p["circle_radius"] * 2 * sc
    n_c = p["circle_horizontal_count"]
    d_c = p["circle_horizontal_distance"] * sc

    edges = [0]
    for i in range(n_c):
        cx = (i - (n_c - 1) / 2) * d_c + cx0
        edges.extend([cx - pile_w / 2, cx + pile_w / 2])
    edges.append(rw)

    y_bot = int(y_base + total)
    b1_y = y_bot + B1
    for i in range(0, len(edges) - 1, 2):
        x1, x2 = int(edges[i]), int(edges[i + 1])
        anns.append(("h", x1, y_bot, x2, y_bot, b1_y, _fmt((x2 - x1) / sc)))

    return anns


def side_view_annotations(p, sc, x_off, y_base):
    """Side view: similar to front but with rect_height as width."""
    rh = p["rect_height"] * sc
    cy0 = rh / 2
    zj = p["zhuangji_height"] * sc
    ct = p["chengtai_height"] * sc
    dz = p["dunzhu_height"] * sc
    total = zj + ct + dz
    anns = []

    # ── Vertical BAND1: local heights (right side) ─────────────────────
    b1_x = int(x_off + rh) + B1
    y0 = int(y_base)
    bands = [
        (y0, int(y0 + zj), str(p["zhuangji_height"])),
        (int(y0 + zj), int(y0 + zj + ct), str(p["chengtai_height"])),
        (int(y0 + zj + ct), int(y0 + total), str(p["zhuangji_height"])),
    ]
    for y1, y2, text in bands:
        anns.append(("v", int(x_off + rh), y1, int(x_off + rh), y2, b1_x, text))

    # ── Horizontal BAND1: chain pile widths (below side view) ──────────
    pile_w = p["circle_radius"] * 2 * sc
    n_cv = p["circle_vertical_count"]
    d_cv = p["circle_vertical_distance"] * sc

    edges = [x_off]
    for j in range(n_cv):
        cy = (j - (n_cv - 1) / 2) * d_cv + cy0
        edges.extend([x_off + cy - pile_w / 2, x_off + cy + pile_w / 2])
    edges.append(x_off + rh)

    y_bot = int(y_base + total)
    b1_y = y_bot + B1
    for i in range(0, len(edges) - 1, 2):
        x1, x2 = int(edges[i]), int(edges[i + 1])
        anns.append(("h", x1, y_bot, x2, y_bot, b1_y, _fmt((x2 - x1) / sc)))

    return anns
