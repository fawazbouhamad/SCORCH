# SCORCH — ALIGNMENT DECISIONS (v1.0.0 pre-release correction programme)

**Branch:** `alignment-v1.0.1` — an internal, never-public pre-release working branch of the research repository (created from `scorch-demo-pack-v1-local` @ `a5853793b6e09bffd78dd93701edeb1419be8a2a`); the branch name is not a release version and no `v1.0.1` release exists
**Date opened:** 2026-08-04
**Author of record:** Fawaz Bouhamad — prepared for review with Dr. Nasser Najibi
**Status:** OPEN — no external publication, tag, push, or Zenodo action has been taken.

---

## 0. Forensic baseline

| Item | Value |
|---|---|
| Repository | `<CANONICAL-REPO>` |
| Branch at start | `scorch-demo-pack-v1-local` |
| HEAD at start | `a5853793b6e09bffd78dd93701edeb1419be8a2a` |
| Working branch | `alignment-v1.0.1` — internal, never-public pre-release working name (same HEAD; all working-tree changes preserved) |
| Local tags | **none** (`v1.0.0` exists only on `origin` and in the audit clone) |
| Remote | `origin https://github.com/fawazbouhamad/SCORCH.git` |
| Stashes | `stash@{0}`, `stash@{1}` — untouched |
| Pre-existing modification | `scripts/common/ellipse_pca.py` (M) — **preserved, see §6** |
| Pre-existing untracked trees | `clean/`, `release_staging/`, `outputs/…`, `paper_intake/`, `scripts/event_global_max/`, `scripts/six_task_review/`, `scripts/validation/`, `colab_assignment/`, `analysis_outputs/`, … — **all preserved** |
| Audit evidence | `<TMPDIR>\SCORCH_AUDIT_20260804` — **read-only, nothing deleted** |

Authoritative document artifacts (confirmed by content hash):

| Artifact | SHA-256 |
|---|---|
| `clean/manuscript/SCORCH_Manuscript_WORKING.docx` | `b21d8e9c2653db702f794f732bcf724994ec00feb51590d8f48d6c2ff31fd4aa` |
| `clean/supplementary/SCORCH_Supplementary_Material_WORKING.docx` (embedded Fig. S.1) | `a5632323514961c61a1b367c1cc2c950c93e1beac48cf7f134826e1367664bdc` |

The supplement's embedded Fig. S.1 hash matches the value supplied in the alignment brief **exactly**, confirming `SCORCH_Supplementary_Material_WORKING.docx` as the authoritative supplement.

---

## 1. Method: how "true original producer" was determined

The brief required that no artifact be assumed authoritative. The determination was made **by hash, not by filename or folder label** — a necessary precaution, because at least one folder in this repository is named in a way that inverts its actual contents (§3.2).

Procedure actually executed:

1. Extracted and SHA-256'd all embedded media from both authoritative DOCX files (16 in the manuscript, 1 in the supplement).
2. Built a SHA-256 index over **887 PNG files** across `clean/`, the latest release staging tree, and the audit evidence tree.
3. Matched every embed to its byte-identical sources.
4. Where no byte-identical source existed, recovered the transformation numerically by search over resampling filters and PNG encoder parameters until byte-exactness was achieved.

**Result: 17/17 embeds fully explained, with a byte-exact deterministic derivation for every one.** No embed is unaccounted for.

---

## 2. Canonical producer register

`repro_figs/*` denotes the reproduction run in the audit evidence tree; `→1950` denotes the recovered presentation downscale defined in §5.

