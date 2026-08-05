#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the canonical axial-orientation statistics (scripts/figures/common/scorch_axial.py).

These tests encode the four acceptance criteria of Correction 1 of the SCORCH
the v1.0.0 pre-release correction alignment programme, plus the properties that make the doubled-angle mean
the *correct* statistic for 180 deg-periodic data.

The regression that motivated this module: the superseded pre-release
manuscript Figure 9 candidate averaged event
orientations arithmetically. For Event 4 that produced -21.101 deg where the
correct axial mean is +68.985 deg -- a ~90 deg error, the maximum possible for an
axial quantity.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "scripts", "figures", "common"))

import scorch_axial as ax  # noqa: E402

# Resolve the catalog through the release path helper so these checks run
# against the versioned processed-data deposit (honours SCORCH_DATA_DIR).
try:
    from _clean_paths import MASTER_CSV
except Exception:  # pragma: no cover - helper unavailable outside the release
    MASTER_CSV = os.path.join(
        _REPO, "data",
        "scorch_new_algorithm_master_cluster_ellipse_event_global_max.csv")

# Event 4's six structure orientations, legacy catalog convention
# (counterclockwise from east, [0, 180)). Kept inline so the core acceptance
# test does not depend on data-file availability; test_event4_matches_catalog
# additionally verifies these against the real catalog.
EVENT4_EAST_CCW = [
    173.9412887267695, 50.01512076564877, 174.75114468076768,
    51.07144886174977, 172.27663718739635, 44.55262860043584,
]
EVENT4_EXPECTED_NORTH_CW = 68.985327547659


# ---------------------------------------------------------------------------
# The four mandated acceptance criteria
# ---------------------------------------------------------------------------
def test_plus89_minus89_gives_axis_near_90_not_zero():
    """(+89, -89) must yield an axis near +/-90, NOT 0.

    This is the canonical failure of arithmetic averaging: the arithmetic mean
    is exactly 0 deg, which is perpendicular to both inputs -- the worst possible
    answer. The two axes are 2 deg apart across the +/-90 wrap, so their mean
    axis must lie next to them, not perpendicular.
    """
    mu = ax.axial_mean_deg([89.0, -89.0])
    assert abs(abs(mu) - 90.0) < 1e-9, f"expected an axis near +/-90, got {mu}"
    assert abs(mu) > 45.0, f"axial mean collapsed toward 0 (got {mu}) -- arithmetic bug"
    # Explicitly contrast with the invalid statistic this module replaces.
    assert np.mean([89.0, -89.0]) == pytest.approx(0.0)


def test_invariance_under_adding_180_to_any_input():
    """Adding 180 deg to any subset of inputs must not change the axial mean.

    180 deg is a relabelling of the same physical axis, so any statistic that
    changes under it is not measuring the axis.
    """
    base = [10.0, 20.0, 35.0, 170.0, 91.5]
    expected = ax.axial_mean_deg(base)
    rng = np.random.default_rng(20260804)
    for _ in range(64):
        shifted = [
            v + 180.0 * int(bit) for v, bit in zip(base, rng.integers(0, 2, len(base)))
        ]
        assert ax.axial_mean_deg(shifted) == pytest.approx(expected, abs=1e-12)
    # Also invariant under a bulk -180 shift.
    assert ax.axial_mean_deg([v - 180.0 for v in base]) == pytest.approx(
        expected, abs=1e-12)


def test_ten_and_twenty_give_fifteen():
    """(10, 20) -> 15: the axial mean agrees with intuition for nearby axes."""
    assert ax.axial_mean_deg([10.0, 20.0]) == pytest.approx(15.0, abs=1e-12)


