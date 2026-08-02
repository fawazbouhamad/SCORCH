#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Raw per-fold validation maps for the 5-fold CV of the four-variable model.

One clean map per fold (5 total), in EXACTLY the style of the main
publication map (make_q1_variant3_four_variable_centroid_map.py: Figures 2-3
cartopy style, fixed 20-70E / 10-46N domain, HEAT_CMAP, full 0-1 decimal
quantile colorbar, external vertical colorbar, horizontal legend below the
map, no place names, 7.2x5.6 in, dpi=600 PNG+PDF). These are RAW fold maps,
not a new analysis:

  * background = quantile (0-1) of the predicted intensity surface from the
    four-variable trend (~ lon + lat + mean_tmax_z + std_tmax_z) refit on
    that fold's TRAINING centroids only (~80%), exactly the surface the
    risk-zone CV scores against
  * black dots = the held-out / out-of-sample centroids of that fold (~20%);
    the color of the box under each dot IS its held-out risk-quantile value
    (the per-centroid numbers live in
    validation_kfold/per_centroid_risk_zone_validation.csv - printing ~152
    numeric labels on the map would be unreadable, so each map instead
    carries a small stats box: n held-out, mean held-out concentration rank,
    top-20% hit rate)

Fold split, seed and per-fold refit are IMPORTED from
kfold_cv_four_variable_centroid_model.py (SEED, N_FOLDS=5, fit_surface), so
these maps use the identical folds as fold_metrics.csv and the risk-zone CV.

Outputs (new files only):
    reproduced/validation_kfold/fold_maps/
        kfold5_fold1_heldout_map.png / .pdf   ... kfold5_fold5_...

