#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stage 1 of the centroid spatial-risk LGCP workflow (PYTHON / data prep).

Builds every input the R/spatstat LGCP stage needs:
  * validated 760 all-ellipse centroid point pattern
  * historical ERA5 Tmax covariate grid over ALL valid 1-degree boxes
    (mean, std, CV, standardized) computed from the FULL daily record
  * Lambert azimuthal equal-area (LAEA) projected x/y (km) for boxes + centroids
  * nearest-box covariate assignment for each centroid (diagnostics)
  * grid-cell centroid counts (zeros included) for the Poisson count diagnostic
  * a regular projected pixel grid carrying lon/lat/mean_tmax_z/cv_tmax_z, which
    R reshapes into spatstat `im` covariate images + observation window.

NOTHING here fits the model; that is the R stage. No previous output is touched.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd
from pyproj import CRS, Transformer

# --- release wiring ----------------------------------------------------------
import argparse

_THIS = os.path.abspath(__file__)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_THIS)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "figures", "common"))
from _clean_paths import GENERATED_DIR, MASTER_CSV as _DEPOSIT_MASTER  # noqa: E402

OUT_DIR = os.path.join(GENERATED_DIR, "lgcp_inputs")
os.makedirs(OUT_DIR, exist_ok=True)

_ap = argparse.ArgumentParser(
    description="Build the R/spatstat LGCP stage inputs (Tier B).")
_ap.add_argument(
    "--master", default=os.environ.get("SCORCH_MASTER_FILE", _DEPOSIT_MASTER),
    help="760-row event-global-max master CSV (default: deposit catalog)")
_ap.add_argument(
    "--tmax-long-csv", default=os.environ.get("SCORCH_ERA5_TMAX_LONG_CSV", ""),
    help="full-record per-box daily Tmax long CSV "
         "(master_exceed_heatwaves_long.csv, produced by "
         "scripts/pipeline/build_master_dataset.py; ~1.8 GB, NOT "
         "redistributed -- see docs/SOURCE_DOWNLOAD_GUIDE.md)")
_args, _ = _ap.parse_known_args()
CENTROID_CSV = _args.master

# Historical daily ERA5 Tmax record (per-box, per-day, FULL record incl.
# non-heatwave days). Column `val` is daily Tmax (degC).
TMAX_LONG_CSV = _args.tmax_long_csv

EXPECTED_CENTROIDS = 760
PIXEL_KM = 25.0   # resolution of the regular projected covariate raster

_checks = []


def check(name, ok, detail=""):
    _checks.append({"check": name, "pass": bool(ok), "detail": str(detail)})
    flag = "PASS" if ok else "FAIL"
    print(f"[{flag}] {name}: {detail}")
    return ok


# -----------------------------------------------------------------------------
# 1) Validate centroids
# -----------------------------------------------------------------------------
def load_centroids():
    df = pd.read_csv(CENTROID_CSV)
    check("centroid_file_exists", True, CENTROID_CSV)
    check("centroid_row_count_760", len(df) == EXPECTED_CENTROIDS,
          f"rows={len(df)} (expected {EXPECTED_CENTROIDS})")
    has_lon = "centroid_lon" in df.columns
    has_lat = "centroid_lat" in df.columns
    check("centroid_lon_lat_present", has_lon and has_lat,
          f"centroid_lon={has_lon} centroid_lat={has_lat}")
    nmiss = int(df["centroid_lon"].isna().sum() + df["centroid_lat"].isna().sum())
    check("no_missing_centroids", nmiss == 0, f"missing={nmiss}")
    check("events_51", df["new_event_id"].nunique() == 51,
          f"events={df['new_event_id'].nunique()}")
    check("event_days_395", df["date"].nunique() == 395,
          f"event_days={df['date'].nunique()}")
    df = df.copy()
    df.insert(0, "centroid_id", np.arange(1, len(df) + 1))
    return df


