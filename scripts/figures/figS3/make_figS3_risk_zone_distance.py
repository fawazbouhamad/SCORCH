#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""INTERNAL COMPONENT producer (legacy internal name "Figure S.3"):
out-of-sample centroid distance to the high-concentration zone (rebuilt from
the validated CV output table).

This is NOT a manuscript figure and "S.3" is NOT a publication label. Its
output is panel (a) of the published **Fig. D** (Appendix D). The file name,
directory name ("figS3") and output name are retained for provenance
continuity only.

Source script: scripts/validation/kfold_cv_risk_zone_validation.py (legacy
"risk" file name; see docs/TERMINOLOGY.md). 5-fold CV over the 760
global-max centroids; per-centroid distances to the top-10/20/30/50%
predicted-concentration zones. This script re-renders the UNCHANGED
validated per-centroid table, the deposit's
validation_kfold/per_centroid_risk_zone_validation.csv, in canonical style:
neutral boxes (the population is all held-out centroids, not event types),
box = Q1-Q3, line = median, diamond = mean (annotated in km), whiskers =
min/max; slide title removed (caption carries it).

Runtime checks: n = 760 centroids, 5 folds; mean distances match the slide
(438 / 286 / 181 / 81 km).

Outputs: outputs/supplementary/Figure_S3_risk_zone_distance.{png,pdf}
         outputs/supplementary/Figure_S3_risk_zone_distance_stats.csv
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
from _clean_paths import data_file  # noqa: E402

IN_CSV = data_file("per_centroid_risk_zone_validation.csv", "validation_kfold")
OUT_DIR = os.path.join(os.environ.get(
    "SCORCH_OUT_DIR", os.path.join(_ROOT, "reproduced")), "supplement")
os.makedirs(OUT_DIR, exist_ok=True)

ZONES = [("Top 10%", "dist_to_top10_km", 438),
         ("Top 20%", "dist_to_top20_km", 286),
         ("Top 30%", "dist_to_top30_km", 181),
         ("Top 50%", "dist_to_top50_km", 81)]


def main() -> None:
    plt.rcParams.update({"font.family": "Arial", "pdf.fonttype": 42,
                         "ps.fonttype": 42})
    d = pd.read_csv(IN_CSV)
    assert len(d) == 760, len(d)
    assert d["fold"].nunique() == 5
    print(f"[FIGS3] {len(d)} held-out centroids over "
          f"{d['fold'].nunique()} folds")

    fig, ax = plt.subplots(figsize=(8.6, 5.6))
    stats, rows = [], []
    for label, col, slide_mean in ZONES:
        v = d[col].to_numpy(float)
        m = v.mean()
        assert abs(m - slide_mean) < 1.0, (label, m, slide_mean)
        stats.append(dict(label=label, med=np.median(v), mean=m,
                          q1=np.percentile(v, 25), q3=np.percentile(v, 75),
                          whislo=v.min(), whishi=v.max(), fliers=[]))
        rows.append(dict(zone=label, n=len(v), mean_km=m,
                         median_km=float(np.median(v)), min_km=v.min(),
                         max_km=v.max(), q1_km=np.percentile(v, 25),
                         q3_km=np.percentile(v, 75)))
        print(f"[FIGS3] {label}: mean {m:.0f} km (slide {slide_mean})")
    arts = ax.bxp(stats, showmeans=True, showfliers=False, widths=0.5,
                  meanprops=dict(marker="D", markerfacecolor="white",
                                 markeredgecolor="black", markersize=6),
                  patch_artist=True)
    for box, med in zip(arts["boxes"], arts["medians"]):
        box.set_facecolor("0.88")
        box.set_edgecolor("0.25")
        med.set_color("0.15")
        med.set_linewidth(2.2)
    for a in arts["whiskers"] + arts["caps"]:
        a.set_color("0.25")
        a.set_linewidth(1.1)
    for i, r in enumerate(rows, start=1):
        ax.annotate(f"mean {r['mean_km']:.0f} km",
                    xy=(i + 0.06, r["mean_km"]), xytext=(i + 0.13,
                                                         r["mean_km"]),
                    fontsize=9.5, color="0.2", va="center")
    ax.set_ylabel("Distance to nearest top-concentration zone (km)",
                  fontsize=11.5)
    ax.tick_params(axis="both", labelsize=10)
    ax.grid(True, axis="y", alpha=0.22, linewidth=0.45)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()

    pd.DataFrame(rows).to_csv(
        os.path.join(OUT_DIR, "Figure_S3_risk_zone_distance_stats.csv"),
        index=False)
    for ext in ("png", "pdf"):
        p = os.path.join(OUT_DIR, f"Figure_S3_risk_zone_distance.{ext}")
        fig.savefig(p, dpi=600)
        print(f"[SAVED] {p}")
    plt.close(fig)


if __name__ == "__main__":
    main()
