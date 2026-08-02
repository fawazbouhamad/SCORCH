"""PCA ellipse fitting (public wrapper around the canonical kernel).

All geometry is computed by ``scorch._kernel.ellipse_pca`` -- a byte-for-byte
copy of the canonical ``scripts/common/ellipse_pca.py`` -- so results are
identical to the published catalog:

  * sigma default 1.25 (canonical ellipse scale),
  * eigenvalue variance floor 1.0 km^2 retained (applied to axis lengths
    only; explained-variance ratios use the raw eigenvalues),
  * no semi-axis floor (removed 2026-07-28; it could never bind).
"""
from __future__ import annotations

import numpy as np

from ._kernel import ellipse_pca as _kernel

SIGMA_DEFAULT = 1.25
NOISE = -1

# Re-exported canonical kernel entry points.
evaluate_cluster_ellipse = _kernel.evaluate_cluster_ellipse
evaluate_cluster_over_sigmas = _kernel.evaluate_cluster_over_sigmas
project_lonlat_to_km = _kernel.project_lonlat_to_km
fit_pca = _kernel.fit_pca
ellipse_semi_axes_km = _kernel.ellipse_semi_axes_km
ellipse_mask = _kernel.ellipse_mask


def _split_cells(cells):
    """Accept (lon_array, lat_array) or an iterable of (lon, lat) pairs."""
    if isinstance(cells, tuple) and len(cells) == 2 and not np.isscalar(cells[0]):
        lon, lat = cells
        return np.asarray(lon, dtype=float), np.asarray(lat, dtype=float)
    arr = np.asarray(list(cells), dtype=float)
    if arr.ndim != 2 or arr.shape[1] != 2:
        raise ValueError(
            "cells must be (lon_array, lat_array) or a sequence of (lon, lat)")
    return arr[:, 0], arr[:, 1]


def fit_pca_ellipses(cells, sigma=SIGMA_DEFAULT, cell_to_val=None):
    """Fit the canonical PCA ellipse to one cluster of cells.

    Parameters
    ----------
    cells : (lon_array, lat_array) tuple, or sequence of (lon, lat) pairs
        The cluster's 1-degree cell centres in degrees.
    sigma : float, ellipse scale (canonical: 1.25).
    cell_to_val : optional dict {(lon, lat): value} for the Tmax-weighted
        centroid.

    Returns
    -------
    dict of canonical ellipse metrics (see
    ``scorch._kernel.ellipse_pca.evaluate_cluster_ellipse``), or None for an
    empty cluster.
    """
    lon, lat = _split_cells(cells)
    return _kernel.evaluate_cluster_ellipse(lon, lat, sigma,
                                            cell_to_val=cell_to_val)


def fit_day_ellipses(lon, lat, labels, sigma=SIGMA_DEFAULT):
    """One canonical ellipse per DBSCAN component (noise excluded).

    Components are enumerated ``cluster_id = 0, 1, ...`` over the SORTED
    distinct non-noise labels, matching the master-catalog build
    (``build_event_global_max_master.py:day_ellipse_rows``).

    Returns
    -------
    list of dicts; each is the kernel metrics dict plus ``cluster_id``.
    """
    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)
    labels = np.asarray(labels)
    rows = []
    comp_labels = sorted(set(labels.tolist()) - {NOISE})
    for cid, lab in enumerate(comp_labels):
        m = labels == lab
        e = _kernel.evaluate_cluster_ellipse(lon[m], lat[m], sigma)
        if not e:
            continue
        e = dict(e)
        e["cluster_id"] = cid
        rows.append(e)
    return rows
