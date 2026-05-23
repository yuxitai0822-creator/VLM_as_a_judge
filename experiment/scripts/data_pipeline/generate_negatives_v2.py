"""
Generate negative samples: Geometry + Annotation decoupled pipeline.

Pipeline:
  1. Render geometry via ezdxf (no dimensions)
  2. Compute annotation metadata from perturbed params
  3. Overlay annotations (OpenCV+PIL)
  4. Save render.png
"""

import json
import os
import sys
import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, os.path.dirname(__file__))

from perturb import generate_all_negatives
from render_from_params import params_to_dxf
from overlay import overlay_annotations
from gen_annotations import top_view_annotations, front_view_annotations, side_view_annotations
from style_config import COLLAGE_SIZE, GAP_V, GAP_H, BG_COLOR

from ezdxf.addons.drawing.matplotlib import qsave, Configuration

# Extra padding around geometry for annotation space (pixels)
PAD = 80


def _render_geometry(doc, output_path):
    """Render DXF geometry only (remove DIMENSION entities first)."""
    msp = doc.modelspace()
    for d in list(msp.query("DIMENSION")):
        msp.delete_entity(d)

    cfg = Configuration(lineweight_scaling=1.0, min_lineweight=0.3)
    tmp = output_path + ".tmp.png"
    qsave(msp, tmp, dpi=600, bg="#FFFFFF", config=cfg)

    img = Image.open(tmp).convert("RGB")
    gray = img.convert("L")
    bold = gray.filter(ImageFilter.MinFilter(3))
    result = Image.merge("RGB", (bold, bold, bold))
    result.save(output_path)
    os.remove(tmp)
    return result


def _dx2px(params, target_px):
    """Scale factor: DXF units → pixels in the final collage."""
    rw = params["rect_width"]
    rh = params["rect_height"]
    zj = params["zhuangji_height"]
    ct = params["chengtai_height"]
    dz = params["dunzhu_height"]
    total_w = max(rw + GAP_H + rh, rw) + 200  # extra margin for annotations
    total_h = rh + GAP_V + zj + ct + dz + 200
    return target_px / max(total_w, total_h)


def generate_one_negative(pos_params, neg_params, output_dir):
    os.makedirs(output_dir, exist_ok=True)

    with open(os.path.join(output_dir, "parameter.json"), "w", encoding="utf-8") as f:
        json.dump(neg_params, f, indent=2, ensure_ascii=False)

    # Step 1: Render geometry
    doc = params_to_dxf(neg_params)
    geo_path = os.path.join(output_dir, "_geo.png")
    geo_img = _render_geometry(doc, geo_path)

    # Step 2: Compute annotations in pixel space
    sc = _dx2px(neg_params, COLLAGE_SIZE)
    rw_px = neg_params["rect_width"] * sc
    rh_px = neg_params["rect_height"] * sc
    gap_v_px = GAP_V * sc
    gap_h_px = GAP_H * sc
    zj_px = neg_params["zhuangji_height"] * sc
    ct_px = neg_params["chengtai_height"] * sc
    dz_px = neg_params["dunzhu_height"] * sc
    total_upper_h = zj_px + ct_px + dz_px

    # View origins (top-left corner of each view in the collage)
    # We add PAD to shift geometry inward, leaving room for annotations
    top_origin = (PAD, PAD)
    front_origin = (PAD, PAD + rh_px + gap_v_px)
    side_origin = (PAD + rw_px + gap_h_px, PAD + rh_px + gap_v_px)

    top_anns = top_view_annotations(neg_params, sc)
    front_anns = front_view_annotations(neg_params, sc, front_origin[1])
    side_anns = side_view_annotations(neg_params, sc, side_origin[0], side_origin[1])

    # Step 3: Create canvas + overlay
    canvas = Image.new("RGB", (COLLAGE_SIZE, COLLAGE_SIZE), BG_COLOR)

    # Resize geometry to fit
    geo_w, geo_h = geo_img.size
    geo_resized = geo_img.resize((COLLAGE_SIZE, COLLAGE_SIZE), Image.Resampling.LANCZOS)

    # Draw annotations on the canvas
    all_anns = top_anns + front_anns + side_anns
    canvas = overlay_annotations(canvas, all_anns, origin=(0, 0))

    # Blend: paste geometry onto white canvas (only dark pixels)
    geo_arr = np.array(geo_resized)
    canvas_arr = np.array(canvas)
    # Where geo is dark (geometry), use geo; where white, keep canvas (annotations)
    mask = np.max(geo_arr, axis=2) < 200
    canvas_arr[mask] = geo_arr[mask]

    final = Image.fromarray(canvas_arr)
    final.save(os.path.join(output_dir, "render.png"))
    os.remove(geo_path)


def main():
    pos_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "positive"))
    neg_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "negative"))

    samples = sorted([d for d in os.listdir(pos_dir) if d.startswith("sample_")])
    print(f"Found {len(samples)} positive samples")

    for sample_name in samples:
        pos_path = os.path.join(pos_dir, sample_name, "parameter.json")
        with open(pos_path, encoding="utf-8") as f:
            pos_params = json.load(f)

        sample_id = int(sample_name.split("_")[1])
        negatives = generate_all_negatives(pos_params, seed=sample_id)

        for ptype, neg_params in negatives.items():
            neg_name = f"{sample_name}_{ptype}"
            neg_sample_dir = os.path.join(neg_dir, neg_name)
            os.makedirs(neg_sample_dir, exist_ok=True)
            import shutil
            shutil.copy2(
                os.path.join(pos_dir, sample_name, "text.txt"),
                os.path.join(neg_sample_dir, "text.txt"),
            )
            generate_one_negative(pos_params, neg_params, neg_sample_dir)

        print(f"  {sample_name} → 3 negatives")

    print(f"\nDone. {neg_dir}")


if __name__ == "__main__":
    main()