# -----------------------------------------------------------------------------
# 2) Historical Tmax aggregation over the FULL daily record (chunked)
# -----------------------------------------------------------------------------
def aggregate_tmax():
    print(f"[INFO] aggregating historical Tmax from {TMAX_LONG_CSV}")
    check("tmax_record_exists", os.path.exists(TMAX_LONG_CSV), TMAX_LONG_CSV)
    if not os.path.exists(TMAX_LONG_CSV):
        raise FileNotFoundError(TMAX_LONG_CSV)

    # accumulators keyed by (lon, lat)
    n = {}      # day count
    s1 = {}     # sum val
    s2 = {}     # sum val^2
    dmin, dmax = None, None
    nrows = 0
    reader = pd.read_csv(TMAX_LONG_CSV,
                         usecols=["date", "lat1", "lon1", "val"],
                         chunksize=2_000_000)
    for ci, ch in enumerate(reader):
        ch = ch.dropna(subset=["val"])
        nrows += len(ch)
        cmin, cmax = ch["date"].min(), ch["date"].max()
        dmin = cmin if dmin is None else min(dmin, cmin)
        dmax = cmax if dmax is None else max(dmax, cmax)
        g = ch.groupby(["lon1", "lat1"])["val"]
        cnt = g.count()
        ssum = g.sum()
        ssq = g.apply(lambda v: float(np.sum(np.square(v))))
        for k, v in cnt.items():
            n[k] = n.get(k, 0) + int(v)
        for k, v in ssum.items():
            s1[k] = s1.get(k, 0.0) + float(v)
        for k, v in ssq.items():
            s2[k] = s2.get(k, 0.0) + float(v)
        print(f"  chunk {ci}: rows={len(ch)} cumulative={nrows} "
              f"cells={len(n)} dates[{cmin}..{cmax}]")

    rows = []
    for (lon, lat), cnt in n.items():
        mean = s1[(lon, lat)] / cnt
        var = max(0.0, s2[(lon, lat)] / cnt - mean * mean)  # population var
        std = float(np.sqrt(var))
        cv = std / mean if mean != 0 else float("nan")
        rows.append((float(lon), float(lat), int(cnt), mean, std, cv))
    grid = pd.DataFrame(rows, columns=["lon", "lat", "n_days",
                                       "mean_tmax", "std_tmax", "cv_tmax"])
    grid = grid.sort_values(["lat", "lon"]).reset_index(drop=True)
    grid.insert(0, "grid_id", np.arange(1, len(grid) + 1))
    return grid, dict(date_start=str(dmin), date_end=str(dmax),
                      total_rows=int(nrows))


# -----------------------------------------------------------------------------
# 3) Projection (LAEA centered on domain midpoint)
# -----------------------------------------------------------------------------
def make_projection(grid):
    lon0 = float((grid["lon"].min() + grid["lon"].max()) / 2.0)
    lat0 = float((grid["lat"].min() + grid["lat"].max()) / 2.0)
    crs = CRS.from_proj4(
        f"+proj=laea +lat_0={lat0} +lon_0={lon0} +x_0=0 +y_0=0 "
        f"+ellps=WGS84 +units=m +no_defs")
    tf = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    return tf, lon0, lat0


def project(tf, lon, lat):
    x, y = tf.transform(np.asarray(lon), np.asarray(lat))
    return np.asarray(x) / 1000.0, np.asarray(y) / 1000.0  # km


