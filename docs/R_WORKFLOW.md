# MIXED-LANGUAGE WORKFLOW (Python + R)

SCORCH is not a pure-Python workflow. The log-Gaussian Cox process (LGCP)
centroid-concentration model of the paper (a model of relative spatial
centroid concentration; see docs/TERMINOLOGY.md) is fitted in R with the
spatstat family; everything else runs in Python. This document states exactly
where the language boundary sits.

## Python stages

1. ERA5 acquisition and daily Tmax NetCDFs (scripts/download/).
2. Master dataset construction: 1-degree aggregation, p95 thresholds,
   exceedance, per-cell heatwave labelling (scripts/pipeline/).
3. Regional day selection (Theta = 371), compound-event construction,
   Method-A DBSCAN parameter selection, event-global-max re-clustering,
   PCA ellipses (sigma = 1.25, 1 km2 eigenvalue floor), Type 1-4 typology
   (the scorch package and scripts/pipeline/).
4. LGCP input preparation: centroids, covariates over the 1,800 grid cells,
   LAEA (km) raster window (scripts/lgcp/build_inputs.py; requires the
   external warm-season Tmax master CSV or its reconstruction).
5. All figures and tables except the LGCP fit itself; the manuscript
   Figure 12 map and the five-fold validation are Python and read the R
   outputs as CSV.

## R stage (R 4.5.1, spatstat.model 3.7-1)

- scripts/lgcp/spatial_risk_lgcp_model_diagnostics.R fits the four candidate
  trend models with kppm (clusters "LGCP", method "mincon", statistic "K",
  exponential covariance) on the 760 centroids and writes
  lgcp_model_parameters.csv and grid_predicted_intensity_all_variants.csv.
  The manuscript model is variant3: ~ lon + lat + mean_tmax_z + std_tmax_z
  fitted to the 760 raw-Celsius Tmax-weighted centroids
  (sigma^2 = 1.642911, scale = 272.455 km).
- Run:
  `Rscript scripts/lgcp/spatial_risk_lgcp_model_diagnostics.R <input-dir> <output-dir>`
  where `<input-dir>` holds the Stage-4 outputs (defaults to
  `scorch_data/lgcp`, the processed-data deposit layout) and `<output-dir>`
  receives the fit results (defaults to
  `reproduced/lgcp/model_diagnostics_and_variants`).
- The R stage is also invoked automatically by
  the provider-level reconstruction guide (`scorch reconstruction-guide`)
  (stage `lgcp-fit-r`), which locates and runs `Rscript` for you.
- The Python-side variant3 extraction (scripts/lgcp/extract_variant3.py) then
  produces grid_predicted_intensity_variant3.csv, which is also archived in
  the processed-data deposit, so the FAST reproduction route never needs R.

## Environment pinning

- Python: environment.yml and the curated lock
  environment/requirements-lock-py312.txt (complete transitive lock with
  hashes).
- R: environment/renv.lock (R 4.5.1; spatstat 3.6-1, spatstat.geom 3.8-1,
  spatstat.model 3.7-1, spatstat.explore 3.8-1, jsonlite 2.0.0). Restore the
  exact R package versions with renv:

  ```
  Rscript -e "install.packages('renv'); renv::restore(lockfile='environment/renv.lock')"
  ```

## Note on the legacy baseline

The research repository historically included a separate `fit_lgcp.R`
baseline centroid-concentration model (cv_tmax_z covariate). It is NOT part
of the paper's canonical chain and that file does not ship in this release;
the diagnostics script above is the only fitting route.
