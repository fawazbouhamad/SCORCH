#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Author-directed restoration of Dr. Najibi's original Figure 1 with the
single authorized threshold-wording correction.

The authoritative donor is the original v1.0.0 manuscript embed
(``original/Figure_01_original.png``, SHA-256 cc561b36..., 4500 x 2531).
Per the author's instruction the ONLY permitted visible change is inside
the orange upper-right text box, whose third text line

    "than a regional P97.5th threshold"

must become

    "than or equal to a regional P97.5th threshold"

because the implemented regional selection rule is N_HW(t) >= 371
(verified against the deposited daily-extent series: ">= 371" selects the
395 catalog days including 1998-05-26 and 2016-08-03, which sit exactly
at 371, while "> 371" would select only 393 days).

Method (smallest deterministic edit):
  * verify the donor hash and canvas before touching anything;
  * clear the third text line's band INSIDE the orange box interior
    (the band contains only white background and the old line's glyphs;
    the orange border is never touched);
  * re-render the corrected line with the same face the slide export
    used - Aptos Regular (identified against the donor glyphs at
    per-word best-shift IoU 0.845 at 93 px; Calibri/Segoe/Arial score
    <= 0.56) - at the same 93 px size, ink-top aligned to the original
    line's ascender row (y = 1019) and centred on the text-box centre;
  * prove locality: every changed pixel must lie inside the authorized
    band, and the new ink must sit fully inside it with margin.

Repeated runs are byte-identical (fixed donor, fixed font file verified
by hash, fixed PIL rasterization, no timestamps).

Usage:
  python restore_fig01_original_threshold.py --out <outdir>
      [--donor PATH] [--font PATH]

Outputs in --out: Figure_01.png (corrected), Figure_01.pdf (corrected
raster on the original 16:9 canvas, deterministic metadata),
fig01_diff_mask.png, fig01_diff_report.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent

DONOR_DEFAULT = HERE / "original" / "Figure_01_original.png"
DONOR_SHA256 = (
    "cc561b368f84b298b3ee38a39415799cc31d8ca932fa586a32bd7624831ec787")
CANVAS = (4500, 2531)

# Aptos Regular, Version 2.01;O365 (Microsoft 365 cloud font). The face
# is not redistributable, so it is referenced in place and pinned by hash.
FONT_DEFAULT = Path(
    "C:/Users/fawaw/AppData/Local/Microsoft/FontCache/4/CloudFonts/Aptos/"
    "30153066857.ttf")
FONT_SHA256 = (
    "95980114fcfd42f2f9c446dae429b70582bf2f03097d68433ea9e7d85a49da0b")
FONT_SIZE_PX = 93

OLD_LINE = "than a regional P97.5th threshold"
NEW_LINE = "than or equal to a regional P97.5th threshold"

