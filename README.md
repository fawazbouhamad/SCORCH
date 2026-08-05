# SCORCH

**SCORCH (Spatiotemporal Classification of Regional Compound Heatwaves)** is
the framework behind the paper *"Understanding the Spatiotemporal Organization
of Regionally Extensive Heatwaves Using the SCORCH Framework"* (Bouhamad and
Najibi). It detects, clusters, and geometrically characterizes regionally
extensive compound heatwaves in ERA5 daily maximum temperature over the
Eastern Mediterranean and Middle East (lat 10-46 N, lon 20-70 E, Apr-Sep
1940-2025), producing a catalog of 51 events / 760 PCA ellipses, a four-class
event typology, and a first-order centroid-concentration model of where
heat-structure centroids concentrate spatially.

Repository: <https://github.com/fawazbouhamad/SCORCH>

## What this repository contains

Two clearly separated things:

1. **The installable SCORCH analysis library** (`src/scorch`, distribution
   name `scorch-heatwaves`, import name `scorch`): the canonical scientific
   kernels (verbatim copies of the research code, so results are identical to
   the canonical catalog), catalog loading/validation, the CLI, and builtin
   end-to-end reconstruction stages.
2. **Repository-level paper reproduction**: the `scripts/` tree (figure,
   table, LGCP and validation generators) and `run_reproduction.py` +
   `Makefile`, which regenerate the publication figures and the manuscript
   tables from the processed-data deposit. The 17 manuscript figures fall
   into four honest reproduction classes, not one: **6** are
   `data_generated` (script output byte-identical to the embedded raster:
   Fig. 2, 3, 12, B, D, S.1); **8** are
   `deployment_export_of_reproduced_original` (the plotted content is
   reproduced byte-identically at full resolution, but the embedded raster
   is a downscaled deployment export of it: Fig. 5, 6, 7, 9, 10, 11, A,
   C -- Figure 9 joined this class in the v1.0.0 pre-release correction,
   which replaced the invalid arithmetic mean of event orientations with
   the doubled-angle axial mean and regenerated the figure end-to-end);
   **1** is `manually_postprocessed_approved_artwork` (the approved
   original carries a manual post-processing pass the script does not
   reproduce: Fig. 8); and **2** are `frozen_approved_artwork` (author
   slide exports with no runnable producer, materialized and hash-verified,
   never regenerated from data: Fig. 1, 4). `docs/FIGURE_PROVENANCE.csv`
   and `docs/MANUSCRIPT_FIGURE_IDENTITY.csv` carry the per-figure class and
   hashes. These are NOT installed with the package: you must CLONE THE
   REPOSITORY to use them.
   The installed package alone runs the reconstruction, not the figures.
   `configs/reproduction_fast.yaml` is a repository copy of the canonical
   stage list; the authoritative copy ships inside the installed package as
   package data, so `scorch reproduce` needs no repository path.

## Pipeline overview

1. **Thresholds** -- aggregate 0.25-degree ERA5 daily Tmax to 1-degree grid
   cells (mean, centres at .5), per-cell 95th-percentile thresholds, 0/1
   exceedance.
2. **Heatwave labelling** -- per-cell episodes: split at two consecutive
   non-exceedance days, trim to exceedance ends, keep runs with >= 3 days and
   >= 3 exceedance days (single-day gaps bridged).
3. **Regional selection** -- days whose heatwave-cell count reaches the
   integer-like P97.5 threshold (Theta = 371; method "higher") are selected
   (395 days); consecutive selected days form 51 events.
4. **Clustering** -- per-day DBSCAN on grid-cell distances; Method-A modal
   parameter selection over a 63-combination grid, then event-global-maximum
   parameters (max averaged eps; max rounded min_samples) per event.
5. **Ellipses** -- one sigma = 1.25 PCA ellipse per component (1 km^2
   eigenvalue variance floor).
6. **Typology** -- mechanical Types 1-4 from the per-day ellipse counts.
7. **Centroid-concentration model** -- an inhomogeneous log-Gaussian Cox
   process fitted to the 760 ellipse centroids (R/spatstat, minimum
   contrast; trend ~ lon + lat + mean_tmax_z + std_tmax_z) summarizing the
   relative spatial centroid concentration across the domain, with an
   occurrence-level five-fold cross-validation. The fitted surface is a
   relative concentration summary of the observed catalog; it is not a
   probability, risk, hazard, or susceptibility estimate, and the mapped
   quantile surface is not a realization of the latent field.

