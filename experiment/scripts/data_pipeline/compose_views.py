"""
Compose three views into a single collage matching TriView2CAD layout.

Layout (1475×1475):
  ┌──────────┬──────────┐
  │  Front   │   Side   │
  ├──────────┴──────────┤
  │      Top View       │
  └─────────────────────┘
"""

from PIL import Image

import style_config as S

# Proportions matching the original dataset
# Top view: full width, ~56% height; Front/Side: half width each, ~44% height
COLLAGE = S.COLLAGE_SIZE
TOP_FRAC = 0.56
H_FRAC = 1 - TOP_FRAC


def compose_three_views(
    top: Image.Image,
    front: Image.Image,
    side: Image.Image,
    output_size: int = COLLAGE,
) -> Image.Image:
    """Compose front, side, top views into a single collage image."""
    canvas = Image.new("RGB", (output_size, output_size), S.BG_COLOR)

    # Calculate view dimensions
    top_h = int(output_size * TOP_FRAC)
    upper_h = output_size - top_h
    half_w = output_size // 2

    # Resize each view to fit its slot
    top_resized = top.resize((output_size, top_h), Image.Resampling.LANCZOS)
    front_resized = front.resize((half_w, upper_h), Image.Resampling.LANCZOS)
    side_resized = side.resize((half_w, upper_h), Image.Resampling.LANCZOS)

    # Paste: front top-left, side top-right, top bottom
    canvas.paste(front_resized, (0, 0))
    canvas.paste(side_resized, (half_w, 0))
    canvas.paste(top_resized, (0, upper_h))

    return canvas
