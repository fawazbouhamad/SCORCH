"""Daily heat-structure clustering (public wrapper).

Wraps the canonical kernel in ``scorch._kernel.clustering``. The canonical
SCORCH pipeline clusters each selected day's HEATWAVE-LABELLED grid cells
(``heatwave_id > 0``: the cells that passed the >=3-day / >=3-exceedance-day
episode rule, a subset of the threshold-exceedance cells) with DBSCAN on the
PRECOMPUTED grid-cell Euclidean distance matrix (grid_step = 1.0 degree),
exactly as in ``build_event_global_max_master.py:dbscan_labels``:

    D = pairwise_distance_cells(lon, lat, grid_step=1.0, chebyshev=False)
    DBSCAN(eps=eps, min_samples=min_samples, metric="precomputed").fit_predict(D)

Labels follow sklearn's convention: components are 0, 1, 2, ... in order of
first appearance; noise cells are -1. The raw label order is preserved (no
relabelling), matching the canonical master-catalog build.
"""
from __future__ import annotations

import numpy as np

from ._kernel import clustering as _kernel_clustering

NOISE = -1
GRID_STEP = 1.0

# Re-exported kernel helpers (canonical implementations).
pairwise_distance_cells = _kernel_clustering.pairwise_distance_cells
pairwise_distance_km = _kernel_clustering.pairwise_distance_km
clusters_as_cell_lists = _kernel_clustering.clusters_as_cell_lists
cluster_cells = _kernel_clustering.cluster_cells
ClusterResult = _kernel_clustering.ClusterResult


def cluster_day_cells(lon, lat, eps, min_samples, grid_step=GRID_STEP):
    """Canonical DBSCAN on the precomputed grid-cell Euclidean distance.

    Faithful wrapper of ``build_event_global_max_master.py:dbscan_labels``.

    Parameters
    ----------
    lon, lat : array-like (degrees), the day's heatwave-labelled 1-degree
        cell centres (heatwave_id > 0).
    eps : float, neighbourhood radius in GRID-CELL units.
    min_samples : int, DBSCAN core-point threshold.
    grid_step : float, grid spacing in degrees (canonical: 1.0).

    Returns
    -------
    labels : np.ndarray of int, aligned to the input order; -1 = noise.
    """
    from sklearn.cluster import DBSCAN
    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)
    D = _kernel_clustering.pairwise_distance_cells(
        lon, lat, grid_step=grid_step, chebyshev=False)
    return DBSCAN(eps=float(eps), min_samples=int(min_samples),
                  metric="precomputed").fit_predict(D)


# Public, descriptive alias used by the package API.
cluster_structures = cluster_day_cells
