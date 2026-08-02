#!/usr/bin/env python3
# Published Figure S.1 composite (four panels), release adaptation of the
# SUPPLEMENT RECOVERY TASK 1 merge script (content-preserving; verified
# byte-identical to the deployed supplement embed, sha256 a5632323...).
#
# Content-preserving merge of the two donors:
#   top block  : the regenerated Type 3 Event 25 figure (panels a, b) --
#                produced by make_figS1_type3_event25.py in this directory
#                (byte-identical to the approved original), read from
#                <out>/supplement/Figure_S1_type3_event25.png
#   bottom row : the FROZEN provisional GHCNd-vs-ERA5 station artwork
#                (panels c, d) -- assets/frozen_figures/figS1_station_donor/
#                Figure_S2_station_provisional.png. This drawing has no
#                runnable producer (transcribed provenance); its metrics are
#                independently recomputed by
#                scripts/validation/ghcn_era5_validation.py
#                (r = 0.9802, RMSE = 1.696, bias = -1.595; window
#                2016-05-31..2016-06-12, n = 9).
# Nothing is recomputed, redrawn or restyled: the only additions are the four
# canonical panel letters (a)-(d), Arial bold 17 pt (q1_style.PANEL_LABEL),
# each horizontally centered on its panel's visible plot frame on a dedicated
# line above the panel. Output is declared at the Supplement DOCX measured
# text width (159.2 mm): PNG metadata + pypdf page scale; pixels untouched.
#
# Run make_figS1_type3_event25.py FIRST (the run_reproduction.py fast tier
# orders the stages correctly); this script fails loudly if the donor is
# missing.
from __future__ import annotations
import os, sys
os.environ.setdefault("MPLBACKEND", "Agg")
sys.dont_write_bytecode = True

import numpy as np
import matplotlib.pyplot as plt

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_FIGS = os.path.dirname(_THIS_DIR)                       # scripts/figures
sys.path.insert(0, os.path.join(_FIGS, "common"))
import q1_style as Q                                     # noqa: E402
from _clean_paths import RELEASE_ROOT, GENERATED_DIR     # noqa: E402

OUT_DIR = os.path.join(GENERATED_DIR, "supplement")
os.makedirs(OUT_DIR, exist_ok=True)

DONOR_A = os.path.join(OUT_DIR, "Figure_S1_type3_event25.png")
DONOR_B = os.path.join(RELEASE_ROOT, "assets", "frozen_figures",
                       "figS1_station_donor",
                       "Figure_S2_station_provisional.png")
for donor, hint in ((DONOR_A, "run make_figS1_type3_event25.py first"),
                    (DONOR_B, "frozen asset missing from the release")):
    if not os.path.exists(donor):
        raise SystemExit(f"FATAL: donor not found: {donor} ({hint})")

DONOR_A_DPI = 600.0
DPI = 600            # save dpi: donor A pixels place 1:1
FIG_W = 12.4         # design width = donor A native width (inches)

# Supplement DOCX measured geometry (read-only): A4 11906x16838 twips,
# margins 1440 twips -> text width 9026 twips = 6.2681 in = 159.21 mm.
TEXT_W_IN = 9026.0 / 1440.0
FINAL_SCALE = TEXT_W_IN / FIG_W

LABEL_LINE_IN = 0.42   # dedicated label line height (in design inches)
BLOCK_GAP_IN = 0.20    # gap between the maps block and the station row


def ink_row_blocks(im, thr=0.99):
    """Contiguous blocks of rows containing any non-white ink."""
    mask = np.any(im[..., :3] < thr, axis=2)
    if im.shape[2] == 4:
        mask &= im[..., 3] > 0.01
    rows = np.flatnonzero(mask.any(axis=1))
    blocks, start = [], rows[0]
    for i in range(1, len(rows)):
        if rows[i] != rows[i - 1] + 1:
            blocks.append((start, rows[i - 1])); start = rows[i]
    blocks.append((start, rows[-1]))
    return blocks


def frame_spans(im, minfrac=0.15):
    """x-spans of the visible panel frames: the dark runs of the FIRST row
    band that contains long horizontal spine segments (top spines)."""
    L = im[..., :3] @ np.array([0.299, 0.587, 0.114])
    dark = L < 0.35
    if im.shape[2] == 4:
        dark &= im[..., 3] > 0.5
    W = dark.shape[1]
    for r in range(dark.shape[0]):
        idx = np.flatnonzero(dark[r])
        if idx.size == 0:
            continue
        sp = np.where(np.diff(idx) > 1)[0]
        st = np.r_[idx[0], idx[sp + 1]]
        en = np.r_[idx[sp], idx[-1]]
        runs = [(int(a), int(b)) for a, b in zip(st, en) if b - a + 1 >= minfrac * W]
        if runs:
            return r, runs
    raise RuntimeError("no panel frame found")