def test_event4_axial_mean_matches_canonical_expectation():
    """Event 4 -> +68.985327547659 deg in the manuscript convention.

    This is the value the corrected Figure 9 must report. The legacy arithmetic
    mean gives -21.101 deg.
    """
    mu = ax.axial_mean_deg(EVENT4_EAST_CCW, convention="north_cw")
    assert mu == pytest.approx(EVENT4_EXPECTED_NORTH_CW, abs=1e-9)
    # Guard against silently reintroducing the arithmetic aggregation.
    legacy = ax.wrap_axis_north_cw(90.0 - np.mean(EVENT4_EAST_CCW))
    assert abs(mu - float(legacy)) > 80.0, "axial and arithmetic results agree -- bug"


# ---------------------------------------------------------------------------
# Convention conversion
# ---------------------------------------------------------------------------
def test_east_ccw_to_north_cw_roundtrip():
    vals = np.array([0.0, 22.15313058041517, 45.0, 89.9, 90.0, 179.5471884424739])
    back = ax.north_cw_to_east_ccw(ax.east_ccw_to_north_cw(vals))
    assert np.allclose(back, ax.wrap_axis_east_ccw(vals), atol=1e-12)


def test_north_cw_range_is_half_open_at_minus90():
    """Range is (-90, 90]: an east-west axis reports +90, never -90."""
    for v in (-90.0, 90.0, 270.0, -270.0):
        out = ax.wrap_axis_north_cw(v)
        assert -90.0 < out <= 90.0
        assert out == pytest.approx(90.0)


def test_east_ccw_range_is_half_open_at_180():
    for v in (0.0, 180.0, 360.0, -180.0):
        out = ax.wrap_axis_east_ccw(v)
        assert 0.0 <= out < 180.0
        assert out == pytest.approx(0.0)


def test_conversion_commutes_with_axial_mean():
    """mean(convert(x)) == convert(mean(x)) -- both orders are valid."""
    a = ax.axial_mean_deg(EVENT4_EAST_CCW, convention="north_cw")
    b = ax.axial_mean_deg(ax.east_ccw_to_north_cw(np.array(EVENT4_EAST_CCW)))
    assert a == pytest.approx(b, abs=1e-12)


# ---------------------------------------------------------------------------
# Wrapping, missing values, resultant length
# ---------------------------------------------------------------------------
def test_nan_inputs_are_ignored_not_treated_as_zero():
    clean = [10.0, 20.0]
    withnan = [10.0, np.nan, 20.0, np.nan]
    assert ax.axial_mean_deg(withnan) == pytest.approx(
        ax.axial_mean_deg(clean), abs=1e-12)


def test_all_nan_returns_nan_and_can_raise_in_strict_mode():
    assert np.isnan(ax.axial_mean_deg([np.nan, np.nan]))
    assert np.isnan(ax.axial_resultant_length([np.nan]))
    with pytest.raises(ValueError):
        ax.axial_mean_deg([np.nan], strict=True)


def test_empty_input_returns_nan():
    assert np.isnan(ax.axial_mean_deg([]))
    mu, r, n = ax.axial_mean_and_resultant([])
    assert np.isnan(mu) and np.isnan(r) and n == 0


def test_resultant_length_bounds_and_extremes():
    assert ax.axial_resultant_length([30.0, 30.0, 30.0]) == pytest.approx(1.0, abs=1e-12)
    # Two perpendicular axes cancel exactly under doubling.
    assert ax.axial_resultant_length([0.0, 90.0]) == pytest.approx(0.0, abs=1e-12)
    for vals in ([10.0, 20.0], EVENT4_EAST_CCW, [0.0, 45.0, 90.0, 135.0]):
        assert 0.0 <= ax.axial_resultant_length(vals) <= 1.0 + 1e-12


def test_degenerate_direction_returns_nan_and_can_raise():
    """Perpendicular axes have no identifiable mean -- do not invent one."""
    assert np.isnan(ax.axial_mean_deg([0.0, 90.0]))
    with pytest.raises(ValueError):
        ax.axial_mean_deg([0.0, 90.0], strict=True)


