"""Required automated tests for the raw-Celsius Tmax-weighted centroid stage.

Covers the remediation test matrix: weighted-average correctness, unit and
transform prohibitions (no Kelvin / abs / clip / threshold / shift /
standardize), strict validation stops, determinism, PCA-geometry invariance
under rigid translation, sigma=1.25 regression, and Appendix A lineage
isolation (Appendix A cannot consume weighted centroid fields).
"""
import ast
import json
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
COMMON = REPO / "scripts" / "figures" / "common"
sys.path.insert(0, str(COMMON))

import ellipse_pca as ep                      # noqa: E402
from tmax_weighted_centroid import (          # noqa: E402
    WeightedCentroidError, tmax_weighted_centroid, translated_axes_lonlat,
    translated_ellipse_lonlat, validate_member_weights)

SIGMA = 1.25


# ---------------------------------------------------------------------------
# Weighted-average correctness (required tests 1-6, 19)
# ---------------------------------------------------------------------------
def test_reference_example_6_7_not_5_5():
    lon = [0.0, 10.0, 0.0, 10.0]
    lat = [0.0, 0.0, 10.0, 10.0]
    w = [10.0, 20.0, 30.0, 40.0]
    r = tmax_weighted_centroid(lon, lat, w)
    assert r["lon_w"] == pytest.approx(6.0, abs=1e-12)
    assert r["lat_w"] == pytest.approx(7.0, abs=1e-12)
    assert (r["lon_w"], r["lat_w"]) != (5.0, 5.0)


def test_kelvin_conversion_would_differ_and_is_not_used():
    lon = [0.0, 10.0, 0.0, 10.0]
    lat = [0.0, 0.0, 10.0, 10.0]
    w_c = [10.0, 20.0, 30.0, 40.0]
    w_k = [v + 273.15 for v in w_c]
    r_c = tmax_weighted_centroid(lon, lat, w_c)
    r_k = tmax_weighted_centroid(lon, lat, w_k)
    assert r_c["lon_w"] != pytest.approx(r_k["lon_w"], abs=1e-9)
    assert r_c["lat_w"] != pytest.approx(r_k["lat_w"], abs=1e-9)
    src = (COMMON / "tmax_weighted_centroid.py").read_text(encoding="utf-8")
    assert "273.15" not in src


def test_equal_weights_reproduce_ordinary_centroid():
    rng = np.random.default_rng(20260704)
    lon = rng.uniform(30, 50, 17)
    lat = rng.uniform(20, 40, 17)
    r = tmax_weighted_centroid(lon, lat, np.full(17, 41.7))
    assert r["lon_w"] == pytest.approx(float(lon.mean()), abs=1e-12)
    assert r["lat_w"] == pytest.approx(float(lat.mean()), abs=1e-12)


def test_hotter_cell_pulls_centroid_toward_it():
    lon = np.array([40.0, 41.0, 42.0])
    lat = np.array([30.0, 30.0, 30.0])
    base = tmax_weighted_centroid(lon, lat, [35.0, 35.0, 35.0])
    hot = tmax_weighted_centroid(lon, lat, [35.0, 35.0, 45.0])
    assert hot["lon_w"] > base["lon_w"]


def test_reordering_cells_is_invariant():
    rng = np.random.default_rng(7)
    lon = np.unique(rng.uniform(25, 60, 60))[:40]
    lat = rng.uniform(15, 40, lon.size)
    w = rng.uniform(20, 50, lon.size)
    a = tmax_weighted_centroid(lon, lat, w)
    p = rng.permutation(lon.size)
    b = tmax_weighted_centroid(lon[p], lat[p], w[p])
    assert a["lon_w"] == pytest.approx(b["lon_w"], abs=1e-12)
    assert a["lat_w"] == pytest.approx(b["lat_w"], abs=1e-12)


def test_positive_scaling_of_weights_is_invariant():
    lon = np.array([40.0, 41.0, 44.0])
    lat = np.array([30.0, 33.0, 31.0])
    w = np.array([21.0, 34.0, 47.0])
    a = tmax_weighted_centroid(lon, lat, w)
    b = tmax_weighted_centroid(lon, lat, 3.7 * w)
    assert a["lon_w"] == pytest.approx(b["lon_w"], abs=1e-12)
    assert a["lat_w"] == pytest.approx(b["lat_w"], abs=1e-12)


