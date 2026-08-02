"""Pure, reusable PCA / ellipse utilities for SCORCH (Phase 4A).

These functions are copied/adapted from ``3_PCA_Algorithm.py`` so that the new
clustering -> PCA pipeline can reuse the SAME formulas and constants WITHOUT
importing the original script (which runs plotting/IO side effects and has a
non-importable, leading-digit filename).

Design constraints:
    * No plotting, no file IO, no globals controlling behaviour.
    * ``sigma`` is always an explicit ARGUMENT (never a fixed module global).
    * Functions accept plain arrays / tuples and return dicts / scalars.

Key differences vs the original, documented on purpose:
    * The original ``fit_pca`` floored eigenvalues to 1.0 (a 1 km^2 variance
      floor). Here :func:`fit_pca` returns the RAW eigenvalues so that
      explained-variance ratios are statistically meaningful. The 1.0 floor is
      re-applied ONLY for ellipse geometry, inside :func:`ellipse_semi_axes_km`,
      so the ellipse shapes match the original for any real cluster
      (eigenvalue >= 1), while variance ratios stay correct.
"""

from __future__ import annotations

import math

import numpy as np

# Same constants as 3_PCA_Algorithm.py:project_lonlat_to_km
_KM_PER_DEG_LON_AT_EQUATOR = 111.320
_KM_PER_DEG_LAT = 110.574

# Floor matching the original ellipse geometry. The variance floor prevents
# zero-width ellipses for perfectly collinear clusters (minor eigenvalue 0).
# A former 1 km semi-axis floor (_AXIS_FLOOR) was removed 2026-07-28: with the
# variance floor applied first, sigma*sqrt(max(eig, 1)) >= sigma km, so the
# axis floor could never strictly bind at any sigma >= 1 used in production;
# audit of all catalog/sensitivity outputs found zero activations.
_VAR_FLOOR = 1.0    # km^2, eigenvalue floor used for axis lengths only


# -----------------------------------------------------------------------------
# Projection
# -----------------------------------------------------------------------------
def project_lonlat_to_km(lon, lat, lon0, lat0):
    """Project lon/lat (deg) to a local equirectangular km plane (origin lon0/lat0)."""
    lat0_rad = math.radians(lat0)
    km_per_deg_lon = _KM_PER_DEG_LON_AT_EQUATOR * math.cos(lat0_rad)
    x = (np.asarray(lon, dtype=float) - lon0) * km_per_deg_lon
    y = (np.asarray(lat, dtype=float) - lat0) * _KM_PER_DEG_LAT
    return np.column_stack((x, y))


# -----------------------------------------------------------------------------
# PCA
# -----------------------------------------------------------------------------
def fit_pca(points_xy):
    """PCA of 2D km points.

    Returns ``(center_xy, eigvecs, eigvals)`` with eigenvalues sorted DESCENDING
    and NOT floored (numerically clipped to >= 0). eigvecs columns are the
    principal axes (column 0 = major).
    """
    points_xy = np.asarray(points_xy, dtype=float)
    if points_xy.shape[0] == 1:
        center = points_xy[0].copy()
        eigvecs = np.eye(2)
        eigvals = np.array([1.0, 1.0], dtype=float)
        return center, eigvecs, eigvals

    center = points_xy.mean(axis=0)
    centered = points_xy - center
    cov = np.cov(centered, rowvar=False, bias=False)

    eigvals, eigvecs = np.linalg.eigh(cov)
    order = np.argsort(eigvals)[::-1]
    eigvals = np.clip(eigvals[order], 0.0, None)
    eigvecs = eigvecs[:, order]
    return center, eigvecs, eigvals


def ellipse_semi_axes_km(eigvals, sigma, var_floor=_VAR_FLOOR):
    """Semi-axes (a, b) in km at scale ``sigma``.

    Reproduces the original geometry: eigenvalues are floored to ``var_floor``
    before sqrt (guarding collinear clusters against zero-width ellipses).
    """
    ev0 = max(float(eigvals[0]), var_floor)
    ev1 = max(float(eigvals[1]), var_floor)
    a = sigma * math.sqrt(ev0)
    b = sigma * math.sqrt(ev1)
    return a, b


def explained_variance_ratio(eigvals):
    """(pc1_ratio, pc1_plus_pc2_ratio) from RAW eigenvalues.

    Note: for 2D spatial PCA the cumulative PC1+PC2 ratio is always 1.0.
    """
    tot = float(eigvals[0] + eigvals[1])
    if tot <= 0:
        return float("nan"), float("nan")
    return float(eigvals[0] / tot), 1.0


def major_axis_orientation_deg(eigvecs):
    """Orientation of the major axis (PC1), degrees CCW from east, in [0, 180)."""
    vx, vy = float(eigvecs[0, 0]), float(eigvecs[1, 0])
    return math.degrees(math.atan2(vy, vx)) % 180.0


