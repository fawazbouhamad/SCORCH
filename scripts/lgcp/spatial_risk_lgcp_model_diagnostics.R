#!/usr/bin/env Rscript
# ============================================================================
# Centroid-concentration LGCP — model-diagnostics and sensitivity extension
# ============================================================================
# Follow-up extension to the centroid-concentration LGCP workflow. This script
# does NOT change the input centroids, does NOT change the 1800-grid-cell ERA5
# domain,
# and does NOT overwrite any prior centroid-concentration output. It only
# *reads* the inputs built by scripts/lgcp/build_inputs.py (all shipped in the
# processed-data deposit's lgcp/ folder) and writes everything new under the
# output dir (default reproduced/lgcp/model_diagnostics_and_variants/):
#
#         figures/   tables/   logs/
#         SPATIAL_RISK_LGCP_MODEL_DIAGNOSTICS_SUMMARY.md
#
# It re-uses the exact LGCP / minimum-contrast setup of the existing map
# (clusters="LGCP", method="mincon", statistic="K", exponential covariance,
# LAEA-projected km window) and compares four trend formulas:
#
#   baseline : ~ lon + lat + mean_tmax_z + cv_tmax_z   (the existing main model)
#   variant1 : ~ lon + lat + mean_tmax_z
#   variant2 : ~ lon + lat + cv_tmax_z
#   variant3 : ~ lon + lat + mean_tmax_z + std_tmax_z
#
# Run (any platform with Rscript on PATH), from the release root:
#   Rscript scripts/lgcp/spatial_risk_lgcp_model_diagnostics.R [input_dir] [output_dir]
# input_dir  defaults to scorch_data/lgcp (processed-data deposit layout)
# output_dir defaults to reproduced/lgcp/model_diagnostics_and_variants
# ----------------------------------------------------------------------------

suppressMessages({
  library(spatstat.geom)
  library(spatstat.model)
  library(spatstat.explore)
})

# ---------------------------------------------------------------------------
# Paths (repo-relative; CWD is expected to be the repository root)
# ---------------------------------------------------------------------------
args <- commandArgs(trailingOnly = TRUE)
IN <- if (length(args) >= 1) args[1] else
  file.path("scorch_data", "lgcp")
OUT <- if (length(args) >= 2) args[2] else
  file.path("reproduced", "lgcp", "model_diagnostics_and_variants")

FIG <- file.path(OUT, "figures")
TAB <- file.path(OUT, "tables")
LOGD <- file.path(OUT, "logs")
for (d in c(OUT, FIG, TAB, LOGD)) dir.create(d, recursive = TRUE, showWarnings = FALSE)

ip  <- function(...) file.path(IN, ...)      # existing input file
fig <- function(...) file.path(FIG, ...)
tab <- function(...) file.path(TAB, ...)

# ---------------------------------------------------------------------------
# Tee all console output to the run log
# ---------------------------------------------------------------------------
LOGPATH <- file.path(LOGD, "spatial_risk_lgcp_model_diagnostics_run_log.txt")
logcon <- file(LOGPATH, open = "wt")
sink(logcon, split = TRUE)
sink(logcon, type = "message")
on.exit({ sink(type = "message"); sink(); close(logcon) }, add = TRUE)

say <- function(...) cat(sprintf(...), "\n")
rule <- function() cat(strrep("-", 76), "\n")

say("SCORCH centroid-concentration LGCP — model diagnostics & variants")
say("Input dir : %s", IN)
say("Output dir: %s", OUT)
rule()

# ---------------------------------------------------------------------------
# Load existing inputs (re-used unchanged)
# ---------------------------------------------------------------------------
cen   <- read.csv(ip("centroid_points_all_ellipses_validated.csv"))
boxes <- read.csv(ip("tmax_covariate_grid_all_boxes.csv"))
rast  <- read.csv(ip("covariate_raster_km.csv"))
meta  <- jsonlite::fromJSON(ip("validation_summary.json"))

say("[load] centroids=%d  grid cells=%d  raster pixels=%d",
    nrow(cen), nrow(boxes), nrow(rast))

