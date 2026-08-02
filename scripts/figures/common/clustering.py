"""Reusable spatial-clustering abstraction for SCORCH.

This module provides a single, consistent interface for clustering the active
(heatwave) gridded cells of a single day, using four methods:

    * ``connected_components`` -- the existing SCORCH baseline (queen/rook
      adjacency on the regular lon/lat grid). No noise label is produced.
    * ``dbscan``   -- sklearn.cluster.DBSCAN on a precomputed km distance matrix
    * ``optics``   -- sklearn.cluster.OPTICS on a precomputed km distance matrix
    * ``hdbscan``  -- sklearn.cluster.HDBSCAN (scikit-learn >= 1.3) or the
      standalone ``hdbscan`` package, on a precomputed km distance matrix

Design goals (Phase 2):
    * Accept active gridded cells as parallel ``lon`` / ``lat`` arrays.
    * Return cluster labels in ONE consistent format for every method
      (see :class:`ClusterResult`).
    * Label noise/outliers as ``-1`` for the density methods.
    * Build pairwise distance matrices in KILOMETRES using the same
      lon/lat -> local-km projection used by the PCA workflow.
    * Let the density methods use ``metric="precomputed"``.

This module deliberately does NOT touch the PCA / ellipse logic. The helper
:func:`clusters_as_cell_lists` returns per-cluster lists of ``(lon, lat)``
tuples so that, in a later phase, each cluster can be fed straight into the
existing ``evaluate_blob_ellipse_clean`` PCA routine.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

# scipy is a core dependency of SCORCH; cdist gives a fast, zero-diagonal,
# symmetric distance matrix.
from scipy.spatial.distance import cdist


# Method name constants (also accepted case-insensitively as plain strings).
CONNECTED_COMPONENTS = "connected_components"
DBSCAN = "dbscan"
OPTICS = "optics"
HDBSCAN = "hdbscan"

SUPPORTED_METHODS = (CONNECTED_COMPONENTS, DBSCAN, OPTICS, HDBSCAN)

NOISE_LABEL = -1


# -----------------------------------------------------------------------------
# Distance / projection helpers
# -----------------------------------------------------------------------------
def project_lonlat_to_km(lon, lat, lon0, lat0):
    """Project lon/lat (degrees) to a local equirectangular km plane.

    Uses the SAME constants as the PCA workflow
    (``3_PCA_Algorithm.py:project_lonlat_to_km``) so distances are consistent
    across the pipeline:

        km_per_deg_lon = 111.320 * cos(lat0)
        km_per_deg_lat = 110.574

    Parameters
    ----------
    lon, lat : array-like (degrees)
    lon0, lat0 : float
        Projection origin (typically the domain-mean lon/lat).

    Returns
    -------
    xy : (N, 2) ndarray of km coordinates.
    """
    lat0_rad = math.radians(lat0)
    km_per_deg_lon = 111.320 * math.cos(lat0_rad)
    km_per_deg_lat = 110.574
    x = (np.asarray(lon, dtype=float) - lon0) * km_per_deg_lon
    y = (np.asarray(lat, dtype=float) - lat0) * km_per_deg_lat
    return np.column_stack((x, y))


def pairwise_distance_km(lon, lat):
    """Symmetric NxN pairwise Euclidean distance matrix in kilometres.

    Cells are projected to a local equirectangular plane centred on the
    domain-mean lon/lat (a good approximation over a regional domain such as
    SCORCH's lat 10-46 N), then straight-line km distances are computed.

    Returns a float64 array with a zero diagonal, suitable for
    ``metric="precomputed"`` in DBSCAN/OPTICS/HDBSCAN.
    """
    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)
    if lon.shape != lat.shape:
        raise ValueError("lon and lat must have the same shape")
    if lon.size == 0:
        return np.zeros((0, 0), dtype=float)
    lon0 = float(lon.mean())
    lat0 = float(lat.mean())
    xy = project_lonlat_to_km(lon, lat, lon0, lat0)
    return cdist(xy, xy).astype(float)


def pairwise_distance_cells(lon, lat, grid_step=1.0, chebyshev=True):
    """Pairwise distance in GRID-CELL units (not km).

    Provided for callers (e.g. a later harness) that prefer a neighbourhood
    radius expressed in cells rather than km. With ``chebyshev=True`` and a
    radius of 1 cell this reproduces queen-style adjacency.

    NOTE: this is NOT used by the default km pipeline; it exists to make the
    "eps in cells" interpretation available if needed. See the unit caveat in
    the Phase 2 report.
    """
    lon = np.asarray(lon, dtype=float) / float(grid_step)
    lat = np.asarray(lat, dtype=float) / float(grid_step)
    pts = np.column_stack((lon, lat))
    metric = "chebyshev" if chebyshev else "euclidean"
    return cdist(pts, pts, metric=metric).astype(float)


# -----------------------------------------------------------------------------
# Result container
# -----------------------------------------------------------------------------
@dataclass
class ClusterResult:
    """Consistent return type for every clustering method.

    Attributes
    ----------
    method : str
        One of :data:`SUPPORTED_METHODS`.
    labels : np.ndarray (int, shape = (N,))
        Cluster id per input cell, aligned to the input lon/lat order.
        Clusters are numbered ``0, 1, 2, ...`` in DESCENDING size order
        (cluster 0 is the largest). Noise points are ``-1`` (density methods
        only; ``connected_components`` never emits ``-1``).
    lon, lat : np.ndarray (float, shape = (N,))
        The input coordinates (copied), for convenience/plotting.
    params : dict
        The parameters actually used.
    n_clusters : int
        Number of clusters, excluding noise.
    n_noise : int
        Number of noise points (labels == -1).
    n_points : int
        Total input cells.
    """

    method: str
    labels: np.ndarray
    lon: np.ndarray
    lat: np.ndarray
    params: dict = field(default_factory=dict)

    @property
    def n_points(self) -> int:
        return int(self.labels.size)

    @property
    def n_noise(self) -> int:
        return int(np.sum(self.labels == NOISE_LABEL))

    @property
    def n_clusters(self) -> int:
        uniq = set(self.labels.tolist()) - {NOISE_LABEL}
        return len(uniq)

    @property
    def noise_fraction(self) -> float:
        return (self.n_noise / self.n_points) if self.n_points else 0.0

    def cluster_sizes(self) -> dict:
        """Map of cluster label -> size (noise excluded)."""
        labs, counts = np.unique(self.labels, return_counts=True)
        return {int(l): int(c) for l, c in zip(labs, counts) if l != NOISE_LABEL}

    def summary(self) -> str:
        return (
            f"{self.method}: n_points={self.n_points} "
            f"n_clusters={self.n_clusters} n_noise={self.n_noise} "
            f"({100.0 * self.noise_fraction:.1f}%) params={self.params}"
        )


# -----------------------------------------------------------------------------
# Label utilities
# -----------------------------------------------------------------------------
def relabel_by_size(labels):
    """Renumber non-noise clusters 0..k-1 in descending size order.

    Noise (-1) is preserved. This gives a uniform convention across methods
    (cluster 0 = largest), matching the PCA workflow's "biggest blob first".
    """
    labels = np.asarray(labels)
    out = np.full(labels.shape, NOISE_LABEL, dtype=int)
    sizes = {}
    for lab in set(labels.tolist()) - {NOISE_LABEL}:
        sizes[lab] = int(np.sum(labels == lab))
    # Sort by size desc, then by original label for deterministic ties.
    ordered = sorted(sizes.keys(), key=lambda l: (-sizes[l], l))
    for new_id, old in enumerate(ordered):
        out[labels == old] = new_id
    return out


def clusters_as_cell_lists(lon, lat, labels, include_noise=False, round_to=6):
    """Group cells into {label: [(lon, lat), ...]} for downstream PCA.

    Coordinates are rounded to ``round_to`` decimals to match the PCA
    workflow's ``round_cell`` convention, so the lists can be fed directly to
    ``evaluate_blob_ellipse_clean`` later without coordinate drift.
    """
    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)
    labels = np.asarray(labels)
    out: dict = {}
    for lab in sorted(set(labels.tolist())):
        if lab == NOISE_LABEL and not include_noise:
            continue
        mask = labels == lab
        cells = [
            (round(float(lo), round_to), round(float(la), round_to))
            for lo, la in zip(lon[mask], lat[mask])
        ]
        out[int(lab)] = cells
    return out


# -----------------------------------------------------------------------------
# Method implementations
# -----------------------------------------------------------------------------
def _connected_components(lon, lat, connectivity="queen", grid_step=1.0, tol=1e-6):
    """Baseline: connected components on the regular grid.

    Equivalent to ``3_PCA_Algorithm.py:connected_components`` but expressed
    directly on the active cells via coordinate adjacency (so it does not need
    the full-domain grid). Two cells are adjacent if they are one ``grid_step``
    apart:

        rook  : 4-neighbourhood (N, S, E, W)
        queen : 8-neighbourhood (adds diagonals)

    Every cell receives a cluster id >= 0; there is no noise label.
    """
    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)
    n = lon.size
    labels = np.full(n, NOISE_LABEL, dtype=int)  # -1 used here only as "unvisited"
    if n == 0:
        return labels

    coords = [(round(float(lo), 6), round(float(la), 6)) for lo, la in zip(lon, lat)]
    index = {c: i for i, c in enumerate(coords)}

    s = float(grid_step)
    if connectivity == "rook":
        offsets = [(-s, 0), (s, 0), (0, -s), (0, s)]
    elif connectivity == "queen":
        offsets = [(-s, 0), (s, 0), (0, -s), (0, s),
                   (-s, -s), (-s, s), (s, -s), (s, s)]
    else:
        raise ValueError("connectivity must be 'queen' or 'rook'")

    current = 0
    for start in range(n):
        if labels[start] != NOISE_LABEL:
            continue
        stack = [start]
        labels[start] = current
        while stack:
            k = stack.pop()
            lo, la = coords[k]
            for dlo, dla in offsets:
                nb = (round(lo + dlo, 6), round(la + dla, 6))
                j = index.get(nb)
                if j is not None and labels[j] == NOISE_LABEL:
                    labels[j] = current
                    stack.append(j)
        current += 1
    return labels


def _ensure_distance_matrix(lon, lat, distance_matrix):
    if distance_matrix is not None:
        D = np.asarray(distance_matrix, dtype=float)
        n = np.asarray(lon).size
        if D.shape != (n, n):
            raise ValueError(
                f"distance_matrix shape {D.shape} != (n, n) = ({n}, {n})"
            )
        return D
    return pairwise_distance_km(lon, lat)


def _run_dbscan(D, eps, min_samples):
    from sklearn.cluster import DBSCAN as _DBSCAN
    model = _DBSCAN(eps=float(eps), min_samples=int(min_samples),
                    metric="precomputed")
    return model.fit_predict(D)


def _run_optics(D, min_samples, xi, max_eps):
    from sklearn.cluster import OPTICS as _OPTICS
    model = _OPTICS(min_samples=int(min_samples), xi=float(xi),
                    max_eps=float(max_eps), metric="precomputed",
                    cluster_method="xi")
    return model.fit_predict(D)


def _run_hdbscan(D, min_cluster_size, min_samples):
    """HDBSCAN via scikit-learn (>=1.3) or the standalone ``hdbscan`` package.

    Raises ImportError with a clear message if neither is available.
    """
    # Preferred: scikit-learn's built-in HDBSCAN (added in 1.3).
    try:
        from sklearn.cluster import HDBSCAN as _SKHDBSCAN
        model = _SKHDBSCAN(
            min_cluster_size=int(min_cluster_size),
            min_samples=(None if min_samples is None else int(min_samples)),
            metric="precomputed",
        )
        return model.fit_predict(D)
    except ImportError:
        pass

    # Fallback: standalone hdbscan package (needs float64 distance matrix).
    try:
        import hdbscan as _hdbscan
    except ImportError as exc:
        raise ImportError(
            "HDBSCAN is unavailable. Install scikit-learn>=1.3 "
            "(provides sklearn.cluster.HDBSCAN) or the standalone 'hdbscan' "
            "package: pip install hdbscan"
        ) from exc

    model = _hdbscan.HDBSCAN(
        min_cluster_size=int(min_cluster_size),
        min_samples=(None if min_samples is None else int(min_samples)),
        metric="precomputed",
    )
    return model.fit_predict(D.astype("double"))


# -----------------------------------------------------------------------------
# Public dispatcher
# -----------------------------------------------------------------------------
def cluster_cells(
    lon,
    lat,
    method,
    *,
    # connected_components
    connectivity="queen",
    grid_step=1.0,
    # dbscan: eps is in the UNITS OF THE DISTANCE MATRIX used (km by default,
    # or grid-cell units when a cell-space distance_matrix is supplied).
    eps=None,
    eps_km=None,  # backward-compatible alias for eps (km)
    # dbscan / optics / hdbscan
    min_samples=5,
    # optics
    xi=0.05,
    max_eps=np.inf,
    # hdbscan
    min_cluster_size=5,
    # shared
    distance_matrix=None,
    do_relabel_by_size=True,
):
    """Cluster active gridded cells with the requested method.

    Parameters
    ----------
    lon, lat : array-like (degrees), same length N.
    method : {'connected_components', 'dbscan', 'optics', 'hdbscan'}
    distance_matrix : optional (N, N) precomputed km distances.
        If None, it is built with :func:`pairwise_distance_km` for the density
        methods. Ignored by ``connected_components``.
    do_relabel_by_size : bool
        If True (default), clusters are renumbered so 0 = largest.

    Returns
    -------
    ClusterResult
    """
    method = str(method).strip().lower()
    if method not in SUPPORTED_METHODS:
        raise ValueError(
            f"Unknown method '{method}'. Supported: {SUPPORTED_METHODS}"
        )

    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)
    if lon.shape != lat.shape:
        raise ValueError("lon and lat must have the same shape")

    if lon.size == 0:
        return ClusterResult(method, np.array([], dtype=int),
                             lon.copy(), lat.copy(), params={})

    if method == CONNECTED_COMPONENTS:
        labels = _connected_components(lon, lat, connectivity=connectivity,
                                       grid_step=grid_step)
        used_params = {"connectivity": connectivity, "grid_step": grid_step}
    else:
        D = _ensure_distance_matrix(lon, lat, distance_matrix)
        if method == DBSCAN:
            eps_value = eps if eps is not None else (
                eps_km if eps_km is not None else 1.5)
            labels = _run_dbscan(D, eps=eps_value, min_samples=min_samples)
            used_params = {"eps": eps_value, "min_samples": min_samples,
                           "metric": "precomputed"}
        elif method == OPTICS:
            labels = _run_optics(D, min_samples=min_samples, xi=xi,
                                 max_eps=max_eps)
            used_params = {"min_samples": min_samples, "xi": xi,
                           "max_eps": max_eps, "metric": "precomputed_km"}
        else:  # HDBSCAN
            labels = _run_hdbscan(D, min_cluster_size=min_cluster_size,
                                  min_samples=min_samples)
            used_params = {"min_cluster_size": min_cluster_size,
                           "min_samples": min_samples,
                           "metric": "precomputed_km"}

    labels = np.asarray(labels, dtype=int)
    if do_relabel_by_size:
        labels = relabel_by_size(labels)

    return ClusterResult(method, labels, lon.copy(), lat.copy(),
                         params=used_params)


# -----------------------------------------------------------------------------
# Self-contained smoke test
# -----------------------------------------------------------------------------
def _toy_cells():
    """Two well-separated 1-degree grid blobs plus one isolated outlier."""
    cells = []
    # Blob A: 3x3 around (40 E, 40 N)
    for lo in (39.5, 40.5, 41.5):
        for la in (39.5, 40.5, 41.5):
            cells.append((lo, la))
    # Blob B: 2x2 around (55 E, 20 N)
    for lo in (54.5, 55.5):
        for la in (19.5, 20.5):
            cells.append((lo, la))
    # Outlier far away
    cells.append((69.5, 10.5))
    lon = np.array([c[0] for c in cells], dtype=float)
    lat = np.array([c[1] for c in cells], dtype=float)
    return lon, lat


def _smoke_test():
    """Run all four methods on toy coordinates and print a short report.

    Distances are in km; at ~40 N, 1-degree-diagonal neighbours are ~140 km
    apart, so eps_km=150 connects within-blob neighbours while keeping the two
    blobs and the outlier separate.
    """
    lon, lat = _toy_cells()
    print("=" * 70)
    print(f"Clustering smoke test on {lon.size} toy cells "
          "(blob A=9, blob B=4, outlier=1)")
    print("=" * 70)

    configs = [
        (CONNECTED_COMPONENTS, dict(connectivity="queen", grid_step=1.0)),
        (DBSCAN, dict(eps_km=150.0, min_samples=2)),
        (OPTICS, dict(min_samples=2, xi=0.05, max_eps=np.inf)),
        (HDBSCAN, dict(min_cluster_size=3, min_samples=2)),
    ]

    ok = True
    for method, kwargs in configs:
        try:
            res = cluster_cells(lon, lat, method, **kwargs)
            print(f"[ OK ] {res.summary()}")
            print(f"       labels = {res.labels.tolist()}")
            print(f"       sizes  = {res.cluster_sizes()}")
        except ImportError as exc:
            print(f"[SKIP] {method}: missing dependency -> {exc}")
        except Exception as exc:  # noqa: BLE001 - smoke test should be robust
            ok = False
            print(f"[FAIL] {method}: {type(exc).__name__}: {exc}")

    print("=" * 70)
    print("Smoke test finished." if ok else "Smoke test finished WITH FAILURES.")
    return ok


if __name__ == "__main__":
    _smoke_test()
