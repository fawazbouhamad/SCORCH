# SCORCH Tmax-Weighted Centroid Remediation: Evidence Report

Branch `fix/tmax-weighted-centroids` · worktree `<WORKTREE>`
Date: 2026-08-07 · Prepared under the direction and responsibility of Fawaz Bouhamad.

---

## 1. Repository identity and lineage

* Canonical repository: `<CANONICAL-REPO>`
  (remote `origin = https://github.com/fawazbouhamad/SCORCH.git`).
* Expected private canonical release commit **verified present**:
  `184f15c6c889044324fb07f7545ec73dd849f8e5`
  ("SCORCH v1.0.0: final pre-release alignment", tree `015de058d46bd555c07c9df8da382f1f645cca17`),
  reachable from `origin/main`; annotated tag `v1.0.0` = object
  `47d0c06dbe28b2b9347d979689205195512b332c` → commit `184f15c6`.
* Working-tree state at audit: branch `alignment-v1.0.1` @ `1c017c9b`,
  **zero modified tracked files**, 22 untracked paths (recorded; none can
  reach a worktree created from `184f15c6`).
* Environment: Python 3.12.10
  (`<PYTHON-3.12.10>/python.exe`),
  R 4.5.1 + spatstat 3.x (`<R-4.5.1>/bin/Rscript.exe`),
  git 2.54.0.windows.1, Windows 11. Package versions captured in
  `provenance/corrections/tmax_weighted_centroids/corrected/event_global_max_algorithm/build_manifest.json`
  (`dependency_versions`).
* Processed-data deposit: `<TMPDIR>/scorch_dep_v100/scorch_processed_data_v1.0.0`
  with **93/93 files verified against its SHA256SUMS (0 mismatch, 0 missing)**.

## 2–3. Base commit, remediation branch, final state

* Isolated worktree created **from `184f15c6`** on new branch
  `fix/tmax-weighted-centroids` (clean at creation: 0 dirty files).
* v1.0.0 commit, tag, deposit, archives, evidence packets, and hashes were
  **not** rewritten, deleted, moved, or overwritten. Nothing pushed; no
  GitHub release; no Zenodo action (DOIs 10.5281/zenodo.21717752 /
  10.5281/zenodo.21717874 untouched).
* Final remediation commits: see `git log` on the branch (logically
  separated: kernel+tests · pipeline wiring · docs/ledger · evidence).

## 4. Root cause (confirmed from the release tree)

`scripts/pipeline/build_event_global_max_master.py` (release path; the
`scripts/event_global_max/` path is an untracked research-tree copy)
called at line 147:

```python
e = ep.evaluate_cluster_ellipse(clon, clat, C.SIGMA)
```

with **no `cell_to_val`**, so `weighted_centroid_lon/lat` returned NaN and
were discarded; every reported `centroid_lon/lat` (and aliases
`centroid_x/y`, `x/y`, `lon/lat`) was the unweighted PCA origin. The
kernel's optional weighting path (`ellipse_pca.py:127–154`) was additionally
**non-compliant**: `tmax_weighted_centroid_from_cells` applied
`max(Tmax, 0.0)` (prohibited clipping) and `safe_weighted_mean` silently
dropped non-finite weights and fell back to the unweighted mean, a
prohibited silent fallback. It was therefore NOT activated; a new strict
stage was implemented. The legacy helpers remain frozen and unused; a test
asserts the canonical builder never calls them.

## 5–7. Implemented equation, units, prohibited transforms

New module `tmax_weighted_centroid.py` (byte-identical copies in
`src/scorch/_kernel/` and `scripts/figures/common/`; a test enforces byte
identity):

```
w_hk(t)       = Tmax_hk(t)                       [degrees Celsius, raw]
lambda_w,h(t) = sum_k lon_hk * w_hk / sum_k w_hk
phi_w,h(t)    = sum_k lat_hk * w_hk / sum_k w_hk
```

* Weights: the processed daily Tmax field
  `gridded/scorch_processed_daily_tmax_field_v1.0.0.nc`, variable `tmax`,
  attribute `units: degC` (checked at load; non-Celsius units refuse to run).
* Weights are raw observed daily Tmax expressed in degrees Celsius,
  following the approved weighting convention. **No** Kelvin conversion, `abs()`,
  `max(,0)`, threshold subtraction, exceedance, shifting, standardization,
  anomalies, normalized fields, area or latitude weights, weighted PCA
  covariance, or PCA refit about the weighted centroid. AST-scan tests
  prohibit `abs/fabs/absolute/clip/maximum/clamp/zscore/nan_to_num` calls
  and the literal `273.15` in the module.