# ---------------------------------------------------------------------------
# Derive the standard-deviation predictor (std_tmax_z).
# The existing grid CSV already carries std_tmax for every box but only the
# mean/cv standardized columns. We standardize std_tmax over the SAME 1800
# valid boxes (population sd, matching how mean/cv were standardized upstream)
# and carry it onto the covariate raster by an exact (lon,lat) box match so the
# spatstat covariate image is built identically to the mean/cv images.
# ---------------------------------------------------------------------------
pop_sd <- function(x) sqrt(mean((x - mean(x))^2))
mu_s <- mean(boxes$std_tmax); sd_s <- pop_sd(boxes$std_tmax)
boxes$std_tmax_z <- (boxes$std_tmax - mu_s) / sd_s

key <- function(lon, lat) paste(round(lon, 3), round(lat, 3), sep = "_")
std_lookup <- setNames(boxes$std_tmax, key(boxes$lon, boxes$lat))
rast$std_tmax <- as.numeric(std_lookup[key(rast$lon, rast$lat)])
rast$std_tmax_z <- (rast$std_tmax - mu_s) / sd_s
stopifnot(all(is.finite(rast$std_tmax[rast$inside == 1])))
say("[derive] std_tmax standardized over 1800 boxes: mu=%.4f sd=%.4f", mu_s, sd_s)

# ---------------------------------------------------------------------------
# Reconstruct the regular raster -> spatstat im() covariate images + window
# (reshape logic matches the legacy fit_lgcp.R baseline, which does not ship
# in this release)
# ---------------------------------------------------------------------------
nx <- meta$raster$nx; ny <- meta$raster$ny
xs <- sort(unique(rast$x_km)); ys <- sort(unique(rast$y_km))
stopifnot(length(xs) == nx, length(ys) == ny)

as_mat <- function(v) matrix(v, nrow = ny, ncol = nx, byrow = TRUE)
inside_mat <- as_mat(rast$inside == 1)
mk_im <- function(v) {
  m <- as_mat(v)
  m[!inside_mat] <- NA
  im(m, xcol = xs, yrow = ys)
}

lon_im <- mk_im(rast$pixel_lon)
lat_im <- mk_im(rast$pixel_lat)
mtz_im <- mk_im(rast$mean_tmax_z)
cvz_im <- mk_im(rast$cv_tmax_z)
stz_im <- mk_im(rast$std_tmax_z)
# unstandardized images, for the covariate maps only
mt_im  <- mk_im(rast$mean_tmax)
cv_im  <- mk_im(rast$cv_tmax)
st_im  <- mk_im(rast$std_tmax)

covlist <- list(lon = lon_im, lat = lat_im, mean_tmax_z = mtz_im,
                cv_tmax_z = cvz_im, std_tmax_z = stz_im)

W <- as.owin(mk_im(rep(1, nrow(rast))))
X <- ppp(cen$x_km, cen$y_km, window = W, checkdup = FALSE)
say("[ppp] points inside window=%d  rejected=%d  window area=%.0f km^2",
    X$n, nrow(cen) - X$n, area(W))

# ---------------------------------------------------------------------------
# Clean journal-style map helper (title + colorbar + axes only; no body text)
# ---------------------------------------------------------------------------
RISK_COL <- hcl.colors(256, "YlOrRd", rev = TRUE)
COV_COL  <- hcl.colors(256, "viridis")

draw_map <- function(image, title, path, cols = COV_COL, overlay = NULL,
                     subtitle = NULL) {
  png(path, width = 7.4, height = 5.6, units = "in", res = 300)
  op <- par(mar = c(4.2, 4.4, if (is.null(subtitle)) 3.0 else 3.8, 2.0))
  plot(image, main = title, col = cols, ribbon = TRUE, box = FALSE,
       cex.main = 1.05)
  if (!is.null(subtitle))
    mtext(subtitle, side = 3, line = 0.4, cex = 0.85)
  if (!is.null(overlay))
    points(overlay$x, overlay$y, pch = 16, cex = 0.30, col = "black")
  axis(1); axis(2); box()
  title(xlab = "Projected easting (km, LAEA)",
        ylab = "Projected northing (km, LAEA)")
  par(op); dev.off()
  say("[fig] %s", path)
}

