# SCORCH v1.0.0 release reproducibility report (2026-08-04)

> Lineage note: this report was first compiled for the internal pre-release
> source snapshot historically labelled "V12" (2026-07-30) and was carried
> forward into the v1.0.0 pre-release correction. "V12" and the other
> "VN" labels below are HISTORICAL internal pre-release pass names, never
> public releases; the only public identity is SCORCH v1.0.0.

Verified status of every manuscript-facing result in this release, measured
on the build machine (Windows 11, Python 3.12.10, numpy 2.4.6, pandas 3.0.3,
matplotlib 3.10.9, cartopy 0.25.0, R 4.5.1 with the spatstat family).
Companion machine-readable records, all in this directory:
`FIGURE_PROVENANCE.csv`, `REPRODUCIBILITY_MATRIX.csv`,
`TABLE_PROVENANCE.csv`, `SANITIZATION_NOTES.md`.

## Evidence classes used in this document

| Class | Meaning |
|---|---|
| **EXECUTED** | The shipped script was actually run here, against the processed-data deposit, with the stated result. |
| **STAGEWISE VERIFIED** | Executed as a connected chain in which each stage consumed the previous stage's newly generated output, and each stage's result was checked against the archived comparison target. |
| **FROZEN** | No runnable producer exists; only the frozen publication asset is shipped, with checksums. No reproduction is claimed. |
| **STRUCTURALLY VALIDATED** | The script ships, imports, and exposes the documented arguments, but it was NOT run (provider-scale runtime or non-redistributed inputs). No result is claimed. |

Nothing in this report is described as reproduced unless it falls in one of
the first two classes.

## 1. Tests

| Condition | Result |
|---|---|
| `pytest tests -q` in a source-only checkout WITHOUT the deposit or fixtures | **350 passed, 46 skipped** (current head, separately measured; the skips are the deposit-, DOCX- and font-dependent guards, each with an explicit skip reason). PRIOR HEAD `44a54a05`, historical only: 327 passed / 36 skipped. HISTORICAL, not current: 212 passed / 34 skipped was measured on the pre-remediation tree (measured in the hash-locked clean-room environment; every skip is deposit-, frozen-catalog- or FINAL-DOCX-dependent -- canonical catalog and axial catalog regression tests, Figure A sigma matrices, deposit Table 1 checksum guard, output-isolation stage cases, the two FINAL-DOCX identity guards, and the 19 document-reading final-DOCX display-geometry/content-identity guards -- each skipping with a clear message) |
| `pytest tests -q` WITH the deposit and fixtures (`SCORCH_DATA_DIR`, `SCORCH_CANONICAL_DATA_DIR`, `SCORCH_FINAL_DOCX_DIR`, `SCORCH_APTOS_FONT`) | **373 passed, 22 skipped, 1 xfailed** (current head, measured). The 22 skips are 21 FINAL-DOCX-dependent guards and 1 pinned-Aptos-font guard (a non-redistributable Microsoft 365 cloud font); the 1 xfail is the recorded archive-NetCDF staleness blocker. A zero-skip fully configured acceptance run is PENDING the final release gate and is NOT claimed at this head. PRIOR HEAD `44a54a05`, historical only: 363 passed / 0 skipped. HISTORICAL, not current: 244 passed / 2 skipped was the pre-remediation measurement |

With the deposit and archive candidate configured the current head measures 373 passed, 22 skipped, 1 xfailed; the remaining skips are the 21 FINAL-DOCX-dependent guards and the pinned-Aptos-font guard. A zero-skip fully configured run is PENDING the final release gate. At the PRIOR HEAD `44a54a05` there were no remaining skips (363 passed, 0 skipped). In a source-only checkout 46 guards skip - the deposit-, DOCX- and font-dependent cases, including the publication-outputs isolation cases that require a materialized `publication_outputs/` tree - each with an explicit skip reason.

