# SCORCH

**Spatiotemporal Classification of Regional Compound Heatwaves**

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

SCORCH is a reproducible Python framework for detecting and characterizing
regionally extensive compound heatwaves over the Eastern Mediterranean and
Middle East. From ERA5-derived daily maximum temperature it detects local
heatwave episodes, selects the days on which heat is regionally extensive,
groups consecutive selected days into compound events, resolves the daily
spatial heat structures within them, summarizes each structure's geometry
with a PCA ellipse, and assigns every event to one of four types defined by
duration and daily structural multiplicity.

**Documentation:** [Reproducibility](docs/REPRODUCIBILITY_REPORT.md) ·
[Provider reconstruction](docs/PROVIDER_RECONSTRUCTION_GUIDE.md) ·
[Figure provenance](docs/FIGURE_PROVENANCE.csv) ·
[Reproducibility matrix](docs/REPRODUCIBILITY_MATRIX.csv) ·
[Licences and attribution](docs/LICENSES_AND_ATTRIBUTION.md) ·
[Terminology](docs/TERMINOLOGY.md)

## Method summary

The analysis domain is a 1° grid over the Eastern Mediterranean and Middle
East (10–46 °N, 20–70 °E), restricted to the April–September warm season for
1940–2025. This yields 1,800 valid grid boxes across 15,738 warm-season
days.

For each grid cell, the local threshold is the 95th percentile of daily Tmax
pooled across all April–September days during 1940–2025: a single fixed
threshold per cell, not a calendar-day climatology. A day is a
threshold-meeting day for that cell when its Tmax is greater than or equal
to that value.

Local heatwave episodes are delimited by two consecutive non-exceedance
days, trimmed to begin and end on threshold-meeting days, and retained when
they span at least three days and contain at least three threshold-meeting
days. An isolated non-exceedance day inside a qualifying episode is bridged
and remains part of it. Cells belonging to a retained episode on a given day
are heatwave-labeled cells.

Days on which the count of heatwave-labeled cells reaches the regional
97.5th-percentile threshold (*N*<sub>HW</sub>(*t*) ≥ 371) are retained as
regionally selected days; there are 395 of them. Compound events are the
maximal runs of consecutive selected days: 51 events. Event construction is
purely temporal: the consecutive-day runs, not any clustering step, define
compound events.

Within each selected day, DBSCAN is applied to that day's heatwave-labeled
cells to delineate spatially coherent daily heat structures, giving 760
structures overall. Each structure's geometry is summarized by a PCA ellipse
at a fixed σ = 1.25, computed without temperature weighting and then rigidly
translated to the structure's Tmax-weighted centroid (raw degrees Celsius
within that structure). The translation changes the ellipse's location only;
it does not alter clustering, PCA axes, orientation, area, shape ratio, or
typology. Events are then classified by duration and daily structural
multiplicity into four types, with 3, 4, 20 and 24 events in Types 1–4
respectively.

SCORCH does not track structures across days: it characterizes each day's
structures independently and makes no claim about structure identity,
continuity, splitting, or merging over time. SCORCH also fits a log-Gaussian
Cox process to the structure centroids; that surface is a relative
concentration summary, not a probability, risk, hazard, susceptibility, or
impact estimate, and not a forecast.

## Analysis workflow

<p align="center">
  <img src="assets/frozen_figures/fig01/Figure_01.png"
       alt="SCORCH workflow from ERA5 daily maximum temperature through local heatwave detection, regional-day selection, event construction, daily spatial clustering, PCA geometry, event classification, and downstream analyses."
       width="820">
</p>

<p align="center"><em>SCORCH analysis workflow. Local heatwave episodes are
identified, regionally selected days are chosen, and maximal
consecutive-day runs define compound events before daily spatial clustering
of heatwave-labeled cells and geometric analysis.</em></p>

## Event typology

<p align="center">
  <img src="assets/frozen_figures/fig04/Figure_04.png"
       alt="Four SCORCH compound-heatwave event types defined by event duration and daily heat-structure multiplicity."
       width="820">
</p>

<p align="center"><em>SCORCH compound-heatwave typology based on duration
and daily structural multiplicity. The diagram summarizes daily
configurations and does not represent tracked structure identities,
splitting, or merging.</em></p>

## Installation and reproduction

Python orchestrates the whole workflow. The log-Gaussian Cox process stage
additionally invokes R with `spatstat` through an external `Rscript` call;
that stage is documented in [docs/R_WORKFLOW.md](docs/R_WORKFLOW.md).

```bash
# 1. install: canonical hash-locked route (fully pinned)
python -m pip install --require-hashes -r environment/requirements-lock-py312.txt
python -m pip install --no-deps -e .

# 2. fetch and verify the processed-data deposit
python -m scorch.cli fetch-data \
  --doi 10.5281/zenodo.21717752 \
  --dest scorch_data
python -m scorch.cli validate-deposit --dir scorch_data

# 3. run the full fast route (canonical bootstrap NBOOT=5000)
python run_reproduction.py fast \
    --data-dir scorch_data \
    --out-dir reproduced \
    --pub-dir publication_outputs \
    --nboot 5000

# 4. unit and regression tests
python -m pytest tests -q
```

Step 1 is the canonical route: it installs the exact hash-pinned
environment that produced the reported numbers. The convenience alternative
`python -m pip install -e ".[full,dev]"` resolves dependencies freely and is
non-canonical.