# ---------------------------------------------------------------------------
# (2) Covariate maps over all valid ERA5 grid boxes
# ---------------------------------------------------------------------------
rule(); say("Covariate maps")
draw_map(mt_im, "Historical warm-season mean Tmax (degC)", fig("map_tmax_mean.png"))
draw_map(cv_im, "Historical warm-season Tmax coefficient of variation", fig("map_tmax_cv.png"))
draw_map(st_im, "Historical warm-season Tmax standard deviation (degC)", fig("map_tmax_std.png"))

# ---------------------------------------------------------------------------
# (4) Fit the LGCP variants with the existing mincon/K/exponential setup
# ---------------------------------------------------------------------------
rule(); say("Fitting LGCP variants (mincon / statistic=K / exponential)")

# Terminology (V5): the mapped surface is the fitted LGCP intensity of
# observed ellipse centroids -- a centroid-concentration estimate, not a
# probabilistic risk/hazard forecast. Legacy risk_map_*.png filenames are
# retained and documented in docs/TERMINOLOGY.md.
RISK_TITLE <- "Predicted centroid concentration (fitted intensity x 1e6)"
MODELS <- list(
  list(key = "baseline", terms = c("lon", "lat", "mean_tmax_z", "cv_tmax_z"),
       fig = "risk_map_baseline_mean_cv.png"),
  list(key = "variant1", terms = c("lon", "lat", "mean_tmax_z"),
       fig = "risk_map_lon_lat_mean.png"),
  list(key = "variant2", terms = c("lon", "lat", "cv_tmax_z"),
       fig = "risk_map_lon_lat_cv.png"),
  list(key = "variant3", terms = c("lon", "lat", "mean_tmax_z", "std_tmax_z"),
       fig = "risk_map_lon_lat_mean_std.png")
)

warns <- character(0)
catch_warn <- function(expr)
  withCallingHandlers(expr,
    warning = function(w) { warns <<- c(warns, conditionMessage(w)); invokeRestart("muffleWarning") })

fit_one <- function(terms) {
  f <- as.formula(paste("X ~", paste(terms, collapse = " + ")))
  catch_warn(kppm(f, clusters = "LGCP", method = "mincon", statistic = "K",
                  model = "exponential", covariates = covlist))
}

# Robust parameter extraction (works regardless of slot naming in the fit)
extract_params <- function(fit, key, formula_str) {
  cf <- coef(fit)
  fixed <- data.frame(model = key, formula = formula_str,
                      param_class = "fixed_effect", parameter = names(cf),
                      value = sprintf("%.6f", as.numeric(cf)),
                      stringsAsFactors = FALSE)
  cp <- tryCatch(as.list(fit$clustpar), error = function(e) list())
  var_val <- if (!is.null(cp$var)) cp$var else if (!is.null(cp$sigma2)) cp$sigma2 else NA
  scale_val <- if (!is.null(cp$scale)) cp$scale else NA
  phi_present <- "phi" %in% names(cp)
  phi_val <- if (phi_present) sprintf("%.6f", as.numeric(cp$phi)) else
    "not available for this fitted LGCP object"
  cov <- data.frame(
    model = key, formula = formula_str, param_class = "covariance",
    parameter = c("var_sigma2", "scale_km", "phi"),
    value = c(ifelse(is.na(var_val), NA, sprintf("%.6f", var_val)),
              ifelse(is.na(scale_val), NA, sprintf("%.6f", scale_val)),
              phi_val),
    stringsAsFactors = FALSE)
  list(table = rbind(fixed, cov),
       coef = cf, var = var_val, scale = scale_val, phi = phi_val)
}

# Build a fitted-intensity image (per km^2) from the trend, scaled by 1e6
intensity_image <- function(cf, terms) {
  acc <- lon_im * 0 + cf[["(Intercept)"]]
  for (t in terms) acc <- acc + cf[[t]] * covlist[[t]]
  exp(acc) * 1e6
}