| Manuscript item | True original producer | Embed derivation | Verdict |
|---|---|---|---|
| Fig. 1 | none — hand-drawn schematic, shipped as frozen asset | identical | Frozen-by-design; **outside reproduction boundary** |
| Fig. 2 | `scripts/figures/fig02/*` | identical | Reproduces |
| Fig. 3 | `scripts/figures/fig03/*` | identical | Reproduces |
| Fig. 4 | none — hand-drawn typology schematic, frozen asset | identical | Frozen-by-design; **outside boundary**; not to be redesigned |
| Fig. 5 | `scripts/figures/fig05_06_07/make_figs_5_6_7.py` | →1950 | Reproduces |
| Fig. 6 | `scripts/figures/fig05_06_07/make_figs_5_6_7.py` | →1950 | Reproduces |
| Fig. 7 | `scripts/figures/fig05_06_07/make_figs_5_6_7.py` | →1950 | Reproduces |
| Fig. 8 | `scripts/figures/fig08/Figure_10_Statistical_Analysis_of_Types_ORIGINAL.py` | →1950 | Reproduces; presentation step now recovered |
| **Fig. 9** | `scripts/figures/fig09/make_figure9_unified_ORIGINAL.py` | →1950 | **DEFECTIVE — see §3** |
| Fig. 10 | `scripts/figures/fig10/Figure_9_Trend_Analysis_With_Table_statistics.py` | →1950 | Reproduces; **contains disallowed inference — see §4** |
| Fig. 11 | `scripts/figures/fig11/make_q1_power_law_2x2_panel.py` | →1950 | Reproduces |
| Fig. 12 | `scripts/figures/fig12/make_q1_variant3_four_variable_centroid_map.py` | identical | Reproduces |
| Appendix A | `scripts/figures/figA1/make_figA1_sigma_sensitivity.py` (renderer) + **recovered analysis, §7** | →1950 | Reproduces end-to-end |
| Appendix B | `scripts/figures/figA2/make_new_figA2_event10_candidate.py` | identical | Reproduces |
| Appendix C | `scripts/figures/figA3/make_figA3_dbscan_params.py` | →1950 | Reproduces |
| Appendix D | `scripts/figures/figS2/make_new_figS2_candidate.py` | identical | Reproduces |
| Fig. S.1 | `scripts/figures/figS1/make_new_figS1_candidate.py` | identical | **Hybrid composite — see §8** |

---

## 3. Correction 1 — Figure 9 orientation (CONFIRMED GENUINE DEFECT)

### 3.1 What was actually executed

The producer of the embedded Figure 9 is the release script
`scripts/figures/fig09/make_figure9_unified_ORIGINAL.py`, which aggregates per-event orientation as:

```python
orientation_deg=("orientation_deg", "mean")     # arithmetic mean of axial angles
```

This is **invalid**. `orientation_deg` is a 180°-periodic axial quantity; its arithmetic mean is not
rotation-equivariant and is not a meaningful statistic. The PCA, DBSCAN, typology, event assignment,
and the 760-row catalog are **not** implicated — the defect is confined to the derived aggregation.

### 3.2 Proof that the defect reached the manuscript

Three distinct Figure 9 artifacts exist. Naming is actively misleading:

| Artifact | SHA-256 (PNG) | Content |
|---|---|---|
| `clean/manuscript/figures/fig09/Figure_09.png` | `9c5f5e39…` | axial-corrected (strip panel (c)) |
| `clean/manuscript/figures/fig09/versions_B2B1_.../Figure_09.png` | `4cb3b38a…` | **legacy arithmetic** — despite the `versions_B2B1` name |
| **manuscript embed** `word/media/image9.png` | `b023c6e5…` | derived from the **legacy** artifact |

> The directory `versions_B2B1_20260722_215245` is a **pre-change backup taken at the B2B-1 edit**, not the B2B-1 result. Reading it as "the B2B-1 version" inverts the truth. This is recorded here to prevent recurrence.

Byte-exact demonstration (executed):

```
repro_figs/fig09/Figure9_assembled.png   (= 4cb3b38a…, legacy arithmetic)
  → convert("RGBA") → resize((1950, int(h*1950/w)), LANCZOS)
  → PNG optimize=False compress_level=6
  = b023c6e55359b69d74dd1b93f7199c2f82f12d782cd76f3de5170a8f36460ad1   ← manuscript embed
```

Pixel agreement with the legacy source is **100.00 %** (mean |Δ| = 0.0000); against the corrected
source it is only 94.21 % (mean |Δ| = 2.94, max 255). **The superseded pre-release manuscript Figure 9 candidate carries the bug.** (The project was never publicly released; "manuscript embed" here means the embed in the pre-release working manuscript.)

### 3.3 Magnitude

Event 4, θ (CCW-from-east) = `[173.941, 50.015, 174.751, 51.071, 172.277, 44.553]`:

