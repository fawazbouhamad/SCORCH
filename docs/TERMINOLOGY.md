# Terminology: the centroid-concentration model and legacy "risk" names

## Current terminology (matches the final manuscript)

The spatial point-process component of SCORCH is the
**centroid-concentration model**: an inhomogeneous log-Gaussian Cox process
(LGCP) fitted by minimum contrast (spatstat `kppm`, exponential covariance)
to the 760 heat-structure ellipse centroids, with first-order trend
`~ lon + lat + mean_tmax_z + std_tmax_z` (the "variant3" four-variable
model). The mapped surface shows the **relative spatial centroid
concentration**: the quantile rank (0-1, across the 1,800 valid grid cells)
of the fitted first-order intensity.

**Explicit qualification (do not remove):** the fitted surface is a relative
concentration summary of the observed 1940-2025 catalog. It is **not** a
probability, **not** a risk, **not** a hazard, **not** a susceptibility
estimate, and the mapped quantile surface is **not** a realization of the
latent Gaussian field. No occurrence probability for any future period is
implied.

Public-facing prose in this repository and the data deposit uses
"centroid-concentration model" / "relative spatial centroid concentration"
and never describes the surface as a risk, probability, hazard, or
susceptibility product.

## Legacy "risk" names retained for provenance

The model was developed under the working name "spatial risk model", and a
number of FILE and COLUMN names from the original runs contain the token
`risk` (or `spatial_risk`). Renaming these artifacts would break the
recorded provenance chain (checksums, run logs, figure provenance, and the
deposited outputs were produced under these names), so the NAMES are
retained while all descriptive text uses the current terminology.

Legacy names you will encounter, and what they mean now:

| Legacy name | Current meaning |
|---|---|
| `scripts/lgcp/spatial_risk_lgcp_model_diagnostics.R` | The canonical centroid-concentration model fit + diagnostics (R/spatstat) |
| `reproduced/lgcp/model_diagnostics_and_variants/figures/risk_map_*.png` | Diagnostic maps of the predicted centroid concentration (fitted intensity); titles corrected in V5, filenames legacy |
| `validation_kfold/per_centroid_risk_zone_validation.csv` | Out-of-sample distances from held-out centroids to the top-10/20/30/50% *concentration* zones |
| `validation_kfold/risk_zone_summary_by_centroid_type.csv` | Summary of the same by centroid subset |
| `figure_table_source_data/figS03/Figure_S3_risk_zone_distance_stats.csv` | Source data of the (superseded standalone) concentration-zone distance panel, now panel (a) of Fig. D |
| columns `heldout_risk_quantile`, `mean_heldout_risk_quantile`, `max_risk_quantile`, `heldout_mean_risk_quantile` | Held-out centroid *concentration quantile* values (rank of fitted intensity) |
| `scripts/validation/kfold_cv_risk_zone_validation.py` | The occurrence-level five-fold concentration-zone validation (MAIN validation) |
| `scripts/figures/figS3/make_figS3_risk_zone_distance.py` | Internal component producer (superseded standalone figure; see FIGURE_PROVENANCE.csv) |
| `outputs .../spatial_risk_lgcp_tmax_centroids/` (dev-repo run directory recorded in provenance notes) | The original run directory name of the centroid-concentration chain |

"Zone" in these names means a top-X% area of the relative concentration
surface, delimited by quantile rank; "risk quantile" means concentration
quantile. Wherever a legacy name appears, read "risk" as "concentration".

## What the figures actually display (current release, SCORCH v1.0.0; wording finalized in the historical internal pre-release pass "V12")

No displayed label in this release uses risk wording. Docstrings,
generated Markdown reports, plot titles, axis labels, legends and other
user-facing prose use "centroid-concentration", "relative
centroid-concentration rank", "predicted centroid concentration" or
"top-concentration zone". File names, stored column identifiers and the
frozen deposit payload (see the grid-cell section below for the analogous
rule) keep their legacy tokens, for provenance.

V5 correction: through V4, the four LGCP diagnostic maps
(`reproduced/lgcp/model_diagnostics_and_variants/figures/risk_map_*.png`)
still displayed the title "Predicted centroid risk (fitted intensity x
1e6)". In V5 the producing script was corrected to "Predicted centroid
concentration (fitted intensity x 1e6)" and the diagnostics were
re-executed against the deposited `lgcp/` inputs (refit parameter table
and predicted-intensity surface byte-identical to the deposit; 0 fit
warnings). The legacy `risk_map_*.png` FILENAMES are retained, as
documented in the table above.

| Figure | Displayed labels |
|---|---|
| Figure 12 | Colorbar: "Relative centroid-concentration rank, R(s)". Marker legend: "Centroid", "Daily-largest structure centroid", "Event-largest structure centroid" ("largest" = ellipse-summary area in km^2). |
| Fig. D (Appendix D of the main manuscript) | Colorbar: "Relative centroid-concentration rank, R(s)". Marker legend: "Daily-largest structure centroid", "Event-largest structure centroid". Panel (a) y-axis: "Distance to nearest top-concentration zone (km)". |
| Fig. D internal component producers (legacy internal names figS3, figS4) | Same concentration wording; these are components, not manuscript figures. |

Figure 12 and the composite now designated Fig. D were regenerated
with the marker-legend wording above. Both corrected assets were DEPLOYED
into the WORKING manuscript on 2026-07-30 in the advisor-directed G2 pass
(historical G2 embeds `6a1a5a76...` and `b7c48232...`, superseded), and the
shipped producers now reproduce the current corrected-manuscript embeds
byte-identically (Fig. 12 `ce09ab2f...`, Fig. D `88f9e177...`). Neither is
pending, provisional or awaiting a further pass.

## Legacy "box" names: grid-cell terminology

Current prose describes the 1-degree analysis units as **grid cells**
("the 1,800 valid grid cells"). Displayed figure labels use grid-cell
wording; V7 corrected the last two displayed labels (Figure 2 panel (b)
axes, now "Fraction of Domain Grid Cells with Heatwave Label" /
"Heatwave-Labeled Fraction of Tmax-Exceedance Grid Cells"). That corrected
Figure 2 was DEPLOYED into the WORKING manuscript on 2026-07-30 in the
advisor-directed G2 pass, and the regenerated output is byte-identical to
the deployed embed `62c20697...`. It is not pending any further pass.

Unavoidable legacy `box` tokens, frozen for provenance (renaming would
break checksums, schemas and the immutable deposit payload):

| Legacy token | Where it is frozen |
|---|---|
| `fig02_box_p95.csv` | Deposit file name (gridded/) |
| `lgcp/tmax_covariate_grid_all_boxes.csv` | Deposit file name |
| `box_agg` | Reconstruction-configuration key (schema-level) |
| stored column names containing `box` | Deposit table schemas |
| immutable payload text (e.g. `thresholds_and_labels_note.md`) | Frozen by the scientific-payload manifest |
| console-only diagnostic prints (e.g. fig02's "371 boxes" line) | Legacy console wording, quoted as such in REPRODUCIBILITY_MATRIX.csv; persistent generated documents use grid-cell wording |
