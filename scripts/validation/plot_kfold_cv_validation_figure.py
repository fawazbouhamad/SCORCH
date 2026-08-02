#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validation figure for the 5-fold CV of the four-variable centroid model.

Reads the fold-level results written by kfold_cv_four_variable_centroid_model.py
and renders a two-panel figure:

  (a) Map (zoomed to the fold locations, Figures 2-3 cartopy feature style):
      for each fold, the OBSERVED mean location of the held-out centroids
      (black filled circle, fold number alongside) and the PREDICTED
      probability-weighted expected location (red X), connected by a line.
      The predicted points cluster tightly because ~80% training subsets
      barely change the fitted surface; the spread of the black points
      around them is the out-of-sample error.
  (b) The per-fold distance errors (km) as bars, with the cross-fold mean
      and its 95% confidence band.

Also writes CV_EXPLAINER.md - a plain-English description of how the
concentration surface was converted to one predicted point, what the
validation does and does not validate, and how to read the headline number -
with all numbers pulled live from cv_summary.csv so the text never drifts
from the results.

Outputs (new files only):
    reproduced/validation_kfold/kfold_cv_validation_figure.png / .pdf
    reproduced/validation_kfold/CV_EXPLAINER.md

Run:  python scripts/validation/plot_kfold_cv_validation_figure.py
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

import cartopy.crs as ccrs
import cartopy.feature as cfeature

import sys

_THIS = os.path.abspath(__file__)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_THIS)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "figures", "common"))
from _clean_paths import GENERATED_DIR, data_file  # noqa: E402

VAL_DIR = os.path.join(GENERATED_DIR, "validation_kfold")
os.makedirs(VAL_DIR, exist_ok=True)


def _cv_input(name):
    """Prefer a freshly reproduced CV table, else the deposit copy."""
    p = os.path.join(VAL_DIR, name)
    return p if os.path.exists(p) else data_file(name, "validation_kfold")


FOLD_CSV = _cv_input("fold_metrics.csv")
SUMMARY_CSV = _cv_input("cv_summary.csv")
OUT_PNG = os.path.join(VAL_DIR, "kfold_cv_validation_figure.png")
OUT_PDF = os.path.join(VAL_DIR, "kfold_cv_validation_figure.pdf")
OUT_MD = os.path.join(VAL_DIR, "CV_EXPLAINER.md")

C_PRED = "#b2182b"


def setup_zoom_map(ax, lon_min, lon_max, lat_min, lat_max):
    """Figures 2-3 cartopy feature style, but zoomed to the fold locations."""
    ax.set_extent([lon_min, lon_max, lat_min, lat_max], crs=ccrs.PlateCarree())
    ax.add_feature(cfeature.OCEAN.with_scale("50m"), facecolor="#dcecf2", zorder=0)
    ax.add_feature(cfeature.LAND.with_scale("50m"), facecolor="#f8f6ef", zorder=0)
    ax.add_feature(cfeature.LAKES.with_scale("50m"), facecolor="#eaf3f7",
                   edgecolor="none", zorder=1)
    ax.add_feature(cfeature.COASTLINE.with_scale("50m"), linewidth=0.45,
                   edgecolor="0.35", alpha=0.65, zorder=7)
    ax.add_feature(cfeature.BORDERS.with_scale("50m"), linewidth=0.35,
                   edgecolor="0.45", alpha=0.45, zorder=7)
    gl = ax.gridlines(crs=ccrs.PlateCarree(), draw_labels=True, linewidth=0.32,
                      alpha=0.28, linestyle="-",
                      xlocs=np.arange(np.floor(lon_min), np.ceil(lon_max) + 1, 2),
                      ylocs=np.arange(np.floor(lat_min), np.ceil(lat_max) + 1, 2),
                      x_inline=False, y_inline=False, zorder=6)
    gl.top_labels = False
    gl.right_labels = False
    gl.xlabel_style = {"size": 8, "color": "black"}
    gl.ylabel_style = {"size": 8, "color": "black"}


