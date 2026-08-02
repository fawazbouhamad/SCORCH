"""Source-data validation (``scorch validate-sources``).

Checks a directory of ERA5 daily-Tmax NetCDF files against the SCORCH study
configuration:

  * expected file count (canonical: 86 warm seasons, 1940-2025),
  * coordinate bounds lat 10-46 N, lon 20-70 E,
  * calendar months restricted to Apr-Sep,
  * variable units attribute in degrees Celsius,
  * value plausibility -40..60 degC.

This module is importable WITHOUT xarray; xarray is imported lazily inside
the functions that open NetCDF files (install the ``download`` extra).
"""
from __future__ import annotations

import glob
import os
from pathlib import Path

# Canonical expectations
EXPECTED_FILE_COUNT = 86
LAT_MIN, LAT_MAX = 10.0, 46.0
LON_MIN, LON_MAX = 20.0, 70.0
MONTHS = {4, 5, 6, 7, 8, 9}
VAL_MIN, VAL_MAX = -40.0, 60.0
VAR_TMAX = "Tmax_C"
_DEGC_UNITS = {"degc", "deg_c", "degree_celsius", "degrees_celsius",
               "celsius", "c", "degreec", "degree c", "degrees c"}


def _require_xarray():
    try:
        import xarray as xr  # noqa: F401
        return xr
    except ImportError as exc:
        raise ImportError(
            "xarray is required to open NetCDF files. Install the download "
            "extra: pip install 'scorch-heatwaves[download]'") from exc


def list_era5_files(directory):
    """List candidate daily NetCDF files ({year}_daily_Tmax.nc, then *_daily.nc)."""
    directory = str(directory)
    files = sorted(glob.glob(os.path.join(directory, "*_daily_Tmax.nc")))
    if not files:
        files = sorted(glob.glob(os.path.join(directory, "*_daily.nc")))
    return files


def _check_file(xr, path, checks):
    import numpy as np
    import pandas as pd
    with xr.open_dataset(path) as ds:
        lat_name = next((n for n in ("latitude", "lat") if n in ds.coords), None)
        lon_name = next((n for n in ("longitude", "lon") if n in ds.coords), None)
        if lat_name is None or lon_name is None:
            checks.append((path, "coords", False,
                           f"lat/lon coords not found in {list(ds.coords)}"))
            return
        lat = ds[lat_name].values
        lon = ds[lon_name].values
        ok_bounds = (float(lat.min()) >= LAT_MIN - 0.5 and
                     float(lat.max()) <= LAT_MAX + 0.5 and
                     float(lon.min()) >= LON_MIN - 0.5 and
                     float(lon.max()) <= LON_MAX + 0.5)
        checks.append((path, "bounds", ok_bounds,
                       f"lat [{lat.min():.2f}, {lat.max():.2f}], "
                       f"lon [{lon.min():.2f}, {lon.max():.2f}]"))

        if "time" in ds.coords:
            months = set(pd.DatetimeIndex(ds["time"].values).month.tolist())
            ok_months = months.issubset(MONTHS)
            checks.append((path, "months", ok_months, f"months={sorted(months)}"))
        else:
            checks.append((path, "months", False, "no 'time' coordinate"))

        if VAR_TMAX in ds:
            var = ds[VAR_TMAX]
            units = str(var.attrs.get("units", "")).strip().lower()
            ok_units = units in _DEGC_UNITS
            checks.append((path, "units", ok_units, f"units='{units}'"))
            vals = var.values
            finite = vals[np.isfinite(vals)]
            if finite.size:
                vmin, vmax = float(finite.min()), float(finite.max())
                ok_range = VAL_MIN <= vmin and vmax <= VAL_MAX
                checks.append((path, "plausibility", ok_range,
                               f"range [{vmin:.1f}, {vmax:.1f}] degC"))
            else:
                checks.append((path, "plausibility", False, "no finite values"))
        else:
            checks.append((path, "variable", False,
                           f"'{VAR_TMAX}' not found in {list(ds.data_vars)}"))


def validate_era5_dir(directory, expected_files=EXPECTED_FILE_COUNT,
                      sample=None):
    """Validate an ERA5 daily-Tmax directory.

    Parameters
    ----------
    directory : path containing {year}_daily_Tmax.nc files.
    expected_files : expected file count (canonical: 86); None disables.
    sample : optionally validate only the first N files (faster).

    Returns
    -------
    dict with keys ``n_files``, ``ok`` (bool) and ``checks`` (list of
    (path, check, passed, detail) tuples).
    """
    directory = Path(directory)
    if not directory.is_dir():
        raise FileNotFoundError(f"not a directory: {directory}")
    files = list_era5_files(directory)
    checks = []
    if expected_files is not None:
        checks.append((str(directory), "file_count",
                       len(files) == int(expected_files),
                       f"found {len(files)}, expected {expected_files}"))
    if files:
        xr = _require_xarray()
        subset = files[:int(sample)] if sample else files
        for path in subset:
            _check_file(xr, path, checks)
    else:
        checks.append((str(directory), "files_present", False,
                       "no *_daily_Tmax.nc or *_daily.nc files found"))
    ok = all(passed for (_p, _c, passed, _d) in checks)
    return {"n_files": len(files), "ok": bool(ok), "checks": checks}


def format_report(report):
    """Human-readable text for a :func:`validate_era5_dir` report."""
    lines = [f"files found: {report['n_files']}"]
    for path, check, passed, detail in report["checks"]:
        status = "OK  " if passed else "FAIL"
        lines.append(f"[{status}] {check:12s} {os.path.basename(str(path))}: "
                     f"{detail}")
    lines.append("RESULT: " + ("PASS" if report["ok"] else "FAIL"))
    return "\n".join(lines)
