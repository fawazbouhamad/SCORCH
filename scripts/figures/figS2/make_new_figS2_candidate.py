#!/usr/bin/env python3
# APPENDIX D (Fig. D) generator - occurrence-level five-fold cross-validation.
#
# LEGACY NAMING NOTICE: this file, its directory (figS2/) and its output
# filename keep the historical "S2" token for provenance. They are INTERNAL
# names, NOT current publication labels. Since the advisor-directed pass of
# 2026-07-30 the figure this script produces is designated **Fig. D in
# Appendix D of the main manuscript**; the supplementary document now
# contains Fig. S.1 only.
#
# G2 LAYOUT (approved 2026-07-30): 2 columns x 3 rows with panel (a) = the
# concentration-zone distance boxplot and panels (b)-(f) = held-out Folds
# 1-5; the shared vertical colorbar spans the full height of all three rows;
# the centroid-marker legend stays centred beneath the composite. Layout and
# labelling only - dataset, seed (20260704), fold membership, refit
# surfaces, ranks, colours, ticks, markers and statistics are unchanged and
# are asserted at run time.
# HISTORICAL NOTE (pre-2026-07-30 wording retained for provenance; the
# "Figure S.3"/"Figure_S3.png"/"figS03" tokens below are LEGACY INTERNAL
# names for this composite, NOT current publication labels - it is designated
# Fig. D in Appendix D):
# LAYOUT-ONLY reflow of the then-deployed Figure S.3 from 3x2 to 2x3
# (rows: (a)(b) / (c)(d) / (e)(f)).  This file is a copy of the verified
# canonical generator figS03/scripts/make_figS3_combined.py, whose UNMODIFIED
# run was confirmed to reproduce the deployed Figure_S3.png byte-identically
# (SHA-256 1696b0ab...) in provenance_check/.  The ONLY changes are:
#   1. grid geometry (2 columns x 3 rows), a wider inter-column gutter,
#      and the recomputed figure width/height that follow from it;
#   2. the colorbar rectangle (same wording/ticks/width treatment, now
#      spanning the top two map rows of the portrait layout);
#   3. output names/paths, plus a final uniform-resize step that declares
#      the finished page at the Supplement DOCX measured text width
#      (159.2 mm) — PNG metadata + pypdf page scale; no pixel/vector
#      content is altered by that step.
# Every dataset, seed, fold split, fit, rank transform, colormap, marker,
# statistic, font, line width and label call is byte-identical to canonical.
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
_sys.path.insert(0, _os.path.join(_SCORCH_ROOT, "scripts", "validation"))
# --- end SCORCH release bootstrap ---
import os, sys
os.environ.setdefault("MPLBACKEND", "Agg")
sys.dont_write_bytecode = True

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm
from matplotlib.lines import Line2D

CLEAN = _SCORCH_ROOT
S4_SCRIPTS = os.path.join(CLEAN, "supplementary", "figures", "figS04", "scripts")
REPO = os.path.dirname(CLEAN)
sys.path.insert(0, S4_SCRIPTS)
sys.path.insert(0, os.path.join(CLEAN, "scripts", "validation"))
sys.path.insert(0, os.path.join(CLEAN, "scripts", "figures"))
import q1_style as Q
import kfold_cv_four_variable_centroid_model as CV
import Figures_2_3_Centroid_Map_Plots as ref
if not ref.HAVE_CARTOPY:
    raise RuntimeError("Cartopy required")
import cartopy.crs as ccrs

OUT_DIR = os.path.join(_SCORCH_REPRO, "supplement"); os.makedirs(OUT_DIR, exist_ok=True)
RISK_BOUNDS = np.round(np.arange(0.0, 1.0001, 0.1), 1)
CBAR_LABEL = "Relative centroid-concentration rank, R(s)"
# Corrected v1.0.1 regression pins (Tmax-weighted centroids, seed 20260704,
# unchanged fold assignment); derived from the corrected validation table.
ZONES = [("Top 10%", "dist_to_top10_km", 389.670138931229),
         ("Top 20%", "dist_to_top20_km", 231.807728434158),
         ("Top 30%", "dist_to_top30_km", 151.672109636537),
         ("Top 50%", "dist_to_top50_km", 69.064508207406)]

