# Provider-level reconstruction guide

> **This document is a GUIDE, not a reproduction run.** Following it rebuilds
> the processed daily field from provider-managed ERA5. The steps are
> STRUCTURALLY VALIDATED ONLY: the scripts ship, import, and expose the
> documented arguments, but they were NOT rerun end to end for this release.
> No command in this release claims to have performed them.
>
> The identical text is printed by `scorch reconstruction-guide` and by
> `python run_reproduction.py guide`.

```
PROVIDER-LEVEL RECONSTRUCTION GUIDE -- DOCUMENTATION ONLY, NOTHING IS RUN
========================================================================
This text describes how a provider-scale user would rebuild the PROCESSED
DAILY FIELD from raw ERA5. It is a GUIDE. Printing it reconstructs nothing,
verifies nothing, and is not a reproduction run. The steps below are
STRUCTURALLY VALIDATED (the scripts ship, import, and expose the documented
arguments) but have NOT been rerun end to end in this release: they need a
multi-hour provider download, LOCAL WORKING STORAGE exceeding 10 GB (about
8.4 GB of yearly daily-Tmax NetCDF files at ~98 MB each, plus a roughly
2 GB derived long-table CSV and intermediates; the possible NETWORK
TRANSFER of hourly source data is a separate quantity of order 100 GB),
and R with the spatstat packages.

What IS executed and verified is the connected reconstruction from the
deposited processed field onward:

    scorch reproduce --base-dir <deposit-root> --route fast

Steps (each must be run by hand, in order):

1. Download daily ERA5 Tmax (1940-2025, April-September, 10-46N / 20-70E):
     python scripts/download/download_era5_arco.py --outdir <ncdir>
   (or the CDS route: download_era5_cds.py + era5_hourly_to_daily_tmax.py)

2. Aggregate to the 1-degree grid, derive per-cell warm-season p95
   thresholds, apply the exceedance rule (tmax >= threshold) and the
   canonical heatwave labelling; writes master_exceed_heatwaves_long.csv:
     python scripts/pipeline/build_master_dataset.py --datadir <ncdir>
   NOTE: --datadir is REQUIRED. Without it the script exits with an error;
   it does not fall back to any default location.

3. Package the processed field as the deposited CF-1.10 NetCDF:
     python scripts/deposit/build_processed_field_netcdf.py \
         --master-csv <step-2 CSV> \
         --extent-csv <deposit gridded/fig02_daily_extent.csv> \
         --out scorch_processed_daily_tmax_field_v1.0.0.nc
   The result is the input to the executable fast route above, which
   performs selection, daily DBSCAN parameter choice, event-global
   parameters, clustering, ellipse geometry and typology, and verifies each
   stage against the deposited catalogs.

4. Centroid-concentration (LGCP) chain, needing the step-2 long table:
     set SCORCH_ERA5_TMAX_LONG_CSV=<step-2 CSV>
     python scripts/lgcp/build_inputs.py
     Rscript scripts/lgcp/spatial_risk_lgcp_model_diagnostics.R \
         reproduced/lgcp_inputs reproduced/lgcp/model_diagnostics_and_variants
     python scripts/lgcp/extract_variant3.py
   (The fit itself HAS been executed against the deposited lgcp/ inputs;
   only the step-2 covariate construction needs this provider chain.)

The processed-data deposit already contains the verified outputs of steps
2-4, so nothing downstream requires this guide to be executed.
```