## Install

```bash
pip install git+https://github.com/fawazbouhamad/SCORCH.git
# optional extras:
#   .[maps]      matplotlib + cartopy figure stack
#   .[download]  xarray/netCDF4/zarr/gcsfs/cdsapi source-data tooling
#   .[figures]   pymannkendall + imageio + Pillow + pypdf + tabulate
#                (trend/figure/statistics scripts)
#   .[full]      everything above
#   .[dev]       pytest + netCDF4 (netCDF4 enables the NetCDF-dependent tests)
```

Requires Python >= 3.11. The import name is `scorch`; the distribution name
is `scorch-heatwaves`. This unpinned CONVENIENCE install resolves current
compatible versions; it is NOT the exact environment that produced the
paper outputs. For exact reproduction install the hash lock:
`pip install --require-hashes -r environment/requirements-lock-py312.txt`
then `pip install --no-deps .`.

Known benign import warning: the netCDF4/cftime binary wheels emit
`RuntimeWarning: numpy.ndarray size changed` when `netCDF4` is imported
after pandas/scikit-learn/scipy. This is an upstream wheel artifact that
occurs on every numpy 2.x tested, INCLUDING the exact hash-locked
reproduction environment, and does not indicate a real incompatibility
(all tests pass and every canonical number reproduces). The test
configuration filters exactly this message; no version pin can eliminate
it. The R stages (LGCP fit) additionally require R >= 4.3
with the `spatstat` packages -- see `docs/R_WORKFLOW.md` and
`environment/renv.lock`.

## Quickstart (API)

```python
import pandas as pd
import scorch

# 1. Label heatwaves in one grid cell's 0/1 exceedance series
exceed = pd.Series([0, 1, 1, 1, 0, 1, 1, 0],
                   index=pd.date_range("2000-06-01", periods=8))
labels, episodes = scorch.identify_heatwaves(exceed)

# 2. Cluster one day's heatwave cells (event-global-max parameters)
lon = [30.5, 31.5, 32.5, 40.5]
lat = [20.5, 20.5, 21.5, 30.5]
labels = scorch.cluster_structures(lon, lat, eps=2.5, min_samples=2)

# 3. Fit the canonical PCA ellipse (sigma = 1.25)
ellipse = scorch.fit_pca_ellipses((lon, lat), sigma=1.25)
print(ellipse["ellipse_area_km2"], ellipse["orientation_deg"])

# 4. Load and validate the canonical master catalog, re-derive the typology
master = scorch.load_master("scorch_data/scorch_processed_data_v1.0.0/"
                            "catalogs/scorch_new_algorithm_master_cluster_"
                            "ellipse_event_global_max.csv")
scorch.validate_master(master, expect_canonical_counts=True)
types = scorch.classify_events(master)
```

## Quickstart (CLI)

```bash
scorch version
# Download the Zenodo deposit ZIP, extract it safely, locate the deposit
# root, and verify every embedded checksum (fails hard on any mismatch).
# fetch-data REQUIRES the deposit identifier: pass --doi (or --url), or set
# the SCORCH_DATA_DOI environment variable. The DOI is reserved while the
# Zenodo draft is private and becomes publicly resolvable when the record
# is published; there is no built-in default to discover it:
scorch fetch-data --doi 10.5281/zenodo.21717752 --dest scorch_data
#   (equivalently:  SCORCH_DATA_DOI=10.5281/zenodo.21717752 scorch fetch-data ...
#    or:            scorch fetch-data --url <deposit record URL> ...)
# Structure + checksum + row-count + type-count validation:
scorch validate-deposit --dir scorch_data
# Deposit-only end-to-end reconstruction (processed field -> catalog),
# verified stage-by-stage against the archived deposit. Any selected stage
# that is missing or fails ABORTS with a non-zero exit status:
# The canonical stage list is BUNDLED with the installed package, so no
# --config and no repository checkout are needed:
scorch reproduce --base-dir scorch_data/scorch_processed_data_v1.0.0 \
    --route fast --out-dir reproduced
# Provider-level ERA5 reconstruction guide (prints steps; runs nothing):
scorch reconstruction-guide
scorch validate-sources --dir /path/to/era5_daily --sample 5
```

