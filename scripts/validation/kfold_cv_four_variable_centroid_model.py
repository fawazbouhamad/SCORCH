#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""5-fold cross-validation of the FOUR-VARIABLE centroid-concentration model.

Model under validation (the main model, "variant3" in the
LGCP diagnostics): an inhomogeneous point-process intensity over the 1800
valid 1-degree ERA5 boxes with log-linear trend

    log lambda(s) = b0 + b1*lon + b2*lat + b3*mean_tmax_z + b4*std_tmax_z

i.e. exactly longitude, latitude, mean Tmax and Tmax standard deviation.

WHAT THE MODEL OUTPUTS (checked against the code, not assumed):
The fitted model (spatstat kppm/ppm in
scripts/lgcp/spatial_risk_lgcp_model_diagnostics.R)
does NOT predict a point location. It outputs an intensity/density SURFACE
lambda(s) (events per km^2) over the study domain. The repo's own R
diagnostics note that the LGCP minimum-contrast fit estimates the trend by
Poisson likelihood, so the trend coefficients equal those of the Poisson
point-process fit. This script therefore refits the SAME four-variable
Poisson trend per fold via an exact Poisson GLM on per-box centroid counts
with offset log(box area km^2) - the standard discretized equivalent of the
continuous fit (the repo already builds grid_cell_counts_for_poisson.csv for
exactly this equivalence). As a sanity check the full-data Python
coefficients are compared against the R variant3 coefficients.

PREDICTED LOCATION (primary metric, per Dr. Najibi's spec):
The predicted surface is normalized into per-box probabilities
    p_i = lambda_i * A_i / sum_j(lambda_j * A_j)
(A_i = box area, so p_i is the probability mass that a centroid falls in
box i), and the probability-weighted expected location is
    lon_hat = sum_i(lon_i * p_i),  lat_hat = sum_i(lat_i * p_i).
A MAP (highest-density box) location is also computed as a diagnostic.

OBSERVED HELD-OUT LOCATION (explicit choice):
The model produces ONE predicted distribution per fold (it cannot produce a
different point per held-out centroid), so the fold-level comparison is
    predicted expected location  vs  MEAN lon/lat of the held-out centroids.
Per-centroid distances from each held-out centroid to the predicted expected
location are ALSO computed (secondary; they mix model bias with the natural
spatial spread of centroids) so a median "pure distance" is available.

CROSS-VALIDATION DESIGN (5-fold since 2026-07-09, per Dr. Najibi; was
10-fold):
  * all centroids (count computed from the data, expected ~760)
  * shuffled ONCE with a fixed seed (SEED below) - NOT chronological
  * split into 5 folds; each centroid held out exactly once
  * per fold: train on ~80% -> refit the 4-variable trend -> predict surface
    -> compare against the held-out ~20%
  * extra scores per fold: mean held-out log predictive density (log of the
    normalized per-km^2 density at each held-out centroid's box) and the mean
    concentration-quantile of held-out boxes under the trained surface.

Outputs (new files only; nothing existing is modified):
    reproduced/validation_kfold/
            fold_metrics.csv            (5 rows, one per fold)
            per_centroid_distances.csv  (760 rows)
            cv_summary.csv              (final averaged metrics)
            KFOLD_CV_REPORT.md          (plain-English interpretation)

Run:  python scripts/validation/kfold_cv_four_variable_centroid_model.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_THIS = os.path.abspath(__file__)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_THIS)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "figures", "common"))
from _clean_paths import DATA_DIR, GENERATED_DIR, data_file  # noqa: E402

# Deposit-layout defaults; override via --data-dir (main) or configure().
SR_DIR = DATA_DIR
VARIANTS_CSV = data_file("grid_predicted_intensity_all_variants.csv", "lgcp")
CENTROIDS_CSV = data_file(
    "centroid_points_with_nearest_grid_covariates.csv", "lgcp")
R_PARAMS_CSV = data_file("lgcp_model_parameters.csv", "lgcp")
OUT_DIR = os.path.join(GENERATED_DIR, "validation_kfold")