* Member-weight audit over all 760 structures (188,720 member cell-days):
  min 19.234 °C, max 52.505 °C, mean 37.441 °C, sd 6.409 °C;
  **0 missing, 0 duplicated, 0 non-finite, 0 zero-or-negative**; every
  denominator finite and positive. (Had any weight been ≤ 0 °C the code
  raises `WeightedCentroidError`, an explicit stop with no fallback.)
* Join: exact structure date + exact 1° cell-centre coordinates (stable
  identifiers; never row position; never approximate matching); exactly one
  Tmax per member cell enforced.

## 8. Dependency map (upstream frozen vs downstream affected)

Frozen upstream (verified unchanged): source NetCDF field · thresholds ·
15,738 days · 1,800 valid cells · 371-cell rule · 395 selected days ·
51 events · clustering params & labels (`final_labels_event_global_max.csv`
byte-identical) · DBSCAN noise · structure membership · Appendix A
(figA1 producer reads ONLY the labels CSV and recomputes unweighted PCA;
renderer reads ONLY the four frozen `figA1_inputs` CSVs) · σ=1.25 ·
unweighted PCA origins, covariances, eigenvalues/vectors, axes, areas,
ratios, orientations · event classification · Table 1 · area tails.

Downstream location products (regenerated): master-catalog centroid fields
→ Fig 3 (panels + composite; footprint re-rasterized) · Figs 5/6/7
(`snapshots.py` now renders via the weighted stages) · Fig 12 · LGCP inputs
(`build_inputs.py`) → R `kppm` refit → variant3 surface → k-fold CV +
risk-zone validation → CV figure, fold maps, Figure S4 (Appendix D) ·
sector counts. Power-law/Table-1/statistics scripts read **areas only**;
they are unaffected, and their inputs are unchanged.

## 9–10. Appendix A isolation and sigma proof

* Appendix A producer (`make_figA1_sigma_matrices.py`) reads exactly one
  data file (the labels CSV) and recomputes ordinary unweighted PCA
  (`lon.mean()`, `fit_pca`) over a 9×9 σ grid; the `MASTER` binding in it
  is dead code (assigned, never used). The renderer reads only the four
  frozen `figA1_inputs/*.csv` (byte-pinned in `docs/CANONICAL_SCIENCE.json`
  `sigma_sensitivity_figureA.expected_matrix_sha256`, verification status
  "4/4 BYTE-IDENTICAL"). Neither script references any weighted field or
  the new module, as enforced by lineage tests
  (`test_appendix_a_scripts_cannot_read_weighted_fields`,
  `test_appendix_a_inputs_are_the_frozen_sigma_matrices`,
  `test_upstream_stages_do_not_import_weighted_module`).
* σ = 1.25 confirmed in every authoritative source:
  `scripts/figures/common/common.py:57`, `snapshots.py:44`,
  `src/scorch/ellipses.py:18` (`SIGMA_DEFAULT`), `src/scorch/pipeline.py:73`
  + `configs/reproduction_fast.yaml:52` (operative config value),
  `docs/CANONICAL_SCIENCE.json` (`ellipse_geometry.sigma = 1.25`;
  `sigma_sensitivity_figureA.selected_sigma = 1.25`, combined score
  204.5440673062212 at 1.25, selection rule intact). Disambiguation: the
  LGCP `sigma2` (=1.647219 baseline) is the Gaussian random-field variance,
  and CV/bootstrap seeds are unrelated quantities; neither is the ellipse
  scale. Regression test `test_sigma_remains_exactly_1_25_everywhere`
  added. Appendix A was **not** re-run as a sensitivity experiment; its
  figure, tables, caption, and interpretation are untouched.

## 11. Frozen-artifact verification

* Pre-implementation freeze manifest:
  `provenance/corrections/tmax_weighted_centroids/freeze/freeze_manifest_pre.json` (126 files: 94 deposit +
  32 release-tree frozen artifacts, SHA-256 each) and
  `provenance/corrections/tmax_weighted_centroids/freeze/baseline_verification.json` (all §8 baseline values
  verified: counts 1800/15738/371/395/51/760; types 3-4-20-24 events,
  3-4-75-313 event-days, 3-13-185-559 structures; median area
  1.310172e6 km², max 6.507975e6 km², median ratio 0.5738; daily tail
  n=395, A_min=4,851,424, n_tail=43, α=10.519, p=0.1344; event tail n=51,
  A_min=3,590,049, n_tail=19, α=5.341, p=0.3592; unweighted LGCP variant3
  −11.352611 / −0.016062 / 0.063142 / 0.464404 / −0.007187, σ²=1.647219,
  scale 287.70796 km; CV 0.332895 top-20, 285.656/173.234 km,
  0.6349/0.655 ranks; sectors 145/144/18).
