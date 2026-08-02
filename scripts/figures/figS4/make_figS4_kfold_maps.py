#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 2E — INTERNAL COMPONENT producer (legacy internal name
"Figure S.4"): 5-fold cross-validated held-out concentration maps (slide 28
rebuilt as ONE coherent multi-panel figure).

This is NOT a manuscript figure and "S.4" is NOT a publication label. Its
output supplies panels (b)-(f) of the published **Fig. D** (Appendix D).
The file name, directory name ("figS4") and output name are retained for
provenance continuity only.

Source scripts (found): scripts/validation/make_kfold_fold_maps.py and
scripts/validation/kfold_cv_four_variable_centroid_model.py (CV engine:
fixed SEED, N_FOLDS = 5, per-fold Poisson trend refit on the 760 current
global-max centroids — 152 held out per fold). This candidate reuses the
IDENTICAL CV design (imported, not reimplemented): same seed, same fold
split, same fit_surface refit, same rank-quantile map transform, same
HEAT_CMAP + BoundaryNorm(0..1 in 0.1 steps).

Composition per Phase 2E instructions: folds 1..5 in order as (a)-(e) on
one figure; EQUAL map frames (identical axes rectangles; axes aspect equals
the fixed 50/36 domain extent) and identical spatial extents
(setup_panel_ax); ONE shared colorbar (all five panels share the same
quantile normalization and colormap) and ONE shared legend (identical
held-out-centroid encoding); per-fold statistics boxes retained (numeric
information); no slide header.

Outputs: outputs/supplementary/Figure_S4_kfold_heldout_maps.{png,pdf}
         outputs/supplementary/Figure_S4_fold_metrics.csv
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("MPLBACKEND", "Agg")
sys.dont_write_bytecode = True   # never write pyc outside clean/

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import BoundaryNorm  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_FIGS = os.path.dirname(_THIS_DIR)                       # scripts/figures
_ROOT = os.path.dirname(os.path.dirname(_FIGS))          # release root
sys.path.insert(0, os.path.join(_FIGS, "common"))
sys.path.insert(0, os.path.join(_ROOT, "scripts", "validation"))
import q1_style as Q  # noqa: E402
import kfold_cv_four_variable_centroid_model as CV  # noqa: E402
import Figures_2_3_Centroid_Map_Plots as ref  # noqa: E402

if not ref.HAVE_CARTOPY:
    raise RuntimeError("Cartopy required to reproduce the approved maps")
import cartopy.crs as ccrs  # noqa: E402

OUT_DIR = os.path.join(os.environ.get(
    "SCORCH_OUT_DIR", os.path.join(_ROOT, "reproduced")), "supplement")
os.makedirs(OUT_DIR, exist_ok=True)

RISK_BOUNDS = np.round(np.arange(0.0, 1.0001, 0.1), 1)
# V4 correction: the mapped field is the per-fold PERCENTILE RANK of the
# predicted intensity (quantile_grid: rank(pct=True), 0-1), not a physical
# concentration or intensity, so the colorbar must not carry physical
# units. Wording matches the canonical Figure 12 colorbar (CBAR_LABEL in
# scripts/figures/fig12/make_q1_variant3_four_variable_centroid_map.py).
CBAR_LABEL = "Relative centroid-concentration rank, R(s)"

# Layout (inches): 3 + 2 map axes, all identical; shared right gutter.
AX_W = 4.30
AX_H = AX_W * 36.0 / 50.0                      # 3.096 — extent aspect
L_M, COL_GAP, ROW_GAP, TOP_M, BOT_M = 0.45, 0.55, 0.75, 0.45, 0.25
CB_GUTTER = 1.05
FIG_W = L_M + 3 * AX_W + 2 * COL_GAP + CB_GUTTER + 0.15
FIG_H = TOP_M + 2 * AX_H + ROW_GAP + BOT_M + 0.55   # bottom legend region


def quantile_grid(grid, lam):
    g = grid.copy()
    g["risk_q"] = pd.Series(lam).rank(method="average", pct=True).to_numpy()
    lons = np.sort(g["lon"].unique())
    lats = np.sort(g["lat"].unique())
    grid2d = (g.pivot(index="lat", columns="lon", values="risk_q")
                .reindex(index=lats, columns=lons).to_numpy())
    return lons, lats, grid2d


