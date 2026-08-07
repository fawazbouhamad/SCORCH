"""Post-PCA raw-Celsius Tmax-weighted centroid and rigid ellipse translation.

Remediation stage separation (fix/tmax-weighted-centroids):

  * Stage 1 -- unweighted PCA geometry: ``ellipse_pca.evaluate_cluster_ellipse``
    (UNCHANGED; the only stage Appendix A and the sigma sensitivity analysis
    may consume).
  * Stage 2 -- raw-Celsius Tmax-weighted centroid: THIS module. Runs strictly
    AFTER the complete PCA ellipse has been calculated. Never called by
    clustering, PCA, or Appendix A.
  * Stage 3 -- rigid translation: THIS module. Re-renders the frozen km-frame
    ellipse/axis geometry at the weighted centre without refitting, resizing,
    rotating, or otherwise altering it.

Scientific definition of the weights (advisor-approved):

    w_hk(t) = Tmax_hk(t)   in degrees Celsius ("absolute Tmax" = the observed
                            processed daily Tmax level, NOT abs()).

    lambda_w = sum(lon_k * w_k) / sum(w_k)
    phi_w    = sum(lat_k * w_k) / sum(w_k)

Prohibited operations (none are performed anywhere in this module): Kelvin
conversion, abs(), max(Tmax, 0) clipping, threshold subtraction / exceedance,
shifting, standardization / rescaling, anomaly or normalized fields, grid-area
or latitude weights, weighting the PCA covariance, re-running PCA about the
weighted centroid. The division by sum(w) is the weighted-average denominator,
not a temperature normalization.

Invalid inputs (missing, duplicated, non-finite, zero or negative Celsius
weights, empty structures) raise :class:`WeightedCentroidError` -- an explicit
scientific stop. There is NO silent unweighted fallback in this module.

This file is intentionally byte-identical in ``src/scorch/_kernel/`` and
``scripts/figures/common/`` (the same dual-copy convention as
``ellipse_pca.py``); the dual-layout import below keeps both copies importable.
"""
from __future__ import annotations

import math

import numpy as np

try:                                     # package layout: src/scorch/_kernel/
    from . import ellipse_pca as _geom   # type: ignore
except ImportError:                      # script layout: scripts/figures/common/
    import ellipse_pca as _geom          # type: ignore


class WeightedCentroidError(ValueError):
    """Explicit scientific stop: invalid Tmax weights or member cells."""


# -----------------------------------------------------------------------------
# Stage 2: raw-Celsius Tmax-weighted centroid (strict; structure-specific)
# -----------------------------------------------------------------------------
def validate_member_weights(lon, lat, tmax_c, context=""):
    """Validate one structure's member coordinates and raw-Celsius weights.

    Returns ``(lon, lat, w)`` as float arrays. Raises WeightedCentroidError on
    any violation; never repairs, clips, converts, or falls back.
    """
    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)
    w = np.asarray(tmax_c, dtype=float)
    tag = f" [{context}]" if context else ""
    if lon.ndim != 1 or lat.ndim != 1 or w.ndim != 1:
        raise WeightedCentroidError(f"inputs must be 1-D arrays{tag}")
    n = lon.size
    if n == 0:
        raise WeightedCentroidError(f"empty structure: no member cells{tag}")
    if lat.size != n or w.size != n:
        raise WeightedCentroidError(
            f"length mismatch: lon={n} lat={lat.size} tmax={w.size}{tag}")
    if not np.all(np.isfinite(lon)) or not np.all(np.isfinite(lat)):
        raise WeightedCentroidError(f"non-finite member coordinates{tag}")
    if not np.all(np.isfinite(w)):
        bad = int(np.count_nonzero(~np.isfinite(w)))
        raise WeightedCentroidError(
            f"{bad} non-finite Tmax weight(s); explicit stop, no fallback{tag}")
    pairs = set()
    for lo, la in zip(lon.tolist(), lat.tolist()):
        key = (round(lo, 6), round(la, 6))
        if key in pairs:
            raise WeightedCentroidError(
                f"duplicate member cell {key}; join must be exactly 1:1{tag}")
        pairs.add(key)
    if np.any(w <= 0.0):
        bad = int(np.count_nonzero(w <= 0.0))
        raise WeightedCentroidError(
            f"{bad} member-cell Tmax value(s) are zero or negative degC; "
            f"scientific stop required -- do NOT clip, transform, take "
            f"absolute values, convert units, or fall back to the unweighted "
            f"centroid{tag}")
    wsum = float(np.sum(w))
    if not math.isfinite(wsum) or wsum <= 0.0:
        raise WeightedCentroidError(f"invalid weight denominator {wsum}{tag}")
    return lon, lat, w


