# XLSX semantic-equivalence report

Evidence for the `approved_removal` record of

`remediation/corrected/event_global_max_algorithm/scorch_new_algorithm_master_cluster_ellipse_event_global_max.xlsx`

in `remediation/corrected_outputs/SHA256_MANIFEST.json`.

**Verdict: SEMANTIC EQUIVALENCE PASSES.** The workbook carried no information the
canonical CSV beside it does not.

The verdict is unchanged from the first issue of this report. What changed is the
strength of the program that produces it: four ways of handing the comparison a
workbook that was *not* equivalent and still collecting a PASS were closed, and
this report has been re-measured against the hardened program rather than
inherited from the earlier run. Section 6 states each closed bypass, and section 9
records every superseded claim.

## 1. How to reproduce

From the repository root:

```
python remediation/xlsx_equivalence/compare_master_csv_xlsx.py
```

The script re-derives every number below from a fresh extraction of the workbook;
no result is cached and no earlier run is consulted. It prints a JSON report and
exits `0` on PASS, `1` on FAIL, `2` if the inputs are unavailable.

The workbook is no longer in the repository. To reproduce against the deposited
copies, extract the processed-data archive `scorch_processed_data_v1.0.0.zip` and
set `SCORCH_DATA_DIR` to the extracted root; the script then reads
`catalogs/scorch_new_algorithm_master_cluster_ellipse_event_global_max.{csv,xlsx}`.

Environment of the recorded run: CPython 3.12.10, pandas 3.0.3, numpy 2.4.6,
openpyxl 3.1.5. Readers are `pandas.read_csv`, `pandas.read_excel(sheet_name=
"master_cluster_ellipse")`, `openpyxl.load_workbook(data_only=False)` and a raw
`zipfile.ZipFile` part listing.

A malformed package no longer produces a bare traceback. Both `load_workbook` and
`read_excel` failures are caught and reported as a structured FAIL carrying
`workbook_load_error` / `comparison_ran: false` with `inert: false`, so an
unreadable workbook yields a verdict to act on rather than an unhandled crash.

## 2. Byte identity of the compared artifacts

Not byte-identical to each other, and never expected to be: one is a ZIP-container
spreadsheet, the other plain text. Both scopes declared by
`remediation/corrected_outputs/SHA256_MANIFEST.json` are retained permanently,
whatever the relocation state.

| Artifact | Scope | Bytes | SHA-256 |
|---|---|---|---|
| CSV | historical Windows worktree (CRLF) | 816,814 | `dffb5e8f393080728f0b1f11c53f9e0803889705429cb190ed8548604194a53d` |
| CSV | repository-normalized (LF) | 816,053 | `f9e98478875cb706721a023b06759317903065d413948b4c1170bc773e62fc5c` |
| XLSX | historical Windows worktree | 428,600 | `4ca9ef136ee0a98ada2acc7d3976bc314a4402f8b22af62f818119ba286e6b42` |
| XLSX | repository-normalized | 428,600 | `4ca9ef136ee0a98ada2acc7d3976bc314a4402f8b22af62f818119ba286e6b42` |

The XLSX is binary, so its two scopes are identical. The CSV's two scopes differ
**only** by LF↔CRLF, a proven end-of-line transformation, not byte identity.

The recorded run read the **archive members**, not a repository copy: the report's
`csv_source` and `xlsx_source` are both `deposit`. Those members hash to
`dffb5e8f…4a53d` / 816,814 B and `4ca9ef13…6e6b42` / 428,600 B: that is, the
deposited CSV is byte-identical to the *historical-worktree* (CRLF) form, and the
deposited workbook is byte-identical to both declared XLSX scopes. The comparison
therefore ran against exactly the bytes this report names, and says which copy
they came from rather than leaving it to be assumed.

## 3. Workbook structure

