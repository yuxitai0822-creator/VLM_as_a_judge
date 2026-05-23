"""
Render three-view CAD drawing from flat TriView2CAD parameters.

Pipeline:
  parameter.json → ezdxf DXF (layered) → matplotlib render → PIL bold text overlay → render.png

DXF layout matches the original TriView2CAD dataset:
  ┌──────────┬──────────┐  y_top
  │  Front   │   Side   │
  ├──────────┴──────────┤  y_base (= rect_height + GAP_V)
  │      Top View       │
  └─────────────────────┘  y=0

Layers: chengtai, dunzhu, zhuangji
"""

import os

import ezdxf
from ezdxf.addons.drawing import RenderContext, Frontend
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend, Configuration, qsave
from matplotlib.figure import Figure
from PIL import Image, ImageDraw, ImageFont

# Layout constants (matching original DXF files)
GAP_V = 500   # vertical gap between top view and front/side
GAP_H = 350   # horizontal gap between front and side views

# Dimension band offsets (DXF units from geometry edge)
BAND_FEATURE = 40   # feature dimensions (rounded rect w/h)
BAND_LOCAL = 80     # spacing dimensions (rect spacing, circle V spacing)
BAND_CIRCLE = 100   # circle horizontal spacing
BAND_OVERALL = 120  # overall dimensions

TEXT_HEIGHT = 20.0  # DXF units (for viewport sizing)
RENDER_DPI = 600


# ── public API ───────────────────────────────────────────────────────────

def render_three_view(params: dict, output_path: str, img_size: int = 1475):
    doc, text_anns = params_to_dxf(params)
    _render_dxf(doc, text_anns, output_path, img_size)


def params_to_dxf(params: dict):
    doc = ezdxf.new()
    msp = doc.modelspace()
    doc.layers.add("chengtai", color=7)
    doc.layers.add("dunzhu", color=7)
    doc.layers.add("zhuangji", color=7)

    std = doc.dimstyles.get("Standard")
    std.dxf.dimscale = 8
    std.dxf.dimtxt = 2.5
    std.dxf.dimasz = 2.5
    std.dxf.dimexe = 1.25
    std.dxf.dimexo = 0.625
    std.dxf.dimgap = 0.625
    std.dxf.dimtad = 0
    std.dxf.dimclrd = 7
    std.dxf.dimclre = 7
    std.dxf.dimclrt = 7
    std.dxf.dimjust = 0
    std.dxf.dimdec = 1
    std.dxf.dimdsep = 46

    _draw_top_view(msp, params)
    _draw_front_view(msp, params)
    _draw_side_view(msp, params)
    text_anns = _add_dimensions(msp, params)
    return doc, text_anns


# ── DXF rendering + PIL bold text overlay ────────────────────────────────

