"""Convert CDS hourly ERA5 t2m files to yearly daily-Tmax NetCDFs.

Companion to download_era5_cds.py (the dataset-of-record alternative route).
Produces yearly files with the same schema as download_era5_arco.py:
variable Tmax_C (degC), months April-September, latitude 10-46 N,
longitude 20-70 E, one file {year}_daily_Tmax.nc per year.

Usage:
    python era5_hourly_to_daily_tmax.py --indir /path/to/era5_hourly --outdir /path/to/era5_daily
"""

import argparse
import glob
import os

import xarray as xr

MONTHS = [4, 5, 6, 7, 8, 9]
LAT_N, LAT_S = 46, 10
LON_W, LON_E = 20, 70


def find_t2m_var(ds):
    """Return the 2m-temperature variable name in a CDS file."""
    for name in ("t2m", "2m_temperature"):
        if name in ds:
            return name
    raise KeyError(
        f"No 2m temperature variable found; variables present: {list(ds.data_vars)}"
    )


def subset_domain(ds):
    """Clip to lat 10-46 N, lon 20-70 E, handling either longitude convention."""
    lat = ds["latitude"]
    if float(lat[0]) > float(lat[-1]):
        ds = ds.sel(latitude=slice(LAT_N, LAT_S))
    else:
        ds = ds.sel(latitude=slice(LAT_S, LAT_N))

    lon = ds["longitude"]
    if float(lon.min()) >= 0 and float(lon.max()) > 180:
        # 0-360 convention
        ds = ds.sel(longitude=slice(LON_W % 360, LON_E % 360))
    else:
        # -180..180 convention (20-70 E is unchanged)
        ds = ds.sel(longitude=slice(LON_W, LON_E))
    return ds


def process_year(year, indir, outdir):
    """Concatenate one year's monthly hourly files into a daily-Tmax NetCDF."""
    pattern = os.path.join(indir, f"era5_t2m_{year}_*.nc")
    files = sorted(glob.glob(pattern))
    if not files:
        print(f"Skip {year}: no input files matching {pattern}")
        return False

    ds = xr.open_mfdataset(files, combine="by_coords")
    var = find_t2m_var(ds)
    ds = subset_domain(ds)

    # Kelvin to Celsius, hourly to daily maximum
    tc = ds[var] - 273.15
    daily = xr.Dataset({"Tmax_C": tc.resample(time="1D").max()})
    daily = daily.sel(time=daily["time"].dt.month.isin(MONTHS))

    daily["Tmax_C"].attrs.update(
        long_name="Daily maximum 2m air temperature",
        units="degC",
    )
    daily.attrs.update(
        source="ERA5 hourly 2m temperature via Copernicus Climate Data Store",
        note=(
            "Hourly ERA5 2m temperature converted to daily Tmax; Apr-Sep; "
            "lat 10-46 N; lon 20-70 E"
        ),
    )

    out = os.path.join(outdir, f"{year}_daily_Tmax.nc")
    comp = dict(zlib=True, complevel=4, shuffle=True)
    daily.to_netcdf(out, encoding={"Tmax_C": comp})
    ds.close()
    print("Wrote:", out)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--indir", required=True, help="Directory of monthly hourly CDS files")
    parser.add_argument("--outdir", required=True, help="Output directory for yearly daily-Tmax files")
    parser.add_argument("--start", type=int, default=1940)
    parser.add_argument("--end", type=int, default=2025)
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    for year in range(args.start, args.end + 1):
        out = os.path.join(args.outdir, f"{year}_daily_Tmax.nc")
        if os.path.exists(out):
            print(f"Skip {year} already exists: {out}")
            continue
        try:
            process_year(year, args.indir, args.outdir)
        except Exception as exc:
            print(f"FAILED {year}: {exc}")
            continue


if __name__ == "__main__":
    main()