| Property | Result |
|---|---|
| Sheet count | 1 |
| Sheet names | `master_cluster_ellipse` |
| Sheet states | `master_cluster_ellipse` = `visible` |
| Hidden / very-hidden sheets | 0 |
| Formula cells | 0 |
| External-link parts (`xl/externalLink*`) | 0 |
| External relationship targets | 0 |
| Charts | 0 |
| Images | 0 |
| Cell comments | 0 |
| Defined (named) ranges | 0 |
| VBA archive / macro parts | none |
| Pivot caches (object model) | 0 |
| Worksheet pivots (object model) | 0 |
| Raw `xl/pivotCache*` / `xl/pivotTables*` ZIP parts | 0 |
| `.rels` parts scanned | 2 |
| Relationships parsed | 6 |
| `.rels` parse errors | 0 |

Complete ZIP member list (9 parts, no macro and no external-link part):
`[Content_Types].xml`, `_rels/.rels`, `docProps/app.xml`, `docProps/core.xml`,
`xl/_rels/workbook.xml.rels`, `xl/styles.xml`, `xl/theme/theme1.xml`,
`xl/workbook.xml`, `xl/worksheets/sheet1.xml`.

### Relationships: every `.rels` part, parsed as XML

The relationship scan enumerates **every** `.rels` member in the container and
parses each as XML, rather than string-matching a single known part. Two parts
exist and both were scanned:

| Part | Id | Type (short) | Target | TargetMode |
|---|---|---|---|---|
| `_rels/.rels` | rId1 | officeDocument | `xl/workbook.xml` | internal |
| `_rels/.rels` | rId2 | core-properties | `docProps/core.xml` | internal |
| `_rels/.rels` | rId3 | extended-properties | `docProps/app.xml` | internal |
| `xl/_rels/workbook.xml.rels` | rId1 | worksheet | `/xl/worksheets/sheet1.xml` | internal |
| `xl/_rels/workbook.xml.rels` | rId2 | styles | `styles.xml` | internal |
| `xl/_rels/workbook.xml.rels` | rId3 | theme | `theme/theme1.xml` | internal |

All six are internal; `external_relationships`, `external_relationship_parts` and
`external_relationship_targets_detail` are all empty, and
`relationship_parse_errors` is empty.

**This is new information, and it is recorded as such.** The earlier
implementation read only `xl/_rels/workbook.xml.rels`, by counting strings.
`_rels/.rels` (which holds three of the six relationships) had never been
inspected at all when the first issue of this report was written. The finding does
not change the verdict (there was no external relationship to find), but the
earlier report's clean external-link line rested on a narrower scan than its
wording implied.

### Scope of the inertness claim

The reproducer checks **23 enumerated properties** and emits them as
`workbook_structure.inertness_properties_checked`. Beyond the table above it
also verifies, all measured **0**: merged cell ranges, conditional-formatting
ranges, data validations, hyperlinks, worksheet tables, auto filters, frozen
panes, and pivot caches.

The claim is **scoped to that enumerated list** and is stated as such. It is NOT
a blanket claim that the workbook carries no presentation information
whatsoever. Five property groups are deliberately **not constrained** and are
listed in `inertness_properties_not_checked`: cell number formats (reported, not
required to be empty), cell styles (fonts, fills, borders, alignment), column
widths and row heights, print settings and page setup, and sheet protection.
Requiring zero number formats would be a false criterion, since a date column
may legitimately carry a display format a CSV cannot represent.

None of the unchecked properties can affect semantic equivalence here, because
every cell **value** is compared directly and date columns are normalized to ISO
strings before comparison. As it happens the measured `number_formats_observed`
for this workbook is exactly `['General']` - the default and nothing else - so
no non-default format is present either, but that is a measurement, not part of
the pass criterion.

The workbook therefore carries no logic or linkage a CSV cannot represent, and
no presentation information among the 23 checked properties.

## 4. Shape, columns, row keys, exact fields

