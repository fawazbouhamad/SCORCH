#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SUPERSEDED internal diagnostic: DBSCAN parameter-selection heatmap
examples (Event 7). The canonical, deployed Figure B is the Event-10
figure produced by make_new_figA2_event10_candidate.py in this directory;
this script is retained only as a documented internal diagnostic.

IDENTIFICATION (verified at run time): the slide's three grids are the
parameter-selection matrices for the three consecutive days of
new_event_id 7 (CURRENT global-max type: Type 4), 2000-07-07 / 08 / 09.
Each cell holds the number of ellipse clusters obtained at that
(eps, min_samples) combination; the shaded cells are the stable
selected-parameter region, whose means are the day's selected parameters
(min_samples 8.25 / 9.14 / 9.22; eps 3.175 / 3.159 / 3.333 — exactly the
slide's marginal-boxplot means).

Source machinery: the research repository's parameter-heatmap scripts; the
frozen derived matrices ship with this release at
scripts/figures/figA2_inputs/ (env SCORCH_FIGA2_INPUTS).
This script re-renders those unchanged matrices as ONE 1x3 figure with
equal aligned panels, canonical (a)-(c) labels, the selected region and all
cell values preserved, and the selection means annotated per panel (the
slide's marginal boxplots are summarized by these means; distributions are
in the derived CSVs).

Outputs: outputs/appendix/Figure_A2_dbscan_selection_heatmaps.{png,pdf}
         outputs/appendix/Figure_A2_selected_cells_stats.csv
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("MPLBACKEND", "Agg")
sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_FIGS = os.path.dirname(_THIS_DIR)                       # scripts/figures
_ROOT = os.path.dirname(os.path.dirname(_FIGS))          # release root
sys.path.insert(0, os.path.join(_FIGS, "common"))
import q1_style as Q  # noqa: E402
from _clean_paths import MASTER_CSV  # noqa: E402

# Fig B inputs: the frozen event-7 parameter-selection matrices ship with
# the release under scripts/figures/figA2_inputs/ (env-overridable).
SRC_DIR = os.environ.get("SCORCH_FIGA2_INPUTS",
                         os.path.join(_FIGS, "figA2_inputs"))
OUT_DIR = os.path.join(os.environ.get(
    "SCORCH_OUT_DIR", os.path.join(_ROOT, "reproduced")), "appendix")
os.makedirs(OUT_DIR, exist_ok=True)

DAYS = ["2000-07-07", "2000-07-08", "2000-07-09"]
EVENT_ID = 7
HL_FACE = "#bcd9ec"
HL_EDGE = "#2a6ea6"
EXPECTED_MEANS = {"2000-07-07": (8.25, 3.175),
                  "2000-07-08": (9.136, 3.159),
                  "2000-07-09": (9.222, 3.333)}


def verify_event() -> None:
    df = pd.read_csv(MASTER_CSV)
    e = df[df["date"].isin(DAYS)]
    assert set(e["new_event_id"]) == {EVENT_ID}
    assert set(e["type"]) == {"Type 4"}, set(e["type"])
    print(f"[FIGA2] global-max verified: event {EVENT_ID}, CURRENT type "
          f"'Type 4', days {sorted(set(e['date']))}, ellipses/day "
          f"{e.groupby('date').size().to_dict()}")


def draw_panel(ax, mat, hl, date, show_ylabel):
    ms = [int(s[2:]) for s in mat.index]          # ms4..ms12 -> 4..12
    eps = [float(c[3:]) for c in mat.columns]     # eps1.0.. -> 1.0..
    vals = mat.to_numpy(float)
    n_r, n_c = vals.shape
    hl_set = {(int(r.min_samples), float(r.eps)) for r in hl.itertuples()}
    for i in range(n_r):
        for j in range(n_c):
            is_hl = (ms[i], eps[j]) in hl_set
            if is_hl:
                ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1,
                                           facecolor=HL_FACE,
                                           edgecolor=HL_EDGE, linewidth=1.4,
                                           zorder=2))
            ax.text(j, i, f"{vals[i, j]:.0f}", ha="center", va="center",
                    fontsize=8.5, zorder=3,
                    fontweight="bold" if is_hl else "normal",
                    color="black")
    ax.set_xlim(-0.5, n_c - 0.5)
    ax.set_ylim(-0.5, n_r - 0.5)
    ax.set_xticks(range(n_c), [f"{e:g}" for e in eps], fontsize=9)
    ax.set_yticks(range(n_r), [str(m) for m in ms], fontsize=9)
    ax.set_xlabel("eps (grid-cell units)", fontsize=11)
    if show_ylabel:
        ax.set_ylabel("min_samples", fontsize=11)
    ax.set_xticks(np.arange(-0.5, n_c, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, n_r, 1), minor=True)
    ax.grid(which="minor", color="0.85", linewidth=0.5)
    ax.tick_params(which="minor", length=0)
    for s in ax.spines.values():
        s.set_linewidth(0.8)
    mean_ms = hl["min_samples"].mean()
    mean_eps = hl["eps"].mean()
    # Phase 2E-R2 (author decision): the upper-left information box (date +
    # selected parameter means) is REMOVED from the visible figure. Its
    # exact text is preserved verbatim, with the verified context, in
    # docs/FIGURE_A2_CAPTION_SOURCE_NOTE.md for concise use in the caption.
    # Panels, letters, axes, cells, highlights, labels, ticks, margins,
    # spacing and values are untouched.
    return mean_ms, mean_eps


