# LICENCES AND ATTRIBUTION

## Licence scope by path (authoritative)

Every file deployed to the public repository (the `scorch-release` tree
minus the never-deployed `reproduced/` outputs, the materialized
`publication_outputs/` tree, any downloaded `scorch_data/`, and tool
caches) and every file in the companion Zenodo data deposit falls under
exactly one row below. `publication_outputs/` is excluded because it is
deterministic output rather than source: it is assembled by
`scripts/publication/build_publication_outputs.py` from files that are
themselves covered by the rows below, so classifying it would licence the
same material twice. Each assembled file inherits the licence of the row
that covers the input it was materialized from; `publication_outputs/`
carries its own `README.md` recording that inheritance, and every figure's
`PROVENANCE.txt` names the input it was routed from by SHA-256. The two governing legal
notices - this repository's `LICENSE` file and the deposit's
`LICENSE.txt` - have their own explicit rows: each is the controlling
legal and attribution notice for its collection and is not additionally
covered by any content row.

| Path | Licence |
|---|---|
| `src/**`, `scripts/**`, `tests/**`, `run_reproduction.py`, `Makefile`, `configs/**` - **software and text only**, expressly EXCLUDING the three frozen artwork rasters carved out in the next row | **GPL-3.0-only** (see `LICENSE`) |
| `scripts/figures/fig01/original/Figure_01_original.png`, `scripts/figures/fig04/original/Figure_04_original.png`, `scripts/figures/fig04/donor/Figure_04_approved_horizontal.png` (the archived-original and immutable-donor slide artwork that the Figure 1 and Figure 4 producers READ as input) | **CC BY 4.0 PENDING - NOT YET IN FORCE.** These three files are author-created slide ARTWORK that happens to sit under a code directory; they are NOT software and are NOT GPL-3.0-only. The row above must never be read as licensing them: a GPL grant over the SCORCH software is not artwork permission. The artwork creator's CC BY 4.0 declaration for these files **has not been recorded** in this repository state. Until it is, no public licence is granted over these three rasters and no CC BY 4.0 grant may be asserted anywhere for them |
| `environment/**`, `environment.yml`, `pyproject.toml`, `.gitattributes`, `.gitignore` (environment locks, build and repository configuration) | **GPL-3.0-only** (see `LICENSE`) |
| `docs/**`, `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `CITATION.cff`, `.zenodo.json` (author-created documentation and record metadata) | CC BY 4.0 |
| `assets/frozen_figures/README.md`, `assets/frozen_figures/SHA256SUMS` (the authors' own checksum and documentation records for this directory - text, not artwork) | CC BY 4.0 |
| `assets/frozen_figures/fig01/**`, `assets/frozen_figures/fig04/**` (the shipped Figure 1 and Figure 4 slide artwork, PNG and PDF) | **CC BY 4.0 PENDING - NOT YET IN FORCE.** Same artwork, same gate as the donor rasters above: the artwork creator's CC BY 4.0 declaration **has not been recorded** in this repository state. No CC BY 4.0 grant is in force over Figure 1 or Figure 4 in this repository, in the companion deposit, in `publication_outputs/`, or in any PNG/PDF export derived from them. Figures 1 and 4 depict no ERA5 or GHCN-Daily material, so no provider terms attach to them; the gate here is the creator's own recorded declaration alone |
| `assets/frozen_figures/figS1_station_donor/**` (frozen station-comparison artwork) | CC BY 4.0 for the authors' artwork; the depicted station observations remain subject to the GHCN-Daily source/use terms and attribution, and the depicted reanalysis values to the current Copernicus ERA5 terms and required attribution |
| `assets/manuscript_final/**` (the **six** authenticated manuscript-final figure rasters - Figures 8, 9, 10, 11 and Appendices A and C - and their checksum/README records) | CC BY 4.0 for the authors' artwork + current Copernicus ERA5 terms and required attribution for the depicted ERA5-derived material. These are the exact rasters embedded in the manuscript; each is plotted from the deposit catalogs, which are ERA5-derived, so they follow the Method-A auxiliary-data treatment rather than the plain CC BY 4.0 treatment of the frozen slide exports. The count is **six, not nine**: the pre-correction Figure 5, 6 and 7 exports are no longer shipped here (see `docs/RELOCATED_ARTIFACTS.csv`), and the CC BY 4.0 grant in this row covers only these six rasters and the directory's own records |
| `data/auxiliary/**` (author-generated Method-A analysis data) | CC BY 4.0 for the authors' original processing and contribution + current Copernicus ERA5 terms and required attribution for the underlying ERA5-derived material |
| `LICENSE` (repository licence file) | The complete, unmodified GNU General Public License v3.0 text, reproduced verbatim under the FSF's own terms for copying that document. It is the controlling software licence for the rows marked GPL-3.0-only above and is not itself separately licensed content. The data attribution notices that earlier revisions appended to this file now live in the "Relocated data and attribution notices" section of **this** document, so that `LICENSE` remains the unmodified GPL text and is machine-detectable as `GPL-3.0-only` |
| Data deposit: `LICENSE.txt` | The deposit's controlling legal and attribution notice; its section 0 is the deposit's authoritative path table |
| Data deposit: `validate_deposit.py` | **MIT** (software, not CC BY) |
| Data deposit: author-created processed data and documentation not otherwise identified in this table | CC BY 4.0 for the authors' original contributions |
| Data deposit: ERA5-derived files (`gridded/**`, `lgcp/tmax_covariate_grid_all_boxes.csv`, `lgcp/covariate_raster_km.csv`, `validation_station/era5_*`, `figure_table_source_data/fig02/*`) | CC BY 4.0 for the authors' processing + current Copernicus ERA5 terms and required attribution |
| Data deposit: `validation_station/ghcnd_*`, `merged_station_validation.csv`, `recompute_result.json` | GHCN-Daily source/use terms and attribution (applicable source-provider rights retained); authors' processing CC BY 4.0; the merged file's ERA5 column also carries the Copernicus terms; `recompute_result.json` is the authors' derived output under CC BY 4.0 |

## Figure 1 / Figure 4 artwork: CC BY 4.0 PENDING, not yet in force

The Figure 1 and Figure 4 slide artwork - the shipped assets under
`assets/frozen_figures/fig01/` and `fig04/`, the archived-original and
immutable-donor rasters under `scripts/figures/fig01/original/` and
`scripts/figures/fig04/{original,donor}/`, and every PNG/PDF export derived
from them, including anything materialized into `publication_outputs/` - is
**CC BY 4.0 PENDING and NOT YET IN FORCE.**

This artwork was created by Fawaz Bouhamad, who is its copyright holder
and sole licensor. Dr. Nasser Najibi provided scientific guidance, review
and corrections for these figures and is credited for that contribution,
and is not a licensor of this artwork. The creator's CC BY 4.0
declaration **has not been recorded** in this repository state, so no
CC BY 4.0 grant exists over this artwork anywhere in this repository, the
companion data deposit, or any export. Two things that are NOT that
declaration: the GPL-3.0 licence covering the SCORCH software, and the
fact that the artwork's producers and some of its donor rasters sit under
`scripts/`. No record may state or imply an active
CC BY 4.0 licence for Figure 1 or Figure 4 while this section stands; that
contradiction is machine-enforced by
`tests/test_public_consistency_guards.py`.

`validate_deposit.py` is SOFTWARE and is licensed MIT. Any earlier statement
assigning it to CC BY 4.0 alone is superseded. The deposit's own
`LICENSE.txt` carries the same path table together with the FULL legal texts
of the MIT licence and the CC BY 4.0 summary, and the ERA5 and NOAA notices.

Full licence texts: the complete GNU General Public License v3.0 text
governing the SCORCH software is in this repository's `LICENSE` file
(verbatim, unmodified) and at https://www.gnu.org/licenses/gpl-3.0.txt. The
complete MIT text applying to the deposit's `validate_deposit.py` is in
section 2 of the deposit's `LICENSE.txt`. The complete CC BY 4.0 legal code
is at https://creativecommons.org/licenses/by/4.0/legalcode
(summary: https://creativecommons.org/licenses/by/4.0/); section 1 of the
deposit's `LICENSE.txt` reproduces the operative summary and points to that
legal code.

## Relocated data and attribution notices

Revisions of this repository up to and including v1.0.0 carried these
notices appended beneath the licence text inside the root `LICENSE` file.
They were moved here so that `LICENSE` can hold the complete, unmodified GNU
GPL v3.0 text and be correctly detected as `GPL-3.0-only` by automated
licence scanners. The notices themselves are unchanged in substance and
remain in force.

- This repository is the controlling collection for the path table above.
  The complete non-overlapping path table that assigns rights to every
  deployed file is **this document**; the companion deposit's own
  controlling notice is its `LICENSE.txt`.
- This repository redistributes no raw provider data. Derived data products
  and their attribution requirements are described above, including the
  required Copernicus/ECMWF notice for ERA5-derived content and the
  applicable GHCN-Daily source/use terms and NOAA/NCEI attribution for
  GHCN-Daily-derived content.
- The auxiliary Method-A analysis data under `data/auxiliary/` is the
  authors' original processing under CC BY 4.0, with the Copernicus terms
  continuing to apply to the underlying ERA5-derived material.
- The frozen station-donor artwork under
  `assets/frozen_figures/figS1_station_donor/` is the authors' CC BY 4.0
  artwork depicting GHCN-Daily and ERA5 material that remains subject to
  those providers' terms.
- Author-created processed data and documentation in the companion archive
  use CC BY 4.0 as the primary licence for the authors' contributions. Other
  files retain the path-specific MIT, GHCN-Daily source/use, and Copernicus
  terms described above and in the deposit's `LICENSE.txt`.

The licensing status of earlier public revisions is recorded separately in
`docs/LICENSING_HISTORY.md`.

## Source datasets (not owned by the SCORCH authors; not redistributed raw)

### ERA5 (Copernicus Climate Change Service, ECMWF)
- Dataset: ERA5 hourly data on single levels from 1940 to present,
  DOI 10.24381/cds.adbb2d47. Accessed for this work through the ARCO-ERA5
  public mirror on Google Cloud (Google Research arco-era5 project).
- Licence: the underlying Copernicus information is provided under the licence
  to use Copernicus products, https://ecds.ecmwf.int/licences/licence-to-use-copernicus-products
  That URL replaces the legacy licence URLs cited by earlier versions of this
  release (`apps.ecmwf.int/datasets/licences/copernicus/` and the CDS dataset
  Licence tab). The authors' CC BY 4.0 licence covers only their own
  contribution; no CC BY licence is granted or implied over the underlying
  ERA5 information, and no copyright is claimed over it.
- ERA5 coverage used in this work: 1940-2025 (warm seasons, April-September).
  This coverage span is stated separately and is NOT the notice's year token.
- Required notice, which must accompany all ERA5-derived content, reproduced
  verbatim and without brackets:
  Contains modified Copernicus Climate Change Service information 2026. Neither the European Commission nor ECMWF is responsible for any use that may be made of the Copernicus information or data it contains.
- Citation: Hersbach et al. (2020), Q. J. R. Meteorol. Soc., 10.1002/qj.3803.

### GHCN-Daily (NOAA NCEI)
- Dataset: Global Historical Climatology Network - Daily,
  DOI 10.7289/V5D21VHZ. Station GHCND:EG000062414 (Aswan, Egypt).
- Terms: GHCN-Daily source material is distributed by NOAA/NCEI.
  GHCN-Daily integrates observations from international source datasets;
  users should follow the dataset's current use constraints
  (https://www.ncei.noaa.gov/metadata/geoportal/rest/metadata/item/gov.noaa.ncdc%3AC00861/html
  and https://www.ncei.noaa.gov/archive) and observe any applicable
  source-provider rights. NOAA requests citation of the
  dataset and the descriptive paper.
- Citation: Menne et al. (2012), J. Atmos. Oceanic Technol., 10.1175/JTECH-D-11-00103.1.

### Basemap data
- Figure basemaps use Natural Earth public-domain data fetched by cartopy at
  render time; no basemap data are redistributed here.

## Third-party software dependencies

Dependencies are installed from their own distributions and are not vendored
into this repository. Principal licences: numpy, pandas, scipy, scikit-learn,
xarray, dask, zarr, gcsfs, netCDF4, pyproj, shapely, matplotlib (BSD-style);
cartopy (BSD-3-Clause); pyyaml, openpyxl (MIT); cdsapi (Apache-2.0);
R spatstat family (GPL-2 or later, used as an external runtime, not linked or
redistributed). A full inventory with versions is in
docs/THIRD_PARTY_DEPENDENCIES.md.

## Non-claims

The SCORCH authors claim no ownership of ERA5, ARCO-ERA5, GHCN-Daily, or
Natural Earth data. Nothing in this repository grants rights to those
datasets beyond their providers' own terms.
