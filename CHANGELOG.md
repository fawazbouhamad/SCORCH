# Changelog

## 1.0.0 (unreleased; date set at public release)

Initial public release accompanying the SCORCH paper
(SCORCH = Spatiotemporal Classification of Regional Compound Heatwaves).

### Pre-release remediation: raw-Celsius Tmax-weighted structure centroids

Applied before any public release. This work was developed on an internal
`1.0.1-rc` working line; it is **not** a released 1.0.1 and is folded here
as pre-release remediation of the forthcoming v1.0.0.

An earlier pre-release catalog candidate reported the ordinary (unweighted) PCA origin as each
daily heat structure's location; the advisor-approved raw-Celsius
Tmax-weighted centroid was never applied (the builder called
`evaluate_cluster_ellipse` without structure-specific Tmax weights, and the
legacy optional helper additionally used a prohibited `max(Tmax, 0)` clip
with a silent unweighted fallback).

* New post-PCA stages (`tmax_weighted_centroid.py`, byte-identical in
  `src/scorch/_kernel/` and `scripts/figures/common/`): strict raw-Celsius
  Tmax-weighted centroid (`w_i = Tmax_i` in degC; no Kelvin, abs, clipping,
  threshold subtraction, shifting, or standardization; explicit
  `WeightedCentroidError` stop on invalid weights) and rigid translation of
  the completed sigma=1.25 ellipse (no refit/resize/rotation).
* Catalog: generic centroid aliases now report the Tmax-weighted location;
  unweighted PCA origins preserved in `*_unweighted` columns; 20 new
  explicit columns (see DATA_DICTIONARY).
* Upstream science unchanged and verified: thresholds, 395 selected days,
  51 events, clustering/membership/noise, Appendix A, sigma=1.25, PCA
  covariance/eigenstructure/axes/areas/ratios/orientations, event types,
  Table 1, area tails (frozen-column comparison at rel <= 1e-12).
* Regenerated: Figures 3, 5, 6, 7, 12; LGCP variant3 refit; k-fold CV
  (seed 20260704, identical folds); Appendix D products; sector counts.
* Evidence packet: `remediation/` (freeze manifest, 760-row displacement
  audit, before/after results, manuscript impact inventory).

### Pre-release corrections (2026-08-04)

Applied before any public release; earlier builds are superseded
pre-release candidates, never published.

* **Final remediation (documentation/provenance only).** A second
  correction pass fixed the remaining active provenance contradictions:
  the Figure A producer's false `33+100+76 = 209` account (now the exact
  `29.20696324951644 + 100 + 75.33710405670476 = 204.5440673062212`,
  displayed 205), a stale superseded Table 1 checksum in an active
  reproducibility-matrix row, "published" wording about the superseded
  pre-release Figure 9 candidate, a time-sensitive public-tag claim,
  present-tense GitHub/Zenodo archival claims, retired staging-tree
  paths, V12-as-current wording, and unqualified deposit-copy claims
  (the online Zenodo data draft still requires table01 synchronization).
  Sixteen stale-provenance guards were added to the test suite
  (`tests/test_stale_provenance.py`). No scientific output changed.
* **R3 remediation (documentation/provenance only).** A third pass
  repaired the malformed `docs/TABLE_PROVENANCE.csv` row (proper CSV
  quoting; historical checksum retained, labelled superseded),
  corrected the publication builder's obsolete Table 1 provenance prose
  (the shipped table matches the manuscript layout exactly; 0
  presentation differences; MANUSCRIPT constant terminology), completed
  the lifecycle-language sweep (manuscript/canonical wording in place
  of false 'published' claims across scripts, src docstrings and docs),
  and resolved the Figure S.1 producer contradiction (canonical station
  panels are regenerated; only the superseded legacy fallback lacks its
  original producer). Six structural/lifecycle guards were added.
  No scientific output changed.
