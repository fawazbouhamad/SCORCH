# SOURCE DOWNLOAD GUIDE

How to obtain the external source data for the provider-level
reconstruction guide (documentation only; structurally validated, not
rerun end to end for this release).
For the fast (Tier A) reproduction you do not need any of this; use the Zenodo
processed-data deposit instead.

## 1. ERA5 daily Tmax NetCDFs via ARCO-ERA5 (route used for the paper)

Requirements: Python environment from `environment.yml` (xarray, zarr, gcsfs,
dask, netCDF4). No account or credentials are needed; the bucket is public.

```
python scripts/download/download_era5_arco.py --outdir /path/to/era5_daily
```

Behaviour:
- Downloads one year at a time (1940-2025), Apr-Sep, lat 10-46 N, lon 20-70 E,
  converts hourly 2m temperature (K) to daily Tmax (degC), writes
  `{year}_daily_Tmax.nc` (~98 MB each, ~8.4 GB total).
- Restartable: existing complete files are skipped; a failed year writes
  `{year}.failed.txt` and the script continues; re-run to retry failures.
- Approximate time: several hours on a home connection; each year moves
  roughly 1-2 GB of hourly source data over the network (over the full
  1940-2025 record that is on the order of 100 GB of total network
  transfer, distinct from the ~8.4 GB stored on disk). Plan for LOCAL
  WORKING STORAGE exceeding 10 GB once the derived long-table CSV
  (~2 GB) and processing intermediates are included.

## 2. ERA5 via the Copernicus Climate Data Store (alternative, dataset of record)

Not the route used for the paper (see SOURCE_DATA_PROVENANCE.md). Use only if
you specifically want the C3S-distributed files.

1. Create a free account at https://cds.climate.copernicus.eu and accept the
   licence for "ERA5 hourly data on single levels from 1940 to present"
   (DOI 10.24381/cds.adbb2d47).
2. Create `~/.cdsapirc` with your own key (never commit this file), replacing
   the placeholder value below with the Personal Access Token shown on your
   CDS profile page:

```
url: https://cds.climate.copernicus.eu/api
key: REPLACE_WITH_YOUR_PERSONAL_ACCESS_TOKEN
```

3. Run the chunked, resumable downloader (one request per year-month to stay
   inside CDS limits; safe to interrupt and re-run):

```
python scripts/download/download_era5_cds.py --outdir /path/to/era5_hourly
```

Each request is equivalent to:

```python
client.retrieve(
    "reanalysis-era5-single-levels",
    {
        "product_type": "reanalysis",
        "variable": "2m_temperature",
        "year": "1940",             # looped 1940..2025
        "month": "04",              # looped 04..09
        "day": [f"{d:02d}" for d in range(1, 32)],
        "time": [f"{h:02d}:00" for h in range(24)],
        "area": [46, 20, 10, 70],   # N, W, S, E
        "format": "netcdf",
    },
    "era5_t2m_1940_04.nc",
)
```

Convert to daily Tmax with `scripts/download/era5_hourly_to_daily_tmax.py`
before entering the pipeline. Note that CDS conversion paths may differ at
floating-point level from the ARCO mirror.

## 3. GHCN-Daily Aswan station (validation input)

The archived station extract is included in the processed-data deposit
(`validation_station/`), so this step is optional.

To retrieve fresh from NOAA NCEI (no account needed):

- Station: GHCND:EG000062414 (Aswan, Egypt).
- Direct bulk route: download
  https://www.ncei.noaa.gov/data/global-historical-climatology-network-daily/access/EG000062414.csv
  (CSV with DATE, TMAX etc.; TMAX in tenths of degrees C in the bulk access
  format).
- Climate Data Online route (as originally used): order daily summaries for
  station GHCND:EG000062414 at https://www.ncdc.noaa.gov/cdo-web/ with
  standard units (TMAX in degrees F) and convert with (F - 32) x 5/9.
- Keep the 2016 station file (the download may cover all of 2016). The
  comparison window used in the paper is 2016-05-31 to 2016-06-12
  (31 May-12 June 2016); compare against ERA5 cell 24.0 N, 32.75 E as
  described in the supplement.
- Quality control: the validation uses the provider's quality-checked daily
  values as delivered; days with missing TMAX are dropped before pairing
  (n = 9 valid overlapping days in the 2016-05-31..2016-06-12 window).

## 4. Integrity checks

After any download, run:

```
scorch validate-sources --dir /path/to/era5_daily
```

which verifies file count (86 years), coordinate bounds, calendar coverage,
units metadata, and value plausibility ranges. SHA-256 checksums are not
published for provider files because provider-side re-encodings can change
bytes without changing values; the processed-data deposit carries checksums
for every archived file instead.