* Post-implementation comparison (760 rows, keyed by
  date/event/cluster): **all 53 frozen catalog columns match**; integer
  and string columns exact; float geometry columns worst relative
  difference **2.6e-16 (1 ulp)**: floating-point associativity between
  builds, far inside the release's own 1e-6 acceptance and the contract's
  1e-12 geometry tolerance; explained, not silent. Unweighted origins
  preserved bitwise except 20/1520 coordinate values differing by
  ≤ 3.6e-15 degrees (≈0.4 µm; same ulp cause). Labels CSV and
  `event_global_max_parameters.csv` regenerated **byte-identical** to the
  deposit. LGCP per-box covariate grid and covariate raster regenerated
  from the 1.78 GB Tmax record **byte-identical** to the frozen deposit
  copies.

## 12. Automated tests

* New suite `tests/test_tmax_weighted_centroid.py`: 26 tests covering the
  required matrix: reference example (6,7)≠(5,5) · Kelvin differs & unused ·
  equal-weight = ordinary centroid · hotter-cell pull · permutation and
  positive-scaling invariance · determinism · AST prohibitions ·
  missing/mismatch/duplicate/non-finite/zero-negative explicit stops ·
  structure independence · full PCA-geometry invariance under rigid
  translation (covariance, eigenvalues, eigenvectors up to sign, axis
  lengths, area, ratio, orientation, relative km-frame ellipse/axis
  geometry, marker at weighted centroid) · Tmax change moves only the
  weighted location · arbitrary downstream location cannot alter PCA ·
  bbox containment · σ=1.25 pins · Appendix A lineage isolation ·
  kernel-copy byte identity.
* Full release suite with the corrected catalog:
  **248 passed, 4 skipped** (skips: environment-dependent DOCX/canonical
  discovery variants), including the canonical regression tests
  (counts, typology recomputation, ellipse-geometry recomputation at
  rel 1e-6) and the reproduction-pipeline guardrails.
* Weighted stage invoked **exactly 760 times** for 760 catalog rows
  (builder hard-fails otherwise; recorded in `build_manifest.json`).
* Deterministic rebuild: two independent catalog builds byte-identical
  (SHA-256 `dffb5e8f393080728f0b1f11c53f9e0803889705429cb190ed8548604194a53d`).

## 13–15. Displacement audit

`provenance/corrections/tmax_weighted_centroids/audit/centroid_displacement_audit_760.csv` (760 rows: date,
event id/type, structure id, member count, both coordinate pairs, WGS84
geodesic displacement + bearing, old/new nearest analysis cell + change
flag, old/new sector + change flag, member Tmax min/max/mean/sd, total
Celsius weight, structure diameter, hull containment).

| stat | km |
|---|---|
| min | 0.0250 |
| Q1 | 6.928 |
| median | 31.258 |
| mean | 54.260 |
| Q3 | 101.516 |
| P90 | 133.209 |
| P95 | 149.852 |
| P99 | 174.599 |
| max | 200.383 |

Zero-displacement count 0 · nearest-cell reassignments 360/760 · sector
reassignments 29/760 · **0 displacements exceed the structure diameter** ·
**760/760 weighted centroids inside their structure's convex hull** (all
weights positive; bbox containment also enforced in-code). Largest cases
(`top20_displacements.csv`): event 46 (Type 4, 2024-06-01…04, 494–596
member cells, ~180–200 km westward) and event 22 (2012-07-13, 183.8 km).
Breakdowns by type/year/member-count/area/multiplicity:
`displacement_by_*.csv`. Audit-only map:
`audit_map_old_vs_new_centroids.png` (not a manuscript figure).

## 16–17. Fixed counts and geometry invariance

All §8 fixed counts reproduced exactly (see §11). PCA geometry invariance:
frozen columns identical at ≤1 ulp; ellipse centre = weighted centroid in
all regenerated products; relative ellipse/axis geometry preserved exactly
in the km frame (test-verified); daily-largest and event-largest structure
**identities unchanged** (areas frozen), coordinates now weighted.