* **R4 remediation (documentation/guard only).** A fourth pass corrected
  the four remaining lifecycle residues that had survived R3 (two code
  comments — the S.1 composite stage note in `run_reproduction.py` and
  the catalog-expectations note in `src/scorch/catalog.py` — one
  `FIGURE_PROVENANCE.csv` note cell, and a newline-spanning
  `accepted\nmanuscript` phrase in `assets/manuscript_final/README.md`
  that R3's line-based literal scan could not see), and hardened the lifecycle
  guard in `tests/test_stale_provenance.py`: whole-file normalization
  (Unicode hyphens, whitespace/line breaks, case) plus regex detection
  with space/hyphen-interchangeable separators, negation handling and
  explicit provider/bibliographic/historical/future-conditional
  allowances, proven by 34 parameterized regression fixtures (suite:
  226 collected tests). Executable production code is AST-identical to
  R3. No scientific output changed.
* **R5 remediation (display geometry / cached metadata / guards only).**
  A fifth pass corrected the display geometry of two manuscript figures
  by a surgical OOXML edit (no Pandoc/LibreOffice round trip): Fig. A
  (Picture 13, `image13.png`, native 1950x1781) now displays at exactly
  5697940x5204119 EMU and Fig. B (Picture 14, `image14.png`, native
  5340x7488) at exactly 4128400x5789038 EMU, with `wp:extent` and
  `pic:spPr/a:xfrm/a:ext` identical, both figures uncropped and
  centered, and display/native aspect-ratio error below 0.001%; both
  embedded PNGs are byte-identical to the canonical images. The
  supplement's stale cached `docProps/app.xml` page count was corrected
  from 4 to the actual 2. Twenty final-DOCX display-geometry and
  content-identity guards were added
  (`tests/test_final_docx_geometry.py`): exact extents, extent/xfrm
  agreement, native-aspect preservation, all 17 embedded publication
  images pinned byte-for-byte, supplement page count, and unchanged
  Table 1 OOXML, alt text, captions/prose, comments/tracking state and
  media relationships; the two whole-file FINAL-DOCX hash pins were
  updated to the corrected documents. No manuscript prose, caption,
  table value, figure pixel, or scientific output changed. Executable
  production code is AST-identical to R4.

* **Figure 9 axial orientation.** Event orientation is aggregated with the
  doubled-angle axial mean (`scripts/figures/common/scorch_axial.py`),
  wrapped to the manuscript's north-referenced (-90, 90] convention. The
  superseded chain averaged 180-degree-periodic axial angles arithmetically
  (Event 4: -21.101 deg instead of the correct +68.98532754765856 deg).
  Panels 9(a)/(b), event areas and axis ratios are unchanged; superseded
  artifacts are archived under `legacy_defective_figure09/`.
* **Frequency inference removed.** Annual Type 3/Type 4 event counts are
  descriptive only and are not trend-tested; frequency Mann-Kendall/Sen
  rows were removed from the table producer, the Figure 10 console output
  and the deposit staging copy. Duration trends are unchanged and
  reproduce exactly (Type 3: 0.0083/0.6630; Type 4: 0.4122/0.0086).
* **Table 1.** The frequency header reads "Frequency of Occurrence (Number
  of Selected Event-Days)" (3/4/75/313 are selected event-days, not
  events); the canonical public labels are Type 1: Widespread (Isolated) /
  Type 2: Spatially Clustered / Type 3: Temporally Clustered / Type 4:
  Compound Clustering (Multi-Type); the producing script emits the
  manuscript column order. The local staging copy of the Zenodo data
  deposit's `figure_table_source_data/table01/` was corrected to match and
  its `SHA256SUMS` regenerated (online data draft synchronization is a
  required manual release step).
* **Figure A.** The sensitivity producer
  (`scripts/figures/figA1/make_figA1_sigma_matrices.py`) was recovered and
  wired into the workflow before the renderer; all four 9x9 matrices
  regenerate byte-identically from the deposit (sigma = 1.25 combined
  score 204.5440673062212, displayed 205, the equal-sigma-diagonal
  maximum).
* **Figure S.1.** Fully regenerated from the deposited GHCNd and ERA5
  series (station panels by `make_figS1_station_panels.py` +
  `make_figS1_station_strip.py`); the frozen station donor is a
  clearly-labelled fallback only and the superseded hybrid composite is
  historical.
* **Geometry floors.** The 1 km^2 eigenvalue/variance floor is retained;
  the separate 1 km semi-axis floor was removed after an audit showed it
  could never bind at any production sigma (all catalog and sensitivity
  outputs are byte-identical with and without it).

* `scorch` package with the canonical scientific kernel (verbatim
  `_kernel/ellipse_pca.py` and `_kernel/clustering.py`) and documented
  wrappers: thresholds, heatwave labelling, regional day selection,
  Method-A DBSCAN parameter selection, event-global-max derivation,
  daily clustering, sigma=1.25 PCA ellipses, mechanical Type 1-4 typology,
  and master-catalog load/validate/export.
* Builtin end-to-end reconstruction stages (`scorch.pipeline`): processed
  daily field -> thresholds/exceedance consistency -> regional selection
  (Theta = 371 -> 395 days -> 51 events) -> daily Method-A DBSCAN
  parameters -> event-global parameters -> re-clustering (760 structures)
  -> PCA ellipse geometry -> typology, each stage verified against the
  archived deposit and failing loudly on any mismatch.
* `scorch` CLI: `fetch-data` (Zenodo ZIP download, safe extraction with a
  path-traversal guard, deposit-root location, mandatory SHA256SUMS
  verification), `reproduce` (route-aware stage runner: builtin / script /
  rscript kinds; missing or failing stages abort with a non-zero exit),
  `validate-sources`, `validate-deposit` (real deposit layout: catalogs/,
  gridded/, lgcp/, power_law/, selected_days/, validation_kfold/,
  validation_station/, figure_table_source_data/; checksums both ways;
  row-count and type-count invariants), `version`.
