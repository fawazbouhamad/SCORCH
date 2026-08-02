#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Q1 map of the FOUR-VARIABLE centroid-concentration model (main model).

Model: LGCP minimum-contrast fit with trend
    ~ lon + lat + mean_tmax_z + std_tmax_z          ("variant3")
i.e. exactly longitude, latitude, mean Tmax and Tmax standard deviation.
The fitted per-box intensity comes from the already-run R diagnostics
(scripts/lgcp/spatial_risk_lgcp_model_diagnostics.R); this script
does NOT re-run the model, it renders the main publication map of relative
spatial centroid concentration.

Style: reuses scripts/figures/Figures_2_3_Centroid_Map_Plots.py verbatim
(projection, fixed 20-70E / 10-46N domain, cartopy features, gridlines,
HEAT_CMAP, external colorbar, below-axes horizontal legend convention,
7.2x5.6 figure, dpi=600 PNG+PDF). Per Dr. Najibi (2026-07-04):
  * NO place-name labels (no cities / countries / seas)
  * colorbar is the DECIMAL quantile of predicted centroid concentration
    over the FULL 0..1 range in 0.1 steps
    (underlying intensity is per-km^2; the display converts it to its
    quantile rank across the 1800 boxes -> decimals, not 0-100 percentiles).
    2026-07-09 (Dr. Najibi): extended from the earlier clipped 0.1-0.9
    segmentation to the full 0-1 range, and the label now states the
    quantile semantics plus the x10^6 intensity scaling explicitly (the
    ranked column pred_intensity_x1e6_variant3 is exp(trend)*1e6, i.e. the
    LGCP predicted intensity in centroids per km^2 multiplied by 10^6 -
    quantile ranks are unaffected by that monotone scaling).
  * every centroid = small black dot (reference marker convention)
  * largest-AREA ellipse per event-day  = larger open ring
  * largest-AREA ellipse per event      = "X" marker (white halo, on top)
    + the same ring
  * marker legend below the map, horizontal, reference legend style;
    legend says "Daily-largest structure centroid" / "Event-largest
    structure centroid"; "largest" is defined by ellipse-summary AREA (km^2)

Caption notes (for the manuscript): the colorbar shows the QUANTILE of
predicted centroid concentration across the 1800 boxes - 0.9 means the 90th
percentile of predicted concentration, NOT a 90% probability. The colorbar
spans the full 0-1 quantile range in 0.1 steps.

Counts are COMPUTED from the master CSV (not hard-coded) and printed,
including verification that every biggest-per-event centroid is also a
biggest-per-day centroid.

Outputs (new files only, nothing overwritten):
    reproduced/fig12/
        q1_four_variable_centroid_risk_map.png / .pdf
        (legacy "risk" output file name; see docs/TERMINOLOGY.md)
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

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm
from matplotlib.lines import Line2D

_THIS = os.path.abspath(__file__)
# Clean-package path repair: this copy lives in clean/scripts/spatial_risk/;
# style module and central paths come from this package. The full variants
# table (R diagnostics output grid_predicted_intensity_all_variants.csv) is
# replaced by the minimal archived prediction table holding exactly the
# columns this map needs (lon, lat, pred_intensity_x1e6_variant3; 1800 boxes),
# so the displayed map regenerates without the R/spatstat + ERA5 chain.
# Phase 2C candidate copy: outputs into the candidate workspace; ONLY the
# visible colorbar label changes (author revision 2026-07-14) — the map,
# data, quantile ranks, ticks, centroids and legend are untouched.
_CAND = os.path.dirname(os.path.dirname(_THIS))
CLEAN_ROOT = os.path.dirname(os.path.dirname(_CAND))
sys.path.insert(0, os.path.join(CLEAN_ROOT, "scripts", "figures"))
sys.path.insert(0, os.path.join(CLEAN_ROOT, "scripts"))
from _clean_paths import DATA_DIR, MASTER_CSV, data_file  # noqa: E402


def generated(sub):
    p = os.path.join(_SCORCH_REPRO, sub)
    os.makedirs(p, exist_ok=True)
    return p
import Figures_2_3_Centroid_Map_Plots as ref  # noqa: E402  (style source of truth)
import cartopy.crs as ccrs  # noqa: E402