Known benign import warning (investigated in V5): the netCDF4/cftime
binary wheels emit `RuntimeWarning: numpy.ndarray size changed` when
`netCDF4` is imported after pandas/scikit-learn/scipy. Controlled tests
show it is INDEPENDENT of the numpy version (2.4.6 and 2.5.1 both emit it
in that import order and both are clean when netCDF4 is imported first)
and that it occurs in the exact hash-locked environment as well as in the
unpinned convenience install, so no version constraint can eliminate it.
It is an upstream wheel artifact with no observed effect: all tests pass
and every canonical number reproduces. The pytest configuration filters
exactly this message (and only it), so any OTHER binary-compatibility
warning still surfaces.

History of the totals: V2 measured 50 + 3 without data (53 with); V3 added
six tests (a mocked Zenodo record-API download test and five
bundled-configuration tests; 59 total); V4 added six
configuration-consumption tests for sigma, Theta and the DBSCAN grids
(65 total); V5 added twenty-eight tests IN TOTAL (93 total:
configuration-guardrail tests -- variance-floor consumption and mismatch,
YAML expected-count enforcement in the final validation stage, canonical
fixed-rule enforcement, rejection of unsupported configuration overrides
-- and the derived-Theta placement test); V6 added thirty-one
schema-completeness guardrail tests (124 total); V7 adds four
repository-level output-isolation guards (128 total); the v1.0.0 final
remediation (2026-08-04) adds sixteen stale-provenance release-alignment
guards (`tests/test_stale_provenance.py`: false Figure A account, stale
Table 1 checksums, defective-Figure-9-as-published wording, retired
staging paths, V12-as-current wording, version fields, contract-path
existence, frequency-inference reappearance, pinned Figure 9 / S.1 /
FINAL-DOCX hashes); the R3 remediation adds six structural/lifecycle
guards (shipped-CSV rectangularity, JSON and CITATION.cff parsing,
Table 1 provenance-prose consistency, S.1 producer-contradiction guard,
extended false-lifecycle-phrase guard), bringing the suite to 192
collected tests; the R4 remediation hardens the false-lifecycle-phrase
guard (whole-file normalization of Unicode hyphens, whitespace, line
breaks and case, regex detection with space/hyphen-interchangeable
separators, negation handling, and explicit provider/bibliographic/
historical/future-conditional allowances) and adds 34 parameterized
regression fixtures proving the evasive variants fail and the
legitimate wordings pass, bringing the suite to 226 collected tests;
the R5 remediation adds 20 final-DOCX display-geometry and
content-identity guards (`tests/test_final_docx_geometry.py`: exact
corrected Fig. A / Fig. B extents with matching `wp:extent` and
`a:xfrm/a:ext`, native-aspect preservation below 0.001% error, the 17
embedded publication images pinned byte-for-byte, the supplement
`docProps/app.xml` page count of 2, and unchanged Table 1 OOXML, alt
text, captions/prose, comments/tracking state and media relationships),
bringing the suite to 246 collected tests.

## 2. Connected reconstruction: processed field to catalog

**STAGEWISE VERIFIED (EXECUTED).** Run with:

```
scorch reproduce --base-dir <deposit-root> --route fast --out-dir reproduced
```

The stage list is bundled inside the installed package, so this works from a
wheel install with no repository checkout and no `--config`. Every stage
writes newly generated intermediates under `<out-dir>/reconstruction/`, and
every later stage reads ONLY those newly generated files. The deposited
final catalogs are used exclusively as comparison targets, never as upstream
inputs.