def tmax_weighted_centroid(lon, lat, tmax_c, context=""):
    """Raw-Celsius Tmax-weighted centroid of one structure (Stage 2).

    Weighting is structure-specific: callers must pass ONLY the member cells
    of one structure on its exact date (noise cells and other structures'
    cells excluded upstream by the frozen DBSCAN labels).

    Returns a dict with full-precision ``lon_w``, ``lat_w``, the weight audit
    (min/max/mean/sd/sum in degC) and ``n_cells``.
    """
    lon, lat, w = validate_member_weights(lon, lat, tmax_c, context=context)
    wsum = float(np.sum(w))
    lon_w = float(np.sum(lon * w) / wsum)
    lat_w = float(np.sum(lat * w) / wsum)
    # Positive weights make the weighted mean a convex combination: it must
    # lie inside the member bounding box. Defensive invariant only.
    eps = 1e-9
    if not (lon.min() - eps <= lon_w <= lon.max() + eps
            and lat.min() - eps <= lat_w <= lat.max() + eps):
        raise WeightedCentroidError(
            f"weighted centroid ({lon_w}, {lat_w}) escaped the member "
            f"bounding box; invariant violation [{context}]")
    return dict(
        lon_w=lon_w, lat_w=lat_w, weight_sum_c=wsum,
        n_cells=int(lon.size),
        tmax_min_c=float(w.min()), tmax_max_c=float(w.max()),
        tmax_mean_c=float(w.mean()), tmax_sd_c=float(w.std(ddof=0)),
    )


# -----------------------------------------------------------------------------
# Stage 3: rigid translation of the completed PCA ellipse
# -----------------------------------------------------------------------------
def translated_ellipse_lonlat(target_lon, target_lat, eigvecs, eigvals, sigma,
                              n=240):
    """Render the COMPLETED PCA ellipse rigidly at the weighted centre.

    The km-frame geometry (eigenvectors, eigenvalues, sigma scaling, axis
    lengths, area, orientation) is passed through UNCHANGED from the
    unweighted PCA stage; only the geographic anchor point moves. No second
    PCA fit is performed here.
    """
    return _geom.ellipse_points_lonlat_from_km(
        float(target_lon), float(target_lat), np.zeros(2),
        eigvecs, eigvals, sigma, n=n)


def translated_axes_lonlat(target_lon, target_lat, eigvecs, eigvals, sigma):
    """Principal-axis segment endpoints rendered rigidly at the weighted centre."""
    return _geom.axes_segments_lonlat_from_km(
        float(target_lon), float(target_lat), np.zeros(2),
        eigvecs, eigvals, sigma)


def translated_ellipse_mask(lon_arr, lat_arr, target_lon, target_lat,
                            eigvecs, eigvals, sigma):
    """Point-in-ellipse footprint of the rigidly translated ellipse."""
    return _geom.ellipse_mask(lon_arr, lat_arr, float(target_lon),
                              float(target_lat), np.zeros(2), eigvecs,
                              eigvals, sigma)


# -----------------------------------------------------------------------------
# Geodesic displacement (audit metric; NOT Euclidean degrees)
# -----------------------------------------------------------------------------
def geodesic_displacement_km(lon1, lat1, lon2, lat2):
    """Geodesic displacement (km) and forward bearing (deg) old -> new.

    Uses pyproj's WGS84 geodesic when available; otherwise a spherical
    great-circle fallback (audit metric only, never a model input).
    """
    try:
        from pyproj import Geod
        g = Geod(ellps="WGS84")
        az12, _, dist_m = g.inv(float(lon1), float(lat1),
                                float(lon2), float(lat2))
        return float(dist_m) / 1000.0, float(az12) % 360.0
    except Exception:
        r = 6371.0072
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dl = math.radians(lon2 - lon1)
        h = (math.sin((p2 - p1) / 2.0) ** 2
             + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2)
        d = 2.0 * r * math.asin(min(1.0, math.sqrt(h)))
        y = math.sin(dl) * math.cos(p2)
        x = (math.cos(p1) * math.sin(p2)
             - math.sin(p1) * math.cos(p2) * math.cos(dl))
        return d, math.degrees(math.atan2(y, x)) % 360.0
