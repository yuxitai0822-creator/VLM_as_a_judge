"""
Overlay dimension annotations onto geometry image.

Annotation tuples from gen_annotations:
  ("h", x1, y1, x2, y2, dim_y, text)   → horizontal dim
  ("v", x1, y1, x2, y2, dim_x, text)   → vertical dim
  ("r", cx, cy, r, _, _, text)          → radius/diameter label
"""

import numpy as np
from PIL import Image
from draw_dimension import draw_horizontal_dim, draw_vertical_dim, draw_radius_ann


def overlay_annotations(geo_img: Image.Image, annotations: list, origin: tuple = (0, 0)) -> Image.Image:
    """Draw all annotations onto geometry image.

    origin: (ox, oy) pixel offset for the view within the full collage.
    All annotation coords are relative to the view origin.
    """
    img = np.array(geo_img)
    ox, oy = origin

    for ann in annotations:
        atype = ann[0]
        if atype == "h":
            _, x1, y1, x2, y2, dim_y, text = ann
            draw_horizontal_dim(img, x1 + ox, y1 + oy, x2 + ox, y2 + oy, dim_y + oy, text)
        elif atype == "v":
            _, x1, y1, x2, y2, dim_x, text = ann
            draw_vertical_dim(img, x1 + ox, y1 + oy, x2 + ox, y2 + oy, dim_x + ox, text)
        elif atype == "r":
            _, cx, cy, r, _, _, text = ann
            draw_radius_ann(img, cx + ox, cy + oy, r, text)

    return Image.fromarray(img)
