from pathlib import Path

ROOT = Path.cwd()

folders = [
    "scripts/main_workflow",
    "scripts/figures",
    "scripts/tables",
    "outputs/figures/main_manuscript",
    "outputs/figures/supplementary",
    "outputs/tables/main_manuscript",
    "outputs/tables/supplementary",
    "docs",
    "data",
]

for folder in folders:
    (ROOT / folder).mkdir(parents=True, exist_ok=True)

files = {}

files["README.md"] = """# SCORCH

**Spatial Characterization of Heatwaves**

SCORCH is a Python-based research workflow for detecting, classifying,
and spatially characterizing heatwave events across the Eastern
Mediterranean and Middle East region.

## Workflow

ERA5 Data Download and Processing
        ↓
Binary Exceedance and Heatwave Detection
        ↓
PCA Spatial Characterization
        ↓
Statistics and Trend Analysis
        ↓
Figures and Tables
"""

for filename, content in files.items():
    (ROOT / filename).write_text(content, encoding="utf-8")

print("SCORCH repository structure created successfully.")