| Statistic | Value (manuscript convention, CW-from-north) |
|---|---|
| Correct doubled-angle axial mean | **+68.98532754765856°** |
| Arithmetic mean (as embedded in the superseded pre-release manuscript candidate) | **−21.10137813712798°** |

Discrepancy ≈ **90°** — a maximal axial error. The axial value reproduces the target
`68.985327547659°` given in the brief to 12 significant figures. **Verified.**

### 3.4 Conventions (both retained, explicitly)

- **Legacy catalog convention (preserved, unchanged):** `orientation_deg` is **counterclockwise from east, in [0, 180)**. Verified directly against `pc1_vec_x/pc1_vec_y` (row 1: atan2(0.3771, 0.9262) = 22.153° = `orientation_deg`).
- **Manuscript convention:** **clockwise from north, in (−90, 90]**, via θ_N = 90 − θ_E, wrapped.

### 3.5 Decision

| Question | Decision |
|---|---|
| What was executed? | Arithmetic mean of axial angles (invalid). |
| Scientifically valid? | **No.** |
| Canonical implementation? | New tested module `scorch_axial.py`; the axial logic already drafted in `clean/manuscript/figures/fig09/scripts/make_figure9_unified.py` is adopted as the reference behaviour. |
| Presentation of panel (c)? | **KDE retained.** The manuscript caption states "Kernel density estimates"; the brief forbids redesigning figures beyond the stated corrections. Only the *values* change, not the display form. The drafted strip-plot variant is **rejected** as an unrequested redesign. |

**Downstream artifacts requiring regeneration:** Fig. 9 event-level CSV; panel 9(c); assembled Fig. 9;
panel extracts; →1950 manuscript artwork; `publication_outputs/figures/Figure_09/*`;
`PROVENANCE.txt`; `SHA256SUMS`; `PUBLICATION_OUTPUTS_MANIFEST.csv`; the manuscript embed.
**Figures 9(a)–(b), event areas, and axis-ratio summaries are unchanged** (they do not involve angles).

---

## 4. Correction 2 — contradictory frequency inference

**Manuscript (already correct):** *"Annual event counts are reported descriptively and are not subjected to a trend test."*

**Code (contradicts the manuscript):**

- `scripts/pipeline/make_global_max_tables.py` L157–L168 — computes Sen's slope **and** Mann–Kendall p for *frequency* (`sen_f`, `p_f`) and emits them into the public Table B.
- `scripts/figures/fig10/Figure_9_Trend_Analysis_With_Table_statistics.py` L516–L517 — same for the Fig. 10 path and console output.

**Decision:** the manuscript is correct; the code is wrong. Remove all *frequency* MK/Sen computation,
table rows, and console output. Annual event-count plots remain, descriptive. The trend table retains
**only the two approved duration analyses**. Type-3 and Type-4 duration values must be confirmed
bit-for-bit unchanged after removal.

---

## 5. Correction 6(a) — recovered presentation processing (RESOLVED)

The Figure 8 / Figure 9 "approved manual presentation processing" was not lost — it was never written
down. It has now been **recovered numerically and proven byte-exact**:

```python
im = Image.open(src).convert("RGBA")
w, h = im.size
im.resize((1950, int(h * 1950 / w)), Image.LANCZOS) \
  .save(dst, "PNG", optimize=False, compress_level=6)
```

Note `int(...)` (truncation), **not** rounding — three figures disambiguate this (App. A: 1781.90 → 1781;
App. C: 1330.95 → 1330; Fig. 10: 1222.58 → 1222). Rounding fails on all three.

**Validation: 9/9 byte-exact** — Figs. 5, 6, 7, 8, 9, 10, 11, Appendix A, Appendix C.
The remaining 8 embeds are byte-identical to their producers with no processing.

This is encoded as a deterministic script and applies unchanged to corrected Figure 9.

---

## 6. Pre-existing `ellipse_pca.py` change (PRESERVED AND VINDICATED)

The working tree removes a 1 km **semi-axis** floor (`_AXIS_FLOOR`) while **retaining the 1 km²
variance floor** (`_VAR_FLOOR`) — consistent with the brief's instruction to retain the variance floor
and the implemented full-axis geometry. The change comment asserts the axis floor could never bind.

**This assertion is now empirically confirmed** (§7): re-running the sensitivity analysis under the
modified module reproduces the pre-change frozen matrices byte-identically. The change is retained.

