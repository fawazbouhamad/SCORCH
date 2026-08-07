#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Author-directed horizontal Type 4 correction of manuscript Figure 4.

The approved Figure 4 slide export draws the Type 4 panel as five purple
circles - a left pair (stacked vertically), a central circle, and a right
pair (stacked vertically) - with all four arrows pointing INWARD to the
centre. The author requires the Type 4 temporal progression to read
horizontally from left to right:

    two structures -> one structure -> two structures

With the circles already in a 2-1-2 column layout, the smallest
deterministic edit is arrow-direction only:

  * the two LEFT arrows already point from the left pair toward the
    central circle (down-right and up-right): KEEP, byte-identical;
  * the two RIGHT arrows point inward (down-left and up-left): rotate
    each arrow's own pixels (the arrow body plus its antialiased fringe,
    with every circle pixel explicitly protected) by exactly 180 degrees
    inside the arrow's bounding box - a lossless pixel permutation, no
    interpolation - so they point from the central circle outward to the
    right pair (up-right and down-right). The top-right circle's edge
    intrudes 6 core pixels plus fringe into the upper arrow's box, so a
    blind box rotation would notch the circle and orphan an edge
    fragment; the protected mask rotation leaves circles untouched.

After the edit the first arrow pair converges on the middle state and the
second pair diverges from it toward the right pair; every arrowhead
progresses left to right and no temporal sequence runs top to bottom.
The circles, the Type 4 title and bottom label, the other three panels,
and the dividers are untouched; a difference mask and a JSON report prove
zero changed pixels outside the two right-arrow boxes (which lie inside
the Type 4 interior symbol region).

This supersedes ``correct_fig04_type4_arrows.py`` (the earlier
lower-arrow correction, kept for history), and starts again from the
verified archived original so the two corrections never compound.

Usage:
  python correct_fig04_type4_horizontal.py --src <original PNG> --out <dir>

Outputs in --out: Figure_04.png (corrected), Figure_04.pdf (corrected PNG
on the original 16:9 canvas, deterministic metadata),
fig04_diff_mask.png, fig04_diff_report.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

DONOR_SHA256 = (
    "d595fb363d0a284abc1f9cc3049661f5786d1e42cf5e30ea3e50cea143a3bcde")