# -----------------------------------------------------------------------------
# Build everything
# -----------------------------------------------------------------------------
def main():
    if not TMAX_LONG_CSV:
        raise SystemExit(
            "Set SCORCH_ERA5_TMAX_LONG_CSV (or pass --tmax-long-csv) to the "
            "master_exceed_heatwaves_long.csv produced by "
            "scripts/pipeline/build_master_dataset.py. This ~1.8 GB Tier-B "
            "input is not redistributed with the release.")
    cen = load_centroids()
    grid, period = aggregate_tmax()

    check("grid_box_count_~1800", 1500 <= len(grid) <= 2200,
          f"valid boxes={len(grid)} (expected ~1800)")
    finite = np.isfinite(grid[["lon", "lat", "mean_tmax", "std_tmax",
                               "cv_tmax"]].to_numpy()).all()
    check("grid_covariates_finite", bool(finite), "all lon/lat/mean/std/cv finite")

    tf, lon0, lat0 = make_projection(grid)
    grid["x_km"], grid["y_km"] = project(tf, grid["lon"], grid["lat"])
    cen["x_km"], cen["y_km"] = project(tf, cen["centroid_lon"], cen["centroid_lat"])

    # standardized predictors (over grid boxes = the prediction surface)
    mu_m, sd_m = grid["mean_tmax"].mean(), grid["mean_tmax"].std(ddof=0)
    mu_c, sd_c = grid["cv_tmax"].mean(), grid["cv_tmax"].std(ddof=0)
    grid["mean_tmax_z"] = (grid["mean_tmax"] - mu_m) / sd_m
    grid["cv_tmax_z"] = (grid["cv_tmax"] - mu_c) / sd_c

    grid_cols = ["grid_id", "lon", "lat", "x_km", "y_km", "n_days",
                 "mean_tmax", "std_tmax", "cv_tmax", "mean_tmax_z", "cv_tmax_z"]
    grid_out = grid[grid_cols].copy()
    grid_out.to_csv(os.path.join(OUT_DIR, "tmax_covariate_grid_all_boxes.csv"),
                    index=False)

    # --- nearest-box assignment for each centroid (diagnostics only) ---
    from sklearn.neighbors import NearestNeighbors
    gxy = grid[["x_km", "y_km"]].to_numpy()
    nn = NearestNeighbors(n_neighbors=1).fit(gxy)
    dist, idx = nn.kneighbors(cen[["x_km", "y_km"]].to_numpy())
    idx = idx.ravel()
    near = grid.iloc[idx].reset_index(drop=True)
    cen_out = pd.DataFrame({
        "centroid_id": cen["centroid_id"].values,
        "new_event_id": cen["new_event_id"].values,
        "event_id": cen.get("event_id", pd.Series([np.nan] * len(cen))).values,
        "date": cen["date"].values,
        "v3_type": cen.get("v3_type", pd.Series([np.nan] * len(cen))).values,
        "event_type_name": cen.get("event_type_name",
                                   pd.Series([""] * len(cen))).values,
        "centroid_lon": cen["centroid_lon"].values,
        "centroid_lat": cen["centroid_lat"].values,
        "x_km": cen["x_km"].values, "y_km": cen["y_km"].values,
        "nearest_grid_id": near["grid_id"].values,
        "nearest_grid_lon": near["lon"].values,
        "nearest_grid_lat": near["lat"].values,
        "mean_tmax": near["mean_tmax"].values,
        "std_tmax": near["std_tmax"].values,
        "cv_tmax": near["cv_tmax"].values,
        "mean_tmax_z": near["mean_tmax_z"].values,
        "cv_tmax_z": near["cv_tmax_z"].values,
        "nearest_grid_dist_km": dist.ravel(),
    })
    cen_out.to_csv(
        os.path.join(OUT_DIR, "centroid_points_with_nearest_grid_covariates.csv"),
        index=False)
    check("centroid_match_distance_reasonable",
          float(dist.max()) < 120.0,
          f"max nearest-box distance={float(dist.max()):.1f} km (<~1 box diag)")

    # validated centroid pattern (lean, for the ppp)
    val_cols = ["centroid_id", "new_event_id", "event_id", "date", "v3_type",
                "event_type_name", "centroid_lon", "centroid_lat", "x_km", "y_km"]
    have = [c for c in val_cols if c in cen.columns]
    cen[have].to_csv(
        os.path.join(OUT_DIR, "centroid_points_all_ellipses_validated.csv"),
        index=False)

    # --- grid-cell counts (zeros included) for the Poisson count diagnostic ---
    counts = (pd.Series(near["grid_id"].values).value_counts()
              .rename("centroid_count"))
    gc = grid_out.copy()
    gc["centroid_count"] = gc["grid_id"].map(counts).fillna(0).astype(int)
    gc.to_csv(os.path.join(OUT_DIR, "grid_cell_counts_for_poisson.csv"),
              index=False)
    check("grid_counts_sum_eq_760", int(gc["centroid_count"].sum()) == len(cen),
          f"sum counts={int(gc['centroid_count'].sum())}")
    check("grid_counts_has_zeros", int((gc['centroid_count'] == 0).sum()) > 0,
          f"zero-count boxes={int((gc['centroid_count'] == 0).sum())}")

    # --- regular projected covariate raster for spatstat im() + window ---
    pad = PIXEL_KM
    x0, x1 = grid["x_km"].min() - pad, grid["x_km"].max() + pad
    y0, y1 = grid["y_km"].min() - pad, grid["y_km"].max() + pad
    xs = np.arange(x0 + PIXEL_KM / 2, x1, PIXEL_KM)
    ys = np.arange(y0 + PIXEL_KM / 2, y1, PIXEL_KM)
    XX, YY = np.meshgrid(xs, ys)            # shape (ny, nx)
    pix = np.column_stack([XX.ravel(), YY.ravel()])
    pdist, pidx = nn.kneighbors(pix)        # nearest ERA5 box to each pixel
    pdist = pdist.ravel()
    pidx = pidx.ravel()
    inside = pdist <= (PIXEL_KM + 80.0)     # mask pixels far from any box
    near_pix = grid.iloc[pidx].reset_index(drop=True)
    rast = pd.DataFrame({
        "ix": np.tile(np.arange(len(xs)), len(ys)),
        "iy": np.repeat(np.arange(len(ys)), len(xs)),
        "x_km": pix[:, 0], "y_km": pix[:, 1],
        "inside": inside.astype(int),
        "lon": near_pix["lon"].values, "lat": near_pix["lat"].values,
        "mean_tmax": near_pix["mean_tmax"].values,
        "cv_tmax": near_pix["cv_tmax"].values,
        "mean_tmax_z": near_pix["mean_tmax_z"].values,
        "cv_tmax_z": near_pix["cv_tmax_z"].values,
    })
    # lon/lat covariate images: use the actual pixel lon/lat (inverse projection)
    tf_inv = Transformer.from_crs(tf.target_crs, "EPSG:4326", always_xy=True)
    plon, plat = tf_inv.transform(pix[:, 0] * 1000.0, pix[:, 1] * 1000.0)
    rast["pixel_lon"] = plon
    rast["pixel_lat"] = plat
    rast.to_csv(os.path.join(OUT_DIR, "covariate_raster_km.csv"), index=False)
    raster_meta = dict(nx=int(len(xs)), ny=int(len(ys)), pixel_km=PIXEL_KM,
                       x0=float(xs[0]), y0=float(ys[0]),
                       x_step=PIXEL_KM, y_step=PIXEL_KM,
                       n_inside=int(inside.sum()))

    # all centroids must fall inside the raster window
    cdist, _ = nn.kneighbors(cen[["x_km", "y_km"]].to_numpy())
    all_inside = bool((cdist.ravel() <= (PIXEL_KM + 80.0)).all())
    check("all_centroids_inside_window", all_inside,
          "every centroid within masked covariate window")

    meta = dict(
        centroid_csv=os.path.relpath(CENTROID_CSV, REPO_ROOT),
        tmax_record=TMAX_LONG_CSV,
        tmax_period=period,
        n_centroids=int(len(cen)), n_grid_boxes=int(len(grid)),
        n_events=int(cen["new_event_id"].nunique()),
        n_event_days=int(cen["date"].nunique()),
        projection=f"LAEA lon_0={lon0:.4f} lat_0={lat0:.4f} (km)",
        lon0=lon0, lat0=lat0,
        tmax_standardization=dict(mean_tmax_mu=float(mu_m), mean_tmax_sd=float(sd_m),
                                  cv_tmax_mu=float(mu_c), cv_tmax_sd=float(sd_c)),
        raster=raster_meta,
        domain=dict(lon_min=float(grid["lon"].min()), lon_max=float(grid["lon"].max()),
                    lat_min=float(grid["lat"].min()), lat_max=float(grid["lat"].max())),
        checks=_checks,
        all_checks_pass=bool(all(c["pass"] for c in _checks)),
    )
    with open(os.path.join(OUT_DIR, "validation_summary.json"), "w",
              encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)

    print("\n=== SUMMARY ===")
    print(f"centroids={len(cen)}  grid_boxes={len(grid)}  "
          f"period={period['date_start']}..{period['date_end']}")
    print(f"raster: {raster_meta['nx']}x{raster_meta['ny']} px @ {PIXEL_KM}km, "
          f"inside={raster_meta['n_inside']}")
    print(f"all_checks_pass={meta['all_checks_pass']}")
    if not meta["all_checks_pass"]:
        print("[ERROR] one or more sanity checks FAILED", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