---

## 7. Correction 6(b) — Figure A sensitivity analysis (RECOVERED AND VERIFIED)

The release ships only *frozen derived* matrices at `scripts/figures/figA1_inputs/`, and its renderer
docstring concedes the producer lives in "the research repository". Re-rendering archived matrices does
not constitute end-to-end reproduction.

**The producer has been located** — untracked, in the working tree:
`scripts/event_global_max/regenerate_pca_sigma_sensitivity_matrix_global_max.py`

Method: for each of 81 (σ_PC1, σ_PC2) pairs over `[0.5 … 2.5]` step 0.25, compute
`target_component_purity = |H ∩ E| / |E|` across all **760** components; aggregate as
Minimum / Maximum / Average; **Combined = Min + Max + Average**.

**Executed re-run result — 4/4 matrices byte-identical to the frozen release inputs:**

| Matrix | SHA-256 |
|---|---|
| `pca_sigma_matrix_minimum.csv` | `89890a9459ed19e427bc64c45c366e035ab178eec7da1e59c5ddde24de92e61c` |
| `pca_sigma_matrix_maximum.csv` | `a7eb107c7d2dbc1de6a515c165b8a31f63f3e9e229c15b776167bbbd0d9c84b7` |
| `pca_sigma_matrix_average.csv` | `4d52067b61862e0e796de827ca08bb4e27b9aaed9f0ad2fd09d92e1c4bd233c5` |
| `pca_sigma_matrix_combined.csv` | `03cf1cc4b1e53043b0b7c5e0dfb4b627ceeffad352dd1b32db5dc59b9542045d` |

Confirmations against the brief:

- (1.25, 1.25) combined = **204.5440673062212** → displays as **205** ✓
- It is the **maximum of the equal-σ diagonal** (next: 203.791 at σ=1.5; 198.994 at σ=1.0) ✓
- σ = 1.25 retained ✓
- Best off-diagonal pair (1.5, 0.75) scores 213.6 but is **reference-only by design** — the one-scalar
  algorithm selects on the diagonal. Recorded here so the higher off-diagonal number cannot later be
  mistaken for an inconsistency.

**Decision:** this script becomes canonical and ships in the release, promoting Figure A from
"re-render of frozen inputs" to genuine end-to-end reproduction.

---

## 8. Correction 6(c) — Figure S.1 status

Panels S.1(a–b) regenerate. Panels S.1(c–d) currently derive from **frozen donor artwork**
(`assets/frozen_figures/figS1_station_donor/`), with only the statistics regenerating.

**Until a deterministic station plotter is in place, provenance must read "hybrid composite" and must
not claim "fully regenerated from deposited data."** The supplement text itself is scientifically
aligned and its reported statistics (r = 0.98, RMSE = 1.70 °C, bias = −1.60 °C) are correct.

---

## 9. Correction 5 — environment discrepancies (RESOLVED)

**R 4.5.1 vs 4.5.3 — not a conflict.** The executed log (`evidence/lgcp_R.log`) shows only:

```
package 'spatstat.geom' was built under R version 4.5.3
```

This is R's standard *build-provenance* warning. The **executing interpreter was R 4.5.1**
(`environment/renv.lock` `"Version": "4.5.1"`, and the installed toolchain at
`<R-4.5.1>/bin/Rscript.exe`). Documented as: **executed under R 4.5.1 with spatstat
binaries built under R 4.5.3.** The fit completed with `Captured fit warnings: 0` and
`ALL QC CHECKS PASS: TRUE`.

**`spatstat.model` typography.** Already correct as **`3.7-1`** throughout the release
(`renv.lock`, `R_WORKFLOW.md`, `THIRD_PARTY_DEPENDENCIES.md`). A repository-wide search found **no**
`3.7.1` occurrence in the release tree. Recorded as verified-correct; the contract pins `3.7-1`.

**φ = 287.7 km.** The manuscript's φ corresponds to the LGCP output field **`scale_km`**
(`scale = 272.455153` km for the current weighted-centroid fit; the superseded
pre-remediation value was `287.707960` km), **not** the separate `phi` field the R script emits. `spatstat`'s
`kppm` does not define a cluster-strength `phi` for this LGCP parameterisation; the script's own note
says so. This must be stated explicitly wherever φ is reported.

