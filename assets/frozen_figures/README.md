# Frozen figure assets (Figures 1 and 4)

Figures 1 (framework flowchart) and 4 (typology schematic) of the
manuscript are AUTHOR-CREATED SCHEMATIC DRAWINGS exported from the
authors' presentation slides. They have **no runnable computational
producer** in this repository, and none is claimed: these PNG/PDF files
are the final approved assets, shipped frozen so the release contains
every manuscript figure.

Verification: the PNG files here are byte-identical (SHA-256) to the
images embedded in the deployed manuscript:

| Asset | SHA-256 | Matches manuscript embed |
|---|---|---|
| `fig01/Figure_01.png` | `cc561b368f84b298b3ee38a39415799cc31d8ca932fa586a32bd7624831ec787` | yes (word/media/image1.png) |
| `fig01/Figure_01.pdf` | `37edc70067c3e6a033d635cdd2c34733e8b5e42bbb9be54f48e5714400540b6e` | (PDF companion of the same export; author metadata corrected 2026-07-31 - rendered pages and extracted text byte-identical) |
| `fig04/Figure_04.png` | `d595fb363d0a284abc1f9cc3049661f5786d1e42cf5e30ea3e50cea143a3bcde` | yes (word/media/image4.png) |
| `fig04/Figure_04.pdf` | `515d45063c860225c9a5bd429088e735c94d7e8150d008b71a3f4436b522df25` | (PDF companion of the same export; author metadata corrected 2026-07-31 - rendered pages and extracted text byte-identical) |

## Frozen station artwork (Figure S.1 panels c, d) - SUPERSEDED, fallback only

**Since the v1.0.0 pre-release correction, the manuscript Fig. S.1 no longer
uses this donor.** Panels (c, d) are fully regenerated from the deposited
GHCNd and ERA5 series by `scripts/figures/figS1/make_figS1_station_panels.py`
and `make_figS1_station_strip.py`, and the manuscript composite
(SHA-256 `050a0721509656d7337102fe451a400b2bed35ee967965e19ad444b54675f538`)
is assembled by `scripts/figures/figS1/make_new_figS1_candidate.py` from
those regenerated panels plus the fully reproducible Type 3 Event 25 figure.

`figS1_station_donor/Figure_S2_station_provisional.png` (SHA-256
`8620b52a92dc5028b47e1dc16c5679378d8170f3a5a754ee38ad01bd0512deba`) is the
superseded provisional GHCNd(Aswan)-vs-ERA5 station comparison drawing that
formed panels (c, d) of the pre-correction hybrid composite
(`a5632323...`, historical only). It was transcribed from approved slide
artwork and had no runnable producer. It is retained solely as a
clearly-labelled fallback: if the compositor is ever forced to use it, the
build prints `HYBRID COMPOSITE` and the provenance says so. The station
metrics are independently recomputed by
`scripts/validation/ghcn_era5_validation.py` (r = 0.9802, RMSE = 1.696
degC, bias = -1.595 degC; comparison window 31 May - 12 June 2016, n = 9
overlapping days).

### Rights for the station-donor asset

The station-donor drawing is licensed differently from the other frozen
assets and has its own row in `docs/LICENSES_AND_ATTRIBUTION.md`. The
authors' artwork is CC BY 4.0, but the drawing DEPICTS third-party
source material: the plotted station observations remain subject to the
GHCN-Daily source/use terms and NOAA/NCEI attribution (Menne et al.,
2012; DOI 10.7289/V5D21VHZ; applicable source-provider rights retained),
and the plotted reanalysis values remain subject to the current
Copernicus ERA5 terms and the required notice "Contains modified
Copernicus Climate Change Service information [1940-2025]; neither the
European Commission nor ECMWF is responsible for any use of the
Copernicus information." Figures 1 and 4 carry no such third-party
material and are CC BY 4.0 without qualification.

`SHA256SUMS` in this directory carries the same digests in checkable form
(`sha256sum -c SHA256SUMS`).

The vector "recreation" scripts that existed early in the project history
were superseded by these author-approved slide exports and are not part of
this release; the figures' scientific content (the Type 1-4 definitions in
Figure 4) is enforced in code by `src/scorch/typology.py`.
