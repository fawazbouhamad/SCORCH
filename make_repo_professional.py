from pathlib import Path

ROOT = Path.cwd()

folders = [
    "data",
    "outputs/figures",
    "outputs/tables",
    "docs",
]

files = {
    ".gitignore": """# Python
__pycache__/
*.py[cod]
.ipynb_checkpoints/

# Virtual environments
.venv/
venv/
env/

# Large climate/geospatial data
data/*
!data/README.md
*.nc
*.grib
*.grb
*.h5
*.hdf
*.tif
*.tiff
*.zip
*.7z

# Outputs
outputs/*
!outputs/README.md
!outputs/figures/
!outputs/tables/

# OS / editor
.DS_Store
Thumbs.db
.vscode/
.idea/

# OneDrive temporary files
~$*
*.tmp
""",

    "requirements.txt": """numpy
pandas
xarray
scipy
matplotlib
cartopy
shapely
scikit-learn
pymannkendall
netCDF4
cdsapi
""",

    "LICENSE": """MIT License

Copyright (c) 2026 Fawaz Bouhamad

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
""",

    "CITATION.cff": """cff-version: 1.2.0
message: "If you use this repository, please cite it as below."
title: "SCORCH: Spatial Characterization of Heatwaves"
authors:
  - family-names: "Bouhamad"
    given-names: "Fawaz"
year: 2026
version: "1.0.0"
repository-code: "https://github.com/fawazbouhamad/SCORCH"
""",

    "data/README.md": """# Data

This folder is reserved for input datasets.

Large raw climate datasets are not stored directly in this GitHub repository.

Expected data sources may include:

- ERA5 reanalysis data
- Daily maximum temperature fields
- Binary heatwave exceedance grids
- Intermediate heatwave event catalogues

Users should download or prepare the required datasets separately before running the workflow.
""",

    "outputs/README.md": """# Outputs

This folder is reserved for generated outputs.

Generated figures, tables, maps, and intermediate results are not tracked by Git by default.

Recommended output folders:

- `outputs/figures/`
- `outputs/tables/`
""",

    "docs/methodology.md": """# Methodology

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
""",
}

for folder in folders:
    (ROOT / folder).mkdir(parents=True, exist_ok=True)

for relative_path, content in files.items():
    path = ROOT / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

print("=" * 70)
print("SCORCH repository professional setup complete.")
print("=" * 70)
print("Created or updated:")
for folder in folders:
    print(f"Folder: {folder}")
for file_path in files:
    print(f"File: {file_path}")

print("\nNext Git commands:")
print("git add .")
print('git commit -m "Add professional repository files"')
print("git push")