## 18. Figure 3 footprint (before → after)

Point-in-ellipse footprint over the 1,800 valid cells, σ=1.25, all 760
ellipses (`provenance/corrections/tmax_weighted_centroids/audit/fig3_footprint_before_after.json`):
max overlap 280 → **279** footprints; argmax cell (41.5°E, 31.5°N) →
**(43.5°E, 30.5°N)**; covered cells 1683 → 1674; mean 71.66 → 71.29.
Figure 3 regenerated with all centroids/axes/ellipses at weighted centres,
same panel organization, "PCA-ellipse footprints per grid cell" convention
preserved (no "Event Frequency"), alignment acceptance checks passed
(frame spread ≤ 1 px).

## 19. LGCP (before → after), all 760 weighted centroids

| parameter | unweighted (v1.0.0) | Tmax-weighted (corrected) |
|---|---|---|
| intercept | −11.352611 | −11.457776 |
| lon | −0.016062 | −0.016147 |
| lat | 0.063142 | 0.066264 |
| mean_tmax_z | 0.464404 | 0.546415 |
| std_tmax_z | −0.007187 | −0.010951 |
| σ²_G | 1.647219 | 1.642911 |
| spatial scale (km) | 287.70796 | 272.455153 |
| intensity ratio | 15.8624 | 21.8254 |

Uncertainty measures: the minimum-contrast `kppm` fit does not produce
standard errors for fixed effects; **none are invented** (matching the
v1.0.0 convention "phi not available for this fitted LGCP object").
Geographic interpretation: qualitatively unchanged, with the intensity maximum in
the northeastern Tigris–Euphrates lowland corridor; hotspot cell
(45.5°E, 32.5°N); mean-Tmax remains the dominant covariate (stronger after
correction); weak negative std-Tmax effect; smooth NW–SE rank gradient
preserved. Covariates re-extracted at weighted locations
(`centroid_points_with_nearest_grid_covariates.csv`, max nearest-box
distance 72.7 km, all checks pass).

## 20. Sector counts (38–48°E, 29–37°N; fixed, post hoc, descriptive)

| set | unweighted | Tmax-weighted |
|---|---|---|
| all structures | 145/760 | **154/760** |
| daily-largest | 144/395 | **153/395** |
| event-largest | 18/51 | **19/51** |

Window bounds untouched and not re-optimized.

## 21. Cross-validation (seed 20260704; five folds of 152; fold assignment verified IDENTICAL to baseline by occurrence id)

Pooled (rank convention: pandas ascending fractional rank, average ties;
`heldout_risk_quantile` = area-weighted rank):

| metric | unweighted | Tmax-weighted |
|---|---|---|
| top-10% hit | 0.171053 | 0.188158 |
| top-20% hit | 0.332895 | **0.344737** |
| top-30% hit | 0.450000 | 0.476316 |
| top-50% hit | 0.672368 | 0.688158 |
| mean dist to top-20% (km) | 285.656 | **231.808** |
| median dist to top-20% (km) | 173.234 | **134.919** |
| area-weighted rank mean | 0.6349 | 0.6438 |
| area-weighted rank median | 0.6550 | 0.6801 |

Per-fold refits (betas in `fold_metrics.csv`) all completed; per-fold and
pooled outputs in `provenance/corrections/tmax_weighted_centroids/corrected_outputs/validation_kfold/`.
Interpretation preserved: occurrence-level validation of the first-order
spatial trend (not external validation).

## 22–23. Regenerated vs verified-unchanged artifacts

Regenerated (hashes: `provenance/corrections/tmax_weighted_centroids/corrected_outputs/SHA256_MANIFEST.json`,
29 artifacts): corrected master catalog CSV/XLSX (+ build manifest with
machine-readable weighting metadata), LGCP inputs and refit tables,
variant3 surface, CV tables, Figures 3/5/6/7/12, Figure S4, CV figure,
fold maps, displacement audit set. Corrected data overlay (deposit layout,
baseline never touched):
`<TMPDIR>/scorch_dep_v100/scorch_corrected_overlay_v1.0.1`
(DATA_DICTIONARY extended with the 20 new columns).
Verified unchanged: v1.0.0 deposit (93/93 hashes), labels/params CSVs
(byte-identical rebuilds), covariate grids (byte-identical), Appendix A
inputs/outputs (frozen, hash-pinned), Figures 1/2/4/8/9/10/11 and
Appendices A–C and station validation (area-only or non-centroid lineage;
inputs untouched; hashes preserved in the freeze manifest).