# -----------------------------------------------------------------------------
# Ellipse membership (copied from 3_PCA_Algorithm.py:ellipse_mask)
# -----------------------------------------------------------------------------
def ellipse_mask(lon_arr, lat_arr, center_lon, center_lat, center_xy,
                 eigvecs, eigvals, sigma, var_floor=_VAR_FLOOR):
    """Boolean mask: which (lon, lat) points fall inside the sigma-ellipse."""
    all_xy = project_lonlat_to_km(lon_arr, lat_arr, center_lon, center_lat)
    rel = all_xy - center_xy
    pc = rel @ eigvecs
    a, b = ellipse_semi_axes_km(eigvals, sigma, var_floor=var_floor)
    return ((pc[:, 0] / a) ** 2 + (pc[:, 1] / b) ** 2) <= 1.0 + 1e-12


# -----------------------------------------------------------------------------
# Weighted-centroid helpers (copied from 3_PCA_Algorithm.py)
# -----------------------------------------------------------------------------
def safe_weighted_mean(values, weights):
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    good = np.isfinite(values) & np.isfinite(weights)
    if not np.any(good):
        return float("nan")
    values = values[good]
    weights = weights[good]
    weights = np.where(weights > 0, weights, 0.0)
    sw = float(np.sum(weights))
    if sw <= 0.0:
        return float(np.mean(values))
    return float(np.sum(values * weights) / sw)


def tmax_weighted_centroid_from_cells(cells, cell_to_val):
    """Weighted centroid of ``cells`` (list of (lon, lat)) using cell_to_val."""
    cell_list = sorted(cells)
    if len(cell_list) == 0:
        return float("nan"), float("nan"), 0.0
    lon = np.array([c[0] for c in cell_list], dtype=float)
    lat = np.array([c[1] for c in cell_list], dtype=float)
    w = np.array([max(float(cell_to_val.get(c, np.nan)), 0.0) for c in cell_list],
                 dtype=float)
    lon_w = safe_weighted_mean(lon, w)
    lat_w = safe_weighted_mean(lat, w)
    wsum = float(np.nansum(np.where(np.isfinite(w), w, 0.0)))
    return lon_w, lat_w, wsum


# -----------------------------------------------------------------------------
# Single-cluster evaluation (the main entry point for the Phase 4 harness)
# -----------------------------------------------------------------------------
def evaluate_cluster_ellipse(lon, lat, sigma, cell_to_val=None, round_to=6,
                             var_floor=_VAR_FLOOR):
    """Fit PCA to one cluster and return ellipse metrics at scale ``sigma``.

    Parameters
    ----------
    lon, lat : array-like, the cluster's cell-centre coordinates (deg).
    sigma : float, ellipse scale (number of std devs).
    cell_to_val : optional dict {(lon, lat): value} for the Tmax-weighted
        centroid (e.g. the day's per-cell value). Coordinates are rounded to
        ``round_to`` decimals to match the keys.
    var_floor : float, eigenvalue floor in km^2 applied to the ellipse
        geometry (canonical: 1.0). Explained-variance ratios always use the
        raw eigenvalues.

    Returns
    -------
    dict of metrics, or None if the cluster is empty.
    """
    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)
    n = lon.size
    if n == 0:
        return None

    center_lon_pca = float(lon.mean())
    center_lat_pca = float(lat.mean())

    xy = project_lonlat_to_km(lon, lat, center_lon_pca, center_lat_pca)
    center_xy, eigvecs, eigvals = fit_pca(xy)

    a, b = ellipse_semi_axes_km(eigvals, sigma, var_floor=var_floor)
    major_axis = 2.0 * a
    minor_axis = 2.0 * b
    area = math.pi * a * b
    orientation = major_axis_orientation_deg(eigvecs)
    pc1_ev, pc1pc2_ev = explained_variance_ratio(eigvals)

    # Tmax-weighted centroid (optional)
    w_lon = w_lat = w_sum = float("nan")
    if cell_to_val is not None:
        cells = [(round(float(lo), round_to), round(float(la), round_to))
                 for lo, la in zip(lon, lat)]
        w_lon, w_lat, w_sum = tmax_weighted_centroid_from_cells(cells, cell_to_val)

    # Fraction of the cluster's own cells inside the (PCA-centred) ellipse.
    mask = ellipse_mask(lon, lat, center_lon_pca, center_lat_pca,
                        center_xy, eigvecs, eigvals, sigma,
                        var_floor=var_floor)
    pct_inside = 100.0 * float(mask.sum()) / n

    return dict(
        n_cells=int(n),
        sigma=float(sigma),
        pc1_explained_var=pc1_ev,
        pc1_pc2_explained_var=pc1pc2_ev,
        major_axis_km=float(major_axis),
        minor_axis_km=float(minor_axis),
        ellipse_area_km2=float(area),
        orientation_deg=float(orientation),
        axis_ratio=float(b / a) if a > 0 else float("nan"),
        centroid_lon=center_lon_pca,
        centroid_lat=center_lat_pca,
        weighted_centroid_lon=(float(w_lon) if np.isfinite(w_lon) else float("nan")),
        weighted_centroid_lat=(float(w_lat) if np.isfinite(w_lat) else float("nan")),
        weight_sum=(float(w_sum) if np.isfinite(w_sum) else float("nan")),
        pct_points_inside=float(pct_inside),
        eigval_major=float(eigvals[0]),
        eigval_minor=float(eigvals[1]),
    )


