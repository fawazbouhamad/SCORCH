#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 2E — Figure C candidate: SCORCH-selected DBSCAN parameters by
event type (slides 19-22 unified into one 2x2 figure).

Published as Fig. C in the appendices since 2026-07-30. The directory name
"figA3" and the output filename are LEGACY INTERNAL names, not the current
publication label.

Data: the deposit's catalogs/scorch_new_algorithm_master_cluster_ellipse_
event_global_max.csv (current global-max catalogue; new_event_id/type used
directly — no stale embedded catalogue).

Populations (verified at run time against the validated main-paper workflow):
  * per event-day (n = 395 big days; type day-counts 3/4/75/313): the
    event-global-max parameter APPLIED to each day of the event
    (event_global_minpts_used / event_global_eps_max broadcast per day) —
    this reproduces the slide-19/21 statistics exactly (per-day means
    9.19 / 3.537), unlike the canonical per-day pre-selection columns;
  * per event (n = 51; type counts 3/4/20/24): one global-max value per
    event (means 8.71 / 3.394) — reproduces slides 20/22.

Layout: (a) min_samples per event-day, (b) min_samples per event,
        (c) eps per event-day,        (d) eps per event.
Equal axes boxes; canonical Type 1-4 palette + neutral gray for "All";
box = Q1-Q3, line = median, diamond = mean, whiskers = min/max (one unified
legend below the figure); canonical (a)-(d) labels; no internal titles
(the long slide headers move to the caption).

Outputs: outputs/appendix/Figure_A3_dbscan_parameters.{png,pdf}
         outputs/appendix/Figure_A3_dbscan_parameter_stats.csv