---

## 10. Correction 3 — Table 1 terminology and type labels

**Verified directly from the 760-row catalog:**

| Quantity | Type 1 | Type 2 | Type 3 | Type 4 | Total |
|---|---|---|---|---|---|
| **Selected event-days** (distinct dates) | 3 | 4 | 75 | 313 | **395** |
| Compound events | 3 | 4 | 20 | 24 | **51** |
| Structures (ellipse rows) | 3 | 13 | 185 | 559 | **760** |

**3 / 4 / 75 / 313 are selected event-days, not events.** They are distinct dates and equal the sum of
`duration_days` per type. The event counts are 3 / 4 / 20 / 24. The manuscript already states this
correctly ("Frequency of Occurrence (Number of Selected Event-Days)"); **generated headers must be
corrected to match.**

**Canonical public type-label mapping** (adopted from manuscript Table 1, which is authoritative):

| Type | Canonical public label | Legacy/internal aliases (documented, not for publication) |
|---|---|---|
| 1 | **Widespread** | `Independent` (`event_type_name`), `Independent` (`event_type_original`) |
| 2 | **Spatially clustered** | `Independent Simultaneous` |
| 3 | **Temporally clustered** | `Back-to-Back` |
| 4 | **Mixed** | `Mixed Multi-Day` |

"Independent" survives **only** as an explicitly documented legacy alias for Type 1 and must not appear
in any public label.

> **Flagged for Fawaz (not silently changed):** the manuscript's own Fig. 4 caption uses
> "Type 1, Widespread (Isolated)" and "Type 4, Compound Clustering (Multi-Type)", which differ from
> Table 1's "Widespread" / "Mixed". The brief forbids redesigning Figure 4, so **no change has been
> made**. Table 1's mapping is taken as canonical for generated artifacts. This wording difference is
> internal to the manuscript and is an editorial decision for the authors.

---

## 11. Release identity (Correction 4) — approach

The working tree and the `v1.0.0` tree are **structurally different projects**: the working tree is the
research repository (`scripts/`, `outputs/`, `clean/`, `release_staging/`), whereas `v1.0.0` is the
curated release (`src/`, `tests/`, `environment/`, `assets/`). They are **not** comparable as a single
tree, and no claim of identity between them should ever be made.

Known deltas already evidenced in the audit tree:

- 36 PDFs differ from frozen by **exactly +6 bytes** — a PDF metadata/timestamp artifact, not science.
- 30 LGCP outputs exist only in the frozen set (not emitted by the figure workflow).
- 10 files differ between the publication run and frozen: `PROVENANCE.txt` × 7, `SHA256SUMS`,
  `PUBLICATION_OUTPUTS_MANIFEST.csv`.

**Decision (as revised by the final v1.0.0 directive):** prepare a **corrected v1.0.0 release
candidate**. SCORCH has never been publicly released, so all corrections are pre-publication
corrections *within* the first release: the final release remains **v1.0.0** and earlier defective
builds are superseded pre-release candidates, not published versions. No active `v1.0.1` release is
created or retained. The pre-existing local `v1.0.0` tag in the release repository (pointing at the
superseded pre-release commit) is left untouched — no tag is created, moved, or deleted; the future
public tag must point at the final corrected commit recorded in `RELEASE_IDENTITY.json`. Any statement
that the Zenodo software archive is identical to a prior candidate must be a precise, path-normalised,
SHA-256-backed statement of what actually matches.

---

## 12. Standing constraints honoured

Pooled April–September threshold retained · σ = 1.25 retained · 1 km² variance floor and full-axis
geometry retained · 1,800 cells / 15,738 days / Θ = 371 / 395 selected days / 51 events / 760
structures retained · event counts 3/4/20/24 · selected event-days 3/4/75/313 · annual counts
descriptive only · duration-trend, power-law, LGCP variant 3, cross-validation and station-validation
results retained · Type-4 permutation analysis **not** restored · Figure 4 **not** redesigned ·
no Discussion section added · heatwave methodology **not** redesigned.

---

## 13. Reproducibility boundary