def test_deterministic_repeat_calls():
    lon = np.array([40.5, 41.5, 42.5, 40.5])
    lat = np.array([30.5, 30.5, 31.5, 31.5])
    w = np.array([38.2, 41.7, 39.9, 40.1])
    assert (tmax_weighted_centroid(lon, lat, w)
            == tmax_weighted_centroid(lon, lat, w))


# ---------------------------------------------------------------------------
# Prohibited-transform guards (required tests 7-10): AST scan of the module.
# ---------------------------------------------------------------------------
def _module_calls():
    tree = ast.parse((COMMON / "tmax_weighted_centroid.py")
                     .read_text(encoding="utf-8"))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name):
                names.append(f.id)
            elif isinstance(f, ast.Attribute):
                names.append(f.attr)
    return names


def test_no_abs_clip_shift_or_standardize_calls():
    calls = _module_calls()
    banned = {"abs", "fabs", "absolute", "clip", "maximum", "clamp",
              "standardize", "zscore", "nan_to_num"}
    assert not banned.intersection(calls), (
        f"prohibited transform in weighted-centroid module: "
        f"{banned.intersection(calls)}")


def test_no_threshold_or_exceedance_in_weight_path():
    src = (COMMON / "tmax_weighted_centroid.py").read_text(encoding="utf-8")
    assert "thr_p95" not in src
    assert "exceedance_value" not in src


def test_canonical_builder_does_not_use_legacy_clipping_helper():
    src = (REPO / "scripts" / "pipeline" / "build_event_global_max_master.py"
           ).read_text(encoding="utf-8")
    assert "tmax_weighted_centroid_from_cells" not in src
    assert "safe_weighted_mean" not in src


# ---------------------------------------------------------------------------
# Strict validation stops (required tests 15-18)
# ---------------------------------------------------------------------------
def test_missing_values_fail_explicitly():
    with pytest.raises(WeightedCentroidError):
        tmax_weighted_centroid([40.0, 41.0], [30.0, 31.0], [35.0, np.nan])


def test_length_mismatch_fails_explicitly():
    with pytest.raises(WeightedCentroidError):
        tmax_weighted_centroid([40.0, 41.0], [30.0, 31.0], [35.0])


def test_duplicate_member_cells_fail_explicitly():
    with pytest.raises(WeightedCentroidError):
        tmax_weighted_centroid([40.0, 40.0], [30.0, 30.0], [35.0, 36.0])


def test_nonfinite_weight_fails_explicitly():
    with pytest.raises(WeightedCentroidError):
        tmax_weighted_centroid([40.0, 41.0], [30.0, 31.0], [35.0, np.inf])


def test_zero_or_negative_celsius_triggers_scientific_stop():
    with pytest.raises(WeightedCentroidError):
        tmax_weighted_centroid([40.0, 41.0], [30.0, 31.0], [0.0, 35.0])
    with pytest.raises(WeightedCentroidError):
        tmax_weighted_centroid([40.0, 41.0], [30.0, 31.0], [-2.0, 35.0])


def test_empty_structure_fails_explicitly():
    with pytest.raises(WeightedCentroidError):
        validate_member_weights([], [], [])


# ---------------------------------------------------------------------------
# Structure independence (required tests 11-13, kernel level)
# ---------------------------------------------------------------------------
def test_structures_weighted_independently():
    lon_a = np.array([40.0, 41.0]); lat_a = np.array([30.0, 30.0])
    lon_b = np.array([50.0, 51.0]); lat_b = np.array([20.0, 20.0])
    a1 = tmax_weighted_centroid(lon_a, lat_a, [30.0, 40.0])
    tmax_weighted_centroid(lon_b, lat_b, [45.0, 25.0])
    a2 = tmax_weighted_centroid(lon_a, lat_a, [30.0, 40.0])
    assert a1 == a2