| Stage | Newly generated output | Result |
|---|---|---|
| field-products | (verification only) | Thresholds recomputed, max difference **3.81e-06 degC**; authoritative exceedance indicator (`tmax >= threshold`) confirmed, 10 documented float32-borderline entries |
| relabel-heatwaves | `heatwave_labels_relabelled.npz`, `daily_regional_coverage.csv` | Grid-level heatwave labelling rerun for all **1,800** cells from the authoritative exceedance field: `heatwave_id` identical to the deposited field on all 15,738 days; derived daily coverage matches the deposited table exactly |
| select-days-events | `selected_days_events.csv` | **Theta = 371**, **395** selected days, **51** compound events, derived from the NEW coverage; day set and event grouping match the deposit |
| daily-dbscan-params | `daily_selected_parameters.csv` | **395/395** daily Method-A DBSCAN parameter selections recomputed on the NEW labels and verified exactly against the catalog's canonical per-day columns |
| event-global-params | `event_global_max_parameters.csv` | **51/51** event-global parameter pairs derived from the NEW daily results; all match the deposit |
| rebuild-catalog | `structure_labels.csv`, `master_cluster_ellipse_catalog.csv` | All 395 days re-clustered with the NEW event parameters: cluster partitions identical, **760** structures, ellipse geometry maximum relative difference **5.69e-15** |
| classify-reconstructed | `event_typology.csv` | **51** events classified from the NEW catalog; type counts **3/4/20/24**; all match the deposited types |
| validate-deposited-catalog | (verification only) | Deposited master valid: 760 rows / 51 events / 395 dates / types 3-4-20-24 |

Cell-order note: the reconstruction emits each day's heatwave-labelled grid
cells in the canonical longitude-major order. That order is load-bearing.
DBSCAN assigns a border point reachable from two clusters to whichever core
point reaches it first, so a different input order yields a different (but
equally valid) partition of border cells. Emitting the canonical order
reproduces the canonical catalog partition exactly and deterministically from
the field alone.

Configuration wiring in the current release: every operative value of
these stages -- including
the PCA eigenvalue variance floor (`var_floor_km2`) -- and the expected
totals enforced by the final validation stage come from the loaded YAML
(`parameters:` / `expected_counts:`); the categorical algorithm rules are
recorded under `fixed_rules:` with exactly ONE supported canonical value
each and any other value fails loudly; Theta is recorded as an expected
DERIVED value (from `bigday_quantile` + its method) under
`expected_counts:`, not as an independent operative input. Adversarial
tests prove that a deliberately different variance floor, deliberately
wrong expected counts, a changed fixed rule, or an unsupported override
fails instead of being silently ignored.

## 3. Publication figures

**17 publication figures in total**: main Figures 1 to 12 (12), Appendix
Figures A, B, C and D (4), and Supplementary Figure S.1 (1). **S.1 is the
ONLY supplementary figure.** Since the advisor-directed deployment of
2026-07-30 the former Appendix Figs. A.1, A.2 and A.3 are designated
**Figs. A, B and C** in the manuscript, and the former Supplementary Fig. S.2
is designated **Fig. D in Appendix D of the main manuscript**. The labels A.1, A.2, A.3
and S.2 are RETIRED and appear below only in explicitly historical
statements. S.3 and S.4 are not current manuscript figures; their scripts
are retained as internal component producers of Fig. D.

Of those 17, by reproduction class: **6 `data_generated`** (Fig. 2, 3, 12,
B, D, S.1), **8 `deployment_export_of_reproduced_original`** (Fig. 5, 6, 7,
9, 10, 11, A, C), **1 `manually_postprocessed_approved_artwork`** (Fig. 8)
and **2 `frozen_approved_artwork`** (Fig. 1, 4). Figure 9 joined the
deployment-export class in the v1.0.0 pre-release correction: the
axial-orientation fix regenerated its approved original end-to-end from the
deposit, so no manual post-processing pass remains. Only the first six are
byte-identical to the embedded raster when regenerated from data; section 3
below describes each situation. Per-figure hashes, including the separate
approved-original, deployed-embed and reproduced-output fields, are in
`FIGURE_PROVENANCE.csv`, and the machine-readable class per figure is in
`MANUSCRIPT_FIGURE_IDENTITY.csv`.

**EXECUTED, byte-identical to the deployed manuscript or supplement embed:**
Figures 2, 3, 12, B, D and S.1.