def test_event4_resultant_length():
    mu, r, n = ax.axial_mean_and_resultant(EVENT4_EAST_CCW, convention="north_cw")
    assert n == 6
    assert r == pytest.approx(0.5734944904104495, abs=1e-12)
    assert mu == pytest.approx(EVENT4_EXPECTED_NORTH_CW, abs=1e-9)


def test_single_value_is_its_own_axial_mean():
    for v in (0.0, 12.5, 179.9):
        assert ax.axial_mean_deg([v], convention="east_ccw") == pytest.approx(
            ax.wrap_axis_east_ccw(v), abs=1e-12)


def test_weights_reduce_to_repetition():
    """Integer weights must equal repeating the observations."""
    vals, w = [10.0, 40.0], [3.0, 1.0]
    repeated = [10.0, 10.0, 10.0, 40.0]
    assert ax.axial_mean_deg(vals, weights=w) == pytest.approx(
        ax.axial_mean_deg(repeated), abs=1e-12)


def test_rotation_equivariance():
    """Rotating every axis by d rotates the mean by d -- arithmetic means fail this."""
    base = [170.0, 175.0, 5.0, 10.0]      # straddles the wrap
    mu0 = ax.axial_mean_deg(base, convention="east_ccw")
    for d in (7.0, 33.0, 91.0, 150.0):
        mud = ax.axial_mean_deg([v + d for v in base], convention="east_ccw")
        assert mud == pytest.approx(
            float(ax.wrap_axis_east_ccw(mu0 + d)), abs=1e-9)


def test_invalid_convention_and_bad_weights_raise():
    with pytest.raises(ValueError):
        ax.axial_mean_deg([1.0, 2.0], convention="nonsense")
    with pytest.raises(ValueError):
        ax.axial_mean_deg([1.0, 2.0], weights=[1.0])
    with pytest.raises(ValueError):
        ax.axial_mean_deg([1.0, 2.0], weights=[0.0, 0.0])


# ---------------------------------------------------------------------------
# Catalog-backed check
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not os.path.exists(MASTER_CSV),
                    reason="event-global-max master catalog not available")
def test_event4_matches_catalog():
    """The inlined Event 4 angles really are the catalog's, and reproduce the value."""
    import pandas as pd
    df = pd.read_csv(MASTER_CSV)
    theta = df.loc[df["event_id"] == 4, "orientation_deg"].astype(float).to_numpy()
    assert theta.size == 6
    assert np.allclose(np.sort(theta), np.sort(EVENT4_EAST_CCW), atol=1e-6)
    assert ax.axial_mean_deg(theta, convention="north_cw") == pytest.approx(
        EVENT4_EXPECTED_NORTH_CW, abs=1e-9)


@pytest.mark.skipif(not os.path.exists(MASTER_CSV),
                    reason="event-global-max master catalog not available")
def test_catalog_orientation_convention_is_east_ccw():
    """orientation_deg is CCW-from-east: it must equal atan2(pc1_vec_y, pc1_vec_x)."""
    import pandas as pd
    df = pd.read_csv(MASTER_CSV)
    derived = np.degrees(np.arctan2(df["pc1_vec_y"].to_numpy(float),
                                    df["pc1_vec_x"].to_numpy(float)))
    assert np.allclose(ax.wrap_axis_east_ccw(derived),
                       ax.wrap_axis_east_ccw(df["orientation_deg"].to_numpy(float)),
                       atol=1e-6)


@pytest.mark.skipif(not os.path.exists(MASTER_CSV),
                    reason="event-global-max master catalog not available")
def test_catalog_shape_invariants():
    """Frozen scientific invariants that must not drift."""
    import pandas as pd
    df = pd.read_csv(MASTER_CSV)
    assert len(df) == 760
    assert df["event_id"].nunique() == 51
    assert df["date"].nunique() == 395
    assert df.groupby("type")["event_id"].nunique().tolist() == [3, 4, 20, 24]
    days = df.groupby("type")["date"].nunique().tolist()
    assert days == [3, 4, 75, 313], "selected event-days per type must be 3/4/75/313"
