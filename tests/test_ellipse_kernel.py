"""Kernel geometry tests: variance floor, sigma scaling, no axis floor."""
import math
import re
from pathlib import Path

import numpy as np
import pytest

from scorch.ellipses import fit_pca_ellipses, SIGMA_DEFAULT
from scorch._kernel import ellipse_pca as kernel


def test_variance_floor_tiny_cluster():
    # A nearly-degenerate cluster: raw eigenvalues far below 1.0 km^2, so both
    # are floored and the semi-axes become exactly sigma * sqrt(1.0) km.
    lon = np.array([40.0, 40.001, 40.002])
    lat = np.array([30.0, 30.0, 30.0])
    sigma = SIGMA_DEFAULT
    res = fit_pca_ellipses((lon, lat), sigma=sigma)
    assert res is not None
    # Raw eigenvalues reported unfloored (both < 1.0 km^2 here).
    assert res["eigval_major"] < 1.0
    assert res["eigval_minor"] < 1.0
    # Geometry floored: semi-axes = sigma * sqrt(max(eig, 1.0)) = sigma.
    assert res["major_axis_km"] == pytest.approx(2.0 * sigma)
    assert res["minor_axis_km"] == pytest.approx(2.0 * sigma)
    assert res["ellipse_area_km2"] == pytest.approx(math.pi * sigma * sigma)


def test_variance_floor_collinear_minor_axis():
    # Perfectly collinear cluster: minor eigenvalue 0 -> floored to 1.0 km^2.
    lon = np.array([40.0, 41.0, 42.0, 43.0])
    lat = np.array([30.0, 30.0, 30.0, 30.0])
    sigma = 2.0
    res = fit_pca_ellipses((lon, lat), sigma=sigma)
    assert res["eigval_minor"] == pytest.approx(0.0, abs=1e-9)
    assert res["minor_axis_km"] == pytest.approx(2.0 * sigma * math.sqrt(1.0))
    assert res["major_axis_km"] > res["minor_axis_km"]


def test_sigma_scaling_area_exact():
    # Area scales exactly as sigma^2 (for eigenvalues above the floor).
    rng = np.random.default_rng(20260617)
    lon = 40.0 + rng.normal(scale=2.0, size=60)
    lat = 30.0 + rng.normal(scale=1.0, size=60)
    r1 = fit_pca_ellipses((lon, lat), sigma=1.25)
    r2 = fit_pca_ellipses((lon, lat), sigma=2.5)
    assert r1["eigval_minor"] > 1.0  # floor not active for this cluster
    assert r2["ellipse_area_km2"] / r1["ellipse_area_km2"] == pytest.approx(
        (2.5 / 1.25) ** 2, rel=1e-12)
    # Axes scale linearly with sigma; orientation is sigma-invariant.
    assert r2["major_axis_km"] / r1["major_axis_km"] == pytest.approx(2.0)
    assert r2["orientation_deg"] == pytest.approx(r1["orientation_deg"])


def test_no_axis_floor_in_package_source():
    # The packaged kernel must retain the variance floor but define no active
    # axis floor (the historical _AXIS_FLOOR was removed 2026-07-28; only a
    # comment documenting the removal may mention its name).
    src = Path(kernel.__file__).read_text(encoding="utf-8")
    assert re.search(r"^_VAR_FLOOR\s*=\s*1\.0", src, re.M), \
        "variance floor _VAR_FLOOR = 1.0 must be present"
    assert re.search(r"^\s*_AXIS_FLOOR\s*=", src, re.M) is None, \
        "no _AXIS_FLOOR assignment may exist in the canonical kernel"
    assert kernel._VAR_FLOOR == 1.0
    assert not hasattr(kernel, "_AXIS_FLOOR")
