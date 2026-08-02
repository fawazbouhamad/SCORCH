#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 2E — Figure S.1 candidate: representative Type 3 event snapshot
(slide 24 rebuilt from the validated renderer and current global-max data).

Classification audit (verified at run time): the slide-24 event
(2016-06-07 / 2016-06-08, South Egypt + SE domain) is new_event_id 25 in
the current global-max master; its CURRENT type is Type 3 (two ellipses on
each of two consecutive days — mechanically consistent multi-day). The
slide heading's "Back-to-Back" is obsolete pre-reclassification
nomenclature and is NOT retained; the candidate uses the canonical
"Type 3" heading in the approved slide-5 style/color.

Presentation follows the approved main-paper Figures 5-7 conventions:
equal frames (identical subplot cells + one shared STUDY_EXTENT), t / t+1
column headings, dates inside the bottom-right of each snapshot, ONE
unified L1/L2/Centroid legend below, no per-snapshot legends, no slide
heading (the event/region description moves to the caption).

Outputs: outputs/supplementary/Figure_S1_type3_event25.{png,pdf}
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

import pandas as pd                    # noqa: E402
import matplotlib.pyplot as plt        # noqa: E402
import common as C                     # noqa: E402
import snapshots as SN                 # noqa: E402
import q1_style as Q                   # noqa: E402
from _clean_paths import MASTER_CSV    # noqa: E402

OUT_DIR = os.path.join(os.environ.get(
    "SCORCH_OUT_DIR", os.path.join(_ROOT, "reproduced")), "supplement")
os.makedirs(OUT_DIR, exist_ok=True)
DPI = 600
TIME_FS = 15
DAYS = ["2016-06-07", "2016-06-08"]
EVENT_ID = 25


def verify_event() -> None:
    df = pd.read_csv(MASTER_CSV)
    e = df[df["date"].isin(DAYS)]
    ids = set(e["new_event_id"])
    types = set(e["type"])
    per_day = e.groupby("date").size().to_dict()
    assert ids == {EVENT_ID}, ids
    assert types == {"Type 3"}, types
    dates = sorted(set(e["date"]))
    assert dates == DAYS, dates
    print(f"[FIGS1] global-max verified: event {EVENT_ID}, CURRENT type "
          f"'Type 3', dates {dates}, ellipses/day {per_day} "
          f"(legacy label 'Back-to-Back' NOT retained)")


def _render(ax, labels_df, date: str) -> None:
    lo, la = C.day_cells(labels_df, date)
    lab = labels_df[labels_df["date"] == date]["label"].to_numpy(int)
    SN.render_day(ax, lo, la, lab, SN.STUDY_EXTENT, draw_ellipses=True,
                  show_centroid_numbers=False, title=None)
    Q.date_label(ax, date)


def _time_label(fig, ax, text: str) -> None:
    b = ax.get_position()
    fig.text((b.x0 + b.x1) / 2.0, b.y1 + 0.012,
             rf"$\mathbf{{{text}}}$", ha="center", va="bottom",
             fontsize=TIME_FS, color="black")


def main() -> None:
    print(f"[FIGS1] heading font = {Q.HEADING_FAMILY}")
    verify_event()
    labels_df = C.load_labels_A()

    kw = dict(subplot_kw={"projection": SN.PROJ}) if SN.HAVE_CARTOPY else {}
    fig, axes = plt.subplots(1, 2, figsize=(12.4, 5.4), squeeze=False, **kw)
    fig.subplots_adjust(top=0.80, bottom=0.14, left=0.055, right=0.985,
                        wspace=0.05)
    for j, d in enumerate(DAYS):
        _render(axes[0, j], labels_df, d)
    Q.type_heading(fig, 0.5, 0.93, 3, fontsize=24)
    _time_label(fig, axes[0, 0], "t")
    _time_label(fig, axes[0, 1], "t+1")
    Q.unified_snapshot_legend(fig)

    for ext in ("png", "pdf"):
        p = os.path.join(OUT_DIR, f"Figure_S1_type3_event25.{ext}")
        fig.savefig(p, dpi=DPI)
        print(f"[SAVED] {p}")
    plt.close(fig)


if __name__ == "__main__":
    main()
