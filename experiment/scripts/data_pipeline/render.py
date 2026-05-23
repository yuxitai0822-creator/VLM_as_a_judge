"""
Three-view rendering utilities for CAD samples.

Expects per-sample views as: front.png, side.png, iso.png
Concatenates them horizontally into a single render.png.
"""

from pathlib import Path

import numpy as np
from PIL import Image


VIEW_ORDER = ["front", "side", "iso"]


def concat_views(
    view_dir: str | Path,
    output_path: str | Path | None = None,
    layout: str = "horizontal",
    padding: int = 10,
    bg_color: tuple = (255, 255, 255),
) -> Image.Image:
    """
    Concatenate front/side/iso views into a single image.

    Args:
        view_dir: Directory containing front.png, side.png, iso.png.
        output_path: Optional path to save the concatenated result.
        layout: 'horizontal' or 'grid'.
        padding: Pixels between views.
        bg_color: Background fill color.

    Returns:
        PIL Image of the concatenated views with labels.
    """
    view_dir = Path(view_dir)
    images = []
    for view_name in VIEW_ORDER:
        img_path = view_dir / f"{view_name}.png"
        if img_path.exists():
            img = Image.open(img_path).convert("RGB")
        else:
            img = Image.new("RGB", (256, 256), bg_color)
        images.append(img)

    return _concatenate(images, layout, padding, bg_color, output_path)


def concat_from_paths(
    paths: dict[str, str | Path],
    output_path: str | Path | None = None,
    layout: str = "horizontal",
    padding: int = 10,
    bg_color: tuple = (255, 255, 255),
) -> Image.Image:
    """
    Concatenate views given explicit file paths.

    Args:
        paths: Dict with keys 'front', 'side', 'iso' mapping to image paths.
        output_path: Optional path to save the result.
        layout: 'horizontal' or 'grid'.
        padding: Pixels between views.
        bg_color: Background fill color.

    Returns:
        PIL Image of the concatenated views.
    """
    images = []
    for view_name in VIEW_ORDER:
        p = Path(paths.get(view_name, ""))
        if p.exists():
            img = Image.open(p).convert("RGB")
        else:
            img = Image.new("RGB", (256, 256), bg_color)
        images.append(img)

    return _concatenate(images, layout, padding, bg_color, output_path)


def _concatenate(
    images: list[Image.Image],
    layout: str,
    padding: int,
    bg_color: tuple,
    output_path: str | Path | None,
) -> Image.Image:
    """Core concatenation logic."""
    # Normalize sizes to match the tallest image
    max_h = max(img.height for img in images)
    resized = []
    for img in images:
        if img.height != max_h:
            ratio = max_h / img.height
            new_w = int(img.width * ratio)
            img = img.resize((new_w, max_h), Image.LANCZOS)
        resized.append(img)

    if layout == "horizontal":
        total_w = sum(img.width for img in resized) + padding * (len(resized) - 1)
        canvas = Image.new("RGB", (total_w, max_h), bg_color)
        x = 0
        for img in resized:
            canvas.paste(img, (x, 0))
            x += img.width + padding
    elif layout == "grid":
        col_count = 3
        row_count = 1
        max_w = max(img.width for img in resized)
        total_w = col_count * max_w + padding * (col_count - 1)
        total_h = row_count * max_h + padding * (row_count - 1)
        canvas = Image.new("RGB", (total_w, total_h), bg_color)
        for idx, img in enumerate(resized):
            col = idx % col_count
            row = idx // col_count
            x = col * (max_w + padding) + (max_w - img.width) // 2
            y = row * (max_h + padding)
            canvas.paste(img, (x, y))
    else:
        raise ValueError(f"Unknown layout: {layout}")

    if output_path is not None:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        canvas.save(str(output_path))

    return canvas