* `configs/reproduction_fast.yaml` (repository copy) and the identical
  copy bundled as package data at `src/scorch/configs/reproduction_fast.yaml`:
  machine-readable pipeline description
  with canonical parameters, seeds, expected counts
  (1800 cells / 15738 days / Theta 371 / 395 days / 51 events / 760
  ellipses; types 3/4/20/24). The `fast` route is the only executable
  route; provider-level reconstruction is a documented guide
  (`scorch reconstruction-guide`). The builtin stages read their operative
  parameters and expected counts from this loaded configuration.
* `scripts/deposit/build_processed_field_netcdf.py`: builds and verifies
  the deposit's CF-1.10 NetCDF of the complete processed daily field.
* Frozen author-created assets with checksums (`assets/frozen_figures/`):
  Figures 1 and 4 are ACTIVE frozen assets WITH deterministic donor-based
  producers (scripts/figures/fig01/restore_fig01_original_threshold.py and
  scripts/figures/fig04/make_fig04_symmetry_final.py), each reproducing its
  shipped asset byte-identically
  (hand-drawn schematics, by design). The old Fig. S.1 station drawing in
  the same tree is a SUPERSEDED HISTORICAL FALLBACK only — since the
  v1.0.0 pre-release correction the canonical S.1 station panels (c)/(d)
  are fully regenerated by `make_figS1_station_panels.py` +
  `make_figS1_station_strip.py`, and the canonical composite is assembled
  by `make_new_figS1_candidate.py`; only that legacy fallback drawing
  lacks its original runnable producer.
* Environment locks: `environment/requirements-lock-py312.txt` (complete
  transitive pip lock WITH hashes, generated by pip-compile in a clean
  Python 3.12 environment from `environment/lock-input-py312.in`, whose
  direct pins are the EXACT versions of the CPython 3.12.10 environment
  that produced the paper outputs - the same pins as environment.yml) and
  `environment/renv.lock` (R 4.5.1 + spatstat).
* Test suite (396 collected; 373 passed / 22 skipped / 1 xfailed with the archive candidate configured, and 350 passed / 46 skipped source-only): unit + schema + CLI/fetch behaviour +
  stale-provenance release-alignment guards (added in the v1.0.0 final
  remediation: false Figure A account, stale Table 1 checksums,
  defective-Figure-9-as-published wording, retired staging paths,
  V12-as-current wording, version fields, contract-path existence,
  frequency-inference reappearance, pinned Figure 9 / S.1 / FINAL-DOCX
  hashes) +
  final-DOCX display-geometry and content-identity guards (added in the
  R5 remediation: exact Fig. A / Fig. B extents with matching
  `wp:extent`/`a:xfrm`, native-aspect preservation, the 17 pinned
  embedded publication images, supplement page count, unchanged Table 1
  OOXML / alt text / captions / comments-tracking state / media
  relationships) +
  doubled-angle axial-statistics regression tests (Figure 9) +
  Figure A sigma-matrix byte-identity and sigma-selection tests +
  configuration-consumption and configuration-guardrail tests (the loaded
  YAML's sigma, PCA variance floor, quantiles and DBSCAN grids are proven
  to reach the builtin stages; the final validation stage enforces the
  YAML expected counts; the canonical categorical rules and unsupported
  configuration overrides fail loudly; the complete configuration schema
  is required key-by-key, so a partial configuration cannot run on module
  defaults) + repository-level output-isolation guards (every generated
  read and write honours `SCORCH_OUT_DIR`; a run never modifies the
  source tree) + canonical regression tests (the latter run when the
  deposit or the frozen catalog is present, and skip with a clear message
  otherwise). Measured in the hash-locked clean-room environment:
  373 passed, 22 skipped, 1 xfailed with the deposit and archive candidate configured (21 FINAL-DOCX skips + 1 non-redistributable Aptos-font skip). A zero-skip acceptance run is PENDING the final release gate. At the PRIOR HEAD `44a54a05`, historical only, this was 363 passed, 0 failed, 0 errors, 0 skipped with the deposit and fixtures
  (fully configured acceptance run); a source-only checkout measures
  350 passed, 46 skipped without the deposit. At the PRIOR HEAD `44a54a05`, historical only, this was 327 passed, 36 skipped
  (current). HISTORICAL, not current: 212 passed + 34 skipped without the
  deposit and 244 passed + 2 skipped with it were pre-remediation
  measurements (their two skips were the
  publication-outputs isolation cases, which need a materialized
  `publication_outputs/` tree that a source-only checkout does not ship).
