#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic manuscript-artwork preparation for SCORCH.

Historically the manuscript figures were prepared from the reproduced artwork by
an undocumented manual step ("approved manual presentation processing"). That
step was recovered numerically during the v1.0.0 pre-release alignment programme by
searching resampling filters and PNG encoder parameters until the embedded media
of the working manuscript reproduced **byte for byte**.

The recovered recipe, validated byte-exact on 9/9 downscaled figures
(Figures 5, 6, 7, 8, 9, 10, 11, Appendix A, Appendix C):

    im = Image.open(src).convert("RGBA")
    w, h = im.size
    im.resize((1950, int(h * 1950 / w)), Image.LANCZOS) \
      .save(dst, "PNG", optimize=False, compress_level=6)

Two details are load-bearing and must not be "tidied":

* The height uses **truncation** ``int(...)``, not rounding. Three figures
  disambiguate this -- Appendix A (1781.897 -> 1781), Appendix C (1330.952 ->
  1330) and Figure 10 (1222.584 -> 1222). Rounding fails all three.
* ``optimize=False`` with ``compress_level=6`` (Pillow's default zlib level).
  Any other combination changes the bytes even though the pixels are identical.

The remaining figures are embedded at full resolution with no processing at all;
they are copied verbatim. Which figures take which path is a recovered fact
about the existing manuscript, not a style choice, so the table below is data,
not policy.

Usage
-----
    python make_manuscript_artwork.py --reproduced <dir> --out <dir> [--manifest <csv>]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import shutil

from PIL import Image

Image.MAX_IMAGE_PIXELS = None

#: Target width in pixels for downscaled manuscript artwork.
MANUSCRIPT_WIDTH_PX = 1950

PASSTHROUGH = "passthrough"
DOWNSCALE = "downscale-1950"

#: (manuscript label, path under the reproduced/ tree, mode)
#: Figures 1 and 4 are hand-drawn schematics with no computational producer;
#: they are sourced from assets/frozen_figures/ instead and are handled by the
#: --frozen option rather than appearing here.
ARTWORK = [
    ("Figure_02", "fig02/Figure2_assembled.png", PASSTHROUGH),
    ("Figure_03", "fig03/Figure3_assembled.png", PASSTHROUGH),
    ("Figure_05", "fig05/Figure5_type1_type2.png", DOWNSCALE),
    ("Figure_06", "fig06/Figure6_type3_two_events.png", DOWNSCALE),
    ("Figure_07", "fig07/Figure7_type4_six_days.png", DOWNSCALE),
    ("Figure_08", "fig08/figure5_type_AGU_hist_boxplot_orientation_area_ratio.png", DOWNSCALE),
    ("Figure_09", "fig09/Figure9_assembled.png", DOWNSCALE),
    ("Figure_10", "fig10/Fig11_SCORCH_event_frequency_duration_ONLY_two_panels.png", DOWNSCALE),
    ("Figure_11", "fig11/q1_power_law_2x2_panel_clean.png", DOWNSCALE),
    ("Figure_12", "fig12/q1_four_variable_centroid_risk_map.png", PASSTHROUGH),
    ("Appendix_A", "appendix/Figure_A1_pca_sigma_sensitivity.png", DOWNSCALE),
    ("Appendix_B", "appendix_a2/New_Figure_A2_Event10_candidate.png", PASSTHROUGH),
    ("Appendix_C", "appendix/Figure_A3_dbscan_parameters.png", DOWNSCALE),
    ("Appendix_D", "supplement/New_Figure_S2_candidate.png", PASSTHROUGH),
    ("Figure_S1", "supplement/New_Figure_S1_candidate.png", PASSTHROUGH),
]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def downscale_to_width(src, dst, width=MANUSCRIPT_WIDTH_PX):
    """Apply the recovered presentation recipe. Returns the output (w, h)."""
    im = Image.open(src).convert("RGBA")
    w, h = im.size
    if w <= 0 or h <= 0:
        raise ValueError(f"degenerate image size {(w, h)} for {src}")
    # Truncation, NOT rounding -- see module docstring.
    out = im.resize((width, int(h * width / w)), Image.LANCZOS)
    out.save(dst, "PNG", optimize=False, compress_level=6)
    return out.size


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reproduced", required=True,
                    help="directory holding the reproduced figure workflow output")
    ap.add_argument("--out", required=True,
                    help="destination directory for manuscript-ready artwork")
    ap.add_argument("--manifest", default=None,
                    help="optional CSV manifest path (default: <out>/ARTWORK_MANIFEST.csv)")
    ap.add_argument("--frozen", default=None,
                    help="optional assets/frozen_figures dir supplying Figures 1 and 4")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    manifest_path = args.manifest or os.path.join(args.out, "ARTWORK_MANIFEST.csv")

    rows, missing = [], []

    if args.frozen:
        for label, rel in (("Figure_01", "fig01/Figure_01.png"),
                           ("Figure_04", "fig04/Figure_04.png")):
            src = os.path.join(args.frozen, rel)
            if not os.path.exists(src):
                missing.append(src)
                continue
            dst = os.path.join(args.out, label + ".png")
            shutil.copyfile(src, dst)
            with Image.open(dst) as im:
                w, h = im.size
            rows.append((label, rel, "frozen-schematic", w, h, sha256_file(dst)))
            print(f"[ARTWORK] {label:11s} {'frozen-schematic':16s} {w}x{h}  {rows[-1][5][:16]}")

    for label, rel, mode in ARTWORK:
        src = os.path.join(args.reproduced, rel)
        if not os.path.exists(src):
            missing.append(src)
            continue
        dst = os.path.join(args.out, label + ".png")
        if mode == DOWNSCALE:
            w, h = downscale_to_width(src, dst)
        else:
            shutil.copyfile(src, dst)
            with Image.open(dst) as im:
                w, h = im.size
        rows.append((label, rel, mode, w, h, sha256_file(dst)))
        print(f"[ARTWORK] {label:11s} {mode:16s} {w}x{h}  {rows[-1][5][:16]}")

    with open(manifest_path, "w", newline="", encoding="utf-8") as fh:
        wtr = csv.writer(fh, lineterminator="\n")
        wtr.writerow(["figure", "source", "mode", "width", "height", "sha256"])
        wtr.writerows(rows)
    print(f"[ARTWORK] wrote {len(rows)} entries -> {manifest_path}")

    if missing:
        print("[ARTWORK] MISSING SOURCES (not fabricated, reported):")
        for m in missing:
            print("   ", m)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
