#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression tests for the Figure A sigma-sensitivity matrices (v1.0.0 pre-release correction).

Before the v1.0.0 pre-release correction the release shipped only the FROZEN derived matrices at
``scripts/figures/figA1_inputs/`` and the Figure A renderer re-rendered them.
Re-rendering archived numbers is not reproduction. The real producer was
recovered and sanitized as ``scripts/figures/figA1/make_figA1_sigma_matrices.py``.

These tests prove the producer regenerates all four 9x9 matrices
**byte-identically** from the deposit, and pin the scientific constants that the
sigma selection rests on.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import sys

import numpy as np
import pandas as pd
import pytest

_TESTS = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_TESTS)
_FIGS = os.path.join(_ROOT, "scripts", "figures")
_FROZEN = os.path.join(_FIGS, "figA1_inputs")
_PRODUCER = os.path.join(_FIGS, "figA1", "make_figA1_sigma_matrices.py")

SIGMAS = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5]
MATRICES = ["minimum", "maximum", "average", "combined"]

#: The one-scalar selection constant. Displayed as 205 in the figure.
COMBINED_AT_1P25 = 204.5440673062212
SELECTED_SIGMA = 1.25
EXPECTED_COMPONENTS = 760

#: SHA-256 of the frozen release inputs, which the producer must reproduce.
EXPECTED_SHA256 = {
    "minimum": "89890a9459ed19e427bc64c45c366e035ab178eec7da1e59c5ddde24de92e61c",
    "maximum": "a7eb107c7d2dbc1de6a515c165b8a31f63f3e9e229c15b776167bbbd0d9c84b7",
    "average": "4d52067b61862e0e796de827ca08bb4e27b9aaed9f0ad2fd09d92e1c4bd233c5",
    "combined": "03cf1cc4b1e53043b0b7c5e0dfb4b627ceeffad352dd1b32db5dc59b9542045d",
}


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _frozen(name):
    return os.path.join(_FROZEN, f"pca_sigma_matrix_{name}.csv")


def _read_matrix(path):
    df = pd.read_csv(path, index_col=0)
    df.columns = [float(c) for c in df.columns]
    return df


# ---------------------------------------------------------------------------
# Constants pinned against the frozen inputs (always runnable)
# ---------------------------------------------------------------------------
def test_frozen_matrices_present_and_square():
    for name in MATRICES:
        df = _read_matrix(_frozen(name))
        assert df.shape == (9, 9), f"{name} must be 9x9, got {df.shape}"
        assert [float(i) for i in df.index] == SIGMAS
        assert list(df.columns) == SIGMAS


def test_combined_equals_min_plus_max_plus_average():
    """The one-scalar score is Min + Max + Average -- not a weighted blend."""
    mn = _read_matrix(_frozen("minimum")).to_numpy()
    mx = _read_matrix(_frozen("maximum")).to_numpy()
    av = _read_matrix(_frozen("average")).to_numpy()
    cb = _read_matrix(_frozen("combined")).to_numpy()
    assert np.allclose(cb, mn + mx + av, atol=1e-12)


def test_combined_score_at_selected_sigma():
    cb = _read_matrix(_frozen("combined"))
    assert cb.loc[SELECTED_SIGMA, SELECTED_SIGMA] == pytest.approx(
        COMBINED_AT_1P25, abs=1e-10)
    assert round(cb.loc[SELECTED_SIGMA, SELECTED_SIGMA]) == 205


def test_selected_sigma_is_max_of_equal_sigma_diagonal():
    """sigma = 1.25 must win ON THE DIAGONAL -- that is the selection rule."""
    cb = _read_matrix(_frozen("combined"))
    diag = np.array([cb.loc[s, s] for s in SIGMAS])
    best = SIGMAS[int(diag.argmax())]
    assert best == SELECTED_SIGMA, f"diagonal maximum moved to sigma={best}"
    assert diag.max() == pytest.approx(COMBINED_AT_1P25, abs=1e-10)
    # The runner-up must be strictly lower, so the choice is unambiguous.
    ordered = np.sort(diag)[::-1]
    assert ordered[0] > ordered[1], "diagonal maximum is not strict"