# ---------------------------------------------------------------------------
# PCA-geometry invariance under rigid translation (required tests 20-28, 35-37)
# ---------------------------------------------------------------------------
def _synthetic_cluster():
    rng = np.random.default_rng(20260617)
    pts = set()
    while len(pts) < 20:
        pts.add((float(np.round(rng.uniform(38, 46) - 0.5) + 0.5),
                 float(np.round(rng.uniform(28, 34) - 0.5) + 0.5)))
    cells = sorted(pts)
    lon = np.array([c[0] for c in cells])
    lat = np.array([c[1] for c in cells])
    w = 30.0 + (lon - lon.min()) + 0.5 * (lat - lat.min())
    return lon, lat, w


def test_rigid_translation_preserves_all_pca_geometry():
    lon, lat, w = _synthetic_cluster()
    e0 = ep.evaluate_cluster_ellipse(lon, lat, SIGMA)
    wc = tmax_weighted_centroid(lon, lat, w)
    e1 = ep.evaluate_cluster_ellipse(lon, lat, SIGMA)
    for k in ("major_axis_km", "minor_axis_km", "ellipse_area_km2",
              "orientation_deg", "axis_ratio", "eigval_major", "eigval_minor",
              "pc1_explained_var", "centroid_lon", "centroid_lat"):
        assert e0[k] == e1[k], k
    xy = ep.project_lonlat_to_km(lon, lat, e0["centroid_lon"],
                                 e0["centroid_lat"])
    c0, v0, l0 = ep.fit_pca(xy)
    c1, v1, l1 = ep.fit_pca(xy)
    assert np.allclose(l0, l1, atol=0)
    assert (np.allclose(v0[:, 0], v1[:, 0])
            or np.allclose(v0[:, 0], -v1[:, 0]))
    # translated ellipse keeps identical km-frame relative geometry
    ex0, ey0 = ep.ellipse_points_lonlat_from_km(
        e0["centroid_lon"], e0["centroid_lat"], np.zeros(2), v0, l0, SIGMA)
    ex1, ey1 = translated_ellipse_lonlat(wc["lon_w"], wc["lat_w"], v0, l0,
                                         SIGMA)
    r0 = ep.project_lonlat_to_km(ex0, ey0, e0["centroid_lon"],
                                 e0["centroid_lat"])
    r1 = ep.project_lonlat_to_km(ex1, ey1, wc["lon_w"], wc["lat_w"])
    assert np.allclose(r0, r1, atol=1e-9)
    # axes move with the centre and keep their km length
    a_lo, a_hi, _, _ = translated_axes_lonlat(wc["lon_w"], wc["lat_w"],
                                              v0, l0, SIGMA)
    seg = ep.project_lonlat_to_km([a_lo[0], a_hi[0]], [a_lo[1], a_hi[1]],
                                  wc["lon_w"], wc["lat_w"])
    length = float(np.hypot(*(seg[1] - seg[0])))
    assert length == pytest.approx(e0["major_axis_km"], rel=1e-9)


def _same_metrics(a, b):
    """Dict equality treating NaN == NaN (unused weighted fields are NaN)."""
    assert a.keys() == b.keys()
    for k in a:
        va, vb = a[k], b[k]
        if isinstance(va, float) and np.isnan(va):
            assert isinstance(vb, float) and np.isnan(vb), k
        else:
            assert va == vb, k


def test_changing_tmax_changes_only_weighted_location():
    lon, lat, w = _synthetic_cluster()
    e_before = ep.evaluate_cluster_ellipse(lon, lat, SIGMA)
    w2 = w.copy(); w2[0] += 15.0                     # dramatic synthetic change
    wc1 = tmax_weighted_centroid(lon, lat, w)
    wc2 = tmax_weighted_centroid(lon, lat, w2)
    e_after = ep.evaluate_cluster_ellipse(lon, lat, SIGMA)
    assert (wc1["lon_w"], wc1["lat_w"]) != (wc2["lon_w"], wc2["lat_w"])
    _same_metrics(e_before, e_after)                 # geometry blind to Tmax


def test_arbitrary_downstream_location_cannot_alter_pca_stage():
    lon, lat, _ = _synthetic_cluster()
    e0 = ep.evaluate_cluster_ellipse(lon, lat, SIGMA)
    translated_ellipse_lonlat(99.0, -45.0, np.eye(2),
                              np.array([4.0, 1.0]), SIGMA)
    e1 = ep.evaluate_cluster_ellipse(lon, lat, SIGMA)
    _same_metrics(e0, e1)


