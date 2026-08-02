#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SCORCH pipeline stage 2: heatwave detection on daily ERA5 Tmax.

Sanitized public-release copy of the canonical
the research repository's ``2_Heatwave_Algorithm.py``. The ONLY change is that
the hard-coded ``DATADIR`` placeholder became a required ``--datadir``
command-line argument (with optional ``--outdir``); every numeric constant,
threshold and labelling rule is preserved verbatim
(see docs/SANITIZATION_NOTES.md).

Input : a folder of ``{year}_daily_Tmax.nc`` files (produced by
        scripts/download/download_era5_arco.py or the CDS route; the older
        ``{year}_daily.nc`` naming is also accepted).
Output: ``master_exceed_heatwaves_long.csv`` (per-box daily values, p95
        thresholds, exceedance flags, heatwave ids), ``episodes_catalog.csv``
        and per-box daily CSVs, under ``<outdir>``.

Usage:
    python scripts/pipeline/build_master_dataset.py --datadir /path/to/nc \\
        [--outdir /path/to/output]
"""

import argparse
import os
import glob
import warnings
import numpy as np
import pandas as pd
import xarray as xr

warnings.filterwarnings("ignore", category=FutureWarning)
os.environ.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")

# =================== CONFIG (canonical constants; do not edit) ==============
# Region of interest
LAT_MIN, LAT_MAX = 10.0, 46.0    # degN
LON_MIN, LON_MAX = 20.0, 70.0    # degE

# 1 deg x 1 deg box aggregation: "mean" (stable) or "max" (hotspotty)
BOX_AGG = "mean"

# Variable and coordinate names
VAR_TMAX  = "Tmax_C"                   # daily Tmax variable
LAT_CANDS = ("latitude", "lat")
LON_CANDS = ("longitude", "lon")
TIME_NAME = "time"


MONTHS = [4, 5, 6, 7, 8, 9]

# Baseline years for thresholds, inclusive (None = all years found)
BASELINE_YEARS = None

# Performance
CHUNK_TIME = 366  # per-file read chunk along time
# ===========================================================================

# Path globals; set from the command line in main() (release sanitization:
# the canonical script hard-coded DATADIR here).
DATADIR = None
FILE_GLOB = None
FILE_GLOB_FALLBACK = None
OUTDIR = None
OUT_MASTER = None
OUT_EPISODES = None
OUT_PER_BOX_DIR = None


def _configure_paths(datadir: str, outdir: str | None) -> None:
    global DATADIR, FILE_GLOB, FILE_GLOB_FALLBACK, OUTDIR
    global OUT_MASTER, OUT_EPISODES, OUT_PER_BOX_DIR
    DATADIR = datadir
    # Script 1 (download) writes "{year}_daily_Tmax.nc". Primary pattern
    # matches that; fallback keeps older "*_daily.nc" naming working.
    FILE_GLOB = os.path.join(DATADIR, "*_daily_Tmax.nc")
    FILE_GLOB_FALLBACK = os.path.join(DATADIR, "*_daily.nc")
    OUTDIR = outdir or os.path.join(DATADIR, "p95_exceed_heatwaves_1deg_flat")
    OUT_MASTER = os.path.join(OUTDIR, "master_exceed_heatwaves_long.csv")
    OUT_EPISODES = os.path.join(OUTDIR, "episodes_catalog.csv")
    OUT_PER_BOX_DIR = os.path.join(OUTDIR, "per_box_daily")


def open_nc_safe(path):
    """Open a NetCDF robustly (netcdf4 -> h5netcdf -> default), with time chunking."""
    try:
        return xr.open_dataset(path, engine="netcdf4", chunks={TIME_NAME: CHUNK_TIME})
    except Exception:
        try:
            return xr.open_dataset(path, engine="h5netcdf", chunks={TIME_NAME: CHUNK_TIME})
        except Exception:
            return xr.open_dataset(path, chunks={TIME_NAME: CHUNK_TIME})


def detect_coords(ds):
    """Return (lat_name, lon_name) from candidate coord names."""
    lat_name = next((nm for nm in LAT_CANDS if nm in ds.coords), None)
    lon_name = next((nm for nm in LON_CANDS if nm in ds.coords), None)
    if lat_name is None or lon_name is None:
        raise KeyError(f"Could not find lat/lon coords in {list(ds.coords)}")
    return lat_name, lon_name


def normalize_lon(var, lon_name):
    """Normalize longitudes to [-180, 180], sort by lon ascending."""
    lon = var[lon_name]
    if float(lon.max()) > 180.0:
        lon_new = (((lon + 180) % 360) - 180)
        order = np.argsort(lon_new.values)
        var = var.assign_coords({lon_name: lon_new}).isel({lon_name: order})
    return var


def clip_region(var, lat_name, lon_name):
    """Clip to region, handling ascending/descending latitude ordering."""
    lat = var[lat_name]
    lat_asc = bool(lat[0] < lat[-1])
    lat_slice = slice(LAT_MIN, LAT_MAX) if lat_asc else slice(LAT_MAX, LAT_MIN)
    return var.sel({lat_name: lat_slice, lon_name: slice(LON_MIN, LON_MAX)})


def filter_months(var):
    """Subset by MONTHS if provided."""
    if MONTHS is None:
        return var
    t = pd.DatetimeIndex(var[TIME_NAME].values)
    mask = np.isin(t.month, MONTHS)
    return var.sel({TIME_NAME: var[TIME_NAME].values[mask]})


def to_boxes_dataframe(field2d, lat_name, lon_name, date_val):
    """
    Flatten a 2D field to rows and assign 1 deg x 1 deg box centers (.5).
    Returns DataFrame: [date, lat1, lon1, val]
    """
    stacked = field2d.stack(point=(lat_name, lon_name))
    df = pd.DataFrame({
        "lat": stacked[lat_name].values.astype(float),
        "lon": stacked[lon_name].values.astype(float),
        "val": stacked.values.astype(float)
    }).dropna()

    # Assign to 1 deg cells centered at .5
    df["lat1"] = np.floor(df["lat"]) + 0.5
    df["lon1"] = np.floor(df["lon"]) + 0.5

    # Keep only boxes fully inside region bounds
    df = df[(df["lat1"].between(LAT_MIN, LAT_MAX)) &
            (df["lon1"].between(LON_MIN, LON_MAX))]

    # Aggregate within each 1 deg cell
    if BOX_AGG.lower() == "max":
        out = df.groupby(["lat1", "lon1"], as_index=False)["val"].max()
    else:
        out = df.groupby(["lat1", "lon1"], as_index=False)["val"].mean()

    out["date"] = pd.to_datetime(date_val)
    return out[["date", "lat1", "lon1", "val"]]


def compute_p95_thresholds(all_box_daily):
    """
    Compute per-box p95 thresholds.
    all_box_daily: DataFrame [date, lat1, lon1, val]
    Applies BASELINE_YEARS and MONTHS (if set) to define the baseline subset.
    Returns: DataFrame [lat1, lon1, thr_p95]
    """
    df = all_box_daily.copy()

    if BASELINE_YEARS is not None:
        y0, y1 = BASELINE_YEARS
        df = df[(df["date"].dt.year >= y0) & (df["date"].dt.year <= y1)]

    if MONTHS is not None:
        df = df[df["date"].dt.month.isin(MONTHS)]

    thr = df.groupby(["lat1", "lon1"], as_index=False)["val"].quantile(0.95)
    thr = thr.rename(columns={"val": "thr_p95"})
    return thr


def ensure_datetime_index(series_like):
    """
    Ensure the input Series has a DatetimeIndex (robust against RangeIndex).
    Raises if conversion is impossible.
    """
    s = pd.Series(series_like)
    try:
        idx = pd.DatetimeIndex(s.index)
    except Exception as e:
        raise ValueError(
            "Expected a DatetimeIndex for the exceedance series. "
            "Make sure to set_index('date') before passing."
        ) from e

    if idx.tz is not None:
        idx = idx.tz_convert(None)

    s.index = idx
    if s.index.isna().any():
        raise ValueError("DatetimeIndex contains NaT values.")
    return s


def label_heatwaves(
    exceed_series,
    min_len=3,
    min_ones=3,  # UPDATED: require at least 3 exceedance days
    allow_unlimited_single_zeros=True
):
    """
    Label heatwaves in a 0/1 daily exceedance series.

    UPDATED BEHAVIOR:
    - Split by any "00" (two consecutive zeros).
    - For each segment, trim leading/trailing zeros so events START and END with '1'.
    - An event qualifies if:
        * trimmed length >= min_len
        * ones_count >= min_ones
      Unlimited single-zero gaps allowed inside the event if allow_unlimited_single_zeros=True.

    Returns
    -------
    labels : pd.Series of heatwave_id (0 if not in any), aligned to input index
    episodes : list of tuples (hw_id, start_date, end_date, length_days, ones_count, zeros_count)
    """
    s = ensure_datetime_index(exceed_series).astype(int)
    idx = s.index
    vals = s.values

    zero = (vals == 0)

    # Positions of the first zero in each "00"
    double_zero_breaks = np.where((zero[:-1]) & (zero[1:]))[0]

    # Build raw segments between "00" breaks (inclusive indices)
    boundaries = [-1] + double_zero_breaks.tolist() + [len(s) - 1]
    raw_segments = []
    for a, b in zip(boundaries[:-1], boundaries[1:]):
        i0, i1 = a + 1, b
        if i0 <= i1:
            raw_segments.append((i0, i1))

    hw_id = 0
    labels = pd.Series(0, index=idx, dtype=int)
    episodes = []

    for (i0, i1) in raw_segments:
        seg_vals = vals[i0:i1 + 1]

        # If there are no 1s, nothing to label
        if seg_vals.sum() == 0:
            continue

        # TRIM so event starts at first 1 and ends at last 1
        ones_pos = np.where(seg_vals == 1)[0]
        j0 = i0 + int(ones_pos[0])
        j1 = i0 + int(ones_pos[-1])

        event_vals = vals[j0:j1 + 1]
        ones_count  = int(event_vals.sum())
        zeros_count = int((event_vals == 0).sum())
        length_days = int(j1 - j0 + 1)

        if allow_unlimited_single_zeros:
            ok = (length_days >= min_len) and (ones_count >= min_ones)
        else:
            ok = (length_days >= min_len) and (ones_count >= min_ones) and (zeros_count <= 1)

        if ok:
            hw_id += 1
            labels.iloc[j0:j1 + 1] = hw_id
            episodes.append((
                hw_id,
                idx[j0].date(),
                idx[j1].date(),
                length_days,
                ones_count,
                zeros_count
            ))

    return labels, episodes


def main():
    ap = argparse.ArgumentParser(
        description="SCORCH heatwave detection on daily ERA5 Tmax NetCDFs.")
    ap.add_argument("--datadir", required=True,
                    help="folder with {year}_daily_Tmax.nc files")
    ap.add_argument("--outdir", default=None,
                    help="output folder (default: "
                         "<datadir>/p95_exceed_heatwaves_1deg_flat)")
    args = ap.parse_args()
    _configure_paths(args.datadir, args.outdir)

    os.makedirs(OUTDIR, exist_ok=True)
    os.makedirs(OUT_PER_BOX_DIR, exist_ok=True)

    files = sorted(glob.glob(FILE_GLOB))
    if not files:
        # Backward-compatible fallback for older "*_daily.nc" naming.
        files = sorted(glob.glob(FILE_GLOB_FALLBACK))
    if not files:
        raise FileNotFoundError(
            f"No files found matching {FILE_GLOB} or {FILE_GLOB_FALLBACK}"
        )

    all_rows = []
    lat_name = lon_name = None

    # 1) Sweep all files -> collect daily 1 deg box values into one long DataFrame
    for fp in files:
        ds = open_nc_safe(fp)

        if lat_name is None:
            lat_name, lon_name = detect_coords(ds)

        if VAR_TMAX not in ds:
            raise KeyError(f"'{VAR_TMAX}' not in {fp}. Found: {list(ds.data_vars)}")

        tmax = ds[VAR_TMAX]
        tmax = normalize_lon(tmax, lon_name)
        tmax = clip_region(tmax, lat_name, lon_name)
        tmax = filter_months(tmax)

        if tmax.sizes.get(TIME_NAME, 0) == 0:
            ds.close()
            continue

        dates = pd.to_datetime(tmax[TIME_NAME].values)

        # Process day-by-day (robust memory behavior)
        for i in range(len(dates)):
            field2d = tmax.isel({TIME_NAME: i}).load()
            day_df = to_boxes_dataframe(field2d, lat_name, lon_name, dates[i])
            all_rows.append(day_df)

        ds.close()

    if not all_rows:
        raise RuntimeError("No data after filtering by months/region.")

    all_box_daily = pd.concat(all_rows, ignore_index=True)
    all_box_daily = all_box_daily.sort_values(["lat1", "lon1", "date"]).reset_index(drop=True)

    # 2) Per-box p95 thresholds from baseline subset
    thr = compute_p95_thresholds(all_box_daily)  # [lat1, lon1, thr_p95]

    # 3) Join thresholds and build 0/1 exceedance
    df = all_box_daily.merge(thr, on=["lat1", "lon1"], how="left")
    if df["thr_p95"].isna().any():
        missing = df[df["thr_p95"].isna()][["lat1", "lon1"]].drop_duplicates()
        raise RuntimeError(f"Missing thresholds for some boxes (no baseline data?):\n{missing}")

    df["exceed"] = (df["val"] >= df["thr_p95"]).astype(int)

    # 4) Per-box heatwave labeling
    per_box_outputs = []
    all_eps = []

    for (la, lo), sub in df.groupby(["lat1", "lon1"], sort=True):
        sub = sub.sort_values("date").reset_index(drop=True)

        exceed_series = sub.set_index("date")["exceed"]

        # UPDATED: min_ones=3 and trim-to-1...1 enforced inside label_heatwaves
        labels, episodes = label_heatwaves(
            exceed_series,
            min_len=3,
            min_ones=3,
            allow_unlimited_single_zeros=True
        )
        out_sub = sub[["date", "lat1", "lon1", "val", "thr_p95", "exceed"]].copy()
        out_sub["heatwave_id"] = labels.reindex(out_sub["date"]).astype(int).values

        # Write per-box daily CSV
        per_box_path = os.path.join(
            OUT_PER_BOX_DIR, f"box_lat{la:+.1f}_lon{lo:+.1f}.csv"
        )
        out_sub.to_csv(per_box_path, index=False)
        per_box_outputs.append(out_sub)

        # Collect episode catalog rows
        for (hw_id, start, end, length_days, ones_count, zeros_count) in episodes:
            all_eps.append({
                "lat1": la, "lon1": lo, "hw_id": hw_id,
                "start_date": start, "end_date": end,
                "length_days": length_days,
                "ones_count": ones_count, "zeros_count": zeros_count
            })

    # Master long CSV (all boxes & days)
    master = pd.concat(per_box_outputs, ignore_index=True).sort_values(["lat1", "lon1", "date"])
    master.to_csv(OUT_MASTER, index=False)

    # Episodes catalog
    episodes_df = pd.DataFrame(all_eps, columns=[
        "lat1", "lon1", "hw_id", "start_date", "end_date",
        "length_days", "ones_count", "zeros_count"
    ]).sort_values(["lat1", "lon1", "start_date"])
    episodes_df.to_csv(OUT_EPISODES, index=False)

    # Summary
    n_boxes = df.drop_duplicates(["lat1", "lon1"]).shape[0]
    n_days  = df["date"].nunique()
    print("\n[DONE]")
    print(f"Files processed : {len(files)}")
    print(f"Boxes           : {n_boxes}")
    print(f"Unique days     : {n_days}")
    print(f"Master (long)   : {OUT_MASTER}")
    print(f"Episodes catalog: {OUT_EPISODES}")
    print(f"Per-box CSVs    : {OUT_PER_BOX_DIR}")


if __name__ == "__main__":
    main()