"""
from __future__ import annotations
# --- SCORCH release bootstrap (auto-inserted; release-relative, no absolute paths) ---
import os as _os, sys as _sys
def _scorch_find_root(_p):
    while _p != _os.path.dirname(_p):
        if _os.path.isdir(_os.path.join(_p, "scripts")) and _os.path.isdir(_os.path.join(_p, "configs")):
            return _p
        _p = _os.path.dirname(_p)
    return _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_SCORCH_ROOT = _os.environ.get("SCORCH_RELEASE_ROOT") or _scorch_find_root(_os.path.dirname(_os.path.abspath(__file__)))
_os.environ["SCORCH_RELEASE_ROOT"] = _SCORCH_ROOT
_sys.path.insert(0, _os.path.join(_SCORCH_ROOT, "scripts", "figures", "common"))
from _clean_paths import GENERATED_DIR as _SCORCH_REPRO  # noqa: E402  central helper; honours SCORCH_OUT_DIR
# --- end SCORCH release bootstrap ---

import os
import sys

os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_CAND = os.path.dirname(_THIS_DIR)
_CLEAN = os.path.dirname(os.path.dirname(_CAND))
sys.path.insert(0, _THIS_DIR)
sys.path.insert(0, os.path.join(_CLEAN, "scripts"))
from _clean_paths import MASTER_CSV  # noqa: E402
import q1_style as Q  # noqa: E402

OUT_DIR = os.path.join(_SCORCH_REPRO, "appendix")
os.makedirs(OUT_DIR, exist_ok=True)

GROUPS = ["All Types", "Type 1", "Type 2", "Type 3", "Type 4"]
COLORS = {"All Types": "#666666",
          "Type 1": "#d7191c", "Type 2": "#f57c00",
          "Type 3": "#d9a300", "Type 4": "#6a3d9a"}
LABEL_FS = 11.5
TICK_FS = 9.5


def group_values(frame, col):
    out = {"All Types": frame[col].to_numpy(float)}
    for t in GROUPS[1:]:
        out[t] = frame.loc[frame["type"] == t, col].to_numpy(float)
    return out


def draw_panel(ax, values, ylabel, pop_note):
    stats, colors = [], []
    for g in GROUPS:
        v = np.sort(values[g])
        stats.append(dict(label=g, med=np.median(v), mean=v.mean(),
                          q1=np.percentile(v, 25), q3=np.percentile(v, 75),
                          whislo=v.min(), whishi=v.max(), fliers=[]))
        colors.append(COLORS[g])
    arts = ax.bxp(stats, showmeans=True, showfliers=False, widths=0.52,
                  meanprops=dict(marker="D", markerfacecolor="white",
                                 markeredgecolor="black", markersize=6),
                  patch_artist=True)
    for box, med, col in zip(arts["boxes"], arts["medians"], colors):
        box.set_facecolor(col)
        box.set_alpha(0.55)
        box.set_edgecolor(col)
        med.set_color(col)
        med.set_linewidth(2.6)
    for i, (w1, w2, c1, c2) in enumerate(zip(arts["whiskers"][::2],
                                             arts["whiskers"][1::2],
                                             arts["caps"][::2],
                                             arts["caps"][1::2])):
        for a in (w1, w2, c1, c2):
            a.set_color(colors[i])
            a.set_linewidth(1.2)
    # Phase 2E-R1 (author decision): all per-category sample-size labels
    # (n=395/51/3/4/20/24/75/313) and the upper-left population summaries
    # ("395 event-days" / "51 events") are REMOVED from the figure. The
    # sample sizes are preserved in Figure_A3_dbscan_parameter_stats.csv and
    # in the caption-source note printed at run time, so the caption can
    # state them once, concisely. `pop_note` is intentionally not drawn.
    del pop_note
    ax.set_ylabel(ylabel, fontsize=LABEL_FS)
    ax.grid(True, axis="y", alpha=0.22, linewidth=0.45)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="both", labelsize=TICK_FS, length=3)


def main() -> None:
    plt.rcParams.update({"font.family": "Arial", "pdf.fonttype": 42,
                         "ps.fonttype": 42})
    df = pd.read_csv(MASTER_CSV)
    days = df.drop_duplicates(["new_event_id", "date"])
    events = df.drop_duplicates(["new_event_id"])

    # Global-max runtime checks against the validated main-paper workflow.
    ev_counts = events.groupby("type").size().to_dict()
    assert ev_counts == {"Type 1": 3, "Type 2": 4, "Type 3": 20,
                         "Type 4": 24}, ev_counts
    day_counts = days.groupby("type").size().to_dict()
    assert day_counts == {"Type 1": 3, "Type 2": 4, "Type 3": 75,
                          "Type 4": 313}, day_counts
    assert len(events) == 51 and len(days) == 395
    print(f"[FIGA3] global-max verified: events {ev_counts}, "
          f"event-days {day_counts}")

    # Column choice follows the found source script
    # the research repository's task1_selected_dbscan_boxplots_global_max.py:
    # per-day = dbscan_avg_eps / dbscan_rounded_minpts (lines 58-59),
    # per-event = event_global_eps_max / event_global_minpts_used (74-75).
    panels = {
        "a": (group_values(days, "dbscan_rounded_minpts"),
              "Selected DBSCAN min_samples", "395 event-days"),
        "b": (group_values(events, "event_global_minpts_used"),
              "Selected DBSCAN min_samples", "51 events"),
        "c": (group_values(days, "dbscan_avg_eps"),
              "Selected DBSCAN eps (grid-cell units)", "395 event-days"),
        "d": (group_values(events, "event_global_eps_max"),
              "Selected DBSCAN eps (grid-cell units)", "51 events"),
    }

    # Stats CSV (derived data for the provenance record).
    rows = []
    for letter, (vals, ylabel, note) in panels.items():
        for g in GROUPS:
            v = vals[g]
            rows.append(dict(panel=letter, metric=ylabel, population=note,
                             group=g, n=len(v), mean=v.mean(),
                             median=float(np.median(v)), min=v.min(),
                             max=v.max(), q1=np.percentile(v, 25),
                             q3=np.percentile(v, 75)))
    stats_csv = os.path.join(OUT_DIR, "Figure_A3_dbscan_parameter_stats.csv")
    pd.DataFrame(rows).to_csv(stats_csv, index=False)
    print(f"[SAVED] {stats_csv}")
    print("[FIGA3-CAPTION-SOURCE] Panels (a)/(c): 395 event-days "
          "(Type 1 n=3, Type 2 n=4, Type 3 n=75, Type 4 n=313); panels "
          "(b)/(d): 51 events (Type 1 n=3, Type 2 n=4, Type 3 n=20, "
          "Type 4 n=24). State once in the Fig. C caption.")

    fig = plt.figure(figsize=(12.6, 8.6))
    AX_W, AX_H = 0.40, 0.345
    X0 = {0: 0.075, 1: 0.575}
    Y0 = {0: 0.585, 1: 0.145}
    axes = {}
    for letter, (r, c) in (("a", (0, 0)), ("b", (0, 1)),
                           ("c", (1, 0)), ("d", (1, 1))):
        ax = fig.add_axes([X0[c], Y0[r], AX_W, AX_H])
        vals, ylabel, note = panels[letter]
        draw_panel(ax, vals, ylabel, note)
        axes[letter] = ax
    fig.canvas.draw()
    for letter, ax in axes.items():
        Q.label_above(fig, ax, f"({letter})")

    handles = [Line2D([0], [0], color="0.2", lw=2.6, label="median"),
               Line2D([0], [0], marker="D", color="w",
                      markerfacecolor="white", markeredgecolor="black",
                      markersize=6, label="mean"),
               Line2D([0], [0], color="0.2", lw=1.2,
                      label="whiskers = min / max")]
    fig.legend(handles=handles, loc="lower center",
               bbox_to_anchor=(0.5, 0.015), ncol=3, frameon=False,
               fontsize=10.5, handlelength=2.2, columnspacing=1.8)

    for ext in ("png", "pdf"):
        p = os.path.join(OUT_DIR, f"Figure_A3_dbscan_parameters.{ext}")
        fig.savefig(p, dpi=600)
        print(f"[SAVED] {p}")
    plt.close(fig)


if __name__ == "__main__":
    main()
