# THIRD-PARTY DEPENDENCY AND LICENCE INVENTORY

Versions are the exact versions of the environment that produced the paper
outputs (complete transitive lock with hashes:
environment/requirements-lock-py312.txt).
Dependencies are installed from PyPI/CRAN; none is vendored into this
repository.

## Python (CPython 3.12.10)

| Package | Version | Licence |
|---|---|---|
| numpy | 2.4.6 | BSD-3-Clause |
| pandas | 3.0.3 | BSD-3-Clause |
| scipy | 1.17.1 | BSD-3-Clause |
| scikit-learn | 1.9.0 | BSD-3-Clause |
| matplotlib | 3.10.9 | PSF-based (matplotlib licence) |
| Cartopy | 0.25.0 | BSD-3-Clause |
| shapely | 2.1.2 | BSD-3-Clause |
| pyproj | 3.7.2 | MIT |
| openpyxl | 3.1.5 | MIT |
| PyYAML | 6.0.3 | MIT |
| Pillow | 12.2.0 | MIT-CMU (HPND) |
| xarray | 2026.4.0 | Apache-2.0 |
| netCDF4 | 1.7.4 | MIT |
| dask | 2026.3.0 | BSD-3-Clause |
| zarr | 3.2.1 | MIT |
| gcsfs | 2026.5.0 | BSD-3-Clause |
| imageio | 2.37.3 | BSD-2-Clause |
| pymannkendall | 1.4.3 | MIT |
| pypdf | 6.12.2 | BSD-3-Clause |
| tabulate | 0.10.0 | MIT |
| cdsapi | 0.7.7 | Apache-2.0 |

### Development (testing) dependencies

Not required to run the workflow; installed by `pip install .[dev]`.

| Package | Version | Licence |
|---|---|---|
| pytest | 9.0.3 | MIT |

## R (4.5.1, external runtime for the LGCP stage)

| Package | Version | Licence |
|---|---|---|
| spatstat | 3.6-1 | GPL (>= 2) |
| spatstat.geom | 3.8-1 | GPL (>= 2) |
| spatstat.model | 3.7-1 | GPL (>= 2) |
| spatstat.explore | 3.8-1 | GPL (>= 2) |
| spatstat.data | 3.1-9 | GPL (>= 2) |
| jsonlite | 2.0.0 | MIT |

The R packages are used as an external interpreter workflow step; they are
not linked into, or redistributed with, the GPL-3.0-only SCORCH code. Their
GPL-2-or-later terms are in any case compatible with GPL-3.0.

## Licence compatibility with GPL-3.0-only

Every Python dependency above is BSD-, MIT-, Apache-2.0-, PSF- or
HPND-licensed. All are one-way compatible with GPL-3.0, none is
copyleft-incompatible, and none is vendored into this repository, so
distributing the SCORCH software under GPL-3.0-only raises no conflict.

## Runtime-fetched data

- Natural Earth basemaps (public domain), fetched by cartopy at figure
  render time.
- ARCO-ERA5 Zarr store (Google Cloud public bucket), read at download time.