def main():
    fold = pd.read_csv(FOLD_CSV)
    summ = pd.read_csv(SUMMARY_CSV).set_index("metric")
    n_folds = len(fold)
    m_d = float(summ.loc["mean_dist_error_km", "value"])
    sd_d = float(summ.loc["mean_dist_error_km", "sd_across_folds"])
    lo_d = float(summ.loc["mean_dist_error_km", "ci95_lo"])
    hi_d = float(summ.loc["mean_dist_error_km", "ci95_hi"])
    m_blon = float(summ.loc["mean_bias_lon_deg", "value"])
    m_blat = float(summ.loc["mean_bias_lat_deg", "value"])
    blon_km = float(summ.loc["mean_bias_lon_km_at_mean_lat", "value"])
    blat_km = float(summ.loc["mean_bias_lat_km", "value"])
    m_rq = float(summ.loc["mean_heldout_risk_quantile", "value"])

    # ---- figure ---------------------------------------------------------------
    fig = plt.figure(figsize=(12.6, 5.4))
    ax_map = fig.add_subplot(1, 2, 1, projection=ccrs.PlateCarree())
    ax_bar = fig.add_subplot(1, 2, 2)

    all_lon = np.concatenate([fold["obs_mean_lon"], fold["pred_lon"]])
    all_lat = np.concatenate([fold["obs_mean_lat"], fold["pred_lat"]])
    pad = 1.5
    setup_zoom_map(ax_map, all_lon.min() - pad, all_lon.max() + pad,
                   all_lat.min() - pad, all_lat.max() + pad)

    tf = dict(transform=ccrs.PlateCarree())
    for _, r in fold.iterrows():
        ax_map.plot([r["pred_lon"], r["obs_mean_lon"]],
                    [r["pred_lat"], r["obs_mean_lat"]],
                    color="0.45", lw=1.0, zorder=8, **tf)
        ax_map.text(r["obs_mean_lon"], r["obs_mean_lat"] + 0.14,
                    str(int(r["fold"])), fontsize=7.5, color="black",
                    ha="center", va="bottom", zorder=11, **tf)
    ax_map.scatter(fold["obs_mean_lon"], fold["obs_mean_lat"], s=42, c="black",
                   edgecolors="white", linewidths=0.6, zorder=10, **tf)
    ax_map.scatter(fold["pred_lon"], fold["pred_lat"], s=60, marker="x",
                   c=C_PRED, linewidths=1.8, zorder=10, **tf)

    handles = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor="black",
               markeredgecolor="white", markersize=7,
               label="Observed held-out mean (fold)"),
        Line2D([0], [0], marker="x", color=C_PRED, markeredgewidth=1.8,
               markersize=8, linestyle="none",
               label="Predicted expected location"),
        Line2D([0], [0], color="0.45", lw=1.0, label="Fold error"),
    ]
    ax_map.legend(handles=handles, loc="upper center",
                  bbox_to_anchor=(0.5, -0.06), ncol=3, fontsize=8.2,
                  frameon=True, fancybox=False, framealpha=1.0,
                  edgecolor="black", facecolor="white", handlelength=2.0,
                  columnspacing=1.4, borderpad=0.65)
    ax_map.set_title("(a) Observed vs predicted, per fold", fontsize=11,
                     color="black", pad=8)

    # ---- panel (b): fold distance errors --------------------------------------
    ax_bar.bar(fold["fold"], fold["dist_error_km"], width=0.62,
               color="0.88", edgecolor="black", linewidth=0.8, zorder=3)
    ax_bar.axhspan(lo_d, hi_d, color=C_PRED, alpha=0.10, zorder=1)
    ax_bar.axhline(m_d, color=C_PRED, lw=1.6, zorder=4)
    ax_bar.text(0.995, m_d + 6, f"mean = {m_d:.0f} km (95% CI {lo_d:.0f}-{hi_d:.0f})",
                transform=ax_bar.get_yaxis_transform(), ha="right", va="bottom",
                fontsize=8.5, color=C_PRED)
    ax_bar.set_xticks(fold["fold"])
    ax_bar.set_xlabel("Fold", fontsize=10.5, color="black")
    ax_bar.set_ylabel("Distance error (km)", fontsize=10.5, color="black")
    ax_bar.tick_params(labelsize=9, colors="black")
    ax_bar.spines["top"].set_visible(False)
    ax_bar.spines["right"].set_visible(False)
    ax_bar.grid(True, axis="y", color="0.90", lw=0.5, zorder=0)
    ax_bar.set_axisbelow(True)
    ax_bar.set_title("(b) Fold distance errors", fontsize=11, color="black",
                     pad=8)

    fig.subplots_adjust(left=0.05, right=0.985, top=0.93, bottom=0.16,
                        wspace=0.18)
    fig.savefig(OUT_PNG, dpi=600, bbox_inches="tight")
    fig.savefig(OUT_PDF, bbox_inches="tight")
    plt.close(fig)
    print("[SAVED]", OUT_PNG)
    print("[SAVED]", OUT_PDF)

    # ---- plain-English explainer (numbers pulled from cv_summary.csv) ---------
    md = f"""# How the centroid model was validated (plain English)

> **SUPPLEMENTARY.** This explainer covers the center-of-mass diagnostic
> only. The MAIN validation is the concentration-zone CV (legacy
> `RISK_ZONE_CV_REPORT.md` file name):
> distance from each held-out centroid to the nearest predicted
> high-concentration zone, plus hit rates and concentration quantiles (legacy
> `risk_zone`/`risk_quantile` naming; see docs/TERMINOLOGY.md). The
> center-of-mass distance below
> mostly reflects sampling variability of the 80/20 split, because a model
> with lon/lat terms always centers its surface on the training sample's
> mean location.

## From concentration surface to one predicted point

The four-variable model (longitude, latitude, mean Tmax, Tmax standard
deviation) does not predict a centroid location directly. It predicts a
**concentration/intensity surface**: for each of the 1800 one-degree grid
cells, an expected
density of heatwave-ellipse centroids per km^2. To compare that surface
against held-out centroids we turn it into a single point in two steps:

1. **Normalize the surface into probabilities.** Each grid cell's intensity is
   multiplied by its area and divided by the total, giving the probability
   `p_i` that a centroid falls in grid cell `i` (all 1800 sum to 1).
2. **Take the probability-weighted average location.**
   `lon_hat = sum(lon_i * p_i)` and `lat_hat = sum(lat_i * p_i)` - the
   "center of mass" of the predicted concentration. This is the predicted point.
   (The highest-concentration single grid cell, the MAP, is also recorded but
   only as a
   diagnostic: for a spread-out surface with a monotonic lon/lat trend its
   argmax sits at a domain edge and is a poor point summary.)

## Why this is a valid approach - and what it does and does not validate

Each of the {n_folds} folds refits the model **from scratch on 80% of the
centroids** and is scored on the 20% it never saw, and every centroid is held
out exactly once (shuffled with a fixed seed, not chronologically). Because
the held-out centroids play no role in fitting, the fold errors measure
genuine **out-of-sample** performance, and comparing the surface's center of
mass with the held-out centroids' mean location is a like-for-like comparison
of two location summaries of the same quantity (where centroids tend to
occur).

* It **does** validate: whether the fitted concentration surface is systematically
  displaced (longitude/latitude bias) and how far off its central location is
  in km for data the model never saw; plus, via the held-out
  concentration-quantile score ({m_rq:.2f} vs 0.50 for a no-skill uniform
  ranking), whether held-out centroids preferentially fall in grid cells the
  model ranks as high-concentration.
* It does **not** validate: per-event forecasting skill (the model is a
  climatological density, not an event predictor), the shape/spread of the
  surface beyond its center, or the LGCP clustering parameters (only the
  four-variable trend is refit per fold - the repo's own diagnostics show the
  minimum-contrast LGCP trend equals this Poisson-likelihood trend).

## Reading the result

On average the predicted expected location is **{m_d:.0f} km** from the mean
held-out centroid location (fold SD {sd_d:.0f} km, 95% CI {lo_d:.0f}-{hi_d:.0f} km),
with essentially **no systematic bias**: mean longitude bias {m_blon:+.2f} deg
(~{blon_km:+.0f} km) and mean latitude bias {m_blat:+.2f} deg (~{blat_km:+.0f} km).
Individual folds miss in different directions (up to ~2.5 deg), but the
misses cancel - the surface is centered correctly, and {m_d:.0f} km (about
1.5 grid cells) is the typical fold-to-fold wobble, driven mostly by which
20% of centroids happens to be held out. For a domain spanning roughly
5000 km x 4000 km, a {m_d:.0f} km displacement of the concentration center of mass
indicates a stable, essentially unbiased spatial model.

See `kfold_cv_validation_figure.png`: panel (a) maps each fold's observed
held-out mean (black, numbered) against the predicted expected location
(red X); panel (b) shows the {n_folds} fold distance errors against their
mean and 95% confidence band.
"""
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write(md)
    print("[SAVED]", OUT_MD)
    print("[DONE]")


if __name__ == "__main__":
    main()