| Property | Result |
|---|---|
| Shape | 760 × 81 in both |
| Column names and order | identical (0 CSV-only, 0 XLSX-only) |
| Row key | `new_event_id` + `date` + `cluster_id` |
| Key uniqueness | unique in both |
| Key order | positionally identical row-for-row; first `1\|1983-07-13\|0`, last `51\|2025-08-15\|1` |
| Non-numeric columns | 5 (`date`, `type`, `event_type`, `event_type_name`, `event_type_original`); **0 differing cells** |
| Integer-schema columns | 20 declared, 20 present, 0 missing; **0 differing cells** |
| Canonical-CSV schema violations | 0 |
| Non-integral cells in an integer column | 0 |
| Non-numeric XLSX cells in an integer column | 0 |
| NaN mask | identical |
| +Inf mask | identical |
| −Inf mask | identical |

Dates are ISO `YYYY-MM-DD` in both and compare as exact strings.

### The integer schema is pinned, and the workbook gets no vote

Semantic type is decided by the **canonical CSV alone**, against a pinned list of
20 declared integer columns (`INTEGER_SCHEMA_COLUMNS`):

`new_event_id`, `event_id`, `v3_type`, `duration_days`, `day_index_in_event`,
`canonical_daily_minpts_used`, `event_global_minpts_max_rounded`,
`event_global_minpts_used`, `dbscan_rounded_minpts`, `day_final_n_clusters`,
`day_n_noise_cells`, `day_n_clustered_cells`, `cluster_id`, `H_component_cells`,
`E_ellipse_cells`, `interH_intersection_cells`, `union_cells`,
`E_ellipse_cells_translated`, `interH_intersection_cells_translated`,
`union_cells_translated`.

All 20 must exist in the CSV, and the CSV must itself satisfy the schema,
reported as `canonical_csv_schema_violations`, measured empty. For those columns
the workbook must be numeric, integral and **exactly equal**; the relative
tolerance of section 5 does not apply to them. The remaining 56 numeric columns
are classified as float from CSV values only.

This matters because the previous rule classified a column as integer only when
*both* sides looked integral. A workbook value of `1.0000000000005` where the CSV
held `1` demoted the whole column to "float", after which its ~5e-13 relative
difference passed comfortably under the 1e-12 float tolerance. The workbook could
therefore edit its own type away. It no longer can: a fractional value in a
declared integer column is now a failure that names the column.

## 5. Floating-point rule and measured differences

**Declared rule.** PASS iff, for every pair of corresponding finite float64
values, the relative difference `|a−b| / max(|a|,|b|)` ≤ **1e-12**.

The rule governs the **56 float columns**. The other 20 of the 76 numeric columns
are the pinned integer schema of section 4 and are held to exact equality.

**Why relative.** The 76 numeric columns span about nine orders of magnitude,
from PCA eigenvector components of order 1e-3 to `ellipse_area_km2` of order
5e6. An absolute tolerance of 1e-12 would demand ~1e-18 relative precision on the
large columns (below float64 resolution) and is not a meaningful criterion.

**Why ULP is a diagnostic, not the criterion.** An Excel round-trip is a decimal
serialisation at fixed significant digits. That bounds the *relative* error, not
the ULP distance: a value just above a binade boundary has small ULP spacing, so
the same relative error costs many ULP.

Measured over 57,760 numeric cells (76 columns × 760 rows):

| Quantity | Value |
|---|---|
| Cells differing under exact `a != b` | 11,670 (20.20 %) |
| Columns with any difference | 55 of 76 |
| Worst absolute difference | 1.862645149230957e-09 |
| Worst relative difference | 3.571463468018517e-14 |
| Worst ULP distance | 255 |

ULP distribution over the 11,670 differing cells:

| ULP | Cells | Share |
|---|---|---|
| 1 | 8,668 | 74.276 % |
| 2 | 2,367 | 20.283 % |
| 3–4 | 497 | 4.259 % |
| 5–64 | 132 | 1.131 % |
| > 64 | 6 | 0.051 % |