- Mandatory clean reproduction begins from the **versioned processed-data Zenodo deposit**.
- This is **distinct** from raw provider-level ERA5 reconstruction, which requires the 1.78 GB
  external Tier-B CSV and CDS/ARCO retrieval. **No claim is made that the full raw ERA5 provider chain
  was executed.** Retrieval scripts and methodology are preserved for reconstruction.
- Manuscript daily/event-maximum power-law results are kept **separate** from any exploratory
  all-760/by-type analysis.
- Figures 1 and 4 are hand-drawn schematics with no computational producer — permanently
  **outside the reproduction boundary**, by design, not by omission.

---

# PART II — REMEDIATION RECORD (2026-08-04)

The forensic determinations in Part I were carried out. This part records what
was **executed**, and where Part I's provisional decisions were overridden by
evidence found during implementation.

## 14. Decisions revised during remediation

| Part I position | Final decision | Why it changed |
|---|---|---|
| Canonical type labels taken from manuscript **Table 1** ("Widespread", "Mixed"), with the Fig. 4 caption flagged as an open editorial item | Canonical vocabulary is the **Fig. 4 / abstract wording**: *Widespread (Isolated)*, *Spatially Clustered*, *Temporally Clustered*, *Compound Clustering (Multi-Type)* | Directed by the alignment brief. Table 1 was updated to match the rest of the manuscript, not the reverse. No open editorial item remains. |
| Table cells rendered `Type N (Label)` | Rendered **`Type N: Label`** | Two canonical labels already contain parentheses; `Type 1 (Widespread (Isolated))` nests badly. Values and column semantics are unchanged. |
| Figure S.1 stays a **hybrid composite**; provenance must say so | Figure S.1 is **fully regenerated from deposited data** | The original station producer *was* recoverable — `clean/scripts/figures/Validation Script.py`. Part I's superseded historical conclusion was that no runnable producer existed, because the release's own docstring said so; that claim was wrong and is corrected here. |
| Table 1 column order not identified as an issue | **Column order corrected** — "Longest Compound Event" moved to column 4 | `docs/TABLE_PROVENANCE.csv` recorded a standing column-order divergence from the manuscript and the deposit. The publication validator now declares 0 presentation differences. |
| `spatstat.model` typography needed correcting to `3.7-1` | **No correction required** | The release already used `3.7-1` everywhere. R's `packageVersion()` renders the same version as `3.7.1`; the two are the same package version, not a discrepancy. |

## 15. Evidence that the Figure 9 correction is correctly scoped

Beyond the Part I forensics, three checks constrain the blast radius:

1. Panel raw-RGB hashes: (a) `5869efc01c7e4662` and (b) `1ba869558cafb0e4` are
   **identical to the superseded pre-release candidate**; only (c) changed. Areas and axis ratios untouched.
2. Out-of-panel ink is **exactly 2779 px** before and after — shared chrome
   (the legend) did not move.
3. The Zenodo processed-data deposit **already carried the axially-corrected
   event CSV**. The regeneration matches it to 2.1e-14 deg, 2.2e-16 (R), and
   exactly 0.0 for area and ratio over all 51 events. The deposit even records
   the legacy arithmetic value as -21.10137813712799.

Point 3 is the strongest single result of this programme: the deposit, the
manuscript prose and the σ-selection analysis were all already correct. **Only
the release code and the rendered Figure 9 lagged.** The alignment direction was
therefore code -> artifacts, never manuscript -> code.

## 16. Deliverables produced — SUPERSEDED interim artifacts (historical record)

The correction pass initially packaged its results under an interim
"v1.0.1" label. **Those interim artifacts are superseded pre-release
candidates** — the final v1.0.0 directive replaced them with the
`SCORCH-1.0.0.zip` archive built by `git archive` from the final release
commit (identity in the external `RELEASE_IDENTITY.json` sidecar) and the
`SCORCH_*_FINAL_v1.0.0.docx` documents. For the record, the interim pass
produced:

* an interim deterministic zip (148 files, SHA-256 `b8d27642…`) — SUPERSEDED,
  never published;
* interim "ALIGNED" manuscript and supplementary DOCX copies (originals
  untouched) — SUPERSEDED by the FINAL v1.0.0 documents;
* clean-room and R environment logs, retained in the private alignment
  staging area (not part of this release tree);