def main():
    plt.rcParams.update({"font.family": "Arial", "pdf.fonttype": 42,
                         "ps.fonttype": 42})
    A = plt.imread(DONOR_A)
    B = plt.imread(DONOR_B)
    print(f"[NEW-S1] donor A {A.shape[1]}x{A.shape[0]} px, "
          f"donor B {B.shape[1]}x{B.shape[0]} px")

    # -- split donor A between the "Type 3" heading and the t / t+1 line -----
    ab = ink_row_blocks(A)
    assert len(ab) >= 2, ab
    split_a = (ab[0][1] + ab[1][0]) // 2          # mid-gap below the heading
    A_top, A_rest = A[:split_a], A[split_a:]
    print(f"[NEW-S1] donor A ink blocks {ab[:3]} -> heading strip rows "
          f"0..{split_a - 1}, maps block rows {split_a}..{A.shape[0] - 1}")

    # -- crop donor B's old "(a)"/"(b)" label strip --------------------------
    bb = ink_row_blocks(B)
    assert len(bb) >= 2, bb
    split_b = (bb[0][1] + bb[1][0]) // 2          # mid-gap below old labels
    B_body = B[split_b:]
    print(f"[NEW-S1] donor B ink blocks {bb[:3]} -> old (a)/(b) strip rows "
          f"0..{split_b - 1} REMOVED, panels rows {split_b}..{B.shape[0] - 1}")

    # -- panel frame centers (px) for label centering ------------------------
    row_a, runs_a = frame_spans(A_rest)
    assert len(runs_a) == 2, runs_a
    cxa = [(a + b) / 2.0 for a, b in runs_a]      # left / right map frames
    row_b, runs_b = frame_spans(B_body)
    assert len(runs_b) == 2, runs_b
    cxb = [(a + b) / 2.0 for a, b in runs_b]      # time-series / scatter frames
    print(f"[NEW-S1] map frames @row {row_a}: {runs_a}; "
          f"station frames @row {row_b}: {runs_b}")

    # -- vertical composition (design inches, top-down) ----------------------
    h_top = A_top.shape[0] / DONOR_A_DPI
    h_rest = A_rest.shape[0] / DONOR_A_DPI
    h_b = FIG_W * B_body.shape[0] / B_body.shape[1]
    FIG_H = (h_top + LABEL_LINE_IN + h_rest + BLOCK_GAP_IN + LABEL_LINE_IN
             + h_b + 0.06)
    fig = plt.figure(figsize=(FIG_W, FIG_H))

    y = FIG_H - h_top
    ax1 = fig.add_axes([0, y / FIG_H, 1.0, h_top / FIG_H])       # Type 3 strip
    y -= LABEL_LINE_IN                                            # (a)(b) line
    y_lab_ab = y / FIG_H
    y -= h_rest
    ax2 = fig.add_axes([0, y / FIG_H, 1.0, h_rest / FIG_H])      # maps block
    y -= BLOCK_GAP_IN + LABEL_LINE_IN                             # (c)(d) line
    y_lab_cd = y / FIG_H
    y -= h_b
    ax3 = fig.add_axes([0, y / FIG_H, 1.0, h_b / FIG_H])         # station row
    for ax, im in ((ax1, A_top), (ax2, A_rest), (ax3, B_body)):
        ax.imshow(im, interpolation="bilinear")
        ax.set_axis_off()

    # -- canonical labels: one shared style, centered on each panel frame ----
    pad = Q._pt_to_fig(fig, Q.LABEL_PAD_PT, "y")
    for cx, letter in zip(cxa, ("(a)", "(b)")):
        fig.text(cx / A_rest.shape[1], y_lab_ab + pad, letter,
                 ha="center", va="bottom", **Q.PANEL_LABEL)
    for cx, letter in zip(cxb, ("(c)", "(d)")):
        fig.text(cx / B_body.shape[1], y_lab_cd + pad, letter,
                 ha="center", va="bottom", **Q.PANEL_LABEL)

    for ext in ("png", "pdf"):
        p = os.path.join(OUT_DIR, f"New_Figure_S1_candidate.{ext}")
        fig.savefig(p, dpi=DPI)
        print(f"[SAVED] {p}")
    plt.close(fig)

    # ---- final uniform resize to the DOCX text width (metadata only) ----
    from PIL import Image
    p_png = os.path.join(OUT_DIR, "New_Figure_S1_candidate.png")
    im2 = Image.open(p_png)
    px_w, px_h = im2.size
    eff_dpi = px_w / TEXT_W_IN
    im2.save(p_png, dpi=(eff_dpi, eff_dpi))
    print(f"[NEW-S1] PNG {px_w}x{px_h} px declared at {eff_dpi:.2f} ppi -> "
          f"{px_w/eff_dpi*25.4:.1f} x {px_h/eff_dpi*25.4:.1f} mm")

    from pypdf import PdfReader, PdfWriter, Transformation
    p_pdf = os.path.join(OUT_DIR, "New_Figure_S1_candidate.pdf")
    rd = PdfReader(p_pdf)
    wr = PdfWriter()
    pg = rd.pages[0]
    pg.add_transformation(Transformation().scale(FINAL_SCALE, FINAL_SCALE))
    pg.mediabox.lower_left = (0, 0)
    pg.mediabox.upper_right = (float(pg.mediabox.width) * FINAL_SCALE,
                               float(pg.mediabox.height) * FINAL_SCALE)
    wr.add_page(pg)
    with open(p_pdf, "wb") as fh:
        wr.write(fh)
    print(f"[NEW-S1] PDF page scaled by {FINAL_SCALE:.4f} -> "
          f"{FIG_W*FINAL_SCALE*25.4:.1f} x {FIG_H*FINAL_SCALE*25.4:.1f} mm")


if __name__ == "__main__":
    main()