The two extremes sit in different columns and neither is near the threshold:

* **Worst relative**: `pc1_vec_x`, value magnitude 7.741127872636276e-04,
  absolute difference 2.7647155398380363e-17, relative 3.571463468018517e-14,
  255 ULP. `pc1_vec_x` and `pc2_vec_y` differ in 195 cells each. These are
  near-zero PCA direction-cosine components: exactly where ULP counting inflates,
  and where the physical content is a unit vector whose direction is unaffected at
  the 14th significant digit.
* **Worst absolute**: `ellipse_area_km2`, value magnitude 4,851,424.382741476,
  absolute difference 1.862645149230957e-09, relative
  **3.839377886332015e-16**, 2 ULP. `ellipse_area_km2` and `area` differ in 288
  cells each.

**Rule outcome: PASS.** Worst relative difference 3.571463468018517e-14 ≤ 1e-12,
a margin factor of **27.99972641340805**. Every string cell, every integer-schema
cell, every row key, the row order, the column set and the column order match
exactly, and the NaN, +Inf and −Inf masks are identical. All observed differences
are a decimal-serialisation round-trip agreeing to at least 13 significant decimal
digits everywhere.

## 6. What a PASS now forbids

Four routes to an undeserved PASS were open when this report was first issued.
Each is now a failure, and each is exercised by an adversarial test in
`tests/test_xlsx_equivalence_guardrails.py`.

| # | Bypass | Why it worked | What happens now |
|---|---|---|---|
| A | Fractional integer | a column counted as integer only if **both** sides looked integral, so `1 → 1.0000000000005` demoted it to float and hid under the 1e-12 float tolerance | type comes from the canonical CSV alone; the workbook must be numeric, integral and exactly equal; `integer_non_integral_columns` names the offender |
| B | Signed infinity | `np.isinf` is sign-blind, so `+inf` against `−inf` produced identical masks | `posinf_mask_identical` and `neginf_mask_identical` are compared **separately**; the verdict follows the signed comparison |
| C | External relationship | only `xl/_rels/workbook.xml.rels` was read, by string-counting, so an external target in any other `.rels` part was invisible | every `.rels` member is enumerated and parsed as XML, and an unparseable part fails **closed** via `relationship_parse_errors` |
| D | Raw pivot content | only openpyxl's object model was consulted | the raw ZIP member list is scanned for `xl/pivotCache/` and `xl/pivotTables/`, case-insensitively |

The sign-blind `inf_mask_identical` field is retained for output compatibility,
but it is no longer what the verdict depends on.

### Honest limitation on bypass B

**The XLSX format cannot carry an infinity.** openpyxl writes `float('inf')` and
pandas reads it back as `NaN`. This is asserted directly by
`test_xlsx_format_cannot_carry_infinity`, which will fail loudly if that ever
changes. The signed-infinity guard is therefore exercised against the real
`compare()` function with the workbook read monkeypatched, rather than end to end
through a subprocess; A, C and D all run end to end through the real program.
That is a property of the file format rather than a softened test, and it is
recorded here instead of being left out.

## 7. Reference disposition: not a bulk rewrite

The five references to the workbook play different roles and receive different
actions:

| File | Kind | Action |
|---|---|---|
| `scripts/pipeline/build_event_global_max_master.py` | generated output | **No change.** It names the workbook it *writes* beneath `SCORCH_OUT_DIR`. Optional XLSX generation is retained. |
| `scripts/pipeline/reclassify_event_types_global_max.py` | generated output | **No change.** Same reproduced-output path. |
| `remediation/corrected/event_global_max_algorithm/build_manifest.json` | historical freeze manifest | **Preserved byte-for-byte.** Records where the artifact was written at build time. |
| `remediation/freeze/freeze_manifest_pre.json` | historical freeze manifest | **Preserved byte-for-byte.** Records the freeze-time hash at the base commit. |
| `remediation/corrected_outputs/SHA256_MANIFEST.json` | current manifest | **Updated, not deleted.** Both byte identities retained; `relocation.files[…xlsx].state = "approved_removal"` with approval, reason and a pointer to this report. |