**EXECUTED, byte-identical to the approved canonical full-resolution asset**
(the deployed DOCX embed is a downscaled deployment export of that asset):
Figures 5, 6, 7, 9, 10, 11, A and C. For Figure 9 this holds since the
v1.0.0 pre-release correction: event orientation is now the doubled-angle
axial mean (`scripts/figures/common/scorch_axial.py`), the reproduced
9000x2940 render `f4dce68d...` IS the approved original, and the manuscript
embed `7859acbd...` is its deterministic width-1950 LANCZOS downscale
(`make_manuscript_artwork.py`). The superseded arithmetic-mean artifacts
(full-resolution `4cb3b38a...`, embed `b023c6e5...`) are HISTORICAL ONLY,
archived under `legacy_defective_figure09/` and excluded from publication
outputs.

**EXECUTED, three distinct artifacts (Figure 8).** For this figure the
approved original, the deployed embed and the reproduced output are three
different files, and `FIGURE_PROVENANCE.csv` records all three hashes in
separate fields:

| | Figure 8 |
|---|---|
| Approved full-resolution original (post-processed "B2B-1" pass) | 6221x4751, `9b2bd0f1...` |
| Deployed DOCX embed (downscaled export of the approved original) | 1950x1489, `c64f1a16...` |
| Reproduced output (this release) | 6221x4751, `bf153356...` |

The reproduced output is byte-identical to the PRE-B2B-1 script output
archived in the research repository. Against the approved original it has
identical dimensions with **5.10%** of pixels differing: that difference is
the authors' manual post-processing pass, which the script does not and
cannot reproduce. The plotted content is reproduced exactly.

**DETERMINISTIC DONOR-BASED PRODUCERS (Figures 1 and 4).** Both figures now
have runnable, deterministic producers that transform approved donor
artwork:
`scripts/figures/fig01/restore_fig01_original_threshold.py` (re-renders one
authorized text line onto the archived original; emits a difference mask and
a locality report) and `scripts/figures/fig04/make_fig04_symmetry_final.py`
(operates on the immutable approved-horizontal donor). Each reproduces its
shipped asset byte-identically across clean builds, and both are
byte-identical to the deployed manuscript embeds. Determinism is enforced by
`tests/test_corrected_schematic_figures.py` and
`tests/test_fig04_symmetry_final.py`. The Figure 1 producer additionally
requires the non-redistributable Aptos face, supplied via `--font` or
`SCORCH_APTOS_FONT`; without it the producer fails deterministically and the
test skips with an explicit reason.

**V3 label corrections (Figure 12 and the composite now designated
Fig. D).** Both figures were regenerated with corrected marker-legend
wording: "Largest centroid per day" and "Largest centroid per event" become
**"Daily-largest structure centroid"** and **"Event-largest structure
centroid"**. The concentration-zone distance boxplot's y-axis becomes
"Distance to nearest top-concentration zone (km)"; that boxplot is
**panel (a)** of Fig. D in the current layout. Scope of that statement:
relative to the immediately preceding pre-label asset, the V3 operation
changed legend and axis WORDING ONLY - plotted data, quantile ranks, ticks,
centroids and cross-validation numbers were unchanged BY THE V3 STEP.
Relative to the PRE-REMEDIATION unweighted artifacts, however, the plotted
centroid positions, the fitted concentration surface and the
cross-validation distances all DID change under the Tmax-weighted-centroid
correction. Figure 12's colorbar already read "Relative
centroid-concentration rank, R(s)" and is unchanged.

*HISTORICAL (V3-era status, superseded -- retained for provenance).* At the
V3 pass these corrected outputs were intentionally not byte-identical to the
then-deployed embeds; they were supplied for manual review, and at that time
nothing had been deployed into either WORKING document.

**CURRENT RESOLUTION.**
Both were DEPLOYED on 2026-07-30 in the
advisor-directed G2 pass (historical G2 embeds: Figure 12 `6a1a5a76...`,
Fig. D `b7c48232...`, superseded). After the 2026-08 Tmax-weighted-centroid
correction rounds the current manuscript embeds are Figure 12
`ce09ab2f...` and Fig. D `88f9e177...`, and the shipped producers
reproduce both byte-identically. Neither figure is pending, provisional
or awaiting any further pass.