def main() -> None:
    plt.rcParams.update({"font.family": "Arial", "pdf.fonttype": 42,
                         "ps.fonttype": 42})
    grid = pd.read_csv(CV.VARIANTS_CSV).sort_values("grid_id") \
             .reset_index(drop=True)
    grid["area_km2"] = (CV.KM_PER_DEG_LON_EQ *
                        np.cos(np.radians(grid["lat"])) * CV.KM_PER_DEG_LAT)
    cen = pd.read_csv(CV.CENTROIDS_CSV)
    gid_to_row = pd.Series(grid.index.values, index=grid["grid_id"].values)
    cen["grid_row"] = cen["nearest_grid_id"].map(gid_to_row).astype(int)
    n_boxes, n_cen = len(grid), len(cen)
    assert n_cen == 760, n_cen
    rng = np.random.default_rng(CV.SEED)
    perm = rng.permutation(n_cen)
    folds = np.array_split(perm, CV.N_FOLDS)

    # Phase 2E-R1: largest-per-day / largest-per-event marker flags from the
    # validated risk-zone CSV, alignment PROVEN before use: same length,
    # same coordinates row-by-row, and the CSV's stored fold assignment must
    # equal the fold split recomputed here (no centroid added, omitted or
    # assigned to the wrong fold).
    pc = pd.read_csv(os.path.join(CV.SR_DIR, "validation_kfold",
                                  "per_centroid_risk_zone_validation.csv")
                     ).sort_values("centroid_id").reset_index(drop=True)
    assert len(pc) == n_cen, len(pc)
    assert np.allclose(pc["lon"], cen["centroid_lon"], atol=1e-9)
    assert np.allclose(pc["lat"], cen["centroid_lat"], atol=1e-9)
    fold_of = np.empty(n_cen, int)
    for k, idx in enumerate(folds, start=1):
        fold_of[idx] = k
    assert (pc["fold"].to_numpy(int) == fold_of).all(), \
        "CSV fold assignment differs from the recomputed split"
    cen["is_daily_max"] = pc["is_daily_max"].astype(bool).to_numpy()
    cen["is_event_max"] = pc["is_event_max"].astype(bool).to_numpy()
    n_day, n_evt = int(cen["is_daily_max"].sum()), \
        int(cen["is_event_max"].sum())
    print(f"[FIGS4-R1] marker flags verified against the CV table: "
          f"{n_day} largest-per-day, {n_evt} largest-per-event of "
          f"{n_cen} centroids; fold assignments identical")
    print(f"[FIGS4] {n_boxes} boxes; {n_cen} global-max centroids; "
          f"seed {CV.SEED}; fold sizes {[len(f) for f in folds]}")

    area = grid["area_km2"].to_numpy(float)
    norm = BoundaryNorm(RISK_BOUNDS, ncolors=ref.HEAT_CMAP.N, clip=True)

    positions = {}
    for k in range(5):
        r, c = divmod(k, 3)
        x = L_M + c * (AX_W + COL_GAP)
        if r == 1:                       # second row: 2 maps, centered
            x = L_M + (c + 0.5) * (AX_W + COL_GAP)
        y = BOT_M + 0.55 + (1 - r) * (AX_H + ROW_GAP)
        positions[k] = (x, y)

    fig = plt.figure(figsize=(FIG_W, FIG_H))
    metrics, axes, im = [], {}, None
    for k, test_idx in enumerate(folds):
        test_mask = np.zeros(n_cen, bool)
        test_mask[test_idx] = True
        train = cen.loc[~test_mask]
        test = cen.loc[test_mask]
        counts_tr = np.bincount(train["grid_row"], minlength=n_boxes)
        _, lam, _ = CV.fit_surface(grid, counts_tr)
        lons, lats, grid2d = quantile_grid(grid, lam)
        rank_q = pd.Series(lam).rank(method="average", pct=True).to_numpy()
        t_rows = test["grid_row"].to_numpy(int)
        heldout_q = rank_q[t_rows]
        desc = np.argsort(lam)[::-1]
        cum = np.cumsum(area[desc]) / area.sum()
        kzone = int(np.searchsorted(cum, 0.20)) + 1
        zone20 = np.zeros(n_boxes, bool)
        zone20[desc[:kzone]] = True
        hit20 = float(np.mean(zone20[t_rows]))
        metrics.append(dict(fold=k + 1, n_heldout=len(test),
                            mean_heldout_risk_quantile=heldout_q.mean(),
                            top20_zone_hit_rate=hit20))

        x, y = positions[k]
        ax = fig.add_axes([x / FIG_W, y / FIG_H, AX_W / FIG_W, AX_H / FIG_H],
                          projection=ccrs.PlateCarree())
        ref.setup_panel_ax(ax)
        im = ax.pcolormesh(lons, lats, grid2d, transform=ccrs.PlateCarree(),
                           cmap=ref.HEAT_CMAP, norm=norm, shading="auto",
                           alpha=0.78, zorder=3)
        # Phase 2E-R1: per-panel metadata box REMOVED (metrics preserved in
        # Figure_S4_fold_metrics.csv); markers restored to the EXACT
        # canonical Figure 12 encoding and drawing order.
        tf = dict(transform=ccrs.PlateCarree())
        is_daily = test["is_daily_max"].to_numpy(bool)
        is_event = test["is_event_max"].to_numpy(bool)
        # 1) every held-out centroid: reference small black dot
        ax.scatter(test["centroid_lon"], test["centroid_lat"],
                   s=ref.POINT_SIZE, c="black", alpha=ref.POINT_ALPHA,
                   edgecolors="none", zorder=8, **tf)
        # 2) largest per event-day: larger open ring around the dot
        ax.scatter(test.loc[is_daily, "centroid_lon"],
                   test.loc[is_daily, "centroid_lat"],
                   s=70, facecolors="none", edgecolors="black",
                   linewidths=0.9, alpha=0.85, zorder=9, **tf)
        # 3) largest per event: X on top, white halo underneath
        ax.scatter(test.loc[is_event, "centroid_lon"],
                   test.loc[is_event, "centroid_lat"],
                   s=62, marker="x", c="white", linewidths=3.2,
                   alpha=1.0, zorder=10, **tf)
        ax.scatter(test.loc[is_event, "centroid_lon"],
                   test.loc[is_event, "centroid_lat"],
                   s=55, marker="x", c="#b2182b", linewidths=1.6,
                   alpha=1.0, zorder=11, **tf)
        print(f"[FIGS4-R1] fold {k + 1} markers: {len(test)} centroids, "
              f"{int(is_daily.sum())} largest-per-day, "
              f"{int(is_event.sum())} largest-per-event")
        axes[k] = ax
        print(f"[FIGS4] fold {k + 1}: n={len(test)}, "
              f"mean q={heldout_q.mean():.3f}, hit20={hit20:.3f}")

    fig.canvas.draw()
    for k, ax in axes.items():
        Q.label_above(fig, ax, f"({chr(ord('a') + k)})")
    # frame-equality proof (identical axes rectangles by construction)
    sizes = {(round(a.get_position().width, 6),
              round(a.get_position().height, 6)) for a in axes.values()}
    assert len(sizes) == 1, sizes
    print(f"[FIGS4] equal map frames confirmed: {AX_W:.2f} x {AX_H:.2f} in "
          f"x5; identical extents via setup_panel_ax")

    # ONE shared colorbar (same normalization in all panels).
    cax = fig.add_axes([(FIG_W - CB_GUTTER + 0.18) / FIG_W,
                        (BOT_M + 0.55 + 0.35) / FIG_H,
                        0.16 / FIG_W,
                        (2 * AX_H + ROW_GAP - 0.7) / FIG_H])
    # Figure-12-exact colorbar styling (fontsize 10; visible 0-1 scale).
    cbar = fig.colorbar(im, cax=cax, orientation="vertical",
                        ticks=RISK_BOUNDS)
    cbar.set_label(CBAR_LABEL, fontsize=10)
    cbar.ax.tick_params(labelsize=9, length=2.5, width=0.6)
    cbar.outline.set_linewidth(0.6)

    # ONE shared legend, horizontally centered, matching canonical Figure 12
    # EXACTLY (handles, labels, order, font, frame, spacing, marker scale).
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
    fig.legend(handles=handles, loc="lower center",
               bbox_to_anchor=(0.5, 0.012), ncol=3, fontsize=8.2,
               frameon=True, fancybox=False, framealpha=1.0,
               edgecolor="black", facecolor="white", handlelength=2.0,
               columnspacing=1.4, borderpad=0.65)

    pd.DataFrame(metrics).to_csv(
        os.path.join(OUT_DIR, "Figure_S4_fold_metrics.csv"), index=False)
    for ext in ("png", "pdf"):
        p = os.path.join(OUT_DIR, f"Figure_S4_kfold_heldout_maps.{ext}")
        fig.savefig(p, dpi=500)
        print(f"[SAVED] {p}")
    plt.close(fig)


if __name__ == "__main__":
    main()