VARIANTS_CSV = data_file("grid_predicted_intensity_variant3.csv", "catalogs")
OUT_FIG_DIR = generated("fig12")
OUT_PNG = os.path.join(OUT_FIG_DIR, "q1_four_variable_centroid_risk_map.png")
OUT_PDF = os.path.join(OUT_FIG_DIR, "q1_four_variable_centroid_risk_map.pdf")

RISK_COL = "pred_intensity_x1e6_variant3"   # ~ lon + lat + mean_tmax_z + std_tmax_z
# Two-line colorbar label: the color scale is the QUANTILE (0-1) of the
# predicted intensity; the ranked values themselves are lambda-hat x 10^6
# per km^2 (the R diagnostics write exp(trend)*1e6), stated so readers know
# the underlying scaling. Quantile ranks are invariant to the x10^6 factor.
# Phase 2C author-approved visible label. NOTE (for PROVENANCE and the
# manuscript caption): the plotted colors remain the QUANTILE RANKS (0-1),
# computed across the 1800 grid boxes, of the LGCP predicted intensity whose
# physical scaling is x10^6 per km^2 — only the visible wording changes.
# Phase 3F LABEL-ONLY revision: the plotted field is the dimensionless
# domain-wide quantile rank R(s) of the fitted first-order trend intensity
# (Methods Eq. 7). The former label wrongly attached intensity units and
# "risk" wording to this 0-1 rank; the visible label now names the rank
# with no units and no risk terminology. The plotted values are unchanged.
CBAR_LABEL = "Relative centroid-concentration rank, R(s)"

# Decimal segment boundaries: full 0 to 1 quantile range in 0.1 increments.
RISK_BOUNDS = np.round(np.arange(0.0, 1.0001, 0.1), 1)


def select_centroid_groups(df: pd.DataFrame):
    """Largest-AREA ellipse per event-day and per event (computed, not hard-coded)."""
    df = df.copy()
    df["date"] = df["date"].astype(str)
    idx_daily = df.groupby(["new_event_id", "date"])["ellipse_area_km2"].idxmax()
    idx_event = df.groupby("new_event_id")["ellipse_area_km2"].idxmax()
    return set(idx_daily), set(idx_event)


