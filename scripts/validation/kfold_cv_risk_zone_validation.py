#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Risk-zone 5-fold CV of the four-variable centroid model (MAIN validation).

WHAT THIS MEASURES (and what it does not):
This is NOT direct centroid-coordinate prediction error - the model is a
spatial intensity/concentration-surface model, not a point predictor. This
validation answers: "How far are unseen centroids from the areas the model
predicts as high centroid concentration?"  For every held-out centroid it
computes the distance (km) to the nearest predicted high-concentration zone
of a model trained WITHOUT that centroid (legacy "risk zone" naming in the
output files/columns; see docs/TERMINOLOGY.md). The headline metric is the
mean out-of-sample distance to the nearest TOP-20% predicted-concentration
zone (top-10% / top-30% / top-50% as sensitivity).

DESIGN (identical folds to the earlier center-of-mass CV - the seed, fold
split and Poisson-GLM trend refit are IMPORTED from
kfold_cv_four_variable_centroid_model.py so the two cannot drift; 5-fold
since 2026-07-09 per Dr. Najibi, was 10-fold):
  * all centroids (computed from data, expected ~760), shuffled once with
    the fixed seed, 5 folds, train ~80% / test ~20%, each centroid held out
    exactly once
  * per fold: refit trend ~ lon + lat + mean_tmax_z + std_tmax_z on the
    training centroids -> predicted intensity over the 1800 boxes
  * HIGH-CONCENTRATION ZONES: boxes sorted by predicted intensity (per km^2), taken
    from the top until they cover 10% / 20% / 30% / 50% of the total domain
    AREA (area-based, since 1-degree boxes shrink with latitude)
  * per held-out centroid:
      - concentration quantile (legacy `risk_quantile` column) in [0,1]:
        fraction of domain area with predicted
        intensity <= the centroid's box (1.0 = hottest spot on the map)
      - hit indicators: is its box inside the top-10/20/30/50% zone?
      - distance to nearest zone: 0 km if inside, else haversine km to the
        nearest zone-box center
      - held-out log predictive density: log of the normalized per-km^2
        density at its box
  * centroid groups (nested): all / largest-AREA per event-day / largest-
    AREA per event, computed from the master CSV (not hard-coded)

Outputs (new files; the older center-of-mass outputs are kept as
SUPPLEMENTARY material):
    reproduced/validation_kfold/
            per_centroid_risk_zone_validation.csv      (760 rows)
            risk_zone_summary_by_centroid_type.csv     (3 rows)
            risk_zone_validation_figure.png / .pdf
            RISK_ZONE_CV_REPORT.md                     (main written report)

Run:  python scripts/validation/kfold_cv_risk_zone_validation.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

_THIS = os.path.abspath(__file__)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_THIS)))
sys.path.insert(0, os.path.dirname(_THIS))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "figures", "common"))
# Reuse SEED, N_FOLDS, PREDICTORS, fit_surface, haversine_km -> identical CV.
import kfold_cv_four_variable_centroid_model as CV  # noqa: E402
from _clean_paths import (DATA_DIR, GENERATED_DIR,  # noqa: E402
                          MASTER_CSV, data_file)

SR_DIR = DATA_DIR
VARIANTS_CSV = CV.VARIANTS_CSV
CENTROIDS_CSV = CV.CENTROIDS_CSV
VALIDATED_CSV = data_file("centroid_points_all_ellipses_validated.csv", "lgcp")
OUT_DIR = os.path.join(GENERATED_DIR, "validation_kfold")

ZONE_FRACS = (0.10, 0.20, 0.30, 0.50)   # top 50% added 2026-07-09 (Najibi)
C_ACC = "#b2182b"


def zone_masks_and_quantiles(lam, area):
    """Area-based top-concentration zones and per-cell area-weighted
    centroid-concentration quantiles.

    Returns (q, masks): q[i] = fraction of total domain area with predicted
    intensity <= lam[i]; masks[frac] = boolean array marking boxes belonging
    to the top-`frac` highest-risk share of the domain AREA.
    """
    total = float(area.sum())
    asc = np.argsort(lam)                       # ascending intensity
    cum_asc = np.cumsum(area[asc]) / total
    q = np.empty_like(lam)
    q[asc] = cum_asc                            # 1.0 = highest-risk box

    desc = asc[::-1]
    cum_desc = np.cumsum(area[desc]) / total
    masks = {}
    for frac in ZONE_FRACS:
        k = int(np.searchsorted(cum_desc, frac)) + 1   # first boxes covering frac
        mask = np.zeros(lam.size, dtype=bool)
        mask[desc[:k]] = True
        masks[frac] = mask
    return q, masks


