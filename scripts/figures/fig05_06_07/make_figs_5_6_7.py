#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 2C — rebuild paper Figures 5, 6, 7 from the validated snapshot data.

Uses the SAME validated renderer (clean/scripts/six_task_review/snapshots.py
render_day: cells, sigma=1.25 PCA ellipses, centroids, fixed study-domain
extent) and the same events/dates as slides 6-8. Presentation per the
author's Phase 2C instructions:

  * equal map frames (identical subplot cells + one shared STUDY_EXTENT);
  * date inside the bottom-right of every snapshot (black, bold, one inset);
  * NO per-snapshot legend — ONE unified horizontal L1/L2/Centroid legend
    centered below each complete figure (q1_style.unified_snapshot_legend);
  * typology headings in the exact slide-5 style (Abadi bold, slide colors);
  * Figure 5: Type 1 (Event 12, 2002-07-31) left, Type 2 (Event 1,
    1983-07-13) right; headings centered above each snapshot; NO (a)/(b);
  * Figure 6: 2x2 — top row Event 29 (2017-07-17/18), bottom row Event 3
    (1991-06-04/05); one "Type 3" heading centered above the figure;
    column headings t / t+1 once above the top row; canonical (a)/(b) row
    labels outside-left, vertically centered per row;
  * Figure 7: 2x3 — Event 10 (2001-08-07..12); one "Type 4" heading;
    t..t+5 centered above each snapshot; no panel letters.

Outputs (PNG dpi=600 + PDF): <phase2c>/outputs/fig05, fig06, fig07.
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

import numpy as np                     # noqa: E402
import matplotlib.pyplot as plt        # noqa: E402
import common as C                     # noqa: E402
import snapshots as SN                 # noqa: E402
import q1_style as Q                   # noqa: E402

OUT = os.environ.get("SCORCH_OUT_DIR",
                     os.path.join(_ROOT, "reproduced"))
DPI = 600
TIME_FS = 15                           # t / t+1 ... labels (bold math style)


def _render(ax, labels_df, date: str) -> None:
    lo, la = C.day_cells(labels_df, date)
    lab = labels_df[labels_df["date"] == date]["label"].to_numpy(int)
    SN.render_day(ax, lo, la, lab, SN.STUDY_EXTENT, draw_ellipses=True,
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


def _save(fig, sub, stem) -> None:
    d = os.path.join(OUT, sub)
    os.makedirs(d, exist_ok=True)
    for ext in ("png", "pdf"):
        p = os.path.join(d, f"{stem}.{ext}")
        fig.savefig(p, dpi=DPI)
        print(f"[SAVED] {p}")
    plt.close(fig)


def figure5(labels_df) -> None:
    fig, axes = _grid(1, 2, (12.4, 5.4), top=0.86, bottom=0.14)
    _render(axes[0, 0], labels_df, "2002-07-31")   # Event 12, Type 1
    _render(axes[0, 1], labels_df, "1983-07-13")   # Event 1,  Type 2
    for j, tn in ((0, 1), (1, 2)):
        b = axes[0, j].get_position()
        Q.type_heading(fig, (b.x0 + b.x1) / 2.0, 0.93, tn, fontsize=24)
    Q.unified_snapshot_legend(fig)
    _save(fig, "fig05", "Figure5_type1_type2")


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
    Q.label_left(fig, list(axes[0, :]), "(a)")
    Q.label_left(fig, list(axes[1, :]), "(b)")
    Q.unified_snapshot_legend(fig)
    _save(fig, "fig06", "Figure6_type3_two_events")


def figure7(labels_df) -> None:
    fig, axes = _grid(2, 3, (15.6, 8.9), top=0.855, bottom=0.095,
                      hspace=0.34)   # room for the t+3..t+5 labels row
    days = ["2001-08-07", "2001-08-08", "2001-08-09",
            "2001-08-10", "2001-08-11", "2001-08-12"]   # Event 10
    flat = list(axes.reshape(-1))
    for k, (ax, d) in enumerate(zip(flat, days)):
        _render(ax, labels_df, d)
        _time_label(fig, ax, "t" if k == 0 else f"t+{k}")
    Q.type_heading(fig, 0.5, 0.945, 4, fontsize=26)
    Q.unified_snapshot_legend(fig)
    _save(fig, "fig07", "Figure7_type4_six_days")


def main() -> None:
    print(f"[FIGS5-7] heading font = {Q.HEADING_FAMILY}")
    labels_df = C.load_labels_A()
    figure5(labels_df)
    figure6(labels_df)
    figure7(labels_df)
    print("[DONE] Figures 5-7 rebuilt")


if __name__ == "__main__":
    main()