def configure(data_dir: str) -> None:
    """Re-point the module inputs at a different deposit-layout data dir."""
    global SR_DIR, VARIANTS_CSV, CENTROIDS_CSV, R_PARAMS_CSV
    SR_DIR = data_dir
    VARIANTS_CSV = os.path.join(
        data_dir, "lgcp", "grid_predicted_intensity_all_variants.csv")
    CENTROIDS_CSV = os.path.join(
        data_dir, "lgcp", "centroid_points_with_nearest_grid_covariates.csv")
    R_PARAMS_CSV = os.path.join(data_dir, "lgcp", "lgcp_model_parameters.csv")

SEED = 20260704          # reproducible shuffle (date of Dr. Najibi's request)
N_FOLDS = 5              # one shuffle, 5 folds (~20% held out each; was 10)
PREDICTORS = ["lon", "lat", "mean_tmax_z", "std_tmax_z"]   # the 4 variables

KM_PER_DEG_LAT = 110.574
KM_PER_DEG_LON_EQ = 111.320


def haversine_km(lon1, lat1, lon2, lat2):
    """Great-circle distance in km (vectorized)."""
    lon1, lat1, lon2, lat2 = map(np.radians, (lon1, lat1, lon2, lat2))
    dlon, dlat = lon2 - lon1, lat2 - lat1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * np.arcsin(np.sqrt(a))


def poisson_glm_irls(X, y, offset, max_iter=200, tol=1e-10):
    """Exact unpenalized Poisson GLM with log link and offset (IRLS).

    y_i ~ Poisson(exp(offset_i + X_i @ beta)). Returns beta
    (intercept first). Tiny ridge (1e-9) only for numerical safety.
    """
    Xd = np.column_stack([np.ones(len(y)), X])
    beta = np.zeros(Xd.shape[1])
    # sensible intercept start: log(total count / total exposure)
    beta[0] = np.log(y.sum() / np.exp(offset).sum())
    for _ in range(max_iter):
        eta = offset + Xd @ beta
        mu = np.exp(np.clip(eta, -30, 30))
        W = mu                                  # Poisson IRLS weights
        z = eta - offset + (y - mu) / mu        # working response
        XtW = Xd.T * W
        H = XtW @ Xd + 1e-9 * np.eye(Xd.shape[1])
        beta_new = np.linalg.solve(H, XtW @ z)
        if np.max(np.abs(beta_new - beta)) < tol:
            beta = beta_new
            break
        beta = beta_new
    return beta