## Reproduction routes

* **Fast route (recommended; minutes to ~1 hour, no ERA5 download)** --
  `scorch fetch-data --doi 10.5281/zenodo.21717752` +
  `scorch reproduce --route fast` runs the complete
  processed-field -> catalog reconstruction from the deposit: CF NetCDF field
  consistency (thresholds, exceedance, daily coverage), regional selection
  (Theta = 371 -> 395 days -> 51 events), Method-A daily DBSCAN parameter
  selection, event-global parameters, re-clustering (760 structures with
  identical partitions), PCA ellipse geometry (relative difference < 1e-6),
  and the typology (3/4/20/24). Every stage verifies against the archived
  values and fails loudly on any deviation.
* **Figure regeneration** -- `python run_reproduction.py fast` (or
  `make fast`) regenerates the manuscript figures and tables from the
  deposit into `reproduced/`; see `docs/REPRODUCIBILITY_REPORT.md` for the
  byte-identity results.
* **Provider-level reconstruction (GUIDE ONLY, not an executable route)** --
  rebuilding the processed daily field itself from provider-managed ERA5 is
  documented, not automated: `scorch reconstruction-guide` (or
  `python run_reproduction.py guide`, or
  `docs/PROVIDER_RECONSTRUCTION_GUIDE.md`) PRINTS the ordered steps and
  exits. It reconstructs nothing and verifies nothing. Those steps are
  STRUCTURALLY VALIDATED ONLY: the scripts ship, import, and expose the
  documented arguments, but they were not rerun end to end for this release
  (multi-hour provider download; plan for LOCAL WORKING STORAGE exceeding
  10 GB - about 8.4 GB of yearly daily-Tmax NetCDF files plus a roughly
  2 GB derived long-table CSV and intermediates - while the possible
  NETWORK TRANSFER of hourly source data is separate and of order 100 GB;
  R + spatstat).
  There is no `--route full`; no command reports success for work it did not
  perform.

## Documentation

* `docs/SOURCE_DATA_PROVENANCE.md` -- ERA5 / GHCN-D provenance and citations.
* `docs/SOURCE_DOWNLOAD_GUIDE.md` -- obtaining the source data.
* `docs/R_WORKFLOW.md` -- the R/spatstat centroid-concentration model chain.
* `docs/TERMINOLOGY.md` -- naming conventions, including legacy "risk"-named
  files/columns retained for provenance.
* `docs/PROVIDER_RECONSTRUCTION_GUIDE.md` -- the provider-level ERA5
  reconstruction guide (documentation only; structurally validated, not
  rerun end to end).
* `configs/reproduction_fast.yaml` -- repository copy of the machine-readable
  stage list (stages, canonical parameters, seeds, expected counts); the
  authoritative copy ships as package data inside the installed package.

## Citation and license

Code and repository/environment configuration: MIT License. Documentation
and record metadata: CC BY 4.0. Rights are PATH-SPECIFIC and the complete,
non-overlapping path table - covering the frozen figure assets, the
station-donor artwork, the auxiliary Method-A analysis data and the
governing `LICENSE` notice - is in `docs/LICENSES_AND_ATTRIBUTION.md`. If
you use this package, please cite
the SCORCH paper (Bouhamad, F. and Najibi, N.) and the data deposit
referenced in `docs/SOURCE_DATA_PROVENANCE.md`. The canonical public records
for the release used in the article are the reserved Zenodo software record
https://doi.org/10.5281/zenodo.21717874, the reserved Zenodo processed-data
record https://doi.org/10.5281/zenodo.21717752, and the GitHub release
<https://github.com/fawazbouhamad/SCORCH/releases/tag/v1.0.0>. RELEASE
INVARIANT: the exact archive approved for publication must be attached to
both the GitHub v1.0.0 release and the Zenodo software record; the DOIs
resolve once the records are published.
ERA5: Copernicus Climate Change Service; contains modified Copernicus
Climate Change Service information. GHCN-Daily: NOAA NCEI.