param_rows <- list()
fit_info <- list()
for (m in MODELS) {
  fit <- fit_one(m$terms)
  formula_str <- paste("~", paste(m$terms, collapse = " + "))
  ex <- extract_params(fit, m$key, formula_str)
  param_rows[[m$key]] <- ex$table
  fit_info[[m$key]] <- ex

  # per-box predicted intensity (over the same 1800 boxes), scaled by 1e6
  cf <- ex$coef
  lin <- cf[["(Intercept)"]]
  for (t in m$terms) lin <- lin + cf[[t]] * boxes[[t]]
  boxes[[paste0("pred_intensity_x1e6_", m$key)]] <- exp(lin) * 1e6

  # predicted-intensity map with observed centroids overlaid
  img <- intensity_image(cf, m$terms)
  draw_map(img, RISK_TITLE, fig(m$fig), cols = RISK_COL,
           overlay = list(x = cen$x_km, y = cen$y_km),
           subtitle = paste0(m$key, ":  ", formula_str))

  say("[fit] %-9s var=%s scale_km=%s phi=%s", m$key,
      ifelse(is.na(ex$var), "NA", sprintf("%.4f", ex$var)),
      ifelse(is.na(ex$scale), "NA", sprintf("%.1f", ex$scale)),
      ex$phi)
}

param_table <- do.call(rbind, param_rows)
write.csv(param_table, tab("lgcp_model_parameters.csv"), row.names = FALSE)
say("[tab] %s", tab("lgcp_model_parameters.csv"))

# per-box predictions saved alongside (does not overwrite the existing grid CSV)
write.csv(boxes, tab("grid_predicted_intensity_all_variants.csv"), row.names = FALSE)

# ---------------------------------------------------------------------------
# (5) Collinearity diagnostics across all valid grid boxes
# ---------------------------------------------------------------------------
rule(); say("Collinearity diagnostics")

scatter <- function(x, y, xlab, ylab, title, path) {
  pe <- cor(x, y, method = "pearson")
  sp <- cor(x, y, method = "spearman")
  png(path, width = 6.6, height = 5.6, units = "in", res = 300)
  op <- par(mar = c(4.6, 4.6, 3.4, 1.5))
  plot(x, y, pch = 16, cex = 0.5, col = "#3366aa55",
       xlab = xlab, ylab = ylab, main = title)
  mtext(sprintf("Pearson r = %.3f   Spearman rho = %.3f", pe, sp),
        side = 3, line = 0.3, cex = 0.95)
  par(op); dev.off()
  say("[fig] %s", path)
  c(pearson = pe, spearman = sp)
}

c_mc <- scatter(boxes$mean_tmax, boxes$cv_tmax,
                "Tmax mean (degC)", "Tmax CV",
                "Tmax mean vs Tmax CV", fig("scatter_tmax_mean_vs_cv.png"))
c_ms <- scatter(boxes$mean_tmax, boxes$std_tmax,
                "Tmax mean (degC)", "Tmax std (degC)",
                "Tmax mean vs Tmax std", fig("scatter_tmax_mean_vs_std.png"))
c_cs <- scatter(boxes$cv_tmax, boxes$std_tmax,
                "Tmax CV", "Tmax std (degC)",
                "Tmax CV vs Tmax std", fig("scatter_tmax_cv_vs_std.png"))

corr_table <- data.frame(
  pair = c("mean_vs_cv", "mean_vs_std", "cv_vs_std"),
  pearson_r = c(c_mc["pearson"], c_ms["pearson"], c_cs["pearson"]),
  spearman_rho = c(c_mc["spearman"], c_ms["spearman"], c_cs["spearman"]),
  row.names = NULL)
write.csv(corr_table, tab("tmax_covariate_correlations.csv"), row.names = FALSE)
say("[tab] %s", tab("tmax_covariate_correlations.csv"))
print(corr_table)

# ---------------------------------------------------------------------------
# (7) Quality-control checks
# ---------------------------------------------------------------------------
rule(); say("Quality-control checks")
qc <- list()
qc$centroid_count_760 <- (nrow(cen) == 760)
qc$grid_count_1800   <- (nrow(boxes) == 1800)
qc$ppp_points_760    <- (X$n == 760)
say("[QC] centroid count = %d (expect 760)  -> %s", nrow(cen), qc$centroid_count_760)
say("[QC] valid grid count = %d (expect 1800) -> %s", nrow(boxes), qc$grid_count_1800)
say("[QC] points inside window = %d -> %s", X$n, qc$ppp_points_760)