**Final Fig. D check.** The regenerated composite reproduces the deployed
figure's content and numbers. Before the V3 label correction its output was
byte-identical to the then-deployed SUPPLEMENTARY embed (`d3de47b8...`),
which establishes that the corrected wording was the only difference at that
point.

**Fig. D status: DEPLOYED (2026-07-30, G2, advisor-approved).** The panel
arrangement Dr. Najibi requested has been produced and deployed. The
composite was rearranged to 2 columns x 3 rows - panel (a) the
concentration-zone distance boxplot, panels (b)-(f) held-out Folds 1-5,
shared vertical colorbar spanning all three rows, centred marker legend -
and RELOCATED from the supplementary document into the main manuscript as
**Fig. D in Appendix D**. Artwork 6050x6019 px, G2-pass embed
`b7c48232...` (superseded by the current Tmax-weighted-centroid embed
`88f9e177...`), reproduced byte-identically by the shipped producer
`scripts/figures/figS2/make_new_figS2_candidate.py` (legacy internal name).
Layout and labelling only: dataset, seed 20260704, fold membership
(152 held-out centroids per fold), refit surfaces, ranks, colours, ticks,
markers and the zone-mean assertions are unchanged in FORM. The zone means
themselves moved with the corrected centroids and are now
**389.670139 / 231.807728 / 151.672110 / 69.064508 km** for the top
10/20/30/50% zones (the superseded unweighted values were
437.85/285.66/180.81/81.48 km, quoted in earlier revisions as
438/286/181/81). They are asserted at run time. The superseded supplementary embed was `d3de47b8...`. The
separate supplementary document now contains **Fig. S.1 only**.

**V4 correction (internal figS4 component).** The internal fold-map
producer's colorbar label previously claimed physical units ("Predicted
centroid concentration (x10^6 km^-2)") although the mapped values are
per-fold PERCENTILE RANKS (0-1). V4 corrects the label to "Relative
centroid-concentration rank, R(s)" (the same wording as Figure 12 and the
composite now designated Fig. D, which were already correct). Regenerated
component hash: `1f0742fa...`. *HISTORICAL:* at the V4 pass the composite
output was unchanged at `54ca830c...`, which confirmed the fix affected only
the internal component. **CURRENT (v1.0.0; resolved in the historical V12 pre-release pass):** that
composite was subsequently
rearranged and deployed in the 2026-07-30 G2 pass as `b7c48232...`
(itself superseded by the current Tmax-weighted-centroid embed
`88f9e177...`); `54ca830c...` is a superseded pre-G2 identity and is
not shipped anywhere in this release.

**Internal component producers (NOT manuscript figures).** The `figS3` and
`figS4` scripts regenerate the two internal components of the manuscript
Fig. D: `figS3` supplies **panel (a)**, the concentration-zone distance
boxplot, and `figS4` supplies **panels (b) to (f)**, the held-out Folds 1-5.
They are components, were never deployed, and therefore have no
deployed-embed hash.

**Superseded Event-7 diagnostic (legacy internal name `figA2`).** The
Event-7 heatmap script
(`make_figA2_dbscan_selection_heatmaps.py`) is a superseded internal
diagnostic. It is **NOT EXECUTED**, is wired into no reproduction tier, and
**no reproduced output is shipped or claimed** for it. The canonical
Figure B is the Event-10 figure, verified byte-identical to the deployed
manuscript embed `word/media/image14.png`. (This corrects the V2 provenance
row, which claimed an executed byte-identical output that is absent from
`reproduced/`.)

When internal outputs are discussed anywhere in this release, the correct
phrasing is: **17 publication figures in four reproduction classes (6
`data_generated`, 8 `deployment_export_of_reproduced_original`, 1
`manually_postprocessed_approved_artwork`, 2 `frozen_approved_artwork`),
plus three internal or superseded diagnostic products.** The phrase "15
regenerated publication figures" must not be used: it counts the nine
deployment exports and manually post-processed artworks as if the scripts
reproduced the embedded rasters, which they do not.

## 4. Tables and numeric results (EXECUTED)

