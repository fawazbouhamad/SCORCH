# Frozen figure assets (Figures 1 and 4)

Figures 1 (framework flowchart) and 4 (typology schematic) of the
manuscript are AUTHOR-CREATED SCHEMATIC DRAWINGS exported from the
authors' presentation slides. In the 2026-08 author-directed figure
correction round both figures were restored to the original slide
artwork with the smallest authorized deterministic edits, applied by
runnable producers:

* **Figure 1** is produced by
  `scripts/figures/fig01/restore_fig01_original_threshold.py`, which
  restores the original slide export
  (`scripts/figures/fig01/original/Figure_01_original.png`, SHA-256
  `cc561b368f84b298b3ee38a39415799cc31d8ca932fa586a32bd7624831ec787`)
  and makes exactly one authorized wording change inside the orange
  upper-right text box: "greater than a regional P97.5th threshold"
  becomes "greater than or equal to a regional P97.5th threshold",
  matching the implemented selection rule N_HW(t) >= 371 (the two
  exactly-at-threshold days 1998-05-26 and 2016-08-03 are selected).
  Every pixel outside the authorized text band is unchanged; the script
  emits a difference mask and locality report proving it. (The 2026-08
  code-native redesign `make_fig01_workflow.py`, PNG `4501b862...`, is
  superseded by this author-directed restoration and kept for history.)
* **Figure 4** is produced by
  `scripts/figures/fig04/make_fig04_symmetry_final.py` (2026-08
  author-approved symmetry round), which reads the **immutable
  approved-horizontal donor**
  (`scripts/figures/fig04/donor/Figure_04_approved_horizontal.png`,
  SHA-256
  `c35d9ed6ccea8d7f6d8ec8ad92d65fb3c5dd2df16d82b015b7a531b2eefc829f`)
  and emits the shipped asset in one deterministic pass. It never reads
  its own output and never patches a raster cumulatively. The edit is
  lossless throughout: every circle, arrow, ellipsis dot and time label
  is lifted out as an intact pixel sprite (verbatim RGB plus its full
  antialiased fringe) and pasted back at an integer offset, the only
  non-translation being an exact vertical mirror (a pixel permutation)
  used so all four Type 4 arrows are one glyph. Type 4 is squared onto
  a symmetric lattice and still reads horizontally left to right - two
  structures -> one structure -> two structures; Type 3 rows, arrows
  and ellipses are levelled; and the six Type 3 time labels are
  translated horizontally onto their circle columns. Type 1, Type 2,
  all titles, all typology names, the dividers, every colour, every
  circle size and the canvas are unchanged, and the output introduces
  no new colours; the script emits a difference mask and a report
  proving it.
* Figure 4 provenance chain:
  archived slide export
  (`scripts/figures/fig04/original/Figure_04_original.png`,
  `d595fb363d0a284abc1f9cc3049661f5786d1e42cf5e30ea3e50cea143a3bcde`)
  -> **superseded** horizontal-only stage
  `scripts/figures/fig04/correct_fig04_type4_horizontal.py`
  -> immutable donor `c35d9ed6...` -> symmetry-final `74ea37f0...`.
  The horizontal-only stage established the two -> one -> two reading
  and is retained as the historical producer of the donor; its shipped
  PNG `c35d9ed6...` and companion PDF
  `6621d6048473e910d6b150dfe2d20709c82066ee82ce77659e4e55ff88cbe591`
  are **superseded historical assets**. (The earlier lower-arrow
  correction `correct_fig04_type4_arrows.py`, PNG `b747c8c8...`,
  produced a vertical temporal reading and is superseded; kept for
  history.)

Verification: the PNG files here are byte-identical (SHA-256) to the
images embedded in the corrected manuscript:

| Asset | SHA-256 | Matches manuscript embed |
|---|---|---|
| `fig01/Figure_01.png` | `d3e0ca5eeefd811777480a412e5f4ec7f79007f7b2f15b2dc150ff3808f99280` | yes (word/media/image1.png) |
| `fig01/Figure_01.pdf` | `fce1921839131e761cabe894e7b71f8226efafba654cd7f488539af78809917b` | (companion from the same producer, deterministic metadata) |
| `fig04/Figure_04.png` | `74ea37f0ab54453a7c28895edd381cad3a75c199af88c60de67154721db23484` | yes (word/media/image4.png) |
| `fig04/Figure_04.pdf` | `53a3f4fe6c15075ed956367712123cd9cc26290c4a09017b7beb87d06d5fc3e4` | (companion from the same producer, deterministic metadata) |

Note: the Figure 1 producer re-renders the corrected text line with the
same face the slide export used (Aptos Regular, Version 2.01;O365,
pinned by SHA-256 in the script). That font is a Microsoft 365 cloud
font and is not redistributable, so byte-identical regeneration
requires a machine with that exact font file; the donor, the authorized
band, and the output hashes above are otherwise fully pinned.

Determinism of both producers is enforced by
`tests/test_corrected_schematic_figures.py`.

## Frozen station artwork (Figure S.1 panels c, d) - SUPERSEDED, fallback only

**Since the v1.0.0 pre-release correction, the manuscript Fig. S.1 no longer
uses this donor.** Panels (c, d) are fully regenerated from the deposited
GHCNd and ERA5 series by `scripts/figures/figS1/make_figS1_station_panels.py`
and `make_figS1_station_strip.py`, and the manuscript composite
(SHA-256 `d125a87d0f3a875a737a9175c43f133f9d353adf95bc307e4c3885731d38e634`;
the v1.0.0-era composite `050a0721...` is superseded)
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
were superseded first by the author-approved slide exports and now by the
2026-08 corrected producers named above; the figures' scientific content
(the Type 1-4 definitions in Figure 4) is enforced in code by
`src/scorch/typology.py`.