## 24. Manuscript impact inventory

See `provenance/corrections/tmax_weighted_centroids/MANUSCRIPT_IMPACT_INVENTORY.md`. The canonical manuscript
`SCORCH_Manuscript_FINAL_v1.0.0(1).docx`
(SHA-256 `9e140b9ea8927ae3b69c4e50afb8301006e8802dcf3e601f1c80c511ca3ca2e3`)
was **not edited**.

## 25. Commands, environment, seeds, runtimes

Key commands (all with `SCORCH_DATA_DIR` → deposit/overlay,
`SCORCH_OUT_DIR` → worktree `reproduced/`, `MPLBACKEND=Agg`,
`SOURCE_DATE_EPOCH=1785374765`): builder
(`scripts/pipeline/build_event_global_max_master.py`, ~3 min ×2 builds);
`scripts/lgcp/build_inputs.py` with `SCORCH_ERA5_TMAX_LONG_CSV` →
1.78 GB record (~4 min); `Rscript scripts/lgcp/spatial_risk_lgcp_model_diagnostics.R`
(~7 min); figure stages (~6 min); `extract_variant3` + CV chain (~4 min);
pytest full suite 33 s. Seeds preserved: CV 20260704; power-law bootstraps
20260617 (+offsets; untouched); DBSCAN deterministic.

## 26. Warnings and unresolved items (disclosed)

1. **RESOLVED 2026-08-07 (v1.0.1 packaging pass):** Supplement Figure S1
   now renders via the canonical `render_day_tmax_weighted` path (see
   §27.1); the stale-unweighted warning no longer applies.
2. Manuscript-embedded assets (`assets/manuscript_final/`,
   `publication-outputs` stage) remain v1.0.0-frozen pending the
   manuscript revision the impact inventory feeds.
3. Ulp-level float differences (≤2.6e-16 rel geometry; ≤3.6e-15 deg
   origins) between deposit and rebuild are documented above.
4. `canonical_daily_*` audit columns are carried verbatim from the source
   workbook during deposit rebuilds (Tier-B daily-adaptive workbook not
   shipped); values byte-identical to v1.0.0.
5. **RESOLVED 2026-08-07:** the corrected overlay now lives in the
   worktree at `release_staging/scorch_corrected_overlay_v1.0.1`
   (gitignored staging; archived, see §27.7).

---

## 27. v1.0.1 supplemental-asset and release-packaging pass (2026-08-07)

Code commit: `8c6cc2b9ee04461f8294bc5f7cece7fed387c7cd` on
`fix/tmax-weighted-centroids` (final branch head incl. this evidence
packet: see `release_staging/evidence/GIT_STATE.txt`).

### 27.1 Figure S.1 regenerated with weighted centroids

`make_figS1_type3_event25.py` switched from `render_day` to the canonical
`render_day_tmax_weighted`; all four displayed structure centroids
verified against the corrected catalog (<1e-9 deg) with displacements
33.459 / 118.254 / 24.271 / 125.601 km (nonzero displacement asserted;
a visually unchanged layer fails the build). Source data exported
(`Figure_S1_type3_event25_source_data.csv`). Station panels (c)/(d)
regenerated from the deposit (r = 0.98, RMSE = 1.70 °C, bias = −1.60 °C,
n = 9). Outputs (sha256 first 16): donor PNG `ae43520722eabbca`, donor
PDF `5b3804589e3bfa12`, composite `New_Figure_S1_candidate.png`
`d125a87d0f3a875a`, `.pdf` `b02015e3c44765ac`.

### 27.2 Appendix D (Fig. D) rebuilt from corrected data

Stale hard-coded means 438/286/181/81 km removed from
`make_figS3_risk_zone_distance.py` and the Fig. D compositor; replaced by
corrected regression pins 389.670138931229 / 231.807728434158 /
151.672109636537 / 69.064508207406 km (1e-6 km tolerance; derived from
the corrected validation table; n = 760, 5×152 folds, seed 20260704).
Fold maps re-derived (equal-grid-cell mean ranks 0.599–0.666; per-fold
top-20% hit rates 0.303–0.408, a DISTINCT convention from the
area-weighted held-out quantiles 0.6438/0.6801, kept separate).
Composite `New_Figure_S2_candidate.png` `88f9e177cf396d0d`, `.pdf`
`be02a4f1e1427b1a`; overlay copies of
`figS03/Figure_S3_risk_zone_distance_stats.csv` and
`figS04/Figure_S4_fold_metrics.csv` refreshed from the regenerated
outputs.