def dist_to_zone_km(test_lon, test_lat, test_rows, mask, grid_lon, grid_lat):
    """0 km if the centroid's own box is in the zone, else haversine km to
    the nearest zone-box center."""
    zlon, zlat = grid_lon[mask], grid_lat[mask]
    out = np.zeros(test_lon.size)
    for j in range(test_lon.size):
        if mask[test_rows[j]]:
            continue
        out[j] = float(np.min(CV.haversine_km(test_lon[j], test_lat[j],
                                              zlon, zlat)))
    return out


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    grid = pd.read_csv(VARIANTS_CSV).sort_values("grid_id").reset_index(drop=True)
    grid["area_km2"] = (CV.KM_PER_DEG_LON_EQ *
                        np.cos(np.radians(grid["lat"])) * CV.KM_PER_DEG_LAT)
    cen = pd.read_csv(CENTROIDS_CSV)
    gid_to_row = pd.Series(grid.index.values, index=grid["grid_id"].values)
    cen["grid_row"] = cen["nearest_grid_id"].map(gid_to_row).astype(int)
    n_boxes, n_cen = len(grid), len(cen)
    print(f"[DATA] grid boxes = {n_boxes}; centroids = {n_cen}")

    # ---- area + largest-per-day / largest-per-event flags from the master ----
    val = pd.read_csv(VALIDATED_CSV)
    m = pd.read_csv(MASTER_CSV)
    assert len(val) == len(m) == n_cen, "row-count mismatch across centroid tables"
    # build_inputs.py wrote the validated table straight from the master;
    # verify the row order is truly identical before aligning by position.
    assert np.allclose(val["centroid_lon"], m["centroid_lon"], atol=1e-6) and \
           np.allclose(val["centroid_lat"], m["centroid_lat"], atol=1e-6), \
           "validated/master centroid order mismatch - positional align unsafe"
    assert np.allclose(cen["centroid_lon"], m["centroid_lon"], atol=1e-6), \
           "covariates/master centroid order mismatch - positional align unsafe"
    cen["ellipse_area_km2"] = m["ellipse_area_km2"].values
    # largest-AREA ellipse per event-day and per event (same selection logic
    # as the power-law scripts and the four-variable map figure)
    mm = m.copy()
    mm["date"] = mm["date"].astype(str)
    idx_daily = set(mm.groupby(["new_event_id", "date"])["ellipse_area_km2"].idxmax())
    idx_event = set(mm.groupby("new_event_id")["ellipse_area_km2"].idxmax())
    cen["is_daily_max"] = cen.index.isin(idx_daily)
    cen["is_event_max"] = cen.index.isin(idx_event)
    n_daily, n_event = int(cen["is_daily_max"].sum()), int(cen["is_event_max"].sum())
    assert set(np.where(cen["is_event_max"])[0]) <= set(np.where(cen["is_daily_max"])[0])
    print(f"[COUNT] all={n_cen}  largest-per-day={n_daily}  largest-per-event={n_event}")

    # ---- identical fold split to the center-of-mass CV -----------------------
    rng = np.random.default_rng(CV.SEED)
    perm = rng.permutation(n_cen)
    folds = np.array_split(perm, CV.N_FOLDS)
    assert np.array_equal(np.sort(np.concatenate(folds)), np.arange(n_cen))
    print(f"[CV] seed={CV.SEED}; {CV.N_FOLDS} folds; sizes={[len(f) for f in folds]}")

    grid_lon = grid["lon"].to_numpy(float)
    grid_lat = grid["lat"].to_numpy(float)
    area = grid["area_km2"].to_numpy(float)

    rows = []
    # exact area-weighted quantile threshold of each zone, per fold (the
    # nominal thresholds are 0.90/0.80/0.70; area weighting shifts them
    # slightly because the crossing box is included whole)
    zone_thr = {frac: [] for frac in ZONE_FRACS}
    for k, test_idx in enumerate(folds, start=1):
        test_mask = np.zeros(n_cen, bool)
        test_mask[test_idx] = True
        train = cen.loc[~test_mask]
        test = cen.loc[test_mask]

        counts_tr = np.bincount(train["grid_row"], minlength=n_boxes)
        _, lam, p = CV.fit_surface(grid, counts_tr)
        q, masks = zone_masks_and_quantiles(lam, area)
        for frac in ZONE_FRACS:
            zone_thr[frac].append(float(q[masks[frac]].min()))
        dens = p / area                                  # normalized per-km^2

        t_lon = test["centroid_lon"].to_numpy(float)
        t_lat = test["centroid_lat"].to_numpy(float)
        t_rows = test["grid_row"].to_numpy(int)

        d = {frac: dist_to_zone_km(t_lon, t_lat, t_rows, masks[frac],
                                   grid_lon, grid_lat)
             for frac in ZONE_FRACS}

        for j, (_, r) in enumerate(test.iterrows()):
            rows.append({
                "centroid_id": int(r["centroid_id"]), "fold": k,
                "lon": float(r["centroid_lon"]), "lat": float(r["centroid_lat"]),
                "ellipse_area_km2": float(r["ellipse_area_km2"]),
                "is_daily_max": bool(r["is_daily_max"]),
                "is_event_max": bool(r["is_event_max"]),
                "heldout_risk_quantile": float(q[t_rows[j]]),
                **{f"hit_top{int(frac*100)}": bool(masks[frac][t_rows[j]])
                   for frac in ZONE_FRACS},
                **{f"dist_to_top{int(frac*100)}_km": float(d[frac][j])
                   for frac in ZONE_FRACS},
                "heldout_log_density": float(np.log(dens[t_rows[j]])),
            })
        print(f"[FOLD {k:2d}] n_test={len(test):3d}  "
              f"top20 hit-rate={np.mean([masks[0.20][i] for i in t_rows]):.2f}  "
              f"mean dist->top20={d[0.20].mean():6.1f} km")

    per = pd.DataFrame(rows).sort_values("centroid_id").reset_index(drop=True)
    assert len(per) == n_cen and per["centroid_id"].is_unique

    # ---- nested group summaries ----------------------------------------------
    def summarize(name, sub):
        return {
            "group": name, "n": len(sub),
            "mean_risk_quantile": sub["heldout_risk_quantile"].mean(),
            "min_risk_quantile": sub["heldout_risk_quantile"].min(),
            "max_risk_quantile": sub["heldout_risk_quantile"].max(),
            "median_risk_quantile": sub["heldout_risk_quantile"].median(),
            **{f"top{int(frac*100)}_hit_rate": sub[f"hit_top{int(frac*100)}"].mean()
               for frac in ZONE_FRACS},
            **{f"mean_dist_to_top{int(frac*100)}_km":
               sub[f"dist_to_top{int(frac*100)}_km"].mean()
               for frac in ZONE_FRACS},
            "median_dist_to_top20_km": sub["dist_to_top20_km"].median(),
            "mean_heldout_log_density": sub["heldout_log_density"].mean(),
        }

    summary = pd.DataFrame([
        summarize("all_centroids", per),
        summarize("largest_per_day_by_area", per[per["is_daily_max"]]),
        summarize("largest_per_event_by_area", per[per["is_event_max"]]),
    ])

    per_csv = os.path.join(OUT_DIR, "per_centroid_risk_zone_validation.csv")
    sum_csv = os.path.join(OUT_DIR, "risk_zone_summary_by_centroid_type.csv")
    per.to_csv(per_csv, index=False)
    summary.to_csv(sum_csv, index=False)

    s_all = summary.iloc[0]
    headline = float(s_all["mean_dist_to_top20_km"])
    d10 = float(s_all["mean_dist_to_top10_km"])
    d30 = float(s_all["mean_dist_to_top30_km"])
    d50 = float(s_all["mean_dist_to_top50_km"])

    # ---- figure: concentration quantiles, hit rates, distance-to-zone --------
    fig, (axq, axh, axd) = plt.subplots(1, 3, figsize=(13.8, 4.4))

    # (a) held-out risk-quantile distribution vs no-skill uniform
    axq.hist(per["heldout_risk_quantile"], bins=20, range=(0, 1),
             color="0.88", edgecolor="black", linewidth=0.8, zorder=3)
    axq.axhline(len(per) / 20.0, color=C_ACC, lw=1.6, ls="--", zorder=4)
    axq.text(0.02, len(per) / 20.0 + 2, "no-skill (uniform)", fontsize=8.5,
             color=C_ACC, va="bottom")
    axq.set_xlabel("Held-out centroid-concentration quantile", fontsize=10.5)
    axq.set_ylabel("Centroids", fontsize=10.5)
    axq.set_title("(a) Concentration quantiles of unseen centroids",
                  fontsize=11, pad=8)

    # (b) hit rates by group vs no-skill expectation
    groups = ["All", "Largest/day", "Largest/event"]
    n_z = len(ZONE_FRACS)
    width = 0.76 / n_z
    xg = np.arange(3)
    greys = ["0.80", "0.62", "0.44", "0.26"][:n_z]
    for i, frac in enumerate(ZONE_FRACS):
        vals = summary[f"top{int(frac*100)}_hit_rate"].to_numpy(float)
        axh.bar(xg + (i - (n_z - 1) / 2) * width, vals, width=width,
                color=greys[i], edgecolor="black",
                linewidth=0.7, zorder=3, label=f"Top {int(frac*100)}%")
        axh.axhline(frac, color=C_ACC, lw=1.0, ls="--", zorder=2)
    axh.set_xticks(xg)
    axh.set_xticklabels(groups, fontsize=9)
    axh.set_ylabel("Hit rate", fontsize=10.5)
    axh.set_ylim(0, 1)
    axh.legend(fontsize=8, frameon=False, loc="upper left")
    axh.text(2.42, ZONE_FRACS[-1] + 0.015, "no-skill", fontsize=7.5,
             color=C_ACC, ha="right")
    axh.set_title("(b) Zone hit rates (dashed = no skill)", fontsize=11, pad=8)

    # (c) distance to nearest zone
    box_data = [per[f"dist_to_top{int(frac*100)}_km"] for frac in ZONE_FRACS]
    box_pos = list(range(1, n_z + 1))
    zone_labels = [f"Top {int(frac*100)}%" for frac in ZONE_FRACS]
    axd.boxplot(box_data, positions=box_pos, widths=0.5,
                showfliers=False, patch_artist=True, whis=(5, 95),
                medianprops=dict(color="black", lw=1.5),
                boxprops=dict(facecolor="0.90", edgecolor="black", lw=0.9),
                whiskerprops=dict(color="black", lw=0.9),
                capprops=dict(color="black", lw=0.9))
    means = [d10, headline, d30, d50]
    axd.plot(box_pos, means, "x", color=C_ACC, ms=9, mew=2, zorder=5)
    for x, v in zip(box_pos, means):
        axd.text(x + 0.08, v, f"mean {v:.0f} km", fontsize=8.5, color=C_ACC,
                 va="center")
    axd.set_xticks(box_pos)
    axd.set_xticklabels(zone_labels, fontsize=9)
    axd.set_ylabel("Distance to nearest top-concentration zone (km)",
                   fontsize=10.5)
    axd.set_title("(c) Out-of-sample distance to top-concentration zones",
                  fontsize=11, pad=8)

    for ax in (axq, axh, axd):
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.tick_params(labelsize=9, colors="black")
        ax.grid(True, axis="y", color="0.92", lw=0.5, zorder=0)
        ax.set_axisbelow(True)

    fig.subplots_adjust(left=0.05, right=0.99, top=0.90, bottom=0.13,
                        wspace=0.26)
    fig_png = os.path.join(OUT_DIR, "risk_zone_validation_figure.png")
    fig_pdf = os.path.join(OUT_DIR, "risk_zone_validation_figure.pdf")
    fig.savefig(fig_png, dpi=600, bbox_inches="tight")
    fig.savefig(fig_pdf, bbox_inches="tight")
    plt.close(fig)

    # ---- standalone panel-C figure for the main paper -------------------------
    fig_s, ax_s = plt.subplots(figsize=(7.2, 5.0))
    ax_s.boxplot(box_data, positions=box_pos, widths=0.5,
                 showfliers=False, patch_artist=True, whis=(5, 95),
                 medianprops=dict(color="black", lw=1.5),
                 boxprops=dict(facecolor="0.90", edgecolor="black", lw=0.9),
                 whiskerprops=dict(color="black", lw=0.9),
                 capprops=dict(color="black", lw=0.9))
    ax_s.plot(box_pos, means, "x", color=C_ACC, ms=9, mew=2, zorder=5)
    for x, v in zip(box_pos, means):
        ax_s.text(x + 0.09, v, f"mean {v:.0f} km", fontsize=9, color=C_ACC,
                  va="center")
    ax_s.set_xlim(0.5, n_z + 0.7)    # room for the mean annotations
    ax_s.set_xticks(box_pos)
    ax_s.set_xticklabels(zone_labels, fontsize=10)
    ax_s.set_ylabel("Distance to nearest top-concentration zone (km)",
                    fontsize=11)
    ax_s.set_title("Out-of-sample centroid distance to top-concentration zone",
                   fontsize=12, color="black", pad=10)
    ax_s.spines["top"].set_visible(False)
    ax_s.spines["right"].set_visible(False)
    ax_s.tick_params(labelsize=10, colors="black")
    ax_s.grid(True, axis="y", color="0.92", lw=0.5, zorder=0)
    ax_s.set_axisbelow(True)
    fig_s.tight_layout()
    solo_png = os.path.join(OUT_DIR, "risk_zone_distance_standalone.png")
    solo_pdf = os.path.join(OUT_DIR, "risk_zone_distance_standalone.pdf")
    fig_s.savefig(solo_png, dpi=600, bbox_inches="tight")
    fig_s.savefig(solo_pdf, bbox_inches="tight")
    plt.close(fig_s)

    # ---- written report --------------------------------------------------------
    rep = os.path.join(OUT_DIR, "RISK_ZONE_CV_REPORT.md")
    s_day = summary.iloc[1]
    s_evt = summary.iloc[2]
    with open(rep, "w", encoding="utf-8") as f:
        f.write(f"# Concentration-zone {CV.N_FOLDS}-fold cross-validation - "
                "four-variable centroid model (MAIN validation)\n\n")
        f.write("**What this is:** the model is a spatial intensity/"
                "concentration-surface model, NOT a direct point predictor, "
                "so this is **concentration-map spatial error**, not "
                "centroid-coordinate prediction error. It answers: *\"How "
                "far are unseen centroids from the areas the model predicts "
                "as high centroid concentration?\"*  Zones are defined on "
                "models trained WITHOUT the "
                f"evaluated centroids ({CV.N_FOLDS} folds, seed "
                f"{CV.SEED}, shuffled, every centroid held out exactly "
                "once; trend `~ lon + lat + mean_tmax_z + std_tmax_z` refit "
                "per fold). Top-concentration zones = grid cells covering the top "
                "10/20/30/50% of domain AREA by predicted intensity. Distance "
                "= 0 km when the centroid's grid cell is inside the zone, "
                "else haversine km to the nearest zone-cell center.\n\n")
        f.write("## Concentration-quantile and zone definitions\n\n")
        f.write("* The centroid-concentration quantile of a grid cell is "
                "the fraction of total domain AREA with predicted intensity "
                "<= that cell. **0.9 means the 90th percentile of predicted "
                "centroid concentration, NOT a 90% probability of "
                "occurrence.**\n")
        for frac in ZONE_FRACS:
            nom = round(1.0 - frac, 2)
            thr = np.mean(zone_thr[frac])
            f.write(f"* Top-{int(frac*100)}% concentration zone ~ "
                    f"concentration quantile >= "
                    f"{nom:.2f}; exact area-weighted threshold used = "
                    f"quantile >= {thr:.4f} (mean across the {CV.N_FOLDS} "
                    f"folds; range {min(zone_thr[frac]):.4f}-"
                    f"{max(zone_thr[frac]):.4f}).\n")
        f.write("* On the main map figure "
                "(`q1_four_variable_centroid_risk_map.png`) the colorbar "
                "spans the full 0-1 quantile range in 0.1 steps and is "
                "labeled as the quantile (0-1) of the LGCP predicted "
                "intensity lambda-hat x 10^6 per km^2.\n")
        f.write("* \"Largest centroid per day\" / \"largest centroid per "
                "event\" in the map legend are defined by ellipse AREA "
                "(largest `ellipse_area_km2` per event-day / per event).\n\n")
        f.write("## Headline result\n\n")
        f.write(f"**Mean out-of-sample distance from held-out centroids to "
                f"the nearest top-20% concentration zone: "
                f"{headline:.0f} km** (median "
                f"{float(s_all['median_dist_to_top20_km']):.0f} km; "
                f"top-10% zone: {d10:.0f} km, top-30% zone: {d30:.0f} km, "
                f"top-50% zone: {d50:.0f} km as sensitivity).\n\n")
        f.write("## Summary by centroid group (nested)\n\n")
        f.write("| metric | all | largest/day | largest/event |\n")
        f.write("|---|---|---|---|\n")
        f.write(f"| n | {int(s_all['n'])} | {int(s_day['n'])} | {int(s_evt['n'])} |\n")
        for lab, col, fmt in [
                ("mean concentration quantile", "mean_risk_quantile", "{:.3f}"),
                ("median concentration quantile", "median_risk_quantile", "{:.3f}"),
                ("min concentration quantile", "min_risk_quantile", "{:.3f}"),
                ("max concentration quantile", "max_risk_quantile", "{:.3f}"),
                ("top-10% hit rate (no-skill 0.10)", "top10_hit_rate", "{:.3f}"),
                ("top-20% hit rate (no-skill 0.20)", "top20_hit_rate", "{:.3f}"),
                ("top-30% hit rate (no-skill 0.30)", "top30_hit_rate", "{:.3f}"),
                ("top-50% hit rate (no-skill 0.50)", "top50_hit_rate", "{:.3f}"),
                ("mean dist to top-10% zone (km)", "mean_dist_to_top10_km", "{:.0f}"),
                ("mean dist to top-20% zone (km)", "mean_dist_to_top20_km", "{:.0f}"),
                ("mean dist to top-30% zone (km)", "mean_dist_to_top30_km", "{:.0f}"),
                ("mean dist to top-50% zone (km)", "mean_dist_to_top50_km", "{:.0f}"),
                ("median dist to top-20% zone (km)", "median_dist_to_top20_km", "{:.0f}"),
                ("mean held-out log density", "mean_heldout_log_density", "{:.3f}"),
        ]:
            f.write(f"| {lab} | {fmt.format(s_all[col])} | "
                    f"{fmt.format(s_day[col])} | {fmt.format(s_evt[col])} |\n")
        f.write("\n## Interpretation\n\n")
        f.write(f"Unseen centroids sit on average {headline:.0f} km from the "
                "nearest area the model flags as a top-20% concentration "
                "zone; a held-out "
                f"centroid lands inside that top-20% area "
                f"{100*float(s_all['top20_hit_rate']):.0f}% of the time "
                "(no-skill expectation 20%). The mean held-out "
                "centroid-concentration quantile "
                f"is {float(s_all['mean_risk_quantile']):.2f} "
                "(0.50 = no skill).\n\n")
        f.write("**Supplementary:** the center-of-mass CV "
                "(`KFOLD_CV_REPORT.md`) is retained only as a "
                "stability/unbiasedness diagnostic of the surface's central "
                "placement; it is NOT the main validation because the "
                "surface's center of mass mathematically tracks the training "
                "sample's mean location for a model containing lon/lat "
                "terms.\n\n")
        f.write("## Files\n\n")
        f.write("* `per_centroid_risk_zone_validation.csv` - 760-row "
                "out-of-sample table (one row per centroid)\n")
        f.write("* `risk_zone_summary_by_centroid_type.csv` - nested group "
                "summary\n")
        f.write("* `risk_zone_validation_figure.png/.pdf` (legacy file name) "
                "- concentration quantiles, "
                "hit rates, distance-to-zone\n")

    print("\n[SUMMARY BY GROUP]")
    print(summary.to_string(index=False))
    print(f"\n[HEADLINE] mean out-of-sample distance to nearest TOP-20% "
          f"concentration zone = {headline:.1f} km "
          f"(top-10%: {d10:.1f} km, top-30%: {d30:.1f} km, "
          f"top-50%: {d50:.1f} km)")
    for pth in (per_csv, sum_csv, fig_png, fig_pdf, rep):
        print("[SAVED]", pth)
    print("[DONE]")


if __name__ == "__main__":
    main()
