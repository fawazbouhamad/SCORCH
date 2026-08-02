"""ERA5 hourly 2m-temperature downloader via the Copernicus Climate Data Store API.

This is the dataset-of-record ALTERNATIVE route. It was NOT the route used
for the paper: the paper's fields were read from the ARCO-ERA5 public mirror
(see download_era5_arco.py and docs/SOURCE_DATA_PROVENANCE.md). Use this
script only if you specifically want files distributed by C3S/CDS
(dataset reanalysis-era5-single-levels, DOI 10.24381/cds.adbb2d47).

Requirements:
- A free CDS account with the ERA5 licence accepted.
- Your own ~/.cdsapirc credentials file (never commit it; this script
  contains no credentials and never prints any).
- The cdsapi package (pip install cdsapi).

The download is chunked one request per year-month (Apr-Sep) to stay inside
CDS request limits, and is resumable: existing completed files are skipped,
and a failed chunk leaves a .failed marker and does not stop the loop.

Usage:
    python download_era5_cds.py --outdir /path/to/era5_hourly
    python download_era5_cds.py --outdir /path/to/era5_hourly --start 2016 --end 2016
"""

import argparse
import os

MONTHS = [4, 5, 6, 7, 8, 9]
START_YEAR, END_YEAR = 1940, 2025

# N, W, S, E — latitude 10-46 N, longitude 20-70 E (paper domain)
AREA = [46, 20, 10, 70]


def get_client():
    """Import cdsapi lazily so the rest of the package works without it."""
    try:
        import cdsapi
    except ImportError as exc:
        raise SystemExit(
            "cdsapi is not installed. Install it with 'pip install cdsapi' "
            "and configure ~/.cdsapirc with your own CDS credentials "
            "(see docs/SOURCE_DOWNLOAD_GUIDE.md)."
        ) from exc
    return cdsapi.Client()


def retrieve_month(client, year, month, outfile):
    """Submit one year-month request for hourly 2m temperature."""
    client.retrieve(
        "reanalysis-era5-single-levels",
        {
            "product_type": "reanalysis",
            "variable": "2m_temperature",
            "year": str(year),
            "month": f"{month:02d}",
            "day": [f"{d:02d}" for d in range(1, 32)],
            "time": [f"{h:02d}:00" for h in range(24)],
            "area": AREA,
            "format": "netcdf",
        },
        outfile,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", required=True, help="Output directory for monthly NetCDF files")
    parser.add_argument("--start", type=int, default=START_YEAR)
    parser.add_argument("--end", type=int, default=END_YEAR)
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    client = get_client()

    print("=" * 80)
    print("ERA5 CDS hourly t2m downloader (dataset of record; alternative route)")
    print("Years   :", args.start, "-", args.end)
    print("Months  :", MONTHS)
    print("Area    : N W S E =", AREA)
    print("Output  :", args.outdir)
    print("=" * 80)

    for year in range(args.start, args.end + 1):
        for month in MONTHS:
            outfile = os.path.join(args.outdir, f"era5_t2m_{year}_{month:02d}.nc")
            fail_marker = outfile + ".failed"
            if os.path.exists(outfile):
                print(f"Skip {year}-{month:02d} already exists: {outfile}")
                continue
            try:
                print(f"Requesting {year}-{month:02d} ...")
                retrieve_month(client, year, month, outfile)
                if os.path.exists(fail_marker):
                    os.remove(fail_marker)
                print("Wrote:", outfile)
            except Exception as exc:
                print(f"FAILED {year}-{month:02d}: {exc}")
                try:
                    with open(fail_marker, "w", encoding="utf-8") as handle:
                        handle.write(str(exc))
                except OSError:
                    pass
                continue


if __name__ == "__main__":
    main()