def main() -> None:
    plt.rcParams.update({"font.family": "Arial", "pdf.fonttype": 42,
                         "ps.fonttype": 42})
    verify_event()

    fig = plt.figure(figsize=(14.4, 5.2))
    AX_W, AX_H = 0.263, 0.70
    X0 = [0.055, 0.385, 0.715]
    rows = []
    axes = {}
    for k, d in enumerate(DAYS):
        tag = f"event{EVENT_ID:02d}_type4_{d}"
        mat = pd.read_csv(os.path.join(SRC_DIR, f"matrix_{tag}.csv"),
                          index_col=0)
        hl = pd.read_csv(os.path.join(SRC_DIR,
                                      f"highlighted_cells_{tag}.csv"))
        assert mat.shape == (9, 7), mat.shape
        ax = fig.add_axes([X0[k], 0.13, AX_W, AX_H])
        mean_ms, mean_eps = draw_panel(ax, mat, hl, d, show_ylabel=(k == 0))
        exp_ms, exp_eps = EXPECTED_MEANS[d]
        assert abs(mean_ms - exp_ms) < 0.01 and abs(mean_eps - exp_eps) < 0.01
        rows.append(dict(date=d, event_id=EVENT_ID, current_type="Type 4",
                         n_selected_cells=len(hl),
                         mean_min_samples=mean_ms, mean_eps=mean_eps))
        axes[chr(ord("a") + k)] = ax
        print(f"[FIGA2] {d}: {len(hl)} selected cells; means "
              f"{mean_ms:.3f}/{mean_eps:.3f} (match slide)")
    fig.canvas.draw()
    for letter, ax in axes.items():
        Q.label_above(fig, ax, f"({letter})")

    stats_csv = os.path.join(OUT_DIR, "Figure_A2_selected_cells_stats.csv")
    pd.DataFrame(rows).to_csv(stats_csv, index=False)
    print(f"[SAVED] {stats_csv}")
    for ext in ("png", "pdf"):
        p = os.path.join(OUT_DIR,
                         f"Figure_A2_dbscan_selection_heatmaps.{ext}")
        fig.savefig(p, dpi=600)
        print(f"[SAVED] {p}")
    plt.close(fig)


if __name__ == "__main__":
    main()