### 27.3 Figure 3 lattice provenance

The DISPLAYED panel (b) uses the 0.25° display lattice (145 × 201 nodes,
20–70°E / 10–46°N): independently recomputed maximum **282** at four
nodes near 42°E, 31°N: (41.75, 31.00), (42.00, 31.00), (43.00, 31.00),
(42.00, 31.25). The earlier-reported 279 @ (43.5°E, 30.5°N) is the
SEPARATE 1° 1,800-cell audit (maximum attained at four cells) and is not
the displayed maximum; §18's footprint block is that audit. Neither
number goes into the manuscript without naming its lattice. The
regenerated `fig03_ab_panel_bboxes.json` replaced the stale overlay copy.

### 27.4 Corrected-overlay repairs (docs, dictionary, metadata)

DATA_README.md re-titled v1.0.1 with a weighted-centroid remediation
section; PROVENANCE.md carries the release identifier, corrected variant3
LGCP fit, corrected CV/risk-zone values, and the event-14 note;
clean_data_README.md documents the 816,814-byte corrected catalog and the
weighted/unweighted field families; DATA_DICTIONARY.csv (649 rows,
99,622 bytes), with weighted-convention descriptions on all generic centroid
aliases + 68 observed ranges refreshed from the corrected payloads;
`lgcp/validation_summary.json` re-pathed (release-relative in-deposit,
`<LOCAL-PATH-REDACTED>/…` external; agrees with PROVENANCE). Zero live
machine paths remain in the overlay.

**Event 14:** the corrected regenerated
`event_global_max_parameters.csv` (event 14 `v3_type` = 3, matching the
mechanical typology and master catalog) was adopted into the overlay;
the prior "params CSV byte-identical" claim was removed from
`evidence.json` (the file differs from the frozen v1.0.0 copy in exactly
that metadata cell; eps/minPts unchanged). Regression test
`test_params_v3_type_matches_master` enforces agreement for all 51
events. The rebuilt-from-scratch parameters file is byte-identical to
the adopted overlay copy.

### 27.5 Manifests and validator

`validate_deposit.py` extended (FILE_MANIFEST coverage + SHA-256 + bytes
+ true CSV data-row counts); new
`scripts/deposit/rebuild_processed_deposit_manifests.py` (preserves path
order/descriptions, strict missing/duplicate/extra failure, rebuilds
SHA256SUMS incl. the final FILE_MANIFEST hash). Final overlay:
**SHA256SUMS 93/93 and FILE_MANIFEST 92/92: zero mismatches from both
systems; extended validator PASS.**

### 27.6 One-command reproducibility

New builtin stage `weighted-centroids` in the fast route (after
rebuild-catalog): reads member Tmax from the deposited NetCDF (units
checked), recomputes all weighted/translation fields with the strict
kernel, and compares every remediation column against the corrected
catalog. Full run against the overlay: **9/9 stages ok; weighted stage
760/760; worst rel diff 2.5e-15**. Appendix A isolation and legacy-helper
freeze unchanged (tests). Full suite: **274 passed, 2 skipped** (skips:
`publication_outputs/` not materialized); this count INCLUDES the 26
original remediation tests and the 4 new guards. Double-build re-verified:
two fresh catalog builds byte-identical to each other and to the overlay
catalog (`dffb5e8f…`).

### 27.7 Archives and portable Git evidence

Corrected-overlay archive
`release_staging/scorch_corrected_overlay_v1.0.1.zip` (94 files,
deterministic, SOURCE_DATE_EPOCH=1785374765):
sha256 `319a3a2b9ca296afd1dd21f0d23b38a54f5f138010a8e77e882fa3fcd118349a`;
overlay root hash (sha256 of SHA256SUMS)
`f7114c04c944090bda7cb7390b76d77f06d9f6a93ab00323ec7d72c710d25182`.
`GIT_STATE.txt`, the verified Git bundle
(`v1.0.0` + `fix/tmax-weighted-centroids`), the source/evidence archive
and the outer release manifest live under `release_staging/evidence/`
(hashes recorded in `RELEASE_MANIFEST.sha256` there). v1.0.0 commit, tag,
deposit, and archives untouched; nothing pushed or published.

---

**Verdict: REMEDIATION PASSED; CORRECTED OVERLAY AND EVIDENCE PACKAGING
VALIDATED (v1.0.1). External release remains withheld pending author
approval.**
