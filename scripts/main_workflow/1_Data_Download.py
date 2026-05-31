
import os
import numpy as np
import xarray as xr
from dask.diagnostics import ProgressBar

ProgressBar().register()

# ---------- CONFIG ----------
AR_URL = "gs://gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3"

OUTDIR = input("Enter output directory path: ").strip().strip('"')

LAT_N, LAT_S = 46, 10
LON_W, LON_E = 20, 70

MONTHS = [4, 5, 6, 7, 8, 9]
START_YEAR, END_YEAR = 1940, 2025
# ----------------------------

os.makedirs(OUTDIR, exist_ok=True)


def open_ar():
    """Open ARCO ERA5 Zarr and keep only Tmax variable source."""
    ds = xr.open_zarr(
        AR_URL,
        consolidated=True,
        storage_options={"token": "anon"}
    )

    return ds[["2m_temperature"]]


def subset_mena(ds):
    """Subset to lat 10–46 N and lon 20–70 E."""

    ds = ds.sel(latitude=slice(LAT_N, LAT_S))

    lonW = LON_W % 360
    lonE = LON_E % 360

    ds = ds.sel(longitude=slice(lonW, lonE))

    return ds


def process_year(y):
    """Process one year Apr–Sep into daily Tmax only."""

    print(f"\nProcessing {y}...")

    ds = open_ar()

    ds = ds.sel(time=slice(f"{y}-04-01", f"{y}-09-30 23:00:00"))

    ds = subset_mena(ds)

    ds = ds.chunk({
        "time": 24 * 30,
        "latitude": 200,
        "longitude": 200
    })

    # Kelvin to Celsius
    Tc = ds["2m_temperature"] - 273.15

    # Daily Tmax only
    daily = xr.Dataset(
        {
            "Tmax_C": Tc.resample(time="1D").max()
        }
    )

    daily = daily.sel(time=daily["time"].dt.month.isin(MONTHS))

    daily["Tmax_C"].attrs.update(
        long_name="Daily maximum 2m air temperature",
        units="degC"
    )

    daily.attrs.update(
        source="ARCO ERA5 Google Cloud Zarr",
        note="Hourly ERA5 2m temperature converted to daily Tmax; Apr–Sep; lat 10–46 N; lon 20–70 E"
    )

    out = os.path.join(OUTDIR, f"{y}_daily_Tmax.nc")

    comp = dict(zlib=True, complevel=4, shuffle=True)

    daily.to_netcdf(
        out,
        encoding={"Tmax_C": comp}
    )

    print("Wrote:", out)


if __name__ == "__main__":

    print("=" * 80)
    print("ERA5 ARCO Daily Tmax Downloader")
    print("Years     :", START_YEAR, "-", END_YEAR)
    print("Latitude  :", LAT_S, "to", LAT_N)
    print("Longitude :", LON_W, "to", LON_E)
    print("Variable  : Tmax only")
    print("Output    :", OUTDIR)
    print("=" * 80)

    for y in range(START_YEAR, END_YEAR + 1):

        out = os.path.join(OUTDIR, f"{y}_daily_Tmax.nc")

        if os.path.exists(out):
            print(f"Skip {y} already exists: {out}")
            continue

        try:
            process_year(y)

        except Exception as e:
            print(f"FAILED {y}: {e}")

            fail_marker = os.path.join(OUTDIR, f"{y}.failed.txt")

            try:
                with open(fail_marker, "w", encoding="utf-8") as f:
                    f.write(str(e))
            except Exception:
                pass

            continue