Run:  python scripts/validation/make_kfold_fold_maps.py
"""
from __future__ import annotations

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
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_THIS)))
sys.path.insert(0, os.path.dirname(_THIS))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "figures", "common"))
# Identical CV design (seed, folds, per-fold Poisson trend refit).
import kfold_cv_four_variable_centroid_model as CV  # noqa: E402
# Style source of truth (same as the main Q1 centroid-concentration map).
import Figures_2_3_Centroid_Map_Plots as ref  # noqa: E402
import cartopy.crs as ccrs  # noqa: E402

from _clean_paths import GENERATED_DIR  # noqa: E402

# Frozen fold maps are never overwritten: output goes to reproduced/.
OUT_DIR = os.path.join(GENERATED_DIR, "validation_kfold", "fold_maps")

# Same colorbar convention as the updated main map: full 0-1 decimal
# quantile range in 0.1 steps, quantile-of-intensity label with the x10^6
# scaling of the ranked intensity stated explicitly.
RISK_BOUNDS = np.round(np.arange(0.0, 1.0001, 0.1), 1)
CBAR_LABEL = ("Relative centroid-concentration rank, R(s)\n"
              r"[rank of trained-fold intensity $\hat{\lambda}\times10^{6}$"
              r" km$^{-2}$]")


def quantile_grid(grid, lam):
    """Quantile rank (0-1) of the per-box intensity, pivoted to lat x lon -
    the same rank(method='average', pct=True) transform as the main map."""
    g = grid.copy()
    g["risk_q"] = pd.Series(lam).rank(method="average", pct=True).to_numpy()
    lons = np.sort(g["lon"].unique())
    lats = np.sort(g["lat"].unique())
    grid2d = (g.pivot(index="lat", columns="lon", values="risk_q")
                .reindex(index=lats, columns=lons).to_numpy())
    return lons, lats, grid2d


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    grid = pd.read_csv(CV.VARIANTS_CSV).sort_values("grid_id").reset_index(drop=True)
    grid["area_km2"] = (CV.KM_PER_DEG_LON_EQ *
                        np.cos(np.radians(grid["lat"])) * CV.KM_PER_DEG_LAT)
    cen = pd.read_csv(CV.CENTROIDS_CSV)
    gid_to_row = pd.Series(grid.index.values, index=grid["grid_id"].values)
    cen["grid_row"] = cen["nearest_grid_id"].map(gid_to_row).astype(int)
    n_boxes, n_cen = len(grid), len(cen)
    print(f"[DATA] grid boxes = {n_boxes}; centroids = {n_cen}")

    # identical shuffled fold split to the CV scripts
    rng = np.random.default_rng(CV.SEED)
    perm = rng.permutation(n_cen)
    folds = np.array_split(perm, CV.N_FOLDS)
    assert np.array_equal(np.sort(np.concatenate(folds)), np.arange(n_cen))
    print(f"[CV] seed={CV.SEED}; {CV.N_FOLDS} folds; sizes={[len(f) for f in folds]}")

    area = grid["area_km2"].to_numpy(float)
    norm = BoundaryNorm(RISK_BOUNDS, ncolors=ref.HEAT_CMAP.N, clip=True)

    for k, test_idx in enumerate(folds, start=1):
        test_mask = np.zeros(n_cen, bool)
        test_mask[test_idx] = True
        train = cen.loc[~test_mask]
        test = cen.loc[test_mask]

        counts_tr = np.bincount(train["grid_row"], minlength=n_boxes)
        _, lam, _ = CV.fit_surface(grid, counts_tr)
        lons, lats, grid2d = quantile_grid(grid, lam)

        # held-out values under the trained surface: rank-based quantile of
        # each held-out box (same transform as the map shading, so the dot's
        # background color IS its value) + top-20% area-zone hit rate
        # (risk-zone CV convention)
        rank_q = pd.Series(lam).rank(method="average", pct=True).to_numpy()
        t_rows = test["grid_row"].to_numpy(int)
        heldout_q = rank_q[t_rows]
        desc = np.argsort(lam)[::-1]
        cum = np.cumsum(area[desc]) / area.sum()
        kzone = int(np.searchsorted(cum, 0.20)) + 1
        zone20 = np.zeros(n_boxes, bool)
        zone20[desc[:kzone]] = True
        hit20 = float(np.mean(zone20[t_rows]))

        # ---- figure: identical panel style to the main map --------------------
        if ref.HAVE_CARTOPY:
            fig, ax = plt.subplots(1, 1, figsize=(7.2, 5.6),
                                   subplot_kw={"projection": ccrs.PlateCarree()})
        else:
            fig, ax = plt.subplots(1, 1, figsize=(7.2, 5.6))
        ref.setup_panel_ax(ax)

        mesh_kw = dict(cmap=ref.HEAT_CMAP, norm=norm, shading="auto",
                       alpha=0.78, zorder=3)
        if ref.HAVE_CARTOPY:
            im = ax.pcolormesh(lons, lats, grid2d,
                               transform=ccrs.PlateCarree(), **mesh_kw)
        else:
            im = ax.pcolormesh(lons, lats, grid2d, **mesh_kw)

        tf = dict(transform=ccrs.PlateCarree()) if ref.HAVE_CARTOPY else {}

        # held-out centroids of this fold: black dots (reference convention),
        # thin white edge so they stay visible on the darkest risk cells
        ax.scatter(test["centroid_lon"], test["centroid_lat"],
                   s=ref.POINT_SIZE + 7, c="black", alpha=0.9,
                   edgecolors="white", linewidths=0.4, zorder=9, **tf)

        # small per-fold stats box (the per-centroid values themselves are
        # the map colors under the dots; full table in the risk-zone CSV)
        ax.text(0.015, 0.985,
                (f"Fold {k}/{CV.N_FOLDS}\n"
                 f"held-out n = {len(test)}\n"
                 f"mean held-out concentration rank = {heldout_q.mean():.2f}\n"
                 f"top-20% zone hit rate = {hit20:.2f}"),
                transform=ax.transAxes, va="top", ha="left", fontsize=8.2,
                color="black", zorder=12,
                bbox=dict(facecolor="white", edgecolor="black",
                          linewidth=0.6, boxstyle="square,pad=0.35"))

        handles = [
            Line2D([0], [0], marker="o", color="w", markerfacecolor="black",
                   markeredgecolor="white", markersize=6,
                   label=f"Held-out centroid (fold {k})"),
        ]
        ax.legend(handles=handles, loc="upper center",
                  bbox_to_anchor=(0.5, -0.045), ncol=1, fontsize=8.2,
                  frameon=True, fancybox=False, framealpha=1.0,
                  edgecolor="black", facecolor="white", handlelength=2.0,
                  columnspacing=1.4, borderpad=0.65)

        plt.tight_layout(rect=[0, 0.04, 0.88, 0.98])
        pos = ax.get_position()
        cax = fig.add_axes([pos.x1 + 0.025, pos.y0, 0.020, pos.height])
        cbar = fig.colorbar(im, cax=cax, orientation="vertical",
                            ticks=RISK_BOUNDS)
        cbar.set_label(CBAR_LABEL, fontsize=10)
        cbar.ax.set_yticklabels([f"{b:.1f}" for b in RISK_BOUNDS])
        cbar.ax.tick_params(labelsize=9, length=2.5, width=0.6)
        cbar.outline.set_linewidth(0.6)

        png = os.path.join(OUT_DIR, f"kfold5_fold{k}_heldout_map.png")
        pdf = os.path.join(OUT_DIR, f"kfold5_fold{k}_heldout_map.pdf")
        plt.savefig(png, dpi=600, bbox_inches="tight")
        plt.savefig(pdf, dpi=600, bbox_inches="tight")
        plt.close(fig)
        print(f"[FOLD {k}] n_test={len(test):3d}  "
              f"mean held-out q={heldout_q.mean():.3f}  "
              f"top20 hit={hit20:.2f}  -> {os.path.relpath(png, REPO_ROOT)}")

    print("[DONE]")


if __name__ == "__main__":
    main()
