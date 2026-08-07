"""Localized deterministic correction of manuscript Figure 4 (Type 4 arrows).

The approved Figure 4 slide export shows all four Type 4 arrows pointing
inward to the central circle. Per the corrected typology reading
(multiple structures -> one structure -> multiple structures), the two LOWER
arrows must instead point outward, from the central circle toward the two
lower circles.

Correction method (smallest possible deterministic edit):
  * detect the four Type 4 arrow glyphs as small purple connected components
    between the circles of the rightmost panel;
  * for the two arrows below the central circle, rotate each arrow's own
    bounding-box crop by exactly 180 degrees (a lossless pixel permutation,
    no interpolation). A 180-degree rotation of a straight arrow reverses
    its direction while reusing the identical antialiased pixels.

Everything outside the two lower-arrow bounding boxes is byte-identical.
The script writes a difference mask and a JSON report proving locality.

Usage:
  python correct_fig04_type4_arrows.py --src <original PNG> --out <outdir>

Outputs in --out: Figure_04.png (corrected), Figure_04.pdf (corrected PNG
placed on the original 16:9 canvas, deterministic metadata),
fig04_diff_mask.png, fig04_diff_report.json.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage


def find_arrow_boxes(rgb: np.ndarray):
    """Return bounding boxes of the 4 Type 4 arrows and circle geometry."""
    h, w, _ = rgb.shape
    r = rgb[:, :, 0].astype(int)
    g = rgb[:, :, 1].astype(int)
    b = rgb[:, :, 2].astype(int)
    # Purple family of the Type 4 panel (title, circles, arrows).
    purple = (r > 60) & (r < 190) & (g < 120) & (b > 110) & (b - g > 40)
    # Restrict to the right-most quarter (Type 4 panel).
    panel = np.zeros_like(purple)
    panel[:, int(w * 0.72):] = True
    mask = purple & panel
    lab, n = ndimage.label(mask)
    objs = ndimage.find_objects(lab)
    comps = []
    for i, sl in enumerate(objs, start=1):
        area = int((lab[sl] == i).sum())
        y0, y1 = sl[0].start, sl[0].stop
        x0, x1 = sl[1].start, sl[1].stop
        comps.append({"id": i, "area": area, "box": (x0, y0, x1, y1),
                      "cy": (y0 + y1) / 2, "cx": (x0 + x1) / 2,
                      "hw": (y1 - y0, x1 - x0)})
    # Circles: the 5 largest, roughly square, big-area components.
    comps.sort(key=lambda c: -c["area"])
    circles = comps[:5]
    circle_cys = sorted(c["cy"] for c in circles)
    center_cy = circle_cys[2]  # middle circle vertical center
    min_circle_area = min(c["area"] for c in circles)
    # Arrows: mid-sized components between the circle rows, not title glyphs.
    top_row_cy, bottom_row_cy = circle_cys[0], circle_cys[-1]
    arrows = [c for c in comps[5:]
              if c["area"] > min_circle_area * 0.01
              and top_row_cy < c["cy"] < bottom_row_cy]
    arrows.sort(key=lambda c: -c["area"])
    arrows = arrows[:4]
    if len(arrows) != 4:
        raise SystemExit(f"expected 4 arrow components, found {len(arrows)}")
    lower = sorted([c for c in arrows if c["cy"] > center_cy],
                   key=lambda c: c["cx"])
    upper = [c for c in arrows if c["cy"] <= center_cy]
    if len(lower) != 2 or len(upper) != 2:
        raise SystemExit("could not split arrows into 2 upper + 2 lower")
    return lower, upper, arrows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pad", type=int, default=2)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    im = Image.open(args.src)
    mode = im.mode
    arr = np.array(im)
    rgb = np.array(im.convert("RGB"))
    lower, upper, arrows = find_arrow_boxes(rgb)

    corrected = arr.copy()
    boxes = []
    for c in lower:
        x0, y0, x1, y1 = c["box"]
        x0 = max(0, x0 - args.pad); y0 = max(0, y0 - args.pad)
        x1 = min(arr.shape[1], x1 + args.pad); y1 = min(arr.shape[0], y1 + args.pad)
        corrected[y0:y1, x0:x1] = corrected[y0:y1, x0:x1][::-1, ::-1]
        boxes.append([int(x0), int(y0), int(x1), int(y1)])

    # Locality proof: every changed pixel must lie inside the two boxes.
    diff = np.any(arr != corrected, axis=-1) if arr.ndim == 3 else (arr != corrected)
    outside = diff.copy()
    for x0, y0, x1, y1 in boxes:
        outside[y0:y1, x0:x1] = False
    n_outside = int(outside.sum())

    Image.fromarray(corrected, mode=mode).save(out / "Figure_04.png")

    # Difference mask image (white = changed pixel).
    Image.fromarray((diff * 255).astype(np.uint8), mode="L").save(
        out / "fig04_diff_mask.png")

    # Deterministic PDF companion: corrected raster on the original canvas.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    h, w = arr.shape[0], arr.shape[1]
    fig = plt.figure(figsize=(15.0, 15.0 * h / w), dpi=300)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.imshow(np.array(Image.fromarray(corrected, mode=mode).convert("RGB")),
              interpolation="none")
    ax.axis("off")
    fig.savefig(out / "Figure_04.pdf",
                metadata={"CreationDate": None, "Producer": None,
                          "Creator": "SCORCH correct_fig04_type4_arrows.py"})
    plt.close(fig)

    report = {
        "src": str(args.src),
        "mode": mode,
        "image_size": [int(w), int(h)],
        "upper_arrow_boxes_untouched": [list(map(int, c["box"])) for c in upper],
        "lower_arrow_boxes_rotated_180": boxes,
        "changed_pixels_total": int(diff.sum()),
        "changed_pixels_outside_boxes": n_outside,
        "locality_ok": n_outside == 0,
    }
    (out / "fig04_diff_report.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))
    if n_outside:
        raise SystemExit("locality violated")


if __name__ == "__main__":
    main()
