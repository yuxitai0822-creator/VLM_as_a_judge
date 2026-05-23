"""
Engineering-style dimension annotation renderer.

Draws dimension primitives using OpenCV (lines, arrows) + PIL (bold text).
All annotations placed OUTSIDE geometry — never crossing model entities.
"""

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import math
import os

import style_config as S


def _load_font(size=None):
    size = size or S.FONT_SIZE
    for path in [S.FONT_NAME,
                 os.path.join("C:/Windows/Fonts", S.FONT_NAME),
                 os.path.join("C:/Windows/Fonts", "arialbd.ttf"),
                 os.path.join("C:/Windows/Fonts", "lucon.ttf")]:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _draw_filled_arrow(img, tip, direction, color, thickness):
    """Draw a closed filled triangular arrowhead at `tip`."""
    dx, dy = direction
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return
    ux, uy = dx / length, dy / length
    # Perpendicular
    px, py = -uy, ux
    L = S.ARROW_LENGTH
    W = S.ARROW_WIDTH
    # Triangle: tip → back-left → back-right
    bx = tip[0] - ux * L
    by = tip[1] - uy * L
    p1 = (int(bx + px * W), int(by + py * W))
    p2 = (int(bx - px * W), int(by - py * W))
    t = (int(tip[0]), int(tip[1]))
    cv2.fillConvexPoly(img, np.array([t, p1, p2], dtype=np.int32), color)


def _draw_extension_line(img, geo_point, dim_point, color):
    """Draw extension line from geometry edge toward dimension line, with offset."""
    thick = S.EXTENSION_LINE_WIDTH
    dx = dim_point[0] - geo_point[0]
    dy = dim_point[1] - geo_point[1]
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return
    ux, uy = dx / length, dy / length
    # Start: offset from geometry edge
    offset = S.EXTENSION_OFFSET
    start = (int(geo_point[0] + ux * offset), int(geo_point[1] + uy * offset))
    # End: overshoot past dimension line
    end = (int(dim_point[0] + ux * S.EXTENSION_OVERSHOOT),
           int(dim_point[1] + uy * S.EXTENSION_OVERSHOOT))
    cv2.line(img, start, end, color, thick, cv2.LINE_AA)


# ── Public API ──────────────────────────────────────────────────────────

def draw_horizontal_dim(img, x1, y1, x2, y2, dim_y, text, color=S.LINE_COLOR):
    """Horizontal dimension with extension lines + arrows + centered text.

    (x1,y1), (x2,y2): geometry boundary points (bottom edges).
    dim_y: y-position of dimension line (below geometry).
    """
    thick = S.ANNOTATION_LINE_WIDTH

    # Extension lines from geometry points down to dim line
    _draw_extension_line(img, (x1, y1), (x1, dim_y), color)
    _draw_extension_line(img, (x2, y2), (x2, dim_y), color)

    # Dimension line
    cv2.line(img, (x1, dim_y), (x2, dim_y), color, thick, cv2.LINE_AA)

    # Arrows pointing outward
    _draw_filled_arrow(img, (x1, dim_y), (-1, 0), color, thick)  # left
    _draw_filled_arrow(img, (x2, dim_y), (1, 0), color, thick)   # right

    # Centered text
    _draw_centered_text(img, (x1 + x2) // 2, dim_y, text, color)
    return img


def draw_vertical_dim(img, x1, y1, x2, y2, dim_x, text, color=S.LINE_COLOR):
    """Vertical dimension with extension lines + arrows + centered text.

    (x1,y1), (x2,y2): geometry boundary points (side edges).
    dim_x: x-position of dimension line (left or right of geometry).
    """
    thick = S.ANNOTATION_LINE_WIDTH

    _draw_extension_line(img, (x1, y1), (dim_x, y1), color)
    _draw_extension_line(img, (x2, y2), (dim_x, y2), color)

    cv2.line(img, (dim_x, y1), (dim_x, y2), color, thick, cv2.LINE_AA)

    _draw_filled_arrow(img, (dim_x, y1), (0, -1), color, thick)  # up
    _draw_filled_arrow(img, (dim_x, y2), (0, 1), color, thick)   # down

    _draw_centered_text(img, dim_x, (y1 + y2) // 2, text, color)
    return img


def draw_radius_ann(img, cx, cy, r, text, color=S.LINE_COLOR):
    """Radius/diameter annotation: leader line from circle to text."""
    thick = S.ANNOTATION_LINE_WIDTH
    start = (int(cx + r), int(cy))
    mid = (int(cx + r + 12), int(cy - 12))
    end = (int(cx + r + 45), int(cy - 12))
    cv2.line(img, start, mid, color, thick, cv2.LINE_AA)
    cv2.line(img, mid, end, color, thick, cv2.LINE_AA)
    _draw_left_text(img, end[0] + 2, end[1], text, color)
    return img


# ── Text helpers ────────────────────────────────────────────────────────

def _draw_centered_text(img, cx, cy, text, color):
    """Bold text centered at (cx, cy) with white background."""
    pil = Image.fromarray(img)
    draw = ImageDraw.Draw(pil)
    font = _load_font()
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx, ty = cx - tw // 2, cy - th // 2
    pad = S.TEXT_BG_PADDING
    draw.rectangle([tx - pad, ty - pad, tx + tw + pad, ty + th + pad], fill=S.TEXT_BG_COLOR)
    draw.text((tx, ty), text, fill=color, font=font)
    np.copyto(img, np.array(pil))


def _draw_left_text(img, x, y, text, color):
    """Bold text at (x, y) with white background."""
    pil = Image.fromarray(img)
    draw = ImageDraw.Draw(pil)
    font = _load_font()
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    ty = y - th // 2
    pad = S.TEXT_BG_PADDING
    draw.rectangle([x - pad, ty - pad, x + tw + pad, ty + th + pad], fill=S.TEXT_BG_COLOR)
    draw.text((x, ty), text, fill=color, font=font)
    np.copyto(img, np.array(pil))
