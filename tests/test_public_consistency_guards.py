"""Guards against stale science re-entering the public-facing surfaces.

The v1.0.1 remediation replaced the unweighted PCA-origin locations with
raw-Celsius Tmax-weighted centroids. Everything downstream of *location*
changed: the LGCP fit, the cross-validation distances, the sector counts and
the centroid-dependent figures. These tests fail if any superseded value or
any scientifically wrong description of the heatwave definition reappears in
an active record.

Superseded values are permitted ONLY inside the explicitly historical
`legacy_unweighted_baseline` namespace of docs/CANONICAL_SCIENCE.json.
"""
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _read(rel):
    return (REPO / rel).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def canonical():
    return json.loads(_read("docs/CANONICAL_SCIENCE.json"))


# ---------------------------------------------------------------------------
# 1. The weighted results must be authoritative under the NORMAL keys
# ---------------------------------------------------------------------------
def test_lgcp_key_holds_the_weighted_fit(canonical):
    p = canonical["lgcp"]["parameters"]
    assert p["intercept"] == pytest.approx(-11.457776, abs=1e-6)
    assert p["lon"] == pytest.approx(-0.016147, abs=1e-6)
    assert p["lat"] == pytest.approx(0.066264, abs=1e-6)
    assert p["mean_tmax_z"] == pytest.approx(0.546415, abs=1e-6)
    assert p["std_tmax_z"] == pytest.approx(-0.010951, abs=1e-6)
    assert p["sigma2"] == pytest.approx(1.642911, abs=1e-6)
    assert p["scale_km"] == pytest.approx(272.455153, abs=1e-6)
    assert canonical["lgcp"]["intensity_ratio"] == pytest.approx(21.8254, abs=1e-4)


def test_cross_validation_key_holds_the_weighted_results(canonical):
    cv = canonical["cross_validation"]
    assert cv["pooled_hit_top20"] == pytest.approx(0.344737, abs=1e-6)
    assert cv["mean_dist_top20_km"] == pytest.approx(231.808, abs=1e-3)
    assert cv["median_dist_top20_km"] == pytest.approx(134.919, abs=1e-3)
    assert cv["area_weighted_rank_mean"] == pytest.approx(0.6438, abs=1e-4)
    assert cv["area_weighted_rank_median"] == pytest.approx(0.6801, abs=1e-4)
    z = cv["mean_distance_by_zone_km"]
    assert z["top10"] == pytest.approx(389.670139, abs=1e-6)
    assert z["top20"] == pytest.approx(231.807728, abs=1e-6)
    assert z["top30"] == pytest.approx(151.672110, abs=1e-6)
    assert z["top50"] == pytest.approx(69.064508, abs=1e-6)


def test_superseded_fit_is_quarantined_as_historical(canonical):
    """The unweighted baseline may survive only under the legacy namespace."""
    legacy = canonical["legacy_unweighted_baseline"]
    assert "HISTORICAL" in legacy["status"].upper()
    assert legacy["lgcp"]["parameters"]["intercept"] == pytest.approx(
        -11.352611, abs=1e-6)
    # and the staging keys must not come back
    assert "lgcp_tmax_weighted" not in canonical
    assert "cross_validation_tmax_weighted" not in canonical


def test_stale_cv_distance_tuple_absent_outside_legacy(canonical):
    """438 / 286 / 181 / 81 km were the UNWEIGHTED zone distances."""
    active = dict(canonical)
    active.pop("legacy_unweighted_baseline", None)
    blob = json.dumps(active)
    for stale in ("438", "286", "181", "81"):
        for zone in ("top10", "top20", "top30", "top50"):
            assert f'"{zone}": {stale}' not in blob
    assert canonical["cross_validation"].get("heldout_mean_distance_km") != 286
    assert canonical["cross_validation"].get("heldout_median_distance_km") != 173


def test_sector_counts_are_the_weighted_ones(canonical):
    w = canonical["sector_counts_38_48E_29_37N"]["tmax_weighted"]
    assert w["structures"] == "154/760"
    assert w["daily_largest"] == "153/395"
    assert w["event_largest"] == "19/51"


# ---------------------------------------------------------------------------
# 2. README must describe the heatwave definition correctly
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def readme_flat():
    return " ".join(_read("README.md").split()).lower()


@pytest.mark.parametrize("wrong", [
    "calendar-day 95th percentile",
    "calendar-day 95th-percentile",
    "per-calendar-day",
    "three consecutive exceedance days",
    "dbscan over the exceeding boxes",
    "dbscan groups the exceeding boxes",
])
def test_readme_rejects_wrong_heatwave_description(readme_flat, wrong):
    assert wrong not in readme_flat, f"README reintroduced: {wrong!r}"


def test_readme_states_the_correct_definition(readme_flat):
    assert "pooled across" in readme_flat and "1940" in readme_flat
    assert "greater than or equal to" in readme_flat
    assert "two consecutive" in readme_flat and "non-exceedance" in readme_flat
    assert "heatwave-labeled cells" in readme_flat
    assert "bridged" in readme_flat


def test_readme_does_not_let_dbscan_create_events(readme_flat):
    """Compound events are maximal runs of selected days, not a clustering
    product."""
    assert ("not any clustering step" in readme_flat
            or "purely temporal" in readme_flat)


# ---------------------------------------------------------------------------
# 3. The weighted-centroid reproduction stage must stay wired in
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("cfg", [
    "configs/reproduction_fast.yaml",
    "src/scorch/configs/reproduction_fast.yaml",
])
def test_weighted_centroid_stage_present(cfg):
    import yaml
    stages = yaml.safe_load(_read(cfg))["stages"]
    names = [s["name"] for s in stages]
    assert "weighted-centroids" in names, f"{cfg} dropped the weighted stage"
    assert names.index("weighted-centroids") > names.index("rebuild-catalog")


# ---------------------------------------------------------------------------
# 4. Weighting convention must not be called an "absolute" temperature level
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("rel", [
    "src/scorch/_kernel/tmax_weighted_centroid.py",
    "scripts/figures/common/tmax_weighted_centroid.py",
    "docs/CANONICAL_SCIENCE.json",
])
def test_no_absolute_temperature_wording(rel):
    t = _read(rel).lower()
    for bad in ('"absolute tmax"', "absolute observed level"):
        assert bad not in t, f"{rel} describes Celsius as an absolute level"
