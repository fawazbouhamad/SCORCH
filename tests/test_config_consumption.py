"""The configured reconstruction route must CONSUME the loaded YAML.

Every test here builds a small synthetic scenario whose configured values
deliberately DIFFER from the library-API defaults (sigma 1.25, Theta 371,
the 63-combination DBSCAN grid). If a stage silently ignored the loaded
configuration and used its built-in defaults instead, the "good config"
run of that test would fail -- so a silently-ignored configuration cannot
pass this module.

Covered controlled changes (per the V4 requirements):
  * sigma                      (stage_rebuild_catalog)
  * theta threshold            (stage_select_days_events, via run_reproduction)
  * DBSCAN eps/min_samples grids (stage_daily_dbscan_params)
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml
from conftest import complete_config

from scorch import cli, pipeline
from scorch._kernel import ellipse_pca as _ke
from scorch.dbscan_params import select_modal
from scorch.pipeline import PipelineError


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _write_yaml(path: Path, stages, parameters=None, expected_counts=None):
    """A schema-COMPLETE config (V6: every key required) with the given
    overrides merged over the canonical values."""
    config = complete_config(parameters=parameters,
                             expected_counts=expected_counts,
                             name="config-consumption-test", base_dir=".",
                             stages=stages)
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def _line_day(tmp_path, day="2001-07-01", n_cells=6):
    """One synthetic day: n_cells heatwave cells in a lon-parallel line.

    Writes reconstruction/heatwave_labels_relabelled.npz +
    selected_days_events.csv under <tmp_path>/out and returns
    (out_dir, lon_array, lat_array).
    """
    out = tmp_path / "out"
    recon = out / pipeline.RECON_SUBDIR
    recon.mkdir(parents=True, exist_ok=True)
    lon = np.arange(20.5, 20.5 + n_cells)          # 20.5 .. 25.5
    lat = np.array([30.5, 31.5])
    labels = np.zeros((1, len(lat), len(lon)), dtype=np.int16)
    labels[0, 0, :] = 1                            # all cells at lat 30.5
    np.savez_compressed(recon / pipeline.RECON_LABELS_NPZ, labels=labels,
                        dates=np.array([day], dtype="U10"), lat=lat, lon=lon)
    pd.DataFrame({"date": [day], "new_event_id": [1]}).to_csv(
        recon / pipeline.RECON_SELECTED_CSV, index=False)
    return out, lon[:], np.full(n_cells, 30.5)


# ---------------------------------------------------------------------------
# theta threshold: consumed end-to-end through run_reproduction
# ---------------------------------------------------------------------------
def _theta_fixture(tmp_path):
    """Synthetic coverage whose P97.5 'higher' threshold is 50 (NOT 371):
    20 days, three consecutive days at 50 boxes -> 3 selected days, 1 event.
    """
    out = tmp_path / "out"
    recon = out / pipeline.RECON_SUBDIR
    recon.mkdir(parents=True, exist_ok=True)
    dates = pd.date_range("2000-06-01", periods=20).strftime("%Y-%m-%d")
    n_hw = np.full(20, 5)
    n_hw[9:12] = 50                                # days 10..12
    pd.DataFrame({"date": dates, "n_hw": n_hw}).to_csv(
        recon / pipeline.RECON_COVERAGE_CSV, index=False)

    base = tmp_path / "deposit"
    sel_path = base / pipeline.SELECTED_CSV
    sel_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"date": dates[9:12], "new_event_id": [1, 1, 1]}).to_csv(
        sel_path, index=False)
    return base, out


THETA_STAGE = [{"name": "select-days-events", "kind": "builtin",
                "builtin": "select_days_events", "route": "fast"}]


def test_theta_threshold_is_read_from_the_config(tmp_path):
    """run_reproduction must verify the DERIVED Theta against the YAML
    expected_counts.theta_threshold (50, not the default 371); with it the
    synthetic scenario passes."""
    base, out = _theta_fixture(tmp_path)
    cfg = _write_yaml(tmp_path / "cfg.yaml", THETA_STAGE,
                      parameters={"bigday_quantile": 0.975,
                                  "bigday_quantile_method": "higher"},
                      expected_counts={"theta_threshold": 50,
                                       "selected_days": 3, "events": 1})
    results = cli.run_reproduction(cfg, base_dir=base, out_dir=out,
                                   route="fast")
    assert results == [("select-days-events", "ok")]


def test_changed_theta_threshold_changes_the_outcome(tmp_path):
    """A controlled change of expected_counts.theta_threshold must be
    honoured: the stage must fail citing the CONFIGURED value, not the
    default (Theta is derived from the quantile; the config records the
    expected derived value)."""
    base, out = _theta_fixture(tmp_path)
    cfg = _write_yaml(tmp_path / "cfg.yaml", THETA_STAGE,
                      parameters={"bigday_quantile": 0.975,
                                  "bigday_quantile_method": "higher"},
                      expected_counts={"theta_threshold": 57,
                                       "selected_days": 3, "events": 1})
    with pytest.raises(PipelineError, match=r"!= 57"):
        cli.run_reproduction(cfg, base_dir=base, out_dir=out, route="fast")


def test_theta_under_parameters_is_rejected(tmp_path):
    """theta_threshold is a DERIVED expected value; carrying it under
    parameters: (the pre-V5 location) must fail loudly, eliminating the
    duplicate source of truth."""
    base, out = _theta_fixture(tmp_path)
    cfg = _write_yaml(tmp_path / "cfg.yaml", THETA_STAGE,
                      parameters={"theta_threshold": 371},
                      expected_counts={"selected_days": 3, "events": 1})
    with pytest.raises(PipelineError, match="theta_threshold"):
        cli.run_reproduction(cfg, base_dir=base, out_dir=out, route="fast")


# ---------------------------------------------------------------------------
# sigma: consumed by the catalog-rebuild stage
# ---------------------------------------------------------------------------
SIGMA_CFG = 2.0                                    # deliberately NOT 1.25


def _sigma_fixture(tmp_path):
    """Deposit comparison targets built at sigma = 2.0 for one 6-cell day."""
    day = "2001-07-01"
    out, clon, clat = _line_day(tmp_path, day=day)
    recon = out / pipeline.RECON_SUBDIR
    pd.DataFrame({"new_event_id": [1], "event_global_eps_max": [1.5],
                  "event_global_minpts_used": [3]}).to_csv(
        recon / pipeline.RECON_EVENT_PARAMS_CSV, index=False)

    base = tmp_path / "deposit"
    labels_path = base / pipeline.LABELS_CSV
    labels_path.parent.mkdir(parents=True, exist_ok=True)
    # eps 1.5 / min_samples 3 on a 6-cell line: one cluster, no noise.
    pd.DataFrame({"date": [day] * 6, "new_event_id": [1] * 6,
                  "lon": clon, "lat": clat, "label": [0] * 6}).to_csv(
        labels_path, index=False)

    e = _ke.evaluate_cluster_ellipse(clon, clat, SIGMA_CFG)
    master_path = base / pipeline.MASTER_CSV
    master_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"date": day, "new_event_id": 1,
                   "centroid_lon": e["centroid_lon"],
                   "centroid_lat": e["centroid_lat"],
                   "major_axis_km": e["major_axis_km"],
                   "minor_axis_km": e["minor_axis_km"],
                   "ellipse_area_km2": e["ellipse_area_km2"],
                   "orientation_deg": e["orientation_deg"]}]).to_csv(
        master_path, index=False)
    return base, out


def _sigma_config(sigma):
    return complete_config(parameters={"sigma": sigma},
                           expected_counts={"ellipses": 1})


def test_sigma_is_read_from_the_config(tmp_path):
    """With the YAML sigma (2.0) the geometry matches targets built at 2.0.
    A stage that silently used the default 1.25 would fail here."""
    base, out = _sigma_fixture(tmp_path)
    assert pipeline.stage_rebuild_catalog(
        {}, base, out, config=_sigma_config(SIGMA_CFG)) == "ok"
    cat = pd.read_csv(out / pipeline.RECON_SUBDIR /
                      pipeline.RECON_CATALOG_CSV)
    assert float(cat.loc[0, "sigma"]) == SIGMA_CFG


def test_changed_sigma_changes_the_outcome(tmp_path):
    """A controlled sigma change (3.0 vs targets at 2.0) must propagate into
    the ellipse geometry and be caught by the comparison."""
    base, out = _sigma_fixture(tmp_path)
    with pytest.raises(PipelineError, match="differs"):
        pipeline.stage_rebuild_catalog({}, base, out,
                                       config=_sigma_config(3.0))


# ---------------------------------------------------------------------------
# DBSCAN eps / min_samples grids: consumed by the daily-parameters stage
# ---------------------------------------------------------------------------
EPS_GRID_CFG = [1.0, 2.0]                          # deliberately NOT the
MS_GRID_CFG = [2, 3]                               # canonical 7 x 9 grid


def _grids_fixture(tmp_path):
    """Master canonical_daily_* columns computed on the CONFIGURED grid."""
    day = "2001-07-01"
    out, clon, clat = _line_day(tmp_path, day=day)
    expected = select_modal(pipeline._day_grid(
        clon, clat, eps_grid=EPS_GRID_CFG, min_samples_grid=MS_GRID_CFG,
        grid_step=1.0))
    base = tmp_path / "deposit"
    master_path = base / pipeline.MASTER_CSV
    master_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"date": day, "new_event_id": 1,
                   "canonical_daily_eps": expected["avg_eps"],
                   "canonical_daily_minpts_raw":
                       expected["raw_avg_min_samples"],
                   "canonical_daily_minpts_used":
                       expected["rounded_min_samples"]}]).to_csv(
        master_path, index=False)
    return base, out


def _grids_config(eps_grid, ms_grid):
    return complete_config(
        parameters={"dbscan_eps_grid": eps_grid,
                    "dbscan_min_samples_grid": ms_grid},
        expected_counts={"selected_days": 1})


def test_dbscan_grids_are_read_from_the_config(tmp_path):
    """With the configured 2x2 grid the recomputed daily parameters match
    targets computed on that same grid. The canonical 63-combination default
    grid yields a different avg_eps here, so silently ignoring the config
    fails."""
    base, out = _grids_fixture(tmp_path)
    assert pipeline.stage_daily_dbscan_params(
        {}, base, out, config=_grids_config(EPS_GRID_CFG, MS_GRID_CFG)) \
        == "ok"
    daily = pd.read_csv(out / pipeline.RECON_SUBDIR /
                        pipeline.RECON_DAILY_PARAMS_CSV)
    # avg over the full configured grid (all combos give 1 component here)
    assert float(daily.loc[0, "avg_eps"]) == pytest.approx(
        float(np.mean(EPS_GRID_CFG)))


def test_changed_dbscan_grids_change_the_outcome(tmp_path):
    """A controlled eps-grid change ([3.0, 4.0] vs targets on [1.0, 2.0])
    must change the selected parameters and be caught."""
    base, out = _grids_fixture(tmp_path)
    with pytest.raises(PipelineError, match="daily DBSCAN parameters"):
        pipeline.stage_daily_dbscan_params(
            {}, base, out, config=_grids_config([3.0, 4.0], MS_GRID_CFG))