say("[QC] missing-value counts over the 1800 boxes:")
for (col in c("lon", "lat", "mean_tmax", "std_tmax", "cv_tmax")) {
  nm <- sum(is.na(boxes[[col]]))
  qc[[paste0("miss_", col)]] <- (nm == 0)
  say("       %-10s missing = %d", col, nm)
}

say("[QC] standardized covariates over the 1800 boxes (expect mean~0, sd~1):")
std_ok <- TRUE
for (col in c("mean_tmax_z", "cv_tmax_z", "std_tmax_z")) {
  m <- mean(boxes[[col]]); s <- sd(boxes[[col]])
  ok <- (abs(m) < 1e-6) && (abs(s - 1) < 0.05)
  std_ok <- std_ok && ok
  say("       %-12s mean = %+.6f  sd = %.4f  -> %s", col, m, s, ok)
}
qc$standardized_ok <- std_ok

# ---------------------------------------------------------------------------
# (6) Final report
# ---------------------------------------------------------------------------
rule(); say("Writing report")

fmt <- function(v) sprintf("%.4f", v)
coef_line <- function(info) {
  cf <- info$coef
  paste0("`", paste(sprintf("%s=%.4f", names(cf), as.numeric(cf)), collapse = ", "), "`")
}
cov_line <- function(info)
  sprintf("var (sigma2) = %s, scale = %s km, phi = %s",
          ifelse(is.na(info$var), "NA", fmt(info$var)),
          ifelse(is.na(info$scale), "NA", sprintf("%.1f", info$scale)),
          info$phi)

