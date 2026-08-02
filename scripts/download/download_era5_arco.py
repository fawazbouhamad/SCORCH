"""ERA5 daily-Tmax downloader via the ARCO-ERA5 public Zarr store.

This is the released, noninteractive form of the project's historical
acquisition script (1_Data_Download.py). The scientific content of the
request is unchanged: hourly ERA5 2-m temperature from the ARCO-ERA5
analysis-ready mirror, subset to April-September, latitude 10-46 N,
longitude 20-70 E, converted from Kelvin to Celsius and reduced to daily
maxima, written one NetCDF per year.

No credentials are required; the Google Cloud bucket is public and is read
anonymously.

Usage:
    python download_era5_arco.py --outdir /path/to/era5_daily
    python download_era5_arco.py --outdir /path/to/era5_daily --start 2016 --end 2016

The run is restartable: complete yearly files are skipped, and a failed
year leaves a {year}.failed.txt marker and does not stop the loop.
"""

import argparse
import os

import xarray as xr
from dask.diagnostics import ProgressBar

AR_URL = "gs://gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3"

LAT_N, LAT_S = 46, 10
LON_W, LON_E = 20, 70

MONTHS = [4, 5, 6, 7, 8, 9]
START_YEAR, END_YEAR = 1940, 2025


def open_ar():
    """Open ARCO ERA5 Zarr and keep only the 2m temperature variable."""
    ds = xr.open_zarr(
        AR_URL,
        consolidated=True,
        storage_options={"token": "anon"},
    )
    return ds[["2m_temperature"]]


def subset_domain(ds):
    """Subset to lat 10-46 N and lon 20-70 E."""
    ds = ds.sel(latitude=slice(LAT_N, LAT_S))
    lon_w = LON_W % 360
    lon_e = LON_E % 360
    ds = ds.sel(longitude=slice(lon_w, lon_e))
    return ds


def process_year(year, outdir):
    """Process one year Apr-Sep into daily Tmax and write a NetCDF."""
    print(f"\nProcessing {year}...")

    ds = open_ar()
    ds = ds.sel(time=slice(f"{year}-04-01", f"{year}-09-30 23:00:00"))
    ds = subset_domain(ds)
    ds = ds.chunk({"time": 24 * 30, "latitude": 200, "longitude": 200})

    # Kelvin to Celsius
    tc = ds["2m_temperature"] - 273.15

    # Daily Tmax only
    daily = xr.Dataset({"Tmax_C": tc.resample(time="1D").max()})
    daily = daily.sel(time=daily["time"].dt.month.isin(MONTHS))

    daily["Tmax_C"].attrs.update(
        long_name="Daily maximum 2m air temperature",
        units="degC",
    )
    daily.attrs.update(
        source="ARCO ERA5 Google Cloud Zarr",
        note=(
            "Hourly ERA5 2m temperature converted to daily Tmax; Apr-Sep; "
            "lat 10-46 N; lon 20-70 E"
        ),
    )

    out = os.path.join(outdir, f"{year}_daily_Tmax.nc")
    comp = dict(zlib=True, complevel=4, shuffle=True)
    daily.to_netcdf(out, encoding={"Tmax_C": comp})
    print("Wrote:", out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", required=True, help="Output directory for yearly NetCDF files")
    parser.add_argument("--start", type=int, default=START_YEAR)
    parser.add_argument("--end", type=int, default=END_YEAR)
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    ProgressBar().register()

    print("=" * 80)
    print("ERA5 ARCO Daily Tmax Downloader")
    print("Years     :", args.start, "-", args.end)
    print("Latitude  :", LAT_S, "to", LAT_N)
    print("Longitude :", LON_W, "to", LON_E)
    print("Variable  : Tmax only")
    print("Output    :", args.outdir)
    print("=" * 80)

    for year in range(args.start, args.end + 1):
        out = os.path.join(args.outdir, f"{year}_daily_Tmax.nc")
        if os.path.exists(out):
            print(f"Skip {year} already exists: {out}")
            continue
        try:
            process_year(year, args.outdir)
        except Exception as exc:
            print(f"FAILED {year}: {exc}")
            fail_marker = os.path.join(args.outdir, f"{year}.failed.txt")
            try:
                with open(fail_marker, "w", encoding="utf-8") as handle:
                    handle.write(str(exc))
            except OSError:
                pass
            continue


if __name__ == "__main__":
    main()