def evaluate_cluster_over_sigmas(lon, lat, sigmas, cell_to_val=None,
                                 var_floor=_VAR_FLOOR):
    """Run :func:`evaluate_cluster_ellipse` across a list of sigma values.

    Returns ``(rows, stability)`` where rows is a list of per-sigma metric
    dicts and stability summarises across-sigma behaviour:
        orientation_std_deg : std of orientation across sigma (≈0 by design,
                              since sigma scales axes but not direction)
        area_cv             : std/mean of ellipse area across sigma
        area_ratio_maxmin   : max area / min area across sigma
        area_log_slope      : slope of log(area) vs log(sigma) (exactly 2 by
                              construction: area scales as sigma^2)
    """
    rows = [evaluate_cluster_ellipse(lon, lat, s, cell_to_val=cell_to_val,
                                     var_floor=var_floor)
            for s in sigmas]
    rows = [r for r in rows if r is not None]
    stability = {}
    if rows:
        oris = np.array([r["orientation_deg"] for r in rows], dtype=float)
        areas = np.array([r["ellipse_area_km2"] for r in rows], dtype=float)
        sig = np.array([r["sigma"] for r in rows], dtype=float)
        stability["orientation_std_deg"] = float(np.std(oris))
        mean_area = float(np.mean(areas))
        stability["area_cv"] = float(np.std(areas) / mean_area) if mean_area else float("nan")
        stability["area_ratio_maxmin"] = (float(areas.max() / areas.min())
                                          if areas.min() > 0 else float("nan"))
        if len(sig) >= 2 and np.all(areas > 0) and np.all(sig > 0):
            slope = np.polyfit(np.log(sig), np.log(areas), 1)[0]
            stability["area_log_slope"] = float(slope)
        else:
            stability["area_log_slope"] = float("nan")
    return rows, stability


# -----------------------------------------------------------------------------
# Drawing geometry helpers (pure; copied/adapted from 3_PCA_Algorithm.py)
# These return lon/lat polylines for plotting the ellipse and its PCA axes.
# `center_xy` is the ellipse centre in the local km frame (use np.zeros(2) when
# the ellipse is positioned by passing the desired centre as center_lon/lat).
# -----------------------------------------------------------------------------
def ellipse_points_lonlat_from_km(center_lon, center_lat, center_xy, eigvecs,
                                  eigvals, sigma, n=240,
                                  var_floor=_VAR_FLOOR):
    a, b = ellipse_semi_axes_km(eigvals, sigma, var_floor=var_floor)
    t = np.linspace(0.0, 2.0 * np.pi, n)
    circle = np.vstack([a * np.cos(t), b * np.sin(t)])
    ell = np.asarray(center_xy, dtype=float).reshape(2, 1) + eigvecs @ circle
    xs, ys = ell[0, :], ell[1, :]
    lat0_rad = math.radians(center_lat)
    km_per_deg_lon = _KM_PER_DEG_LON_AT_EQUATOR * math.cos(lat0_rad)
    lon_e = center_lon + xs / km_per_deg_lon
    lat_e = center_lat + ys / _KM_PER_DEG_LAT
    return lon_e, lat_e


def axes_segments_lonlat_from_km(center_lon, center_lat, center_xy, eigvecs,
                                 eigvals, sigma, var_floor=_VAR_FLOOR):
    a, b = ellipse_semi_axes_km(eigvals, sigma, var_floor=var_floor)
    v1 = eigvecs[:, 0] * a
    v2 = eigvecs[:, 1] * b
    lat0_rad = math.radians(center_lat)
    km_per_deg_lon = _KM_PER_DEG_LON_AT_EQUATOR * math.cos(lat0_rad)

    def inv(pt_xy):
        return (center_lon + pt_xy[0] / km_per_deg_lon,
                center_lat + pt_xy[1] / _KM_PER_DEG_LAT)

    c = np.asarray(center_xy, dtype=float)
    return inv(c - v1), inv(c + v1), inv(c - v2), inv(c + v2)
