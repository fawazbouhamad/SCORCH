# SCORCH

**Spatial Characterization of Heatwaves**

SCORCH is a Python-based research workflow for detecting, classifying, and spatially characterizing heatwave events using gridded climate datasets.

The framework was developed to investigate the spatial evolution of heatwaves across the Eastern Mediterranean and Middle East region using ERA5 reanalysis data, percentile-based exceedance detection, connected-component analysis, Principal Component Analysis (PCA) ellipse fitting, and statistical trend analysis.

---

## Overview

Heatwaves are among the most impactful climate extremes, affecting human health, infrastructure, ecosystems, and energy systems. Traditional heatwave studies often focus on temporal characteristics such as frequency, duration, and intensity. SCORCH extends this approach by quantifying the spatial geometry and evolution of heatwave events.

The workflow enables researchers to:

* Detect heatwave exceedance events from gridded temperature datasets
* Identify contiguous heatwave objects using connected-component analysis
* Characterize heatwave geometry using PCA-derived ellipses
* Classify events into compound spatial–temporal typologies
* Quantify long-term trends in event frequency and duration
* Generate publication-quality figures and summary tables

---

## Workflow

```text
ERA5 Temperature Data
          ↓
Percentile-Based Exceedance Detection
          ↓
Binary Heatwave Identification
          ↓
Connected Component Analysis
          ↓
PCA Ellipse Fitting
          ↓
Heatwave Typology Classification
          ↓
Statistical Analysis & Trend Detection
          ↓
Figures and Tables
```

---

## Repository Structure

```text
SCORCH/
│
├── scripts/
│   ├── main_workflow/
│   │   ├── 1_Data_Download.py
│   │   ├── 2_Heatwave_Algorithm.py
│   │   └── 3_PCA_Algorithm.py
│   │
│   ├── figures/
│   │   └── Figure generation scripts
│   │
│   └── tables/
│       └── Table generation scripts
│
├── README.md
└── LICENSE
```

---

## Main Components

### Heatwave Detection

Heatwaves are identified using percentile-based exceedance thresholds derived from daily maximum temperature fields.

### Spatial Characterization

Each contiguous heatwave object is represented using PCA-derived ellipses, allowing quantification of:

* Spatial extent
* Orientation
* Elongation
* Geometric evolution

### Compound Heatwave Typologies

Events are classified into four categories:

| Type   | Description            |
| ------ | ---------------------- |
| Type 1 | Independent            |
| Type 2 | Spatially Clustered    |
| Type 3 | Temporally Clustered   |
| Type 4 | Mixed Spatial–Temporal |

### Trend Analysis

Temporal trends are evaluated using:

* Mann–Kendall trend tests
* Sen's slope estimator
* Frequency analysis
* Duration analysis

---

## Software Requirements

Recommended Python packages:

```bash
numpy
pandas
scipy
matplotlib
scikit-learn
xarray
cartopy
pymannkendall
```

---

## Applications

SCORCH can be applied to:

* Heatwave climatology
* Climate extremes research
* Remote sensing studies
* Climate risk assessment
* Urban heat investigations
* Regional climate analysis

---

## Citation

If you use this repository in academic work, please cite the associated thesis, dissertation, or publication when available.

---

## Author

**Fawaz Bouhamad**

M.S. Student
Agricultural and Biological Engineering
University of Florida

---

## License

This project is released under the MIT License.
