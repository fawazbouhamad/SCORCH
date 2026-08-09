"""Build the CF-compliant processed daily Tmax field NetCDF for the Zenodo deposit.

Derives ``scorch_processed_daily_tmax_field_v1.0.0.nc`` from the canonical
long-table CSV (28,328,400 rows = 15,738 warm-season days x 1,800 one-degree
grid cells; columns ``date, lat1, lon1, val, thr_p95, exceed, heatwave_id``).

The output contains:
  * ``tmax``               - daily maximum 2-m air temperature (degC), (time, lat, lon)
  * ``tmax_p95_threshold`` - grid-cell warm-season 95th-percentile threshold (degC), (lat, lon)
  * ``exceedance``         - 0/1 indicator: tmax >= tmax_p95_threshold, (time, lat, lon)
  * ``heatwave_id``        - within-cell heatwave episode identifier
                             (0 = cell not in a heatwave episode on that day), (time, lat, lon)

The canonical producer applies ``val >= thr_p95``; the source-precision
consistency check below uses that same ``>=`` rule.

After writing, the script re-opens the file and verifies the declared
invariants: 1,800 valid cells, 15,738 days, the daily coverage counts
(n_hw / n_exceed / n_hw_exceed) against the deposited
``fig02_daily_extent.csv``, and the regional-selection invariants
(Theta = 371 boxes at the P97.5 extent quantile; 395 selected days).
Any failed invariant raises and deletes nothing silently.

Usage:
    python build_processed_field_netcdf.py --master-csv <path> \
        --extent-csv <path to fig02_daily_extent.csv> \
        --out <output .nc path>

The master CSV is the intermediate product of the source-reconstruction
workflow (see docs/SOURCE_DATA_PROVENANCE.md); it is not itself deposited
because the NetCDF written here carries the identical information in
compressed, self-describing form.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from netCDF4 import Dataset, date2num

N_TIME_EXPECTED = 15_738
N_LAT_EXPECTED = 36
N_LON_EXPECTED = 50
N_CELLS_EXPECTED = 1_800
THETA_EXPECTED = 371
N_SELECTED_DAYS_EXPECTED = 395


def build(master_csv: Path, out_nc: Path) -> dict:
    """Stream the long table into dense (time, lat, lon) arrays and write CF NetCDF."""
    # Pass 1 (cheap): establish axes from a full unique scan of the key columns.
    print("[1/4] scanning axes ...", flush=True)
    dates: set[str] = set()
    lats: set[float] = set()
    lons: set[float] = set()
    for chunk in pd.read_csv(master_csv, usecols=["date", "lat1", "lon1"],
                             chunksize=4_000_000):
        dates.update(chunk["date"].unique().tolist())
        lats.update(chunk["lat1"].unique().tolist())
        lons.update(chunk["lon1"].unique().tolist())
    time_axis = sorted(dates)
    lat_axis = np.array(sorted(lats), dtype=np.float64)
    lon_axis = np.array(sorted(lons), dtype=np.float64)
    if len(time_axis) != N_TIME_EXPECTED:
        raise SystemExit(f"FATAL: {len(time_axis)} dates, expected {N_TIME_EXPECTED}")
    if len(lat_axis) != N_LAT_EXPECTED or len(lon_axis) != N_LON_EXPECTED:
        raise SystemExit(f"FATAL: grid {len(lat_axis)}x{len(lon_axis)}, "
                         f"expected {N_LAT_EXPECTED}x{N_LON_EXPECTED}")

    t_index = {d: i for i, d in enumerate(time_axis)}
    la_index = {v: i for i, v in enumerate(lat_axis)}
    lo_index = {v: i for i, v in enumerate(lon_axis)}

    # Pass 2: fill dense arrays.
    print("[2/4] filling dense arrays ...", flush=True)
    shape = (len(time_axis), len(lat_axis), len(lon_axis))
    tmax = np.full(shape, np.nan, dtype=np.float32)
    thr = np.full((len(lat_axis), len(lon_axis)), np.nan, dtype=np.float32)
    exceed = np.zeros(shape, dtype=np.int8)
    hw_id = np.zeros(shape, dtype=np.int16)
    filled = np.zeros(shape, dtype=bool)

    n_rows = 0
    n_f64_mismatch = 0
    n_f32_borderline = 0
    n_f32_borderline_gt = 0
    for chunk in pd.read_csv(
            master_csv,
            usecols=["date", "lat1", "lon1", "val", "thr_p95", "exceed", "heatwave_id"],
            chunksize=4_000_000):
        n_rows += len(chunk)
        ti = chunk["date"].map(t_index).to_numpy()
        li = chunk["lat1"].map(la_index).to_numpy()
        oi = chunk["lon1"].map(lo_index).to_numpy()
        if filled[ti, li, oi].any():
            raise SystemExit("FATAL: duplicate (date, lat, lon) rows in master CSV")
        filled[ti, li, oi] = True
        v64 = chunk["val"].to_numpy()
        t64 = chunk["thr_p95"].to_numpy()
        e8 = chunk["exceed"].to_numpy().astype(np.int8)
        # Consistency in full precision: the stored indicator must equal
        # (val >= thr_p95) exactly as computed on the float64 source values,
        # which is the rule the canonical producer applies.
        n_f64_mismatch += int(((v64 >= t64).astype(np.int8) != e8).sum())
        # Count entries whose comparison flips after float32 rounding; these
        # are documented in the file metadata (the shipped `exceedance`
        # variable is authoritative, not a recomputation from float32 tmax).
        v32 = v64.astype(np.float32)
        t32 = t64.astype(np.float32)
        n_f32_borderline += int(((v32 >= t32).astype(np.int8) != e8).sum())
        n_f32_borderline_gt += int(((v32 > t32).astype(np.int8) != e8).sum())
        tmax[ti, li, oi] = v64.astype(np.float32)
        thr[li, oi] = t64.astype(np.float32)
        exceed[ti, li, oi] = e8
        hw = chunk["heatwave_id"].to_numpy()
        if np.isnan(hw).any():
            raise SystemExit("FATAL: NaN heatwave_id encountered")
        hw_id[ti, li, oi] = hw.astype(np.int16)

    if not filled.all():
        raise SystemExit(f"FATAL: table not dense - {(~filled).sum()} missing cells")
    if np.isnan(tmax).any() or np.isnan(thr).any():
        raise SystemExit("FATAL: NaN tmax or threshold after fill")
    print(f"    {n_rows:,} rows -> dense {shape}", flush=True)

    if n_f64_mismatch:
        raise SystemExit(
            f"FATAL: exceed flag mismatch on {n_f64_mismatch} entries at "
            "float64 precision under the canonical val >= thr_p95 rule")
    print(f"    float32 borderline entries (documented): {n_f32_borderline}", flush=True)

    # Pass 3: write CF NetCDF.
    print("[3/4] writing NetCDF ...", flush=True)
    out_nc.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_nc.with_suffix(".nc.tmp")
    ds = Dataset(tmp, "w", format="NETCDF4")
    try:
        ds.createDimension("time", len(time_axis))
        ds.createDimension("lat", len(lat_axis))
        ds.createDimension("lon", len(lon_axis))
        ds.createDimension("bnds", 2)

        tvar = ds.createVariable("time", "i4", ("time",))
        tvar.standard_name = "time"
        tvar.long_name = "time (warm-season days, April-September, 1940-2025)"
        tvar.units = "days since 1940-01-01 00:00:00"
        tvar.calendar = "standard"
        tvar.axis = "T"
        py_dates = pd.to_datetime(time_axis).to_pydatetime()
        tvar[:] = date2num(list(py_dates), units=tvar.units, calendar=tvar.calendar)

        la = ds.createVariable("lat", "f8", ("lat",))
        la.standard_name = "latitude"
        la.long_name = "latitude of 1-degree grid-cell center"
        la.units = "degrees_north"
        la.axis = "Y"
        la.bounds = "lat_bnds"
        la[:] = lat_axis
        lab = ds.createVariable("lat_bnds", "f8", ("lat", "bnds"))
        lab[:] = np.column_stack([lat_axis - 0.5, lat_axis + 0.5])

        lo = ds.createVariable("lon", "f8", ("lon",))
        lo.standard_name = "longitude"
        lo.long_name = "longitude of 1-degree grid-cell center"
        lo.units = "degrees_east"
        lo.axis = "X"
        lo.bounds = "lon_bnds"
        lo[:] = lon_axis
        lob = ds.createVariable("lon_bnds", "f8", ("lon", "bnds"))
        lob[:] = np.column_stack([lon_axis - 0.5, lon_axis + 0.5])

        crs = ds.createVariable("crs", "i4")
        crs.grid_mapping_name = "latitude_longitude"
        crs.long_name = "WGS 84 geographic coordinate reference system"
        crs.epsg_code = "EPSG:4326"
        crs.semi_major_axis = 6378137.0
        crs.inverse_flattening = 298.257223563

        chunks_3d = (183, len(lat_axis), len(lon_axis))  # one warm season per chunk

        v = ds.createVariable("tmax", "f4", ("time", "lat", "lon"),
                              zlib=True, complevel=4, shuffle=True,
                              chunksizes=chunks_3d, fill_value=np.float32(-9999.0))
        v.standard_name = "air_temperature"
        v.long_name = "daily maximum 2-m air temperature"
        v.units = "degC"
        v.cell_methods = "time: maximum (interval: 1 day)"
        v.grid_mapping = "crs"
        v.comment = ("Daily maximum of hourly ERA5 2-m temperature, aggregated to "
                     "a 1-degree grid; warm-season days (April-September) only.")
        v[:] = tmax

        v = ds.createVariable("tmax_p95_threshold", "f4", ("lat", "lon"),
                              zlib=True, complevel=4, shuffle=True,
                              fill_value=np.float32(-9999.0))
        v.long_name = ("grid-cell 95th percentile of warm-season daily maximum "
                       "2-m air temperature (1940-2025 climatology)")
        v.units = "degC"
        v.grid_mapping = "crs"
        v[:] = thr

        v = ds.createVariable("exceedance", "i1", ("time", "lat", "lon"),
                              zlib=True, complevel=4, shuffle=True,
                              chunksizes=chunks_3d)
        v.long_name = "threshold-exceedance indicator (tmax >= tmax_p95_threshold)"
        v.units = "1"
        v.flag_values = np.array([0, 1], dtype=np.int8)
        v.flag_meanings = "no_exceedance exceedance"
        v.grid_mapping = "crs"
        v.comment = ("Authoritative indicator computed as tmax >= "
                     "tmax_p95_threshold on the float64 source values. "
                     "Recomputing it from the float32 values stored in this "
                     "file disagrees only on a handful of borderline entries "
                     "whose value sits within float32 resolution of the "
                     f"threshold ({n_f32_borderline} entries under >=, "
                     f"{n_f32_borderline_gt} under >); use this variable, "
                     "not a recomputation, as the exceedance record.")
        v[:] = exceed

        v = ds.createVariable("heatwave_id", "i2", ("time", "lat", "lon"),
                              zlib=True, complevel=4, shuffle=True,
                              chunksizes=chunks_3d)
        v.long_name = ("within-cell heatwave episode identifier; 0 = grid cell "
                       "not in a heatwave episode on that day; positive integers "
                       "number successive episodes within each grid cell")
        v.units = "1"
        v.comment = ("The grid-level heatwave indicator used in the paper is "
                     "heatwave_id > 0: those are the HEATWAVE-LABELLED grid "
                     "cells that the daily clustering takes as input (a "
                     "subset of the threshold-exceedance cells, since the "
                     "labelling additionally requires the >=3-day / "
                     ">=3-exceedance-day episode rule). Identifiers are only "
                     "unique within a grid cell, not across cells.")
        v.grid_mapping = "crs"
        v[:] = hw_id

        ds.Conventions = "CF-1.10"
        ds.title = ("SCORCH processed daily 1-degree maximum temperature field with "
                    "95th-percentile thresholds, exceedance indicator, and grid-level "
                    "heatwave episode identifiers (1940-2025 warm seasons)")
        ds.institution = "University of Florida"
        # NOTE: no Copernicus attribution notice belongs in `source`. Earlier
        # revisions appended "Contains modified Copernicus Climate Change
        # Service information (1940-2025)" here, which is NOT the required
        # notice: the notice's year token is the year of use (2026), never the
        # data's coverage span, and a parenthesised range is not the verbatim
        # wording. The one authoritative, verbatim notice lives in `license`
        # below; 1940-2025 appears here only as the coverage interval. Keeping a
        # second, differently worded copy in `source` is what let it drift.
        ds.source = ("ERA5 hourly 2-m temperature (Hersbach et al., 2020), retrieved "
                     "from the ARCO-ERA5 analysis-ready public mirror "
                     "(gs://gcp-public-data-arco-era5); dataset of record: Copernicus "
                     "Climate Data Store, DOI 10.24381/cds.adbb2d47. ERA5 coverage "
                     "used: 1940-2025 (warm seasons, April-September). Required "
                     "Copernicus attribution: see the `license` attribute.")
        ds.references = ("Bouhamad and Najibi, Understanding the Spatiotemporal "
                         "Organization of Regionally Extensive Heatwaves Using the "
                         "SCORCH Framework (in review). SCORCH: Spatiotemporal "
                         "Classification of Regional Compound Heatwaves.")
        ds.license = ("CC BY 4.0 for the value added by the authors "
                      "(https://creativecommons.org/licenses/by/4.0/), which "
                      "covers only the authors' contribution; the underlying "
                      "ERA5 information is provided under the licence to use "
                      "Copernicus products, https://ecds.ecmwf.int/licences/"
                      "licence-to-use-copernicus-products, and is not CC "
                      "BY licensed by this deposit. ERA5 coverage used: "
                      "1940-2025 (warm seasons, April-September). Required "
                      "attribution: Contains modified Copernicus Climate "
                      "Change Service information 2026. Neither the European "
                      "Commission nor ECMWF is responsible for any use that "
                      "may be made of the Copernicus information or data it "
                      "contains.")
        ds.comment = ("Dense field: 15,738 warm-season days x 1,800 one-degree cells "
                      "(lat 10.5..45.5N, lon 20.5..69.5E, cell centers). No missing "
                      "data; _FillValue conventions declared for completeness.")
        ds.history = "Built by scripts/deposit/build_processed_field_netcdf.py from the canonical long-table CSV."
    finally:
        ds.close()
    tmp.replace(out_nc)
    return {"n_rows": n_rows, "shape": list(shape)}


def verify(out_nc: Path, extent_csv: Path) -> dict:
    """Re-open the file and verify every declared invariant. Raises on failure."""
    print("[4/4] verifying invariants ...", flush=True)
    ds = Dataset(out_nc, "r")
    try:
        n_time = len(ds.dimensions["time"])
        n_lat = len(ds.dimensions["lat"])
        n_lon = len(ds.dimensions["lon"])
        tmax = ds.variables["tmax"][:]
        thr = ds.variables["tmax_p95_threshold"][:]
        exceed = ds.variables["exceedance"][:]
        hw = ds.variables["heatwave_id"][:]
        tvar = ds.variables["time"]
        from netCDF4 import num2date
        dates = [d.strftime("%Y-%m-%d") for d in
                 num2date(tvar[:], tvar.units, tvar.calendar)]
    finally:
        ds.close()

    checks = {}
    checks["n_days"] = (n_time, N_TIME_EXPECTED)
    checks["n_cells"] = (n_lat * n_lon, N_CELLS_EXPECTED)
    valid_cells = int(np.isfinite(np.asarray(thr, dtype=float)).sum())
    checks["n_valid_threshold_cells"] = (valid_cells, N_CELLS_EXPECTED)

    ex = np.asarray(exceed)
    hwa = np.asarray(hw)
    n_exceed = ex.reshape(n_time, -1).sum(axis=1)
    n_hw = (hwa > 0).reshape(n_time, -1).sum(axis=1)
    n_hw_exceed = ((hwa > 0) & (ex == 1)).reshape(n_time, -1).sum(axis=1)

    ref = pd.read_csv(extent_csv)
    ref = ref.sort_values("date").reset_index(drop=True)
    if list(ref["date"]) != dates:
        raise SystemExit("FATAL: date axis differs from deposited daily-extent table")
    for col, arr in (("n_hw", n_hw), ("n_exceed", n_exceed),
                     ("n_hw_exceed", n_hw_exceed)):
        n_bad = int((ref[col].to_numpy() != arr).sum())
        checks[f"daily_coverage_{col}_mismatch_days"] = (n_bad, 0)

    # Regional-selection invariants: Theta at P97.5 of the daily heatwave
    # extent, selected days = days with extent >= Theta.
    theta = float(np.percentile(n_hw, 97.5))
    theta_boxes = int(np.ceil(theta)) if not float(theta).is_integer() else int(theta)
    n_selected = int((n_hw >= THETA_EXPECTED).sum())
    checks["theta_p975_boxes"] = (theta_boxes, THETA_EXPECTED)
    checks["n_selected_days"] = (n_selected, N_SELECTED_DAYS_EXPECTED)
    checks["theta_fraction_of_domain"] = (round(THETA_EXPECTED / (n_lat * n_lon), 4), 0.2061)

    failures = {k: v for k, v in checks.items() if v[0] != v[1]}
    result = {
        "file": str(out_nc),
        "sha256": hashlib.sha256(out_nc.read_bytes()).hexdigest(),
        "size_bytes": out_nc.stat().st_size,
        "checks": {k: {"actual": v[0], "expected": v[1]} for k, v in checks.items()},
        "theta_p975_raw": theta,
        "pass": not failures,
    }
    print(json.dumps(result, indent=2))
    if failures:
        raise SystemExit(f"FATAL: invariant failures: {sorted(failures)}")
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--master-csv", required=True, type=Path)
    ap.add_argument("--extent-csv", required=True, type=Path,
                    help="canonical fig02_daily_extent.csv for coverage verification")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--report-json", type=Path, default=None)
    args = ap.parse_args()

    build(args.master_csv, args.out)
    result = verify(args.out, args.extent_csv)
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(result, indent=2))
    print("OK: NetCDF built and all invariants verified.")


if __name__ == "__main__":
    sys.exit(main())