| Item | Result |
|---|---|
| Table 1 (Compound Typologies) | BYTE-IDENTICAL to the corrected LOCAL STAGING COPY of the Zenodo data deposit (sha256 `f12ee1ab...`). Since the v1.0.0 pre-release correction the producing script emits the manuscript column order (Longest Compound Event at column 4), the manuscript header "Frequency of Occurrence (Number of Selected Event-Days)" and the canonical public type labels (Type 1: Widespread (Isolated) / Type 2: Spatially Clustered / Type 3: Temporally Clustered / Type 4: Compound Clustering (Multi-Type)); the local staging copy of `figure_table_source_data/table01/` was corrected to match and its `SHA256SUMS` regenerated. No column-permutation or rename exception remains. The ONLINE Zenodo data draft still carried the pre-correction table01 files at audit time; synchronizing it is a required manual release step |
| Trend tables (Sen slope + Mann-Kendall) | Byte-identical to the corrected local staging copies of the Zenodo data deposit (`figure_table_source_data/table01/`), pending the same online-draft synchronization |
| Power-law statistics (canonical `--nboot 5000`) | The entire `power_law/statistics/` directory is byte-identical to the deposit, bootstrap CSVs included |
| variant3 surface extraction | Exact: max absolute difference **0.0** over 1,800 rows against the frozen variant3 CSV |
| 5-fold CV (seed 20260704) | Mean held-out distance **85.009602 km** (verified from the corrected committed `validation_kfold/cv_summary.csv`); all five CV CSVs byte-identical to the deposit |
| Concentration-zone CV distances (legacy `risk_zone` file and column names; see `TERMINOLOGY.md`) | **389.670139 / 231.807728 / 151.672110 / 69.064508 km** (weighted centroids; the superseded pre-remediation values were 437.854964 / 285.656041 / 180.807535 / 81.475518 km) |
| GHCN-ERA5 Aswan validation | r = 0.9802, RMSE = 1.696 C, bias = -1.5952 C, n = 9 (manuscript 0.98 / 1.70 / -1.60) |
| Canonical counts | 1,800 cells; 15,738 days; Theta = 371; fraction 0.2061; 395 days; 51 events; 760 ellipses; types 3/4/20/24; event-day split 3/4/75/313; event 14 = Type 3 |

The canonical bootstrap replicate count is **5000**, and it is the default of
both `run_reproduction.py` and the `Makefile`. Any smaller value is a QUICK,
NONCANONICAL run: the driver prints an explicit warning, and the `make quick`
target is named accordingly. Its power-law numbers are not the canonical
manuscript values and must not be reported as reproductions of them.

## 5. Centroid-concentration (LGCP) model: EXECUTED and matched

`scripts/lgcp/spatial_risk_lgcp_model_diagnostics.R` was **executed** in V3
and RE-EXECUTED (history: in the V5 and again in the V6 pass) against the
deposited `lgcp/` inputs under R 4.5.1
with the spatstat family. The V5-era rerun corrected the four diagnostic map
titles from "Predicted centroid risk" to the scientifically accurate
"Predicted centroid concentration (fitted intensity x 1e6)" (the mapped
surface is the fitted intensity of observed ellipse centroids, not a
probabilistic risk forecast); the legacy `risk_map_*.png` filenames are
retained and documented in `TERMINOLOGY.md`. The refit numbers are
unchanged:

* ALL QC CHECKS PASS, with **0 captured fit warnings**.
* The refit parameter table (all 30 rows) is **identical** to the deposited
  canonical table, including variant3 `sigma2 = 1.642911` and
  `scale = 272.455153 km`, trend `~ lon + lat + mean_tmax_z + std_tmax_z`,
  fitted to the 760 raw-Celsius Tmax-weighted centroids. (The superseded
  unweighted fit, `sigma2 = 1.647219`, `scale = 287.707960 km`, is retained
  only under `legacy_unweighted_baseline` in docs/CANONICAL_SCIENCE.json.)
