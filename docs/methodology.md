# Methodology

SCORCH is a Python-based workflow for detecting, classifying, and spatially characterizing heatwave events.

## Main steps

1. Download and preprocess ERA5 temperature data.
2. Apply percentile-based heatwave exceedance detection.
3. Identify connected heatwave objects.
4. Use PCA-based ellipse fitting for spatial characterization.
5. Classify heatwave typologies.
6. Generate statistical summaries, figures, and tables.

## Repository structure

- `scripts/main_workflow/` contains the main processing pipeline.
- `scripts/figures/` contains figure-generation scripts.
- `scripts/tables/` contains table-generation scripts.
- `data/` is reserved for input data.
- `outputs/` is reserved for generated results.