Step 2 requires the data record to be published. The data DOI
`10.5281/zenodo.21717752` is currently reserved and does not yet resolve, so
`fetch-data --doi` will not retrieve anything until the record is public.
Until then, point `--data-dir` at an authorized preview or existing local
copy of the deposit and skip `fetch-data`.

The fast route begins from the processed deposit, not from raw provider
files. Rebuilding the inputs from raw ERA5 fields retrieved from the
Copernicus Climate Data Store is documented in
[docs/PROVIDER_RECONSTRUCTION_GUIDE.md](docs/PROVIDER_RECONSTRUCTION_GUIDE.md);
that provider-level route is not fully automated. Useful variants:
`python run_reproduction.py smoke` (catalog validation plus a figure/table
subset) and `python run_reproduction.py guide` (print the provider
reconstruction guide). `--nboot` defaults to the canonical 5000; smaller
values give a quick, non-canonical run.

## Repository structure

| Path | Contents |
|---|---|
| `assets/` | Figures and figure provenance |
| `configs/` | Reproducibility configuration |
| `data/` | Tracked data documentation and auxiliary inputs |
| `docs/` | Scientific and release documentation |
| `environment/` | Environment specifications |
| `scripts/` | Executable workflows and release tools |
| `src/` | The Python package |
| `tests/` | Verification and regression tests |
| `provenance/` | Scientific correction evidence and legacy artifact records |

Per-figure provenance is machine-readable: see
[docs/FIGURE_PROVENANCE.csv](docs/FIGURE_PROVENANCE.csv),
[docs/MANUSCRIPT_FIGURE_IDENTITY.csv](docs/MANUSCRIPT_FIGURE_IDENTITY.csv)
and [docs/REPRODUCIBILITY_MATRIX.csv](docs/REPRODUCIBILITY_MATRIX.csv).

## Data and software availability

| Resource | Identifier | Status |
|---|---|---|
| Source repository | https://github.com/fawazbouhamad/SCORCH | Public |
| Processed-data archive | [10.5281/zenodo.21717752](https://doi.org/10.5281/zenodo.21717752) | Reserved DOI; record forthcoming |
| Software archive | [10.5281/zenodo.21717874](https://doi.org/10.5281/zenodo.21717874) | Reserved DOI; record forthcoming |

Both Zenodo DOIs are reserved and not yet resolvable. The records are
unpublished drafts; the DOIs will begin to resolve when the records are
published, and archive badges will be added at that point, not before.

SCORCH redistributes no raw provider data. ERA5-derived content carries the
Copernicus/ECMWF terms and required notice, and GHCN-Daily-derived content
the NOAA/NCEI source and use terms; both are set out in
[docs/LICENSES_AND_ATTRIBUTION.md](docs/LICENSES_AND_ATTRIBUTION.md).

## Verification status

| Check | Result |
|---|---|
| Frozen release test collection | 1,261 tests; sorted node-ID SHA-256 `bc3709c63ec859047813d761a964eddfab386379b90ecb751e8c8296be036077` |
| Source-only profile | 1,215 pass and 46 skip (deposit-, catalog-, DOCX- and font-dependent guards); none fail |
| Fully configured profile | 1,259 pass, with 2 expected pre-finalization identity check failures |
| NetCDF release gate | Pass against the corrected candidate archive |
| Fast reproduction route | 33/33 stages pass, including the publication-outputs assembly |
| Reconstruction route | 9/9 stages pass, weighted-centroid stage executing 760/760 |

The two configured-profile failures are expected before release
finalization: they compare the corrected candidate archive against
superseded identity values that the controlled finalization step will
update. The acceptance record in
[docs/CANONICAL_SCIENCE.json](docs/CANONICAL_SCIENCE.json) additionally
preserves the clean-room measurement at its 496-test recording point, where
450 passed with 46 skipped in the source-only profile and 473 passed with
one expected failure in the required-archive profile.

## Citation

Cite the software using the metadata in [`CITATION.cff`](CITATION.cff);
GitHub renders it under **Cite this repository**. The associated manuscript
is:

> Bouhamad, F., and Najibi, N. Understanding the Spatiotemporal Organization
> of Regionally Extensive Heatwaves Using the SCORCH Framework. Manuscript
> prepared for submission to *Weather and Climate Extremes*.

If you use SCORCH, please cite the software archive and manuscript; if you
use the deposited data, please also cite the data archive. Citation is
requested as a matter of scholarly practice and is not an additional
condition of the GPL.

## License and attribution

SCORCH source code is licensed under the GNU General Public License v3.0
only (GPL-3.0-only). Data, figures, documentation, and third-party material
may have separate path-specific terms described in
[docs/LICENSES_AND_ATTRIBUTION.md](docs/LICENSES_AND_ATTRIBUTION.md).
Earlier public revisions of this repository were released under the MIT
License and remain under the licence included with those revisions; see
[docs/LICENSING_HISTORY.md](docs/LICENSING_HISTORY.md).

Contains modified Copernicus Climate Change Service information 2026.
Neither the European Commission nor ECMWF is responsible for any use that may
be made of the Copernicus information or data it contains.

ERA5 coverage used in this work: 1940–2025 (warm seasons, April–September).
Copernicus licence: https://ecds.ecmwf.int/licences/licence-to-use-copernicus-products
CC BY 4.0 covers only the authors' contributions; it is not asserted over the
underlying ERA5 or GHCN-Daily observations.

## Issues and contact

Please open an issue on the
[issue tracker](https://github.com/fawazbouhamad/SCORCH/issues). Contributor
guidance is in [CONTRIBUTING.md](CONTRIBUTING.md).
