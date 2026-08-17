# SOURCE DATA PROVENANCE

This document records, from repository evidence, exactly where every external
input of the SCORCH analysis came from and how it was transformed. Statements
here distinguish what was actually executed for the paper from alternative
authoritative routes that were not used.

## 1. ERA5 hourly 2-m air temperature

### 1.1 What the paper actually used

The hourly ERA5 2-m temperature fields were read from the ARCO-ERA5
analysis-ready mirror of ERA5 hosted on Google Cloud Storage, not through the
Copernicus Climate Data Store API. The acquisition script is
`scripts/download/download_era5_arco.py` (released form of the project's
`1_Data_Download.py`), whose complete request is:

| Parameter | Value |
|---|---|
| Store | `gs://gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3` (public bucket, anonymous access, `storage_options={"token": "anon"}`) |
| Variable | `2m_temperature` (hourly, Kelvin, native 0.25 degree grid) |
| Years | 1940 to 2025 inclusive, processed one year at a time |
| Time slice per year | `{year}-04-01` through `{year}-09-30 23:00` |
| Months retained | April to September |
| Hours | all 24 hours (no subsetting) |
| Spatial subset | latitude 10 to 46 N, longitude 20 to 70 E |
| In-script transforms | Kelvin to Celsius; hourly to daily maximum (`resample(time="1D").max()`) |
| Output | one NetCDF per year (`{year}_daily.nc` in the historical archive; the script writes `{year}_daily_Tmax.nc`), zlib level 4, variable `Tmax_C` with `units="degC"` |