* The predicted-intensity surface matches the deposited canonical CSV
  exactly (`extract_variant3.py`: shape match, max absolute difference
  **0.000e+00**, EQUAL = True).

All R-stage inputs ship in the deposit's `lgcp/` folder, so any user with R
and spatstat can re-run the fit.

`scripts/lgcp/build_inputs.py` is **STRUCTURALLY VALIDATED** only: building
the covariates from scratch needs the provider-scale ERA5 long table, which
is not redistributed. The fit itself was executed from the deposited
covariates, as recorded above.

## 6. Provider-level reconstruction: STRUCTURALLY VALIDATED, not rerun

Rebuilding the processed daily field from provider-managed ERA5 is a
documented GUIDE, not an executable route. `scorch reconstruction-guide`,
`python run_reproduction.py guide` and
`docs/PROVIDER_RECONSTRUCTION_GUIDE.md` print the ordered steps and exit.
They reconstruct nothing and verify nothing, and no command in this release
reports success for that work. There is no `--route full`.

The scripts involved (`scripts/download/*`,
`scripts/pipeline/build_master_dataset.py`,
`scripts/deposit/build_processed_field_netcdf.py`) ship, import, and expose
the documented arguments; `build_master_dataset.py` requires `--datadir` and
exits with an error without it. They were not rerun end to end for this
release. Plan for LOCAL WORKING STORAGE exceeding 10 GB on this route: the
86 yearly daily-Tmax NetCDF files are about 98 MB each (about 8.4 GB
total), the derived long-table master CSV is close to 2 GB, and the
processed outputs come on top. Network TRANSFER is a separate quantity
that depends on the chosen provider route (the ARCO route streams subsets
of a cloud Zarr store; the CDS route downloads hourly source files that
are aggregated locally) and can exceed the on-disk footprint. Everything
downstream of the deposited processed field IS executed and verified, as
recorded in section 2.

## 7. Deposit integrity (EXECUTED)

* `validate_deposit.py`: **PASS**, including the NetCDF invariants.
* `scorch validate-deposit`: **PASS** (structure, SHA256SUMS verified both
  ways, no unlisted files, row counts, type counts).
* Processed daily field NetCDF: CF-1.10, 15,738 x 36 x 50, 1,800 valid
  cells, daily coverage counts exact, Theta = 371 at raw P97.5, 395 selected
  days.
* The NetCDF was rebuilt in V3 after correcting the source-precision
  consistency rule from `val > threshold` to the canonical
  `val >= threshold`. The DATA VALUES are byte-identical to V2 for every
  variable, because no float64 equality case occurs; only metadata,
  manifests, checksums and archive hashes changed.

## 8. How to re-run

```
# Dependencies, hash-verified, in a clean Python 3.12 environment:
pip install --require-hashes -r environment/requirements-lock-py312.txt
pip install --no-deps .                 # the SCORCH package itself

# Data (the deposit identifier is REQUIRED; there is no built-in default
# that can discover an unpublished record):
scorch fetch-data --doi 10.5281/zenodo.21717752 --dest scorch_data
    # or --url <record URL>, or set SCORCH_DATA_DOI; downloads via
    # links.content, safely extracts, verifies every checksum
scorch validate-deposit --dir scorch_data

# Connected reconstruction (installed package alone; no repository needed):
scorch reproduce --base-dir scorch_data/scorch_processed_data_v1.0.0 \
    --route fast --out-dir reproduced

# Repository-level figures and tables (REQUIRES a repository clone).
# The statistics/power-law stages need `tabulate` (pandas
# DataFrame.to_markdown); it is hash-pinned in the exact lock above, so no
# extra install is needed (unpinned installs get it via the [figures] or
# [full] extra).
python run_reproduction.py smoke        # small subset, about 20 s
python run_reproduction.py fast         # canonical nboot 5000
python run_reproduction.py guide        # prints the provider guide only
```

`make smoke`, `make fast`, `make quick`, `make reconstruct` and `make guide`
are equivalent where `make` exists. No script writes outside the chosen
output directory; the deposit and the frozen assets are never modified.