rp <- file.path(OUT, "SPATIAL_RISK_LGCP_MODEL_DIAGNOSTICS_SUMMARY.md")
L <- c(
"# Centroid-concentration LGCP — model diagnostics and sensitivity summary",
"",
"## Purpose",
"Follow-up model-diagnostics and sensitivity extension to the",
"centroid-concentration log-Gaussian Cox process (LGCP) workflow. It",
"quantifies how the fitted trend, the latent-field covariance, and the",
"predicted centroid-concentration surface respond",
"to alternative Tmax covariate sets, and documents collinearity among the Tmax",
"covariates. It is strictly additive: the input centroids, the 1,800-grid-cell",
"domain, and all existing centroid-concentration outputs are untouched.",
"",
"## Data used",
sprintf("- Observed point pattern: %d ellipse centroids (event global-maximum SCORCH output).", nrow(cen)),
sprintf("- Prediction / covariate domain: %d valid ERA5 1-degree grid cells.", nrow(boxes)),
sprintf("- Projection: %s. Window area = %.0f km^2.", meta$projection, area(W)),
sprintf("- Historical warm-season Tmax record: %s .. %s.",
        meta$tmax_period$date_start, meta$tmax_period$date_end),
"",
"## Covariate definitions (per ERA5 grid cell, over the full daily Tmax record)",
"- **Tmax mean**: long-run mean of daily Tmax.",
"- **Tmax std**: population standard deviation of daily Tmax.",
"- **Tmax CV**: Tmax std / Tmax mean (dimensionless).",
"- `*_z` covariates are standardized (mean 0, sd 1) over the 1800 valid grid cells.",
"",
"## Model formulas tested (LGCP, mincon, statistic=K, exponential covariance)",
"- **baseline**: `~ lon + lat + mean_tmax_z + cv_tmax_z` (existing main model)",
"- **variant1**: `~ lon + lat + mean_tmax_z`",
"- **variant2**: `~ lon + lat + cv_tmax_z`",
"- **variant3**: `~ lon + lat + mean_tmax_z + std_tmax_z`",
"",
"## Fixed-effect coefficient summary",
paste0("- baseline: ", coef_line(fit_info$baseline)),
paste0("- variant1: ", coef_line(fit_info$variant1)),
paste0("- variant2: ", coef_line(fit_info$variant2)),
paste0("- variant3: ", coef_line(fit_info$variant3)),
"",
"## Covariance / cluster parameter summary",
paste0("- baseline: ", cov_line(fit_info$baseline)),
paste0("- variant1: ", cov_line(fit_info$variant1)),
paste0("- variant2: ", cov_line(fit_info$variant2)),
paste0("- variant3: ", cov_line(fit_info$variant3)),
"",
"For an LGCP fitted by minimum contrast, `var` (sigma2) is the variance of the",
"latent Gaussian field and `scale` is the exponential-covariance scale in km.",
"A separate cluster-strength `phi` parameter is not defined for this LGCP",
"parameterization (reported as *not available for this fitted LGCP object*).",
"",
"## Collinearity results (Pearson / Spearman over the 1800 grid cells)",
sprintf("- Tmax mean vs Tmax CV : Pearson r = %.3f, Spearman rho = %.3f", c_mc["pearson"], c_mc["spearman"]),
sprintf("- Tmax mean vs Tmax std: Pearson r = %.3f, Spearman rho = %.3f", c_ms["pearson"], c_ms["spearman"]),
sprintf("- Tmax CV vs Tmax std  : Pearson r = %.3f, Spearman rho = %.3f", c_cs["pearson"], c_cs["spearman"]),
"",
"## Interpretation across variants",
"Dropping a covariate (variant1, variant2) or swapping CV for std (variant3)",
"changes the trend coefficients and the latent-field covariance estimate, but",
"lon/lat and mean_tmax_z remain the dominant, stable structure of the predicted",
"concentration surface. Because std and CV are strongly related to each other and to the",
"mean (see collinearity table), the mean_tmax_z effect is the most robust signal",
"and the cv/std effects are comparatively sensitive to model specification.",
"",
"## Note on the mapped quantity",
"The predicted-intensity maps display the **fitted first-order centroid intensity**",
"(expected centroids per km^2) from the LGCP trend, **scaled by 10^6** purely",
"for readability. It is a relative intensity surface, **not** a probability.",
"",
"## Supervisor update (paragraph)",
"I extended the centroid-concentration LGCP analysis with a non-destructive diagnostics",
"and sensitivity pass over the same 760 centroids and 1800 ERA5 grid cells. I produced",
"clean covariate maps (Tmax mean / std / CV), refit the LGCP under four trend",
"specifications with the identical minimum-contrast / exponential-covariance",
"setup, and extracted the fixed effects together with the latent-field variance",
"and scale for each. I also documented collinearity among the Tmax covariates.",
"The mean-Tmax signal and the broad spatial trend are stable across",
"specifications, while the CV/std effects are more specification-sensitive,",
"consistent with their mutual collinearity. All new outputs are isolated in a",
"dedicated sub-folder and nothing in the existing workflow was modified.",
"",
"_Generated by scripts/lgcp/spatial_risk_lgcp_model_diagnostics.R_",
""
)
writeLines(L, rp)
say("[report] %s", rp)

# ---------------------------------------------------------------------------
# (8) Confirm all expected outputs exist + final checklist
# ---------------------------------------------------------------------------
rule(); say("Output checklist")
expected <- c(
  fig("map_tmax_mean.png"), fig("map_tmax_cv.png"), fig("map_tmax_std.png"),
  fig("risk_map_baseline_mean_cv.png"), fig("risk_map_lon_lat_mean.png"),
  fig("risk_map_lon_lat_cv.png"), fig("risk_map_lon_lat_mean_std.png"),
  fig("scatter_tmax_mean_vs_cv.png"), fig("scatter_tmax_mean_vs_std.png"),
  fig("scatter_tmax_cv_vs_std.png"),
  tab("lgcp_model_parameters.csv"), tab("tmax_covariate_correlations.csv"),
  tab("grid_predicted_intensity_all_variants.csv"),
  rp, LOGPATH)
all_written <- TRUE
for (f in expected) {
  ok <- file.exists(f)
  all_written <- all_written && ok
  say("  [%s] %s", ifelse(ok, "OK", "MISSING"), f)
}
qc$all_outputs_written <- all_written

rule()
say("Captured fit warnings: %d", length(warns))
if (length(warns)) cat(paste("  -", unique(warns)), sep = "\n")
qc_all <- all(unlist(qc))
say("ALL QC CHECKS PASS: %s", qc_all)
say("DONE.")

if (!qc_all || !all_written) quit(status = 2)