def test_weighted_centroid_inside_bbox_for_positive_weights():
    lon, lat, w = _synthetic_cluster()
    wc = tmax_weighted_centroid(lon, lat, w)
    assert lon.min() <= wc["lon_w"] <= lon.max()
    assert lat.min() <= wc["lat_w"] <= lat.max()


# ---------------------------------------------------------------------------
# sigma = 1.25 regression (required test 33)
# ---------------------------------------------------------------------------
def test_sigma_remains_exactly_1_25_everywhere():
    import common as C
    assert C.SIGMA == 1.25
    if str(REPO / "src") not in sys.path:
        sys.path.insert(0, str(REPO / "src"))
    from scorch.ellipses import SIGMA_DEFAULT
    assert SIGMA_DEFAULT == 1.25
    sci = (REPO / "docs" / "CANONICAL_SCIENCE.json").read_text(
        encoding="utf-8")
    data = json.loads(sci)
    assert "1.25" in sci
    assert data  # parseable


# ---------------------------------------------------------------------------
# Appendix A lineage isolation (required tests 34, 36, 37, 40)
# ---------------------------------------------------------------------------
WEIGHTED_FIELDS = ("centroid_lon_tmax_weighted", "centroid_lat_tmax_weighted",
                   "weighted_centroid_lon", "weighted_centroid_lat",
                   "tmax_weighted_centroid", "weight_sum")


def _source(path):
    return path.read_text(encoding="utf-8", errors="replace")


def test_appendix_a_scripts_cannot_read_weighted_fields():
    figA1 = REPO / "scripts" / "figures" / "figA1"
    for py in sorted(figA1.glob("*.py")):
        src = _source(py)
        for field in WEIGHTED_FIELDS:
            assert field not in src, f"{py.name} references {field}"
        assert "tmax_weighted_centroid" not in src


def test_appendix_a_inputs_are_the_frozen_sigma_matrices():
    inputs = sorted((REPO / "scripts" / "figures" / "figA1_inputs")
                    .glob("*.csv"))
    assert len(inputs) == 4
    src = _source(REPO / "scripts" / "figures" / "figA1" /
                  "make_figA1_sigma_matrices.py")
    joined = src + _source(REPO / "scripts" / "figures" / "figA1" /
                           "make_figA1_sigma_sensitivity.py")
    assert "figA1_inputs" in joined or all(f.name in joined for f in inputs)


def test_upstream_stages_do_not_import_weighted_module():
    upstream = [
        REPO / "scripts" / "figures" / "common" / "clustering.py",
        REPO / "scripts" / "figures" / "common" / "ellipse_pca.py",
        REPO / "src" / "scorch" / "clustering.py",
        REPO / "src" / "scorch" / "_kernel" / "clustering.py",
        REPO / "src" / "scorch" / "_kernel" / "ellipse_pca.py",
        REPO / "src" / "scorch" / "selection.py",
        REPO / "src" / "scorch" / "thresholds.py",
        REPO / "src" / "scorch" / "labeling.py",
        REPO / "src" / "scorch" / "typology.py",
    ]
    for py in upstream:
        # the frozen kernel retains the LEGACY (unused, clipping) helper name
        # tmax_weighted_centroid_from_cells; only imports of the NEW stage
        # module are prohibited upstream.
        src = _source(py).replace("tmax_weighted_centroid_from_cells", "")
        assert "import tmax_weighted_centroid" not in src, (
            f"upstream stage {py} imports the weighted-centroid stage")
        assert "from tmax_weighted_centroid" not in src
        for field in ("centroid_lon_tmax_weighted",
                      "centroid_lat_tmax_weighted"):
            assert field not in src


def test_kernel_copies_are_byte_identical():
    a = (REPO / "src" / "scorch" / "_kernel" / "tmax_weighted_centroid.py"
         ).read_bytes()
    b = (COMMON / "tmax_weighted_centroid.py").read_bytes()
    assert a == b
