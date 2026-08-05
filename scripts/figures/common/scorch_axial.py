#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Canonical axial-orientation statistics for SCORCH.

Ellipse orientation is an **axial** (180 deg-periodic) quantity: an ellipse axis
pointing at 10 deg and one pointing at 190 deg are the same axis. Arithmetic
averaging of such angles is not a valid statistic -- it is not invariant under
the 180 deg relabelling that carries no physical meaning, so its result depends
on an arbitrary bookkeeping choice.

This module is the single canonical implementation of

  * the catalog -> manuscript angle convention conversion, and
  * the doubled-angle (Mardia) axial mean

for every SCORCH figure, table and statistical summary. No SCORCH code may
average orientations arithmetically.

Conventions
-----------
**Legacy catalog convention** (column ``orientation_deg`` in the 760-row
event-global-max master; preserved unchanged for backward compatibility):

    counterclockwise from EAST, wrapped to [0, 180)

Verified directly against the catalog's own PCA eigenvector columns:
``atan2(pc1_vec_y, pc1_vec_x)`` reproduces ``orientation_deg``.

**Manuscript convention** (used in all captions and reported values):

    clockwise from NORTH, wrapped to (-90, 90]

The two are related by ``theta_north = 90 - theta_east`` followed by wrapping.
Because that map is an affine reflection, it commutes with the axial mean:
``axial_mean(90 - theta) == 90 - axial_mean(theta)`` (up to wrapping). Either
order of operations is therefore valid and both are exercised by the tests.

Doubled-angle axial mean
------------------------
    mu = 0.5 * atan2( mean(sin 2*theta), mean(cos 2*theta) )

with the resultant length

    R = hypot(mean(cos 2*theta), mean(sin 2*theta))  in [0, 1]