AX_W = 4.30
AX_H = AX_W * 36.0 / 50.0
# LAYOUT CHANGE: 2 columns x 3 rows; COL_GAP widened 0.55 -> 1.25 so that at
# the 159.2 mm insertion width the clear inter-column space is >= 6-8 mm and
# panel (f)'s y-axis furniture stays >= 4 mm clear of panel (e).
# G2: L_M widened 0.45 -> 1.05 so the boxplot's y-axis label and ticks
# clear the page edge now that it occupies column 1.
L_M, COL_GAP, ROW_GAP, TOP_M, BOT_M = 1.05, 1.25, 0.75, 0.45, 0.25
CB_GUTTER = 1.05
FIG_W = L_M + 2 * AX_W + 1 * COL_GAP + CB_GUTTER + 0.15
FIG_H = TOP_M + 3 * AX_H + 2 * ROW_GAP + BOT_M + 0.55
# snap the canvas to exact 500-dpi pixel multiples so every axes origin lands
# on an integer pixel (as in the deployed donor) — pure float hygiene, the
# layout is unchanged to within 1/500 inch
FIG_W = round(FIG_W * 500) / 500.0
FIG_H = round(FIG_H * 500) / 500.0

# Supplement DOCX measured geometry (read-only): A4 11906x16838 twips,
# margins 1440 twips -> text width 9026 twips.
TEXT_W_IN = 9026.0 / 1440.0          # 6.2681 in = 159.21 mm
FINAL_SCALE = TEXT_W_IN / FIG_W


def quantile_grid(grid, lam):
    g = grid.copy()
    g["risk_q"] = pd.Series(lam).rank(method="average", pct=True).to_numpy()
    lons = np.sort(g["lon"].unique()); lats = np.sort(g["lat"].unique())
    grid2d = (g.pivot(index="lat", columns="lon", values="risk_q")
                .reindex(index=lats, columns=lons).to_numpy())
    return lons, lats, grid2d