CANVAS = (4500, 2531)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def find_type4_geometry(rgb: np.ndarray):
    """Return the 5 circles and 4 arrows of the Type 4 panel."""
    h, w, _ = rgb.shape
    r = rgb[:, :, 0].astype(int)
    g = rgb[:, :, 1].astype(int)
    b = rgb[:, :, 2].astype(int)
    purple = (r > 60) & (r < 190) & (g < 120) & (b > 110) & (b - g > 40)
    panel = np.zeros_like(purple)
    panel[:, int(w * 0.72):] = True
    lab, _n = ndimage.label(purple & panel)
    comps = []
    for i, sl in enumerate(ndimage.find_objects(lab), start=1):
        area = int((lab[sl] == i).sum())
        y0, y1 = sl[0].start, sl[0].stop
        x0, x1 = sl[1].start, sl[1].stop
        comps.append({"id": i, "area": area, "box": (x0, y0, x1, y1),
                      "cy": (y0 + y1) / 2, "cx": (x0 + x1) / 2})
    comps.sort(key=lambda c: -c["area"])
    circles = comps[:5]
    circle_cys = sorted(c["cy"] for c in circles)
    top_cy, bottom_cy = circle_cys[0], circle_cys[-1]
    centre_cx = sorted(c["cx"] for c in circles)[2]
    min_circle_area = min(c["area"] for c in circles)
    arrows = [c for c in comps[5:]
              if c["area"] > min_circle_area * 0.01
              and top_cy < c["cy"] < bottom_cy]
    arrows.sort(key=lambda c: -c["area"])
    arrows = arrows[:4]
    if len(arrows) != 4:
        raise SystemExit(f"expected 4 arrow components, found {len(arrows)}")
    left = sorted([c for c in arrows if c["cx"] < centre_cx],
                  key=lambda c: c["cy"])
    right = sorted([c for c in arrows if c["cx"] >= centre_cx],
                   key=lambda c: c["cy"])
    if len(left) != 2 or len(right) != 2:
        raise SystemExit("could not split arrows into 2 left + 2 right")
    circle_core = np.isin(lab, [c["id"] for c in circles])
    return circles, left, right, circle_core


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pad", type=int, default=2)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    src_path = Path(args.src)
    if _sha256(src_path) != DONOR_SHA256:
        raise SystemExit(f"donor hash mismatch: {src_path} is not the "
                         "verified archived original Figure 4 export")
    im = Image.open(src_path)
    if im.size != CANVAS:
        raise SystemExit(f"donor canvas is {im.size}, expected {CANVAS}")
    mode = im.mode
    arr = np.array(im)
    rgb = np.array(im.convert("RGB"))
    circles, left, right, circle_core = find_type4_geometry(rgb)

    # Protect every circle pixel (labeled core + 2 px of antialiased
    # fringe): the rotation must never move or overwrite circle ink.
    protect = ndimage.binary_dilation(circle_core, iterations=2)

    corrected = arr.copy()
    boxes = []
    for c in right:
        x0, y0, x1, y1 = c["box"]
        x0 = max(0, x0 - args.pad); y0 = max(0, y0 - args.pad)
        x1 = min(arr.shape[1], x1 + args.pad)
        y1 = min(arr.shape[0], y1 + args.pad)
        crop = arr[y0:y1, x0:x1].copy()
        crop_rgb = rgb[y0:y1, x0:x1]
        prot = protect[y0:y1, x0:x1]
        # arrow ink = every non-white pixel in the box that is not circle
        arrow = np.any(crop_rgb < 250, axis=2) & ~prot
        region = corrected[y0:y1, x0:x1]
        region[arrow] = 255                       # lift the arrow out
        rot_vals = crop[::-1, ::-1]
        rot_mask = arrow[::-1, ::-1] & ~prot
        np.copyto(region, np.minimum(region, rot_vals),
                  where=rot_mask[..., None] if region.ndim == 3
                  else rot_mask)
        boxes.append([int(x0), int(y0), int(x1), int(y1)])

    diff = (np.any(arr != corrected, axis=-1)
            if arr.ndim == 3 else (arr != corrected))
    outside = diff.copy()
    for x0, y0, x1, y1 in boxes:
        outside[y0:y1, x0:x1] = False
    n_outside = int(outside.sum())

    # The Type 4 interior symbol region (the circle/arrow area of the
    # right-most panel) must contain every authorized box.
    cx0 = min(c["box"][0] for c in circles)
    cy0 = min(c["box"][1] for c in circles)
    cx1 = max(c["box"][2] for c in circles)
    cy1 = max(c["box"][3] for c in circles)
    interior = [int(cx0), int(cy0), int(cx1), int(cy1)]
    for x0, y0, x1, y1 in boxes:
        if not (cx0 <= x0 and x1 <= cx1 and cy0 <= y0 and y1 <= cy1):
            raise SystemExit("rotated arrow box escapes the Type 4 "
                             "interior symbol region")

    Image.fromarray(corrected, mode=mode).save(out / "Figure_04.png")
    Image.fromarray((diff * 255).astype(np.uint8), mode="L").save(
        out / "fig04_diff_mask.png")

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
                          "Creator":
                          "SCORCH correct_fig04_type4_horizontal.py"})
    plt.close(fig)

    report = {
        "src": str(src_path),
        "donor_sha256": DONOR_SHA256,
        "mode": mode,
        "image_size": [int(w), int(h)],
        "type4_interior_box": interior,
        "left_arrow_boxes_untouched": [list(map(int, c["box"]))
                                       for c in left],
        "right_arrow_boxes_rotated_180": boxes,
        "changed_pixels_total": int(diff.sum()),
        "changed_pixels_outside_boxes": n_outside,
        "locality_ok": n_outside == 0,
        "output_png_sha256": _sha256(out / "Figure_04.png"),
    }
    (out / "fig04_diff_report.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))
    if n_outside:
        raise SystemExit("locality violated")


if __name__ == "__main__":
    main()