``R`` is a descriptive concentration measure, not a significance test. ``R -> 0``
means the axial direction is ill-conditioned (broad dispersion, multimodality,
or cancellation between subgroups) and ``mu`` should not be trusted; the
functions below surface this rather than hiding it.
"""
from __future__ import annotations

import math

import numpy as np

__all__ = [
    "AXIAL_PERIOD_DEG",
    "DEGENERATE_R_TOL",
    "wrap_axis_east_ccw",
    "wrap_axis_north_cw",
    "east_ccw_to_north_cw",
    "north_cw_to_east_ccw",
    "axial_mean_deg",
    "axial_resultant_length",
    "axial_mean_and_resultant",
]

#: Axial angles are periodic with period 180 deg, not 360 deg.
AXIAL_PERIOD_DEG = 180.0

#: Resultant lengths at or below this are treated as a degenerate axial
#: direction. Chosen well above float64 noise for the sample sizes used here
#: (n <= 760) while never firing on genuinely concentrated data.
DEGENERATE_R_TOL = 1e-12


# ---------------------------------------------------------------------------
# wrapping
# ---------------------------------------------------------------------------
def wrap_axis_east_ccw(deg):
    """Wrap axial angle(s) to the legacy catalog range ``[0, 180)``.

    Accepts scalars or array-likes; NaNs propagate as NaN.
    """
    arr = np.asarray(deg, dtype=float)
    out = np.mod(arr, AXIAL_PERIOD_DEG)
    # np.mod maps exact multiples of 180 to 0.0, which is what [0, 180) wants.
    out = np.where(np.isfinite(arr), out, np.nan)
    return float(out) if out.ndim == 0 else out


def wrap_axis_north_cw(deg):
    """Wrap axial angle(s) to the manuscript range ``(-90, 90]``.

    The interval is half-open at -90 and closed at +90, so an axis lying exactly
    east-west reports ``+90``, never ``-90``. Accepts scalars or array-likes;
    NaNs propagate as NaN.
    """
    arr = np.asarray(deg, dtype=float)
    # Map to [-90, 90) then move the -90 endpoint to +90 to close the interval
    # at the top, matching the manuscript convention.
    out = np.mod(arr + 90.0, AXIAL_PERIOD_DEG) - 90.0
    out = np.where(out <= -90.0, out + AXIAL_PERIOD_DEG, out)
    out = np.where(np.isfinite(arr), out, np.nan)
    return float(out) if out.ndim == 0 else out


# ---------------------------------------------------------------------------
# convention conversion
# ---------------------------------------------------------------------------
def east_ccw_to_north_cw(deg):
    """Legacy catalog convention -> manuscript convention.

    ``[0, 180)`` counterclockwise-from-east  ->  ``(-90, 90]`` clockwise-from-north.
    """
    return wrap_axis_north_cw(90.0 - np.asarray(deg, dtype=float))


def north_cw_to_east_ccw(deg):
    """Manuscript convention -> legacy catalog convention (exact inverse)."""
    return wrap_axis_east_ccw(90.0 - np.asarray(deg, dtype=float))


# ---------------------------------------------------------------------------
# doubled-angle axial mean
# ---------------------------------------------------------------------------
def _doubled_angle_components(deg, weights=None):
    """Return ``(mean_cos2, mean_sin2, n_used)`` ignoring non-finite inputs."""
    arr = np.asarray(deg, dtype=float).ravel()
    good = np.isfinite(arr)
    if weights is None:
        w = np.ones(arr.shape, dtype=float)
    else:
        w = np.asarray(weights, dtype=float).ravel()
        if w.shape != arr.shape:
            raise ValueError(
                f"weights shape {w.shape} does not match angles shape {arr.shape}")
        good &= np.isfinite(w)
    arr, w = arr[good], w[good]
    if arr.size == 0:
        return np.nan, np.nan, 0
    wsum = w.sum()
    if not np.isfinite(wsum) or wsum <= 0.0:
        raise ValueError("weights must sum to a positive finite value")
    two = np.deg2rad(2.0 * arr)
    return (float(np.sum(w * np.cos(two)) / wsum),
            float(np.sum(w * np.sin(two)) / wsum),
            int(arr.size))


def axial_resultant_length(deg, weights=None):
    """Doubled-angle resultant length ``R`` in ``[0, 1]``.

    ``R = 1`` means perfectly aligned axes; ``R = 0`` means no resolvable
    preferred axis. Returns NaN when no finite observation is supplied.
    """
    c, s, n = _doubled_angle_components(deg, weights)
    if n == 0:
        return float("nan")
    return float(math.hypot(c, s))


def axial_mean_deg(deg, weights=None, convention="same", strict=False):
    """Doubled-angle axial mean of ``deg``.

    ``mu = 0.5 * atan2(mean(sin 2*theta), mean(cos 2*theta))``

    Parameters
    ----------
    deg
        Axial angles in degrees. Scalars or array-likes. Non-finite values are
        ignored (not treated as zero).
    weights
        Optional non-negative weights, same shape as ``deg``. Default: equal
        weight per observation, which is the SCORCH convention (each structure
        counts once).
    convention
        ``"same"``    -- return in the caller's own convention, wrapped to
                         ``(-90, 90]`` (the default; correct for inputs already
                         in the manuscript convention).
        ``"north_cw"`` -- inputs are legacy catalog (CCW-from-east); return the
                         manuscript convention (CW-from-north, ``(-90, 90]``).
        ``"east_ccw"`` -- inputs are legacy catalog; return the legacy
                         convention, wrapped to ``[0, 180)``.
    strict
        If True, raise ``ValueError`` when the axial direction is degenerate
        (``R <= DEGENERATE_R_TOL``) instead of returning NaN.

    Returns
    -------
    float
        The axial mean, or NaN if no finite observation was supplied or the
        direction is degenerate and ``strict`` is False.
    """
    if convention not in ("same", "north_cw", "east_ccw"):
        raise ValueError(f"unknown convention {convention!r}")

    c, s, n = _doubled_angle_components(deg, weights)
    if n == 0:
        if strict:
            raise ValueError("no finite orientation values supplied")
        return float("nan")

    if math.hypot(c, s) <= DEGENERATE_R_TOL:
        if strict:
            raise ValueError(
                "axial direction is undefined: doubled-angle resultant is zero "
                "(inputs cancel exactly; the mean axis is not identifiable)")
        return float("nan")

    mu = 0.5 * math.degrees(math.atan2(s, c))

    if convention == "north_cw":
        # Inputs were CCW-from-east; convert the *mean* to CW-from-north. The
        # conversion commutes with the axial mean, so this equals taking the
        # mean of the converted angles.
        return float(wrap_axis_north_cw(90.0 - mu))
    if convention == "east_ccw":
        return float(wrap_axis_east_ccw(mu))
    return float(wrap_axis_north_cw(mu))


def axial_mean_and_resultant(deg, weights=None, convention="same", strict=False):
    """Convenience wrapper returning ``(mu, R, n_used)`` in one pass.

    Reporting ``R`` alongside ``mu`` is mandatory for SCORCH summaries: a mean
    axis quoted without its concentration invites over-reading a direction that
    the data may not support.
    """
    c, s, n = _doubled_angle_components(deg, weights)
    if n == 0:
        if strict:
            raise ValueError("no finite orientation values supplied")
        return float("nan"), float("nan"), 0
    r = float(math.hypot(c, s))
    mu = axial_mean_deg(deg, weights=weights, convention=convention, strict=strict)
    return mu, r, n