* `legacy_defective_figure09/` — superseded defective artifacts, clearly
  labelled, excluded from canonical publication outputs, and shipped in this
  release for auditability.

## 17. Standing prohibitions honoured

No push. No tag. No Zenodo publication. No external record touched. The public
`v1.0.0` tag was not moved or rewritten. Neither original DOCX was overwritten.
No legacy evidence was deleted. Both stashes are untouched. The processed-data
deposit re-verified 93/93 against its own `SHA256SUMS` after every run.

---

# PART III — FINAL REMEDIATION RECORD (2026-08-04, second pass)

A final forensic remediation pass corrected the remaining active
provenance/documentation contradictions. **Documentation, provenance and
validation only — no method, result, figure data, configuration, seed, or
numerical conclusion changed.**

| Correction | What changed |
|---|---|
| A | Figure A producer docstring: the false pre-release account `33+100+76 = 209` replaced by the verified exact account `29.20696324951644 + 100 + 75.33710405670476 = 204.5440673062212` (displayed 205; equal-sigma-diagonal maximum), and the conflicting reverse-engineered/recovered provenance language reconciled to the evidence-supported account (original producer recovered from the research tree, sanitized, wired into the release workflow). Matrices unchanged. |
| B | Stale superseded Table 1 checksum `778e08ab…` removed from the active `REPRODUCIBILITY_MATRIX.csv` PASS row; the active checksum is the canonical `f12ee1ab…`, re-proven by regeneration. The old hash survives only in explicitly labelled superseded-historical context. |
| C | All statements describing the defective Figure 9 as "published" reworded to "superseded pre-release manuscript candidate" (the project was never publicly released). Legitimate bibliographic/future-journal uses of "published" untouched. |
| D | The time-sensitive "no public tag exists" claim replaced by the durable invariant: before publication, the public `v1.0.0` tag must resolve to the final canonical release commit and tree. (Audit-time fact, recorded externally: origin/v1.0.0 pointed at the stale commit `3c894e8f` and had not been moved.) |
| E | GitHub/Zenodo lifecycle prose in `.zenodo.json`, `CITATION.cff`, `README.md`, `docs/` made lifecycle-neutral or explicitly pre-publication; DOIs and version unchanged; machine-readable relationship fields retained. |
| F | Stale references into the retired alignment staging tree (the never-shipped `release_staging/ALIGNMENT_V1_0_1_...` working directory) replaced by the shipped `legacy_defective_figure09/` path and the external-evidence `evidence/R_environment.log` reference; dangling research-tree module/producer paths in `CANONICAL_SCIENCE.json` re-pointed to the shipped release paths with verified hashes, research-tree originals kept as explicitly external references. |
| G | "V12" no longer described as the current release anywhere; it survives only as an explicitly historical internal pre-release label. Public identity: SCORCH v1.0.0. |
| H | Deposit-copy claims qualified: byte-identity statements for `table01/` refer to the corrected LOCAL staging copy of the Zenodo data deposit; the ONLINE data draft still carried pre-correction table01 files at audit time and its synchronization is a required manual release step. |
| Guards | `tests/test_stale_provenance.py` (16 tests in R2, 22 after the R3 additions, 56 after the R4 normalization-hardening and its parameterized evasion/allowance fixtures) added so future builds fail on any recurrence, plus `tests/test_final_docx_geometry.py` (20 R5 final-DOCX display-geometry and content-identity guards); suite now 246 collected tests. |

## 19. R3 addendum (2026-08-05)

A third documentation-only pass: `docs/TABLE_PROVENANCE.csv` rewritten
as strictly rectangular CSV (historical checksum retained, labelled);
publication-builder Table 1 provenance prose corrected to the measured
zero-difference state with MANUSCRIPT constant terminology; lifecycle
sweep completed (manuscript/canonical wording replaces false
'published' claims in scripts, src docstrings and docs); Figure S.1
producer contradiction resolved (only the superseded legacy fallback
lacks its original producer); six structural/lifecycle guards added
(shipped-CSV rectangularity, JSON/CFF parsing, Table 1 prose
consistency, S.1 producer guard, false-lifecycle-phrase guard). The
comment-only wording fix in scorch_axial.py updated its pinned hash
(recorded in CANONICAL_SCIENCE.json). No scientific output changed.