def main():
    plt.rcParams.update({"font.family": "Arial", "pdf.fonttype": 42, "ps.fonttype": 42})
    grid = pd.read_csv(CV.VARIANTS_CSV).sort_values("grid_id").reset_index(drop=True)
    grid["area_km2"] = (CV.KM_PER_DEG_LON_EQ * np.cos(np.radians(grid["lat"])) * CV.KM_PER_DEG_LAT)
    cen = pd.read_csv(CV.CENTROIDS_CSV)
    gid_to_row = pd.Series(grid.index.values, index=grid["grid_id"].values)
    cen["grid_row"] = cen["nearest_grid_id"].map(gid_to_row).astype(int)
    n_boxes, n_cen = len(grid), len(cen)
    assert n_cen == 760, n_cen
    rng = np.random.default_rng(CV.SEED)
    folds = np.array_split(rng.permutation(n_cen), CV.N_FOLDS)

    pc = pd.read_csv(os.path.join(CV.SR_DIR, "validation_kfold",
                                  "per_centroid_risk_zone_validation.csv")
                     ).sort_values("centroid_id").reset_index(drop=True)
    assert len(pc) == n_cen
    assert np.allclose(pc["lon"], cen["centroid_lon"], atol=1e-9)
    assert np.allclose(pc["lat"], cen["centroid_lat"], atol=1e-9)
    fold_of = np.empty(n_cen, int)
    for k, idx in enumerate(folds, start=1):
        fold_of[idx] = k
    assert (pc["fold"].to_numpy(int) == fold_of).all()
    cen["is_daily_max"] = pc["is_daily_max"].astype(bool).to_numpy()
    cen["is_event_max"] = pc["is_event_max"].astype(bool).to_numpy()

    area = grid["area_km2"].to_numpy(float)
    norm = BoundaryNorm(RISK_BOUNDS, ncolors=ref.HEAT_CMAP.N, clip=True)

    # G2: slot 0 = distance boxplot, slots 1-5 = Folds 1-5.
    positions = {}
    for k in range(6):
        r, c = divmod(k, 2)
        x = L_M + c * (AX_W + COL_GAP)
        y = BOT_M + 0.55 + (2 - r) * (AX_H + ROW_GAP)
        positions[k] = (x, y)

    fig = plt.figure(figsize=(FIG_W, FIG_H))
    axes, im = {}, None
    for k, test_idx in enumerate(folds):
        test_mask = np.zeros(n_cen, bool); test_mask[test_idx] = True
        train, test = cen.loc[~test_mask], cen.loc[test_mask]
        counts_tr = np.bincount(train["grid_row"], minlength=n_boxes)
        _, lam, _ = CV.fit_surface(grid, counts_tr)
        lons, lats, grid2d = quantile_grid(grid, lam)
        x, y = positions[k + 1]
        ax = fig.add_axes([x / FIG_W, y / FIG_H, AX_W / FIG_W, AX_H / FIG_H],
                          projection=ccrs.PlateCarree())
        ref.setup_panel_ax(ax)
        im = ax.pcolormesh(lons, lats, grid2d, transform=ccrs.PlateCarree(),
                           cmap=ref.HEAT_CMAP, norm=norm, shading="auto",
                           alpha=0.78, zorder=3)
        tf = dict(transform=ccrs.PlateCarree())
        is_daily = test["is_daily_max"].to_numpy(bool)
        is_event = test["is_event_max"].to_numpy(bool)
        ax.scatter(test["centroid_lon"], test["centroid_lat"], s=ref.POINT_SIZE,
                   c="black", alpha=ref.POINT_ALPHA, edgecolors="none", zorder=8, **tf)
        ax.scatter(test.loc[is_daily, "centroid_lon"], test.loc[is_daily, "centroid_lat"],
                   s=70, facecolors="none", edgecolors="black", linewidths=0.9,
                   alpha=0.85, zorder=9, **tf)
        ax.scatter(test.loc[is_event, "centroid_lon"], test.loc[is_event, "centroid_lat"],
                   s=62, marker="x", c="white", linewidths=3.2, zorder=10, **tf)
        ax.scatter(test.loc[is_event, "centroid_lon"], test.loc[is_event, "centroid_lat"],
                   s=55, marker="x", c="#b2182b", linewidths=1.6, zorder=11, **tf)
        axes[k + 1] = ax
        print(f"[FIG-D] fold {k+1} -> panel ({chr(ord('a') + k + 1)}): "
              f"n={len(test)}")

    # G2 panel (a): the canonical distance boxplot, same axes rectangle
    d = pd.read_csv(os.path.join(CV.SR_DIR, "validation_kfold",
                                 "per_centroid_risk_zone_validation.csv"))
    assert len(d) == 760 and d["fold"].nunique() == 5
    x, y = positions[0]
    axf = fig.add_axes([x / FIG_W, y / FIG_H, AX_W / FIG_W, AX_H / FIG_H])
    stats, rows = [], []
    for label, col, pinned_mean in ZONES:
        v = d[col].to_numpy(float); m = v.mean()
        assert abs(m - pinned_mean) < 1e-6, (label, m, pinned_mean)
        stats.append(dict(label=label, med=np.median(v), mean=m,
                          q1=np.percentile(v, 25), q3=np.percentile(v, 75),
                          whislo=v.min(), whishi=v.max(), fliers=[]))
        rows.append(dict(zone=label, mean_km=m))
    arts = axf.bxp(stats, showmeans=True, showfliers=False, widths=0.5,
                   meanprops=dict(marker="D", markerfacecolor="white",
                                  markeredgecolor="black", markersize=5),
                   patch_artist=True)
    for box, med in zip(arts["boxes"], arts["medians"]):
        box.set_facecolor("0.88"); box.set_edgecolor("0.25")
        med.set_color("0.15"); med.set_linewidth(2.0)
    for a in arts["whiskers"] + arts["caps"]:
        a.set_color("0.25"); a.set_linewidth(1.0)
    for i, r in enumerate(rows, start=1):
        axf.annotate(f"mean {r['mean_km']:.0f} km", xy=(i + 0.06, r["mean_km"]),
                     xytext=(i + 0.12, r["mean_km"]), fontsize=8.2,
                     color="0.2", va="center")
    axf.set_ylabel("Distance to nearest top-concentration zone (km)",
                   fontsize=9.5)
    axf.tick_params(axis="both", labelsize=8.2)
    axf.grid(True, axis="y", alpha=0.22, linewidth=0.45)
    axf.spines["top"].set_visible(False); axf.spines["right"].set_visible(False)
    axes[0] = axf

    fig.canvas.draw()
    for k, ax in axes.items():
        Q.label_above(fig, ax, f"({chr(ord('a') + k)})")
    sizes = {(round(a.get_position().width, 6), round(a.get_position().height, 6))
             for a in axes.values()}
    assert len(sizes) == 1, sizes
    print("[FIG-D] equal panel frames confirmed (6 panels)")

    # G2: same colorbar treatment (identical width, ticks, label, styling);
    # the rectangle now spans the FULL height of all three rows.
    cb_y0 = BOT_M + 0.55
    cb_h = 3 * AX_H + 2 * ROW_GAP
    cax = fig.add_axes([(FIG_W - CB_GUTTER + 0.18) / FIG_W,
                        cb_y0 / FIG_H, 0.16 / FIG_W, cb_h / FIG_H])
    cbar = fig.colorbar(im, cax=cax, orientation="vertical", ticks=RISK_BOUNDS)
    cbar.set_label(CBAR_LABEL, fontsize=10)
    cbar.ax.tick_params(labelsize=9, length=2.5, width=0.6)
    cbar.outline.set_linewidth(0.6)

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
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 0.012),
               ncol=3, fontsize=8.2, frameon=True, fancybox=False, framealpha=1.0,
               edgecolor="black", facecolor="white", handlelength=2.0,
               columnspacing=1.4, borderpad=0.65)

    for ext in ("png", "pdf"):
        p = os.path.join(OUT_DIR, f"New_Figure_S2_candidate.{ext}")
        fig.savefig(p, dpi=500)
        print(f"[SAVED] {p}")
    plt.close(fig)

    # ---- final uniform resize to the DOCX text width (metadata only) ----
    from PIL import Image
    p_png = os.path.join(OUT_DIR, "New_Figure_S2_candidate.png")
    im2 = Image.open(p_png)
    px_w, px_h = im2.size
    eff_dpi = px_w / TEXT_W_IN
    im2.save(p_png, dpi=(eff_dpi, eff_dpi))
    print(f"[FIG-D] PNG {px_w}x{px_h} px declared at {eff_dpi:.2f} ppi -> "
          f"{px_w/eff_dpi*25.4:.1f} x {px_h/eff_dpi*25.4:.1f} mm")

    from pypdf import PdfReader, PdfWriter, Transformation
    p_pdf = os.path.join(OUT_DIR, "New_Figure_S2_candidate.pdf")
    rd = PdfReader(p_pdf)
    wr = PdfWriter()
    pg = rd.pages[0]
    pg.add_transformation(Transformation().scale(FINAL_SCALE, FINAL_SCALE))
    pg.mediabox.lower_left = (0, 0)
    pg.mediabox.upper_right = (float(pg.mediabox.width) * FINAL_SCALE,
                               float(pg.mediabox.height) * FINAL_SCALE)
    wr.add_page(pg)
    with open(p_pdf, "wb") as fh:
        wr.write(fh)
    print(f"[FIG-D] PDF page scaled by {FINAL_SCALE:.4f} -> "
          f"{FIG_W*FINAL_SCALE*25.4:.1f} x {FIG_H*FINAL_SCALE*25.4:.1f} mm")


if __name__ == "__main__":
    main()