def main():
    os.makedirs(OUT_FIG_DIR, exist_ok=True)

    pred = pd.read_csv(VARIANTS_CSV)
    for c in ("lon", "lat", RISK_COL):
        assert c in pred.columns, f"missing prediction column: {c}"
    assert pred[RISK_COL].notna().all(), "NaN predicted-risk values present"
    n_boxes = len(pred)
    print(f"[CHECK] prediction grid rows = {n_boxes}")

    # ---- convert intensity -> decimal quantile rank across all boxes ----------
    pred["risk_q"] = pred[RISK_COL].rank(method="average", pct=True)

    lons = np.sort(pred["lon"].unique())
    lats = np.sort(pred["lat"].unique())
    grid2d = (pred.pivot(index="lat", columns="lon", values="risk_q")
                  .reindex(index=lats, columns=lons)
                  .to_numpy())

    # ---- centroid groups from the master ellipse table ------------------------
    m = pd.read_csv(MASTER_CSV)
    for c in ("new_event_id", "date", "ellipse_area_km2",
              "centroid_lon", "centroid_lat"):
        assert c in m.columns, f"missing master column: {c}"
    m = m[np.isfinite(m["centroid_lon"]) & np.isfinite(m["centroid_lat"])].copy()

    idx_daily, idx_event = select_centroid_groups(m)
    n_total = len(m)
    n_daily = len(idx_daily)
    n_event = len(idx_event)
    not_in_daily = idx_event - idx_daily

    print(f"[COUNT] total centroids                 = {n_total}")
    print(f"[COUNT] biggest per event-day (area)    = {n_daily}")
    print(f"[COUNT] biggest per event (area)        = {n_event}")
    print(f"[VERIFY] biggest-per-event subset of biggest-per-day: "
          f"{'YES' if not not_in_daily else 'NO'} "
          f"({len(not_in_daily)} exceptions)")
    if not_in_daily:
        print("[VERIFY] exception rows:", sorted(not_in_daily))

    is_daily = m.index.isin(idx_daily)
    is_event = m.index.isin(idx_event)

    # ---- single-panel figure exactly like ref.make_individual_panels ----------
    if ref.HAVE_CARTOPY:
        fig, ax = plt.subplots(1, 1, figsize=(7.2, 5.6),
                               subplot_kw={"projection": ccrs.PlateCarree()})
    else:
        fig, ax = plt.subplots(1, 1, figsize=(7.2, 5.6))

    ref.setup_panel_ax(ax)

    norm = BoundaryNorm(RISK_BOUNDS, ncolors=ref.HEAT_CMAP.N, clip=True)
    mesh_kw = dict(cmap=ref.HEAT_CMAP, norm=norm, shading="auto",
                   alpha=0.78, zorder=3)
    if ref.HAVE_CARTOPY:
        im = ax.pcolormesh(lons, lats, grid2d, transform=ccrs.PlateCarree(),
                           **mesh_kw)
    else:
        im = ax.pcolormesh(lons, lats, grid2d, **mesh_kw)

    # NO ref.add_google_style_labels(ax): place names explicitly excluded.

    tf = dict(transform=ccrs.PlateCarree()) if ref.HAVE_CARTOPY else {}

    # 1) every centroid: reference small black dot
    ax.scatter(m["centroid_lon"], m["centroid_lat"],
               s=ref.POINT_SIZE, c="black", alpha=ref.POINT_ALPHA,
               edgecolors="none", zorder=8, **tf)

    # 2) biggest per event-day: larger open ring around the dot
    ax.scatter(m.loc[is_daily, "centroid_lon"], m.loc[is_daily, "centroid_lat"],
               s=70, facecolors="none", edgecolors="black", linewidths=0.9,
               alpha=0.85, zorder=9, **tf)

    # 3) biggest per event: X marker plotted ON TOP of rings and dots, with a
    #    white halo underneath so it stays visible on red/orange risk cells
    ax.scatter(m.loc[is_event, "centroid_lon"], m.loc[is_event, "centroid_lat"],
               s=62, marker="x", c="white", linewidths=3.2,
               alpha=1.0, zorder=10, **tf)
    ax.scatter(m.loc[is_event, "centroid_lon"], m.loc[is_event, "centroid_lat"],
               s=55, marker="x", c="#b2182b", linewidths=1.6,
               alpha=1.0, zorder=11, **tf)

    # No "(a)" panel label: this map stands alone (Najibi request 2026-07-05).

    # ---- horizontal marker legend below the map (reference legend style) ------
    handles = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor="black",
               markeredgecolor="black", markersize=5, label="Centroid"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="none",
               markeredgecolor="black", markeredgewidth=1.0, markersize=9,
               label="Daily-largest structure centroid"),
        Line2D([0], [0], marker="x", color="#b2182b", markeredgewidth=1.6,
               markersize=7, linestyle="none",
               label="Event-largest structure centroid"),
    ]
    ax.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.045),
        ncol=3,
        fontsize=8.2,
        frameon=True,
        fancybox=False,
        framealpha=1.0,
        edgecolor="black",
        facecolor="white",
        handlelength=2.0,
        columnspacing=1.4,
        borderpad=0.65,
    )

    # ---- external vertical colorbar with clean decimal ticks ------------------
    plt.tight_layout(rect=[0, 0.04, 0.88, 0.98])
    pos = ax.get_position()
    cax = fig.add_axes([pos.x1 + 0.025, pos.y0, 0.020, pos.height])
    cbar = fig.colorbar(im, cax=cax, orientation="vertical", ticks=RISK_BOUNDS)
    cbar.set_label(CBAR_LABEL, fontsize=10)
    cbar.ax.set_yticklabels([f"{b:.1f}" for b in RISK_BOUNDS])
    cbar.ax.tick_params(labelsize=9, length=2.5, width=0.6)
    cbar.outline.set_linewidth(0.6)

    plt.savefig(OUT_PNG, dpi=600, bbox_inches="tight")
    plt.savefig(OUT_PDF, dpi=600, bbox_inches="tight")
    plt.close(fig)

    assert os.path.exists(OUT_PNG) and os.path.exists(OUT_PDF), "output not written"
    print("[SAVED]", OUT_PNG)
    print("[SAVED]", OUT_PDF)
    print(f"[INFO] model=variant3 (~ lon + lat + mean_tmax_z + std_tmax_z); "
          f"shading=decimal quantile of {RISK_COL}; boxes={n_boxes}; "
          f"centroids={n_total} (daily-max {n_daily}, event-max {n_event})")
    print("[DONE]")


if __name__ == "__main__":
    main()