def test_off_diagonal_optimum_is_reference_only():
    """A higher off-diagonal cell exists and is NOT an inconsistency.

    The one-scalar algorithm selects an equal-sigma pair by design. Recording
    this here stops the higher off-diagonal number being mistaken for a defect.
    """
    cb = _read_matrix(_frozen("combined"))
    arr = cb.to_numpy()
    fi, fj = np.unravel_index(int(arr.argmax()), arr.shape)
    assert (SIGMAS[fi], SIGMAS[fj]) == (1.5, 0.75)
    assert arr[fi, fj] > COMBINED_AT_1P25
    assert fi != fj, "off-diagonal optimum must be off-diagonal"


def test_variance_floor_retained_and_no_separate_axis_floor():
    """1 km^2 variance floor kept; the separate semi-axis floor must stay gone."""
    sys.path.insert(0, os.path.join(_FIGS, "common"))
    import ellipse_pca as ep
    assert ep._VAR_FLOOR == 1.0
    assert not hasattr(ep, "_AXIS_FLOOR"), \
        "a separate semi-axis floor was reintroduced; it changes ellipse geometry"
    # Area must scale exactly as sigma^2 once no axis floor can bind.
    a1, b1 = ep.ellipse_semi_axes_km([4.0, 1.0], 1.0)
    a2, b2 = ep.ellipse_semi_axes_km([4.0, 1.0], 2.0)
    assert a2 == pytest.approx(2 * a1) and b2 == pytest.approx(2 * b1)


# ---------------------------------------------------------------------------
# End-to-end regeneration (needs the deposit)
# ---------------------------------------------------------------------------
def _load_producer():
    spec = importlib.util.spec_from_file_location("figA_producer", _PRODUCER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["figA_producer"] = mod
    spec.loader.exec_module(mod)
    return mod


def _deposit_available():
    if not os.path.exists(_PRODUCER):
        return False
    try:
        mod = _load_producer()
    except Exception:
        return False
    return os.path.exists(mod.LABELS)


@pytest.mark.skipif(not _deposit_available(),
                    reason="processed-data deposit not available (set SCORCH_DATA_DIR)")
def test_matrices_regenerate_byte_identically(tmp_path):
    """The producer must reproduce the frozen release inputs byte for byte."""
    mod = _load_producer()
    mod.OUT = str(tmp_path)
    mod.main()
    for name in MATRICES:
        produced = os.path.join(str(tmp_path), f"pca_sigma_matrix_{name}.csv")
        assert os.path.exists(produced), f"producer did not emit {name}"
        got = _sha256(produced)
        assert got == EXPECTED_SHA256[name], (
            f"{name} matrix is no longer byte-identical to the frozen release "
            f"input\n  produced {got}\n  expected {EXPECTED_SHA256[name]}")
        assert got == _sha256(_frozen(name))


@pytest.mark.skipif(not _deposit_available(),
                    reason="processed-data deposit not available (set SCORCH_DATA_DIR)")
def test_component_count_is_760():
    """The sensitivity is computed over the full 760-structure catalog."""
    mod = _load_producer()
    lab = pd.read_csv(mod.LABELS)
    lab["date"] = lab["date"].astype(str)
    n = sum(1 for (_d, label), _g in lab.groupby(["date", "label"])
            if int(label) != mod.NOISE)
    assert n == EXPECTED_COMPONENTS, f"expected 760 components, got {n}"


@pytest.mark.skipif(not _deposit_available(),
                    reason="processed-data deposit not available (set SCORCH_DATA_DIR)")
def test_producer_sigma_grid_unchanged():
    mod = _load_producer()
    assert mod.SIGMAS == SIGMAS
