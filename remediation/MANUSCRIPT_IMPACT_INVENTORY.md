# Manuscript Impact Inventory — Tmax-Weighted Centroid Remediation

Canonical manuscript: `SCORCH_Manuscript_FINAL_v1.0.0(1).docx`
SHA-256 `9e140b9ea8927ae3b69c4e50afb8301006e8802dcf3e601f1c80c511ca3ca2e3` — **NOT edited by this remediation.**
Every item below cites corrected evidence produced in this remediation
(`remediation/` artifacts); replacement wording is cautious draft text for
the author, not applied text. Section 2 and Appendix A are untouched.

Qualitative-change column: "numeric" = same conclusion, updated numbers;
"qualitative" = statement itself changes.

| # | Locator | Why affected | Corrected evidence | Cautious replacement wording | Change |
|---|---|---|---|---|---|
| 1 | Abstract — any sentence describing structure locations / hotspot corridor / validation strength | Locations now Tmax-weighted | LGCP + CV tables (report §19, §21) | Keep the corridor description; update any quoted hit rate (0.33→0.34) or distance (286→232 km mean) if quoted | numeric |
| 2 | Methods, centroid definition equation | The published equation must state the weighting actually applied | Report §5 | "Each structure's reported centroid is the Tmax-weighted mean of its member-cell centres, \(w_i = T_{\max,i}\) with \(T_{\max,i}\) in °C (observed daily values). The PCA ellipse is fitted unweighted and rigidly translated to this centroid." **Must NOT read \(w_i=\max\{T_{\max,i},0\}\)**; remove any instruction to silently exclude invalid values — canonical inputs are validated and invalid values stop the pipeline | qualitative (methods description) |
| 3 | Methods — new required statements | Stage separation must be explicit | Report §5–§10 | State: clustering unweighted; Appendix A and σ=1.25 selected upstream and unchanged; PCA geometry unweighted; weighting applied only after the completed ellipse; rigid translation; dimensions/orientation unchanged | qualitative (methods description) |
| 4 | Results §4.x — Figure 3 caption/text (footprint maxima, spatial description) | Footprint recomputed at translated ellipses | `remediation/audit/fig3_footprint_before_after.json` | Max overlap 279 footprints at (43.5°E, 30.5°N) [was 280 at (41.5°E, 31.5°N)]; keep "PCA-ellipse footprints per grid cell" | numeric |
| 5 | Results — Figures 5/6/7 captions | Markers/ellipses moved (dates, events, cells, style preserved; Fig 6 dates 2017-07-17/18 and 1991-06-04/05 unchanged) | regenerated figures | Add "ellipse positions shown at Tmax-weighted centroids" if captions describe centroids | numeric |
| 6 | Results — LGCP coefficients (variant3) | Refit on weighted centroids | report §19 | intercept −11.457776; lon −0.016147; lat 0.066264; mean-Tmax 0.546415; std-Tmax −0.010951; σ²_G 1.642911; scale ≈272.46 km; intensity ratio ≈21.8 | numeric |
| 7 | Results — hotspot / geographic interpretation | Surface refit | report §19 | Same corridor (NE Tigris–Euphrates lowlands); hotspot cell (45.5°E, 32.5°N); mean-Tmax dominance strengthened | numeric (interpretation unchanged) |
| 8 | Results — sector counts (38–48°E, 29–37°N) | Locations moved | report §20 | 154/760 structures, 153/395 daily-largest, 19/51 event-largest; window remains post hoc and descriptive | numeric |
| 9 | Results / Appendix D — cross-validation values | Full 5-fold refit (seed 20260704, identical folds) | report §21 | top-20% hit 0.3447; mean/median distance to top-20% zone 231.8/134.9 km; area-weighted rank mean/median 0.644/0.680; keep occurrence-level framing | numeric |
| 10 | Appendix D figure(s) (fold maps / Figure S4 family) | Regenerated | `remediation/corrected_outputs/figures/Figure_S4_kfold_heldout_maps.png` | Update panel values only | numeric |
| 11 | Figure 12 caption/text (marker positions, numeric descriptions) | Surface + markers regenerated | corrected fig12 + variant3 surface | Update quoted intensity range/ratio and any coordinates; daily-/event-largest identities unchanged | numeric |
| 12 | Conclusions — any quoted centroid-based number | Derived from items 6–9 | same | Update numbers; conclusions qualitatively unchanged | numeric |
| 13 | Reproducibility/data-availability text | New catalog columns + weighting metadata | `DATA_DICTIONARY.csv` additions; `build_manifest.json` `tmax_weighted_centroids` block; `CANONICAL_SCIENCE.json` new sections | Describe explicit weighted/unweighted fields and the validation policy | qualitative (documentation) |
| 14 | Any statement that centroids are "cluster means" | No longer the reported quantity | report §5 | Reported locations are Tmax-weighted centroids; unweighted PCA origins preserved as `*_unweighted` | qualitative (description) |

Not affected (do not touch): Section 2; Appendix A (figure, tables,
caption, σ=1.25 selection); Table 1; durations/trends; Figures 1, 2, 4, 8,
9, 10, 11; area-tail statistics; station validation; event typology.