def fit_surface(grid, train_counts):
    """Refit the 4-variable Poisson trend; return per-box intensity lambda_i
    (per km^2) and normalized per-box probability mass p_i."""
    X = grid[PREDICTORS].to_numpy(float)
    offset = np.log(grid["area_km2"].to_numpy(float))
    beta = poisson_glm_irls(X, train_counts.astype(float), offset)
    lam = np.exp(np.clip(np.column_stack([np.ones(len(grid)), X]) @ beta, -30, 30))
    mass = lam * grid["area_km2"].to_numpy(float)
    p = mass / mass.sum()
    return beta, lam, p


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    grid = pd.read_csv(VARIANTS_CSV)
    cen = pd.read_csv(CENTROIDS_CSV)
    for c in PREDICTORS + ["grid_id"]:
        assert c in grid.columns, f"missing grid column: {c}"
    for c in ("centroid_id", "centroid_lon", "centroid_lat", "nearest_grid_id"):
        assert c in cen.columns, f"missing centroid column: {c}"

    n_boxes = len(grid)
    n_cen = len(cen)
    print(f"[DATA] grid boxes = {n_boxes}; centroids = {n_cen} "
          f"(expected ~760; computed, not hard-coded)")

    # 1-degree box area in km^2 (varies with latitude)
    grid = grid.sort_values("grid_id").reset_index(drop=True)
    grid["area_km2"] = (KM_PER_DEG_LON_EQ *
                        np.cos(np.radians(grid["lat"])) * KM_PER_DEG_LAT)
    gid_to_row = pd.Series(grid.index.values, index=grid["grid_id"].values)
    cen = cen.copy()
    cen["grid_row"] = cen["nearest_grid_id"].map(gid_to_row)
    assert cen["grid_row"].notna().all(), "centroid with unknown nearest grid box"
    cen["grid_row"] = cen["grid_row"].astype(int)

    # ---- full-data sanity fit: must reproduce the R variant3 coefficients ----
    counts_all = np.bincount(cen["grid_row"], minlength=n_boxes)
    beta_full, lam_full, _ = fit_surface(grid, counts_all)
    print("[SANITY] full-data Python Poisson-GLM coefficients "
          "(intercept, lon, lat, mean_tmax_z, std_tmax_z):")
    print("         ", np.round(beta_full, 6).tolist())
    if os.path.exists(R_PARAMS_CSV):
        rp = pd.read_csv(R_PARAMS_CSV)
        rv3 = rp[(rp["model"] == "variant3") &
                 (rp["param_class"] == "fixed_effect")]
        r_map = dict(zip(rv3["parameter"], rv3["value"].astype(float)))
        r_vec = [r_map.get("(Intercept)"), r_map.get("lon"), r_map.get("lat"),
                 r_map.get("mean_tmax_z"), r_map.get("std_tmax_z")]
        print("[SANITY] R variant3 (spatstat) coefficients:")
        print("         ", [round(v, 6) for v in r_vec])
        diffs = np.abs(np.array(r_vec, float) - beta_full)
        print(f"[SANITY] max |Python - R| coefficient difference = {diffs.max():.4f}")

    # ---- reproducible shuffled k-fold split (N_FOLDS=5) ----------------------
    rng = np.random.default_rng(SEED)
    perm = rng.permutation(n_cen)
    folds = np.array_split(perm, N_FOLDS)
    held_out_once = np.sort(np.concatenate(folds))
    assert np.array_equal(held_out_once, np.arange(n_cen)), \
        "each centroid must be held out exactly once"
    print(f"[CV] seed={SEED}; {N_FOLDS} folds; fold sizes = "
          f"{[len(f) for f in folds]}")

    fold_rows = []
    per_centroid_rows = []
    for k, test_idx in enumerate(folds, start=1):
        test_mask = np.zeros(n_cen, bool)
        test_mask[test_idx] = True
        train = cen.loc[~test_mask]
        test = cen.loc[test_mask]

        counts_tr = np.bincount(train["grid_row"], minlength=n_boxes)
        beta, lam, p = fit_surface(grid, counts_tr)

        # probability-weighted expected location (PRIMARY prediction)
        lon_hat = float(np.sum(grid["lon"] * p))
        lat_hat = float(np.sum(grid["lat"] * p))
        # MAP / highest-density box (diagnostic)
        i_map = int(np.argmax(lam))
        lon_map, lat_map = float(grid.loc[i_map, "lon"]), float(grid.loc[i_map, "lat"])

        # observed held-out summary: mean lon/lat (explicit convention)
        lon_obs = float(test["centroid_lon"].mean())
        lat_obs = float(test["centroid_lat"].mean())

        bias_lon = lon_hat - lon_obs
        bias_lat = lat_hat - lat_obs
        dist_km = float(haversine_km(lon_hat, lat_hat, lon_obs, lat_obs))
        dist_map_km = float(haversine_km(lon_map, lat_map, lon_obs, lat_obs))

        # per-centroid distances to the predicted expected location (secondary)
        d_i = haversine_km(lon_hat, lat_hat,
                           test["centroid_lon"].to_numpy(),
                           test["centroid_lat"].to_numpy())
        for cid, dd in zip(test["centroid_id"], d_i):
            per_centroid_rows.append({"fold": k, "centroid_id": int(cid),
                                      "dist_to_pred_km": float(dd)})

        # held-out predictive scores
        dens = p / grid["area_km2"].to_numpy()          # normalized per-km^2 density
        test_rows = test["grid_row"].to_numpy()
        mean_log_dens = float(np.mean(np.log(dens[test_rows])))
        risk_q = pd.Series(lam).rank(pct=True).to_numpy()
        mean_risk_q = float(np.mean(risk_q[test_rows]))

        fold_rows.append({
            "fold": k, "n_train": len(train), "n_test": len(test),
            "obs_mean_lon": lon_obs, "obs_mean_lat": lat_obs,
            "pred_lon": lon_hat, "pred_lat": lat_hat,
            "map_lon": lon_map, "map_lat": lat_map,
            "bias_lon_deg": bias_lon, "bias_lat_deg": bias_lat,
            "dist_error_km": dist_km, "dist_error_map_km": dist_map_km,
            "median_percentroid_dist_km": float(np.median(d_i)),
            "heldout_mean_log_density": mean_log_dens,
            "heldout_mean_risk_quantile": mean_risk_q,
            "beta_intercept": beta[0], "beta_lon": beta[1], "beta_lat": beta[2],
            "beta_mean_tmax_z": beta[3], "beta_std_tmax_z": beta[4],
        })
        print(f"[FOLD {k:2d}] n_test={len(test):3d}  "
              f"pred=({lon_hat:6.2f}E,{lat_hat:5.2f}N)  "
              f"obs=({lon_obs:6.2f}E,{lat_obs:5.2f}N)  "
              f"bias_lon={bias_lon:+.3f} deg  bias_lat={bias_lat:+.3f} deg  "
              f"dist={dist_km:6.1f} km")

    fold_df = pd.DataFrame(fold_rows)
    percen_df = pd.DataFrame(per_centroid_rows)

    # ---- final summary across the 5 folds ------------------------------------
    tcrit95 = 2.776  # t(0.975, df=N_FOLDS-1=4)
    def s(col):
        v = fold_df[col].to_numpy(float)
        return (float(v.mean()), float(v.std(ddof=1)),
                float(v.std(ddof=1) / np.sqrt(len(v))))

    m_lon, sd_lon, se_lon = s("bias_lon_deg")
    m_lat, sd_lat, se_lat = s("bias_lat_deg")
    m_d, sd_d, se_d = s("dist_error_km")
    m_dmap, _, _ = s("dist_error_map_km")
    m_logd, _, _ = s("heldout_mean_log_density")
    m_rq, _, _ = s("heldout_mean_risk_quantile")
    med_percen = float(percen_df["dist_to_pred_km"].median())

    # degree biases in km at the mean observed latitude (for interpretation)
    lat0 = float(fold_df["obs_mean_lat"].mean())
    bias_lon_km = m_lon * KM_PER_DEG_LON_EQ * np.cos(np.radians(lat0))
    bias_lat_km = m_lat * KM_PER_DEG_LAT

    summary = pd.DataFrame([
        {"metric": "mean_bias_lon_deg", "value": m_lon, "sd_across_folds": sd_lon,
         "se": se_lon, "ci95_lo": m_lon - tcrit95 * se_lon,
         "ci95_hi": m_lon + tcrit95 * se_lon},
        {"metric": "mean_bias_lat_deg", "value": m_lat, "sd_across_folds": sd_lat,
         "se": se_lat, "ci95_lo": m_lat - tcrit95 * se_lat,
         "ci95_hi": m_lat + tcrit95 * se_lat},
        {"metric": "mean_bias_lon_km_at_mean_lat", "value": bias_lon_km,
         "sd_across_folds": np.nan, "se": np.nan,
         "ci95_lo": np.nan, "ci95_hi": np.nan},
        {"metric": "mean_bias_lat_km", "value": bias_lat_km,
         "sd_across_folds": np.nan, "se": np.nan,
         "ci95_lo": np.nan, "ci95_hi": np.nan},
        {"metric": "mean_dist_error_km", "value": m_d, "sd_across_folds": sd_d,
         "se": se_d, "ci95_lo": m_d - tcrit95 * se_d,
         "ci95_hi": m_d + tcrit95 * se_d},
        {"metric": "mean_dist_error_MAP_km", "value": m_dmap,
         "sd_across_folds": np.nan, "se": np.nan,
         "ci95_lo": np.nan, "ci95_hi": np.nan},
        {"metric": "median_per_centroid_dist_km", "value": med_percen,
         "sd_across_folds": np.nan, "se": np.nan,
         "ci95_lo": np.nan, "ci95_hi": np.nan},
        {"metric": "mean_heldout_log_density", "value": m_logd,
         "sd_across_folds": np.nan, "se": np.nan,
         "ci95_lo": np.nan, "ci95_hi": np.nan},
        {"metric": "mean_heldout_risk_quantile", "value": m_rq,
         "sd_across_folds": np.nan, "se": np.nan,
         "ci95_lo": np.nan, "ci95_hi": np.nan},
    ])

    fold_csv = os.path.join(OUT_DIR, "fold_metrics.csv")
    percen_csv = os.path.join(OUT_DIR, "per_centroid_distances.csv")
    summary_csv = os.path.join(OUT_DIR, "cv_summary.csv")
    report_md = os.path.join(OUT_DIR, "KFOLD_CV_REPORT.md")
    fold_df.to_csv(fold_csv, index=False)
    percen_df.to_csv(percen_csv, index=False)
    summary.to_csv(summary_csv, index=False)

    interp = (
        f"On average, the model's probability-weighted expected centroid "
        f"location is off by {m_d:.0f} km from the mean held-out centroid "
        f"location (SD across folds {sd_d:.0f} km, 95% CI "
        f"{m_d - tcrit95 * se_d:.0f}-{m_d + tcrit95 * se_d:.0f} km), with a "
        f"longitude bias of {m_lon:+.2f} deg (~{bias_lon_km:+.0f} km) and a "
        f"latitude bias of {m_lat:+.2f} deg (~{bias_lat_km:+.0f} km)."
    )

    with open(report_md, "w", encoding="utf-8") as f:
        f.write(f"# {N_FOLDS}-fold cross-validation - four-variable centroid "
                "model (SUPPLEMENTARY)\n\n")
        f.write("> **SUPPLEMENTARY diagnostic only.** The MAIN out-of-sample "
                "validation is `RISK_ZONE_CV_REPORT.md` (distance from "
                "held-out centroids to predicted top-concentration zones). The "
                "center-of-mass metric below only tests the stability and "
                "unbiasedness of the surface's central placement: for a "
                "model containing lon/lat terms, the fitted surface's center "
                "of mass mathematically tracks the training sample's mean "
                "location, so this number should not be read as model "
                "prediction skill.\n\n")
        f.write("Model: Poisson point-process intensity trend "
                "`~ lon + lat + mean_tmax_z + std_tmax_z` (identical trend to "
                "the LGCP variant3 fit; the LGCP minimum-contrast method "
                "estimates its trend by Poisson likelihood).\n\n")
        f.write(f"* Centroids: {n_cen} (computed from data)\n")
        f.write(f"* Folds: {N_FOLDS}, shuffled with seed {SEED} "
                "(not chronological); each centroid held out exactly once\n")
        f.write("* Primary prediction: probability-weighted expected lon/lat "
                "of the normalized predicted surface "
                "(`p_i = lambda_i*A_i / sum`, `lon_hat = sum(lon_i*p_i)`), "
                "compared against the MEAN lon/lat of the held-out centroids "
                "(one predicted distribution per fold; the model outputs a "
                "density surface, not per-centroid points)\n")
        f.write("* MAP (highest-density grid cell) reported as a "
                "diagnostic\n")
        f.write("* Distances: haversine (km)\n\n")
        f.write("## Result\n\n")
        f.write(interp + "\n\n")
        f.write(f"The MAP location is a poorer point summary "
                f"(mean error {m_dmap:.0f} km), as expected for a spread-out "
                "density. Median per-centroid distance to the predicted "
                f"expected location is {med_percen:.0f} km; this mixes model "
                "bias with the natural spatial spread of centroids, so the "
                "fold-level numbers above are the primary bias metric.\n\n")
        f.write(f"Mean held-out log predictive density: {m_logd:.3f}; "
                f"mean held-out concentration quantile: {m_rq:.3f} "
                "(0.5 = no better than uniform ranking; higher = held-out "
                "centroids fall in grid cells the trained model ranks as "
                "higher concentration).\n\n")
        f.write("## Files\n\n")
        f.write("* `fold_metrics.csv` - one row per fold\n")
        f.write("* `per_centroid_distances.csv` - per held-out centroid\n")
        f.write("* `cv_summary.csv` - averaged metrics with SD/SE/95% CI\n")

    print("\n[SUMMARY]")
    print(summary.to_string(index=False))
    print("\n[INTERPRETATION]", interp)
    print("[SAVED]", fold_csv)
    print("[SAVED]", percen_csv)
    print("[SAVED]", summary_csv)
    print("[SAVED]", report_md)
    print("[DONE]")


if __name__ == "__main__":
    main()
