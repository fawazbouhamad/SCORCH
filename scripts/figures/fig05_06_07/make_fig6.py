#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 2C-R2 — regenerate paper Figure 6 ONLY, with row labels moved left.

Identical to the approved Phase 2C Figure 6 (same renderer, events, dates,
grid geometry, Type 3 heading, t/t+1 headings, date insets, unified legend)
EXCEPT the horizontal placement of the (a)/(b) row labels:

  * vertical positions preserved exactly (centered on each row's union
    bounding box, as in Phase 2C q1_style.label_left);
  * both labels share ONE x-coordinate, computed from MEASURED rendered
    bounding boxes: the labels' right edge sits GAP_PT (14 pt >= the required
    12 pt) left of the leftmost y-axis/tick-label bounding box across both
    rows (Axes.get_tightbbox, which includes tick labels and axis labels);
  * the achieved per-row gaps are measured back from the drawn text and
    asserted >= 12 pt.

Output: <phase2c_r2>/outputs/fig06/Figure6_type3_two_events.{png,pdf}
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("MPLBACKEND", "Agg")

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_FIGS = os.path.dirname(_THIS_DIR)                       # scripts/figures
_ROOT = os.path.dirname(os.path.dirname(_FIGS))          # release root
sys.path.insert(0, _THIS_DIR)
sys.path.insert(0, os.path.join(_FIGS, "common"))

import matplotlib.pyplot as plt        # noqa: E402
import common as C                     # noqa: E402
import snapshots as SN                 # noqa: E402
import q1_style as Q                   # noqa: E402

OUT = os.environ.get("SCORCH_OUT_DIR",
                     os.path.join(_ROOT, "reproduced"))
DPI = 600
TIME_FS = 15                           # t / t+1 labels (bold math style)
GAP_PT = 14.0                          # designed label-to-axis gap (>= 12)


def _render(ax, labels_df, date: str) -> None:
    lo, la = C.day_cells(labels_df, date)
    lab = labels_df[labels_df["date"] == date]["label"].to_numpy(int)
    # Canonical convention: rigidly translate each completed sigma=1.25 PCA
    # ellipse to the raw-Celsius Tmax-weighted centroid (tmax_day REQUIRED).
    SN.render_day_tmax_weighted(ax, lo, la, lab, SN.STUDY_EXTENT,
                                SN.load_tmax_day(date), draw_ellipses=True,
                                show_centroid_numbers=False, title=None)
    Q.date_label(ax, date)


def _grid(nrows, ncols, figsize, top, bottom, hspace=0.10):
    kw = dict(subplot_kw={"projection": SN.PROJ}) if SN.HAVE_CARTOPY else {}
    fig, axes = plt.subplots(nrows, ncols, figsize=figsize, squeeze=False,
                             **kw)
    fig.subplots_adjust(top=top, bottom=bottom, left=0.055, right=0.985,
                        wspace=0.05, hspace=hspace)
    return fig, axes


def _time_label(fig, ax, text: str) -> None:
    b = ax.get_position()
    fig.text((b.x0 + b.x1) / 2.0, b.y1 + 0.012,
             rf"$\mathbf{{{text}}}$", ha="center", va="bottom",
             fontsize=TIME_FS, color="black")


def _row_labels_measured(fig, axes) -> None:
    """(a)/(b) outside-left with a measured >=12 pt gap to the leftmost
    y-axis/tick-label bounding box; one shared x for both rows; vertical
    centering identical to Phase 2C."""
    fig.canvas.draw()
    ren = fig.canvas.get_renderer()
    px_per_pt = fig.dpi / 72.0
    fig_w_px = fig.get_size_inches()[0] * fig.dpi

    # Leftmost extent (spine + tick labels + axis labels) per row, from the
    # left-column axes' tight bounding boxes.
    row_left_px = [axes[i, 0].get_tightbbox(ren).x0 for i in range(2)]
    label_right_px = min(row_left_px) - GAP_PT * px_per_pt
    fx = label_right_px / fig_w_px
    print(f"[FIG6-R2] leftmost axis/tick bbox x0 per row (px): "
          f"{row_left_px[0]:.1f}, {row_left_px[1]:.1f}; shared label "
          f"right-edge x = {label_right_px:.1f} px (fig fraction {fx:.4f})")

    texts = []
    for i, letter in ((0, "(a)"), (1, "(b)")):
        bs = [axes[i, j].get_position() for j in range(2)]
        yc = (min(b.y0 for b in bs) + max(b.y1 for b in bs)) / 2.0
        t = fig.text(fx, yc, letter, ha="right", va="center",
                     **Q.PANEL_LABEL)
        texts.append((i, letter, t))

    fig.canvas.draw()
    for i, letter, t in texts:
        bb = t.get_window_extent(ren)
        gap_pt = (row_left_px[i] - bb.x1) / px_per_pt
        print(f"[FIG6-R2] row {letter}: measured label-to-axis gap = "
              f"{gap_pt:.2f} pt (required >= 12); label x0 = {bb.x0:.1f} px")
        assert gap_pt >= 12.0, f"gap {gap_pt:.2f} pt < 12 pt for {letter}"
        assert bb.x0 >= 0.0, f"label {letter} clipped at the figure edge"
    xs = {round(t.get_position()[0], 12) for _, _, t in texts}
    assert len(xs) == 1, f"row-label x offsets differ: {xs}"
    print("[FIG6-R2] identical row-label x offset confirmed")


def figure6(labels_df) -> None:
    fig, axes = _grid(2, 2, (11.6, 9.4), top=0.865, bottom=0.095)
    days = [["2017-07-17", "2017-07-18"],      # Event 29 (top row)
            ["1991-06-04", "1991-06-05"]]      # Event 3  (bottom row)
    for i in range(2):
        for j in range(2):
            _render(axes[i, j], labels_df, days[i][j])
    Q.type_heading(fig, 0.5, 0.945, 3, fontsize=26)
    _time_label(fig, axes[0, 0], "t")           # once, above the top row
    _time_label(fig, axes[0, 1], "t+1")
    _row_labels_measured(fig, axes)             # R2: measured left placement
    Q.unified_snapshot_legend(fig)

    d = os.path.join(OUT, "fig06")
    os.makedirs(d, exist_ok=True)
    for ext in ("png", "pdf"):
        p = os.path.join(d, f"Figure6_type3_two_events.{ext}")
        fig.savefig(p, dpi=DPI)
        print(f"[SAVED] {p}")
    plt.close(fig)


def main() -> None:
    print(f"[FIG6-R2] heading font = {Q.HEADING_FAMILY}")
    labels_df = C.load_labels_A()
    figure6(labels_df)
    print("[DONE] Figure 6 rebuilt (R2)")


if __name__ == "__main__":
    main()