def _load_bold_font(size: int) -> ImageFont.FreeTypeFont:
    for path in [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/consolab.ttf",
        "C:/Windows/Fonts/lucon.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _render_dxf(doc, text_anns: list, output_path: str, img_size: int):
    msp = doc.modelspace()

    # Remove MText placeholders — DIMENSION entities already extend the viewport
    for e in list(msp):
        if type(e).__name__ == "MText":
            msp.delete_entity(e)

    # Step 1: Extract viewport via internal renderer (same entities = same viewport)
    fig_vp = Figure()
    ax_vp = fig_vp.add_axes([0, 0, 1, 1])
    backend_vp = MatplotlibBackend(ax_vp)
    ctx_vp = RenderContext(doc)
    Frontend(ctx_vp, backend_vp).draw_layout(msp)
    xlim = ax_vp.get_xlim()
    ylim = ax_vp.get_ylim()
    del fig_vp, ax_vp, backend_vp, ctx_vp

    # Step 2: Render geometry with qsave (correct white background)
    tmp = output_path + ".tmp.png"
    cfg = Configuration(lineweight_scaling=0.5, min_lineweight=0.3)
    qsave(msp, tmp, dpi=RENDER_DPI, bg="#FFFFFF", config=cfg)

    # Step 3: Load image and overlay bold text via PIL
    img = Image.open(tmp).convert("RGB")
    raw_w, raw_h = img.size
    x_span = float(xlim[1] - xlim[0])
    y_span = float(ylim[1] - ylim[0])

    draw = ImageDraw.Draw(img)
    for ann in text_anns:
        dx, dy = ann["x"], ann["y"]
        text = ann["text"]

        px = (dx - float(xlim[0])) / x_span * raw_w
        py = (1 - (dy - float(ylim[0])) / y_span) * raw_h

        # Font size: scale TEXT_HEIGHT DXF units → pixels
        font_size = max(10, int(TEXT_HEIGHT / y_span * raw_h))
        font = _load_bold_font(font_size)

        draw.text((px, py), text, fill=(0, 0, 0), font=font, anchor="mm")

    # Step 3: Resize to target
    img = img.resize((img_size, img_size), Image.Resampling.LANCZOS)
    img.save(output_path)
    os.remove(tmp)


# ── helpers ──────────────────────────────────────────────────────────────

def _lwpoly(msp, points, layer):
    msp.add_lwpolyline(points, dxfattribs={"layer": layer})


def _add_rounded_rect(msp, x_min, y_min, w, h, r, layer):
    """Draw a rounded rectangle using LINE + ARC (matches original DXF)."""
    x_max = x_min + w
    y_max = y_min + h
    r = min(r, w / 2, h / 2)
    da = {"layer": layer}

    msp.add_line((x_min + r, y_min), (x_max - r, y_min), dxfattribs=da)
    msp.add_line((x_max, y_min + r), (x_max, y_max - r), dxfattribs=da)
    msp.add_line((x_max - r, y_max), (x_min + r, y_max), dxfattribs=da)
    msp.add_line((x_min, y_max - r), (x_min, y_min + r), dxfattribs=da)

    msp.add_arc((x_min + r, y_min + r), r, 180, 270, dxfattribs=da)
    msp.add_arc((x_max - r, y_min + r), r, 270, 360, dxfattribs=da)
    msp.add_arc((x_max - r, y_max - r), r, 0, 90, dxfattribs=da)
    msp.add_arc((x_min + r, y_max - r), r, 90, 180, dxfattribs=da)


def _add_rect(msp, x_min, y_min, w, h, layer):
    """Draw a closed rectangle as LWPOLYLINE."""
    pts = [(x_min, y_min), (x_min + w, y_min), (x_min + w, y_min + h),
           (x_min, y_min + h), (x_min, y_min)]
    _lwpoly(msp, pts, layer)


# ── top view (plan) ─────────────────────────────────────────────────────

def _draw_top_view(msp, p):
    rw, rh = p["rect_width"], p["rect_height"]
    cx0, cy0 = rw / 2, rh / 2

    _add_rect(msp, 0, 0, rw, rh, "chengtai")

    n = p["rounded_rect_horizontal_count"]
    d = p["rounded_rect_horizontal_distance"]
    w = p["rounded_rect_width"]
    h = p["rounded_rect_height"]
    r = p["rounded_rect_radius"]
    for i in range(n):
        x = (i - (n - 1) / 2) * d + cx0 - w / 2
        y = cy0 - h / 2
        _add_rounded_rect(msp, x, y, w, h, r, "dunzhu")

    ch, cv = p["circle_horizontal_count"], p["circle_vertical_count"]
    dh, dv = p["circle_horizontal_distance"], p["circle_vertical_distance"]
    cr = p["circle_radius"]
    solid = p["circle_solid_or_dashed"]
    for i in range(ch):
        for j in range(cv):
            ccx = (i - (ch - 1) / 2) * dh + cx0
            ccy = (j - (cv - 1) / 2) * dv + cy0
            msp.add_circle((ccx, ccy), cr, dxfattribs={"layer": "zhuangji"})
            if not solid:
                msp.add_circle((ccx, ccy), cr, dxfattribs={"layer": "zhuangji", "linetype": "DASHED"})


# ── front view (elevation) ──────────────────────────────────────────────

def _draw_front_view(msp, p):
    rw = p["rect_width"]
    cx0 = rw / 2
    ct_h = p["chengtai_height"]
    dz_h = p["dunzhu_height"]
    zj_h = p["zhuangji_height"]
    y_base = p["rect_height"] + GAP_V

    _add_rect(msp, 0, y_base + zj_h, rw, ct_h, "chengtai")

    n = p["rounded_rect_horizontal_count"]
    d = p["rounded_rect_horizontal_distance"]
    w = p["rounded_rect_width"]
    y_dz = y_base + zj_h + ct_h
    for i in range(n):
        x = (i - (n - 1) / 2) * d + cx0 - w / 2
        _add_rect(msp, x, y_dz, w, dz_h, "dunzhu")

    n_c = p["circle_horizontal_count"]
    d_c = p["circle_horizontal_distance"]
    pw = p["circle_radius"] * 2
    for i in range(n_c):
        x = (i - (n_c - 1) / 2) * d_c + cx0 - pw / 2
        _add_rect(msp, x, y_base, pw, zj_h, "zhuangji")


# ── side view (profile) ─────────────────────────────────────────────────

def _draw_side_view(msp, p):
    rw = p["rect_width"]
    rh = p["rect_height"]
    cx0 = rh / 2
    ct_h = p["chengtai_height"]
    dz_h = p["dunzhu_height"]
    zj_h = p["zhuangji_height"]
    x_off = rw + GAP_H
    y_base = rh + GAP_V

    _add_rect(msp, x_off, y_base + zj_h, rh, ct_h, "chengtai")

    rrd = p["rounded_rect_height"]
    y_dz = y_base + zj_h + ct_h
    _add_rect(msp, x_off + cx0 - rrd / 2, y_dz, rrd, dz_h, "dunzhu")

    n_cv = p["circle_vertical_count"]
    d_cv = p["circle_vertical_distance"]
    pw = p["circle_radius"] * 2
    for j in range(n_cv):
        cy = (j - (n_cv - 1) / 2) * d_cv + cx0
        _add_rect(msp, x_off + cy - pw / 2, y_base, pw, zj_h, "zhuangji")


# ── dimension annotations ───────────────────────────────────────────────

def _add_placeholder_mtext(msp, x, y, text, rotation=0):
    """Add invisible MText to occupy viewport space (so qsave includes annotation area)."""
    mt = msp.add_mtext(text, dxfattribs={
        "char_height": TEXT_HEIGHT, "color": 7,
        "insert": (x, y), "rotation": rotation,
    })
    mt.attach_style = 5  # bottom center


def _add_dimensions(msp, p) -> list[dict]:
    """Selective dimensioning. Returns list of text annotations for PIL overlay.

    All positions computed from params dict — works for any sample.
    Layout tiers (DXF units from geometry edge):
      BAND_FEATURE (40):  feature dims (rounded rect w/h)
      BAND_LOCAL   (80):  spacing dims (rect spacing, circle V spacing)
      BAND_CIRCLE  (100): circle H spacing
      BAND_OVERALL (120): overall dims
    """
    anns = []
    rw, rh = p["rect_width"], p["rect_height"]
    cx0, cy0 = rw / 2, rh / 2

    n_rr = p["rounded_rect_horizontal_count"]
    d_rr = p["rounded_rect_horizontal_distance"]
    w_rr = p["rounded_rect_width"]
    h_rr = p["rounded_rect_height"]
    r_rr = p["rounded_rect_radius"]

    ch, cv = p["circle_horizontal_count"], p["circle_vertical_count"]
    dh, dv = p["circle_horizontal_distance"], p["circle_vertical_distance"]
    cr = p["circle_radius"]

    ct_h = p["chengtai_height"]
    dz_h = p["dunzhu_height"]
    zj_h = p["zhuangji_height"]

    y_base = rh + GAP_V
    x_off = rw + GAP_H
    y_top = y_base + zj_h + ct_h + dz_h
    x_side_r = x_off + rh

    # First rounded rect geometry (parametric)
    cx_rr0 = (0 - (n_rr - 1) / 2) * d_rr + cx0
    rr_left = cx_rr0 - w_rr / 2
    rr_right = cx_rr0 + w_rr / 2
    rr_top = cy0 + h_rr / 2
    rr_bot = cy0 - h_rr / 2

    # First circle center (parametric)
    ccx_00 = (-(ch - 1) / 2) * dh + cx0
    ccy_00 = (-(cv - 1) / 2) * dv + cy0

    # ══ TOP VIEW — below (horizontal dims) ══

    # Tier 1: rounded rect width
    msp.add_linear_dim(base=(0, -BAND_FEATURE), p1=(rr_left, 0),
                       p2=(rr_right, 0)).render()
    _add_placeholder_mtext(msp, cx_rr0, -BAND_FEATURE, str(int(w_rr)))
    anns.append({"x": cx_rr0, "y": -BAND_FEATURE, "text": str(int(w_rr))})

    # Tier 2: rounded rect center-to-center spacing (if 2+ rects)
    if n_rr >= 2:
        cx_rr1 = (1 - (n_rr - 1) / 2) * d_rr + cx0
        msp.add_linear_dim(base=(0, -BAND_LOCAL), p1=(cx_rr0, 0),
                           p2=(cx_rr1, 0)).render()
        mid_x = (cx_rr0 + cx_rr1) / 2
        _add_placeholder_mtext(msp, mid_x, -BAND_LOCAL, str(int(d_rr)))
        anns.append({"x": mid_x, "y": -BAND_LOCAL, "text": str(int(d_rr))})

    # Tier 3: circle horizontal spacing (if 2+ columns)
    if ch >= 2:
        ccx_10 = (1 - (ch - 1) / 2) * dh + cx0
        msp.add_linear_dim(base=(0, -BAND_CIRCLE), p1=(ccx_00, 0),
                           p2=(ccx_10, 0)).render()
        mid_x = (ccx_00 + ccx_10) / 2
        _add_placeholder_mtext(msp, mid_x, -BAND_CIRCLE, str(int(dh)))
        anns.append({"x": mid_x, "y": -BAND_CIRCLE, "text": str(int(dh))})

    # Tier 4: overall width
    msp.add_linear_dim(base=(0, -BAND_OVERALL), p1=(0, 0), p2=(rw, 0)).render()
    _add_placeholder_mtext(msp, rw / 2, -BAND_OVERALL, str(int(rw)))
    anns.append({"x": rw / 2, "y": -BAND_OVERALL, "text": str(int(rw))})

    # ══ TOP VIEW — left (vertical dims) ══

    # Tier 1: rounded rect height
    msp.add_linear_dim(base=(-BAND_FEATURE, 0), p1=(0, rr_bot),
                       p2=(0, rr_top), angle=90).render()
    _add_placeholder_mtext(msp, -BAND_FEATURE, cy0, str(int(h_rr)))
    anns.append({"x": -BAND_FEATURE, "y": cy0, "text": str(int(h_rr))})

    # Tier 2: circle vertical spacing (if 2+ rows)
    if cv >= 2:
        ccy_01 = (1 - (cv - 1) / 2) * dv + cy0
        msp.add_linear_dim(base=(-BAND_LOCAL, 0), p1=(0, ccy_00),
                           p2=(0, ccy_01), angle=90).render()
        mid_y = (ccy_00 + ccy_01) / 2
        _add_placeholder_mtext(msp, -BAND_LOCAL, mid_y, str(int(dv)))
        anns.append({"x": -BAND_LOCAL, "y": mid_y, "text": str(int(dv))})

    # Tier 4: overall height
    msp.add_linear_dim(base=(-BAND_OVERALL, 0), p1=(0, 0),
                       p2=(0, rh), angle=90).render()
    _add_placeholder_mtext(msp, -BAND_OVERALL, rh / 2, str(int(rh)))
    anns.append({"x": -BAND_OVERALL, "y": rh / 2, "text": str(int(rh))})

    # ══ TOP VIEW — R and Ø annotations ══

    # Radius R — first rounded rect only
    if n_rr >= 1 and r_rr > 0:
        arc_cx = cx_rr0 + w_rr / 2 - r_rr
        arc_cy = cy0 - h_rr / 2 + r_rr
        msp.add_radius_dim(center=(arc_cx, arc_cy), radius=r_rr, angle=315).render()
        leader_end = (arc_cx + r_rr * 0.7, arc_cy - r_rr * 0.7 - 25)
        msp.add_line((arc_cx + r_rr, arc_cy), leader_end, dxfattribs={"color": 7})
        r_text = f"R{int(r_rr)}"
        _add_placeholder_mtext(msp, leader_end[0], leader_end[1], r_text)
        anns.append({"x": leader_end[0], "y": leader_end[1], "text": r_text})

    # Diameter Ø — first circle only
    if ch >= 1 and cv >= 1:
        msp.add_diameter_dim(center=(ccx_00, ccy_00), radius=cr, angle=135).render()
        leader_end = (ccx_00 - cr * 0.7 - 40, ccy_00 + cr * 0.7 + 25)
        msp.add_line((ccx_00 - cr, ccy_00), leader_end, dxfattribs={"color": 7})
        dia_text = f"Ø{int(cr * 2)}"
        _add_placeholder_mtext(msp, leader_end[0], leader_end[1], dia_text)
        anns.append({"x": leader_end[0], "y": leader_end[1], "text": dia_text})

    # ══ FRONT VIEW ══

    # Heights chain: zhuangji / chengtai / dunzhu (left side)
    msp.add_linear_dim(base=(-BAND_LOCAL, 0), p1=(0, y_base),
                       p2=(0, y_base + zj_h), angle=90).render()
    _add_placeholder_mtext(msp, -BAND_LOCAL, y_base + zj_h / 2, str(int(zj_h)))
    anns.append({"x": -BAND_LOCAL, "y": y_base + zj_h / 2, "text": str(int(zj_h))})

    msp.add_linear_dim(base=(-BAND_LOCAL, 0), p1=(0, y_base + zj_h),
                       p2=(0, y_base + zj_h + ct_h), angle=90).render()
    _add_placeholder_mtext(msp, -BAND_LOCAL, y_base + zj_h + ct_h / 2, str(int(ct_h)))
    anns.append({"x": -BAND_LOCAL, "y": y_base + zj_h + ct_h / 2, "text": str(int(ct_h))})

    msp.add_linear_dim(base=(-BAND_LOCAL, 0), p1=(0, y_base + zj_h + ct_h),
                       p2=(0, y_top), angle=90).render()
    _add_placeholder_mtext(msp, -BAND_LOCAL, y_base + zj_h + ct_h + dz_h / 2, str(int(dz_h)))
    anns.append({"x": -BAND_LOCAL, "y": y_base + zj_h + ct_h + dz_h / 2, "text": str(int(dz_h))})

    # Overall width (above)
    msp.add_linear_dim(base=(0, y_top + BAND_OVERALL), p1=(0, y_top),
                       p2=(rw, y_top)).render()
    _add_placeholder_mtext(msp, rw / 2, y_top + BAND_OVERALL, str(int(rw)))
    anns.append({"x": rw / 2, "y": y_top + BAND_OVERALL, "text": str(int(rw))})

    # ══ SIDE VIEW ══

    # Heights chain (right side)
    msp.add_linear_dim(base=(x_side_r + BAND_LOCAL, 0), p1=(x_off, y_base),
                       p2=(x_off, y_base + zj_h), angle=90).render()
    _add_placeholder_mtext(msp, x_side_r + BAND_LOCAL, y_base + zj_h / 2, str(int(zj_h)))
    anns.append({"x": x_side_r + BAND_LOCAL, "y": y_base + zj_h / 2, "text": str(int(zj_h))})

    msp.add_linear_dim(base=(x_side_r + BAND_LOCAL, 0), p1=(x_off, y_base + zj_h),
                       p2=(x_off, y_base + zj_h + ct_h), angle=90).render()
    _add_placeholder_mtext(msp, x_side_r + BAND_LOCAL, y_base + zj_h + ct_h / 2, str(int(ct_h)))
    anns.append({"x": x_side_r + BAND_LOCAL, "y": y_base + zj_h + ct_h / 2, "text": str(int(ct_h))})

    msp.add_linear_dim(base=(x_side_r + BAND_LOCAL, 0), p1=(x_off, y_base + zj_h + ct_h),
                       p2=(x_off, y_top), angle=90).render()
    _add_placeholder_mtext(msp, x_side_r + BAND_LOCAL, y_base + zj_h + ct_h + dz_h / 2, str(int(dz_h)))
    anns.append({"x": x_side_r + BAND_LOCAL, "y": y_base + zj_h + ct_h + dz_h / 2, "text": str(int(dz_h))})

    # Overall width (above)
    msp.add_linear_dim(base=(0, y_top + BAND_OVERALL), p1=(x_off, y_top),
                       p2=(x_off + rh, y_top)).render()
    _add_placeholder_mtext(msp, x_off + rh / 2, y_top + BAND_OVERALL, str(int(rh)))
    anns.append({"x": x_off + rh / 2, "y": y_top + BAND_OVERALL, "text": str(int(rh))})

    return anns