# Orange box (outer 1895..3894 x 736..1140, border 7 px). The authorized
# band covers only the third text line inside the interior white area:
# clear x in [1906, 3884), y in [1002, 1128). The old line's ink occupies
# x 2228..3554, y 1019..1098; the band's remainder is pure white.
BAND = dict(x0=1906, y0=1002, x1=3884, y1=1128)
INK_TOP_Y = 1019          # ascender row of the original third line
CENTER_X = 2895           # text-box centre (interior 1902..3887)
MIN_MARGIN = 4            # new ink must keep this distance from the band


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ink_bbox(mask: np.ndarray):
    ys, xs = np.nonzero(mask)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def _render_line(font: ImageFont.FreeTypeFont, text: str) -> np.ndarray:
    """Render *text* black-on-white and return the cropped grayscale ink."""
    bbox = font.getbbox(text)
    pad = 8
    img = Image.new("L", (bbox[2] - bbox[0] + 2 * pad,
                          bbox[3] - bbox[1] + 2 * pad), 255)
    ImageDraw.Draw(img).text((pad - bbox[0], pad - bbox[1]), text,
                             font=font, fill=0)
    arr = np.array(img)
    x0, y0, x1, y1 = _ink_bbox(arr < 255)
    return arr[y0:y1, x0:x1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--donor", default=str(DONOR_DEFAULT))
    ap.add_argument("--font", default=str(FONT_DEFAULT))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    donor_path = Path(args.donor)
    if _sha256(donor_path) != DONOR_SHA256:
        raise SystemExit(f"donor hash mismatch: {donor_path} is not the "
                         "verified original Figure 1 embed")
    font_path = Path(args.font)
    if _sha256(font_path) != FONT_SHA256:
        raise SystemExit(f"font hash mismatch: {font_path} is not "
                         "Aptos Regular Version 2.01;O365")

    im = Image.open(donor_path)
    if im.size != CANVAS or im.mode != "RGB":
        raise SystemExit(f"donor canvas is {im.size} {im.mode}, expected "
                         f"{CANVAS} RGB")
    donor = np.array(im)

    x0, y0, x1, y1 = BAND["x0"], BAND["y0"], BAND["x1"], BAND["y1"]
    band = donor[y0:y1, x0:x1]
    # The band must contain only white background and dark glyph pixels
    # (never the orange border): every pixel is either near-white or
    # near-neutral dark/gray.
    r = band[:, :, 0].astype(int)
    g = band[:, :, 1].astype(int)
    b = band[:, :, 2].astype(int)
    chroma = np.maximum(np.maximum(abs(r - g), abs(g - b)), abs(r - b))
    if int(chroma.max()) > 24:
        raise SystemExit("authorized band unexpectedly contains colored "
                         "(border?) pixels - refusing to edit")

    font = ImageFont.truetype(str(font_path), FONT_SIZE_PX)

    # Metric self-check: the SAME renderer must reproduce the original
    # line's ink height and width closely before we trust it for the
    # corrected line.
    old_ink = _render_line(font, OLD_LINE)
    if abs(old_ink.shape[0] - 80) > 3 or abs(old_ink.shape[1] - 1327) > 12:
        raise SystemExit(
            f"font metric self-check failed: re-rendered original line is "
            f"{old_ink.shape[1]}x{old_ink.shape[0]}, expected ~1327x80")

    new_ink = _render_line(font, NEW_LINE)
    ih, iw = new_ink.shape
    px0 = CENTER_X - iw // 2
    py0 = INK_TOP_Y
    if not (x0 + MIN_MARGIN <= px0 and px0 + iw <= x1 - MIN_MARGIN
            and y0 + MIN_MARGIN <= py0 and py0 + ih <= y1 - MIN_MARGIN):
        raise SystemExit(f"corrected line ({iw}x{ih} at {px0},{py0}) does "
                         "not fit inside the authorized band with margin")

    corrected = donor.copy()
    corrected[y0:y1, x0:x1] = 255                      # clear the band
    region = corrected[py0:py0 + ih, px0:px0 + iw]
    region[:] = np.minimum(region, new_ink[:, :, None])  # composite ink

    # Locality proof.
    diff = np.any(donor != corrected, axis=-1)
    outside = diff.copy()
    outside[y0:y1, x0:x1] = False
    n_outside = int(outside.sum())

    Image.fromarray(corrected, mode="RGB").save(out / "Figure_01.png")
    Image.fromarray((diff * 255).astype(np.uint8), mode="L").save(
        out / "fig01_diff_mask.png")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    h, w = corrected.shape[0], corrected.shape[1]
    fig = plt.figure(figsize=(15.0, 15.0 * h / w), dpi=300)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.imshow(corrected, interpolation="none")
    ax.axis("off")
    fig.savefig(out / "Figure_01.pdf",
                metadata={"CreationDate": None, "Producer": None,
                          "Creator":
                          "SCORCH restore_fig01_original_threshold.py"})
    plt.close(fig)

    report = {
        "donor": str(donor_path),
        "donor_sha256": DONOR_SHA256,
        "font": str(font_path),
        "font_sha256": FONT_SHA256,
        "font_size_px": FONT_SIZE_PX,
        "old_line": OLD_LINE,
        "new_line": NEW_LINE,
        "authorized_band_x0y0x1y1": [x0, y0, x1, y1],
        "new_ink_x0y0x1y1": [px0, py0, px0 + iw, py0 + ih],
        "changed_pixels_total": int(diff.sum()),
        "changed_pixels_outside_band": n_outside,
        "locality_ok": n_outside == 0,
        "output_png_sha256": _sha256(out / "Figure_01.png"),
    }
    (out / "fig01_diff_report.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))
    if n_outside:
        raise SystemExit("locality violated")


if __name__ == "__main__":
    main()