Readers are unaffected. `scripts/figures/common/_clean_paths.py` binds the master
via `data_file(…, "catalogs")` to the **CSV**, and derives `MASTER_XLSX` only for
API compatibility with scripts offering an Excel fallback;
`scripts/figures/common/common.py::load_workbook` reads Excel only when
`SCORCH_WORKBOOK` explicitly names a workbook. No reader change was required.

Anyone re-verifying the two freeze manifests should hash the **Git blob**, not the
checked-out file. On a Windows checkout their worktree bytes carry CRLF and hash
differently while `git status` correctly reports them unmodified; `git show
HEAD:<path>` reproduces the declared values.

## 8. Removal record

The repository copy was removed under author decision D7. Both byte identities
remain permanently recorded in `remediation/corrected_outputs/SHA256_MANIFEST.json`,
whose own `relocation.validation_rules` require a recorded approval and reason
before absence is legal. The removal is **not** a relocation: the workbook is not a
member of the processed-data archive under a relocation record, so `package` and
`archive_member_path` are `null`.

An equivalent workbook remains available as the deposit member
`catalogs/scorch_new_algorithm_master_cluster_ellipse_event_global_max.xlsx`
(428,600 B, SHA-256 `4ca9ef136ee0a98ada2acc7d3976bc314a4402f8b22af62f818119ba286e6b42`),
byte-identical to the removed repository copy, and the producers still emit an
XLSX under `SCORCH_OUT_DIR` on a reproduction run.

## 9. Corrections to earlier drafts of this report

Superseded by the measurements above.

### From the first measured run

| Earlier claim | Measured |
|---|---|
| "1,359 differing cells across 5 columns; worst relative 6.359e-16; about 2–3 ULP" | 11,670 cells across 55 columns; worst relative 3.571463468018517e-14; worst 255 ULP |
| Worst-absolute cell "5.5e-16 relative, 4 ULP" | **3.839377886332015e-16 relative, 2 ULP**, at magnitude 4,851,424.38. The quoted 5.5e-16 was arithmetically wrong in any case: 1.862645149230957e-09 ÷ 5.37e6 ≈ **3.47e-16** |
| Relative-tolerance margin "~350×" | **27.99972641340805×** (1e-12 ÷ 3.571463468018517e-14) |
| Worst-relative cells' absolute difference "1.110e-16" | 2.7647155398380363e-17 |

### From the hardened comparison program

| Earlier claim | Now |
|---|---|
| "The reproducer checks **19 enumerated properties**" | **23.** Worksheet pivots, raw `pivotCache`/`pivotTables` ZIP parts, XML-parseability of every `.rels` part, and absence of an external relationship in *any* `.rels` part were added |
| External-link cleanliness stated without qualifying the scan | the scan had read **one** `.rels` part; it now enumerates **all** of them. Both parts and all 6 relationships are listed in section 3 |
| "Integer-valued columns: 20", classified from what both files looked like | 20 columns **pinned by schema** and classified from the canonical CSV alone; the workbook cannot demote its own type |
| "Inf mask: identical", a single sign-blind mask | **+Inf and −Inf masks compared separately**; the sign-blind field is retained only for output compatibility |
| Margin factor stated as "28.0" | **27.99972641340805**, as measured |
| Bytes read described as the historical-worktree forms | the recorded run read the **deposit members** (`csv_source`/`xlsx_source` = `deposit`), which are byte-identical to those forms |
| A malformed package produced an unhandled traceback and no JSON | caught and reported as a structured FAIL with `workbook_load_error` / `comparison_ran: false` |

The verdict was unchanged by any of these corrections; only the evidence was, and
in the second group the *strength* of the evidence.