ARCO-ERA5 is Google Research's analysis-ready copy of ECMWF's ERA5
(https://github.com/google-research/arco-era5). Its temperature values are the
ERA5 values published by the Copernicus Climate Change Service (C3S); the
underlying dataset of record is ERA5 (Hersbach et al., 2020).

Known non-material discrepancy: the released download script is a cleaned
rewrite of the historical script (output filename differs as noted above); the
downstream step accepts both filename patterns. The historical yearly NetCDFs
were downloaded 2025-09-25 through 2025-10-08, with 2025 refreshed 2026-02-22.

### 1.2 Authoritative dataset of record

- Title: ERA5 hourly data on single levels from 1940 to present
- Provider: Copernicus Climate Change Service (C3S), ECMWF
- Identifier/DOI: 10.24381/cds.adbb2d47 (CDS dataset `reanalysis-era5-single-levels`)
- Variable: 2 m temperature (t2m), units K, native ~31 km, regular 0.25 degree lat-lon distribution
- Licence: licence to use Copernicus products,
  https://ecds.ecmwf.int/licences/licence-to-use-copernicus-products
  It covers the underlying ERA5 information; the authors' CC BY 4.0 licence
  covers only their own contribution and is not asserted over it.
- ERA5 coverage used in this work: 1940-2025 (warm seasons, April-September),
  stated separately from the notice's year token.
- Required attribution, verbatim and without brackets: Contains modified
  Copernicus Climate Change Service information 2026. Neither the European
  Commission nor ECMWF is responsible for any use that may be made of the
  Copernicus information or data it contains.
- Access: free C3S/CDS account with licence acceptance, or the ARCO-ERA5
  public mirror used here (no account required).

An equivalent CDS API request script is provided at
`scripts/download/download_era5_cds.py` for users who prefer the dataset of
record. It was NOT the route used for the paper; small numerical differences
between CDS GRIB/NetCDF conversions and the ARCO Zarr mirror cannot be
excluded a priori, so exact byte-level reproduction of the processed fields
should start from the ARCO route or from the archived processed data.

### 1.3 Processing chain to the processed master dataset

`scripts/pipeline/build_master_dataset.py` (released form of
`2_Heatwave_Algorithm.py`) consumes the yearly daily-Tmax NetCDFs and produces
the processed master table:

1. Longitude normalised to [-180, 180]; domain clip 10-46 N, 20-70 E; months April-September.
2. Aggregation to 1 degree grid cells centred on .5 (grid-cell value = mean of constituent 0.25 degree cells; NaN cells dropped). Result: 1,800 valid grid cells by 15,738 warm-season days (86 years x 183 days).
3. Grid-specific 95th percentile thresholds over the full 1940-2025 warm-season record (pandas `quantile(0.95)`, linear interpolation) giving `thr_p95`.
4. Exceedance flag `exceed = (val >= thr_p95)`.
5. Per-grid-cell heatwave labelling: runs split at two consecutive non-exceedance days, trimmed to exceedance endpoints, qualifying if length >= 3 days and exceedance days >= 3, single-day gaps bridged; label column `heatwave_id` (0 = none).

Output schema (`master_exceed_heatwaves_long.csv`, 1.78 GB, 28.3 M rows):

| Column | Meaning | Example (synthetic) |
|---|---|---|
| date | ISO day, YYYY-MM-DD | 1999-07-15 |
| lat1 | 1 degree grid-cell centre latitude (legacy column name) | 30.5 |
| lon1 | 1 degree grid-cell centre longitude (legacy column name) | 45.5 |
| val | daily Tmax, degrees C (all days, not only heatwaves) | 41.2 |
| thr_p95 | grid-cell 95th percentile threshold, degrees C | 43.1 |
| exceed | 1 if val >= thr_p95 else 0 | 0 |
| heatwave_id | per-cell event label, 0 = none | 0 |

## 2. GHCN-Daily station observations (validation)

- Dataset: Global Historical Climatology Network - Daily (GHCN-Daily), NOAA
  National Centers for Environmental Information (NCEI). Menne et al. (2012);
  dataset DOI 10.7289/V5D21VHZ. Distributed by NOAA/NCEI; subject to the
  dataset's current use constraints and any applicable source-provider
  rights (GHCN-Daily integrates international source datasets); NOAA
  requests citation of the dataset and paper.
- Station: GHCND:EG000062414, "ASSWAN, EG" (Aswan, Egypt), 23.97 N, 32.78 E.
- Retrieval actually performed: manual order through NOAA Climate Data Online
  (order file `4310291.csv`, sha256
  7a65e44635d245dfe7474ff7aef58243c6cca67d91a9733c0cafc444aa92367e). Fields
  STATION, NAME, DATE, TAVG, TMAX, TMIN with TMAX in degrees Fahrenheit;
  converted to Celsius as (F - 32) x 5/9. No scripted download exists; a
  scripted retrieval specification is given in SOURCE_DOWNLOAD_GUIDE.md.
- Use: comparison against the nearest ERA5 1-degree cell (24.0 N, 32.75 E) for
  the 31 May-12 June 2016 comparison window (2016-05-31 to 2016-06-12;
  n = 9 overlapping valid days after dropping days with missing station TMAX;
  r = 0.98, RMSE = 1.70 C, bias = -1.60 C; both series' pooled warm-season
  P95 exceedance on 2 of 2 event days). The GHCN order itself covers all of
  2016; only the 2016-05-31..2016-06-12 window enters the comparison. The extracted station table, Celsius
  conversion, ERA5 cell series, merged comparison table, and recomputation
  result are archived in the processed-data deposit
  (`validation_station/`), so this validation is fully reproducible without a
  new NOAA order.

## 3. What is not redistributed

- The full hourly ERA5 archive (provider-managed, ~terabytes) is not
  redistributed. The yearly daily-Tmax NetCDFs (~8.4 GB) are reconstructible
  with `download_era5_arco.py` and are not part of the Zenodo deposit.
- The raw NOAA CDO order export beyond the Aswan station columns used is not
  redistributed; the extracted station series is.

## 4. Reproducibility tiers

- Tier A (fast reproduction; the only executable route): start from the
  Zenodo processed-data deposit; no external downloads required.
- Tier B (provider-level reconstruction GUIDE): re-running the ARCO-ERA5
  download and the processing chain above is documented in
  `docs/PROVIDER_RECONSTRUCTION_GUIDE.md` (structurally validated, not
  executed end to end for this release). Storage roughly 9 GB NetCDF +
  2 GB CSV; the download is chunked per year and restartable (failed years
  leave `{year}.failed.txt` markers and can be re-run individually).
