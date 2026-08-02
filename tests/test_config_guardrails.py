"""V6 configuration guardrails: variance floor, expected counts, fixed rules.

Five families of adversarial guarantees:

  1. ``var_floor_km2`` is CONSUMED by the PCA ellipse path: a deliberately
     different variance floor changes the geometry (good-config runs use a
     non-default floor, so a silently ignored floor cannot pass) and a
     mismatched floor causes a comparison failure.
  2. The final ``validate-deposited-catalog`` stage takes its expected
     totals (rows/ellipses, events, dates, type counts) from the YAML
     ``expected_counts:``; deliberately wrong configured counts FAIL.
  3. The canonical categorical rules under ``fixed_rules:`` admit exactly
     one supported value each; any other value fails loudly.
  4. Unsupported operative parameters and unknown config sections are
     rejected -- no algorithm-affecting field can be silently ignored.
  5. The schema is COMPLETE: every operative parameter, fixed rule and
     expected count is REQUIRED. A config that omits one (or a section, or
     is empty) fails loudly instead of silently running on module defaults.
"""
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from conftest import complete_config

from scorch import catalog as cat
from scorch import cli, pipeline
from scorch._kernel import ellipse_pca as _ke
from scorch.pipeline import ConfigError, PipelineError

DAY = "2001-07-01"
VAR_FLOOR_CFG = 400.0                       # deliberately NOT the default 1.0


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _line_day(tmp_path, n_cells=6):
    """One synthetic day: n_cells heatwave cells in a lon-parallel line.

    Perfectly collinear, so the minor eigenvalue is 0 and the variance floor
    ALWAYS binds on the minor axis: minor_axis = 2 * sigma * sqrt(floor).
    """
    out = tmp_path / "out"
    recon = out / pipeline.RECON_SUBDIR
    recon.mkdir(parents=True, exist_ok=True)
    lon = np.arange(20.5, 20.5 + n_cells)
    lat = np.array([30.5, 31.5])
    labels = np.zeros((1, len(lat), len(lon)), dtype=np.int16)
    labels[0, 0, :] = 1
    np.savez_compressed(recon / pipeline.RECON_LABELS_NPZ, labels=labels,
                        dates=np.array([DAY], dtype="U10"), lat=lat, lon=lon)
    pd.DataFrame({"date": [DAY], "new_event_id": [1]}).to_csv(
        recon / pipeline.RECON_SELECTED_CSV, index=False)
    pd.DataFrame({"new_event_id": [1], "event_global_eps_max": [1.5],
                  "event_global_minpts_used": [3]}).to_csv(
        recon / pipeline.RECON_EVENT_PARAMS_CSV, index=False)
    return out, lon[:], np.full(n_cells, 30.5)


def _floor_fixture(tmp_path, target_floor):
    """Deposit comparison targets built at the GIVEN variance floor."""
    out, clon, clat = _line_day(tmp_path)
    base = tmp_path / "deposit"
    labels_path = base / pipeline.LABELS_CSV
    labels_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"date": [DAY] * 6, "new_event_id": [1] * 6,
                  "lon": clon, "lat": clat, "label": [0] * 6}).to_csv(
        labels_path, index=False)
    e = _ke.evaluate_cluster_ellipse(clon, clat, 1.25,
                                     var_floor=target_floor)
    master_path = base / pipeline.MASTER_CSV
    master_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"date": DAY, "new_event_id": 1,
                   "centroid_lon": e["centroid_lon"],
                   "centroid_lat": e["centroid_lat"],
                   "major_axis_km": e["major_axis_km"],
                   "minor_axis_km": e["minor_axis_km"],
                   "ellipse_area_km2": e["ellipse_area_km2"],
                   "orientation_deg": e["orientation_deg"]}]).to_csv(
        master_path, index=False)
    return base, out


def _floor_config(var_floor):
    return complete_config(parameters={"var_floor_km2": var_floor},
                           expected_counts={"ellipses": 1})


# ---------------------------------------------------------------------------
# 1. variance floor: consumed by the PCA ellipse path
# ---------------------------------------------------------------------------
def test_var_floor_kernel_geometry():
    """The kernel floors the minor eigenvalue to the REQUESTED var_floor:
    for a collinear cluster minor_axis = 2 * sigma * sqrt(floor)."""
    lon = np.array([40.0, 41.0, 42.0, 43.0])
    lat = np.array([30.0, 30.0, 30.0, 30.0])
    sigma = 2.0
    default = _ke.evaluate_cluster_ellipse(lon, lat, sigma)
    floored = _ke.evaluate_cluster_ellipse(lon, lat, sigma,
                                           var_floor=VAR_FLOOR_CFG)
    assert default["minor_axis_km"] == pytest.approx(2.0 * sigma)
    assert floored["minor_axis_km"] == pytest.approx(
        2.0 * sigma * math.sqrt(VAR_FLOOR_CFG))
    # A different floor MUST change the geometry.
    assert floored["minor_axis_km"] != default["minor_axis_km"]
    assert floored["ellipse_area_km2"] > default["ellipse_area_km2"]


def test_var_floor_is_read_from_the_config(tmp_path):
    """With the YAML var_floor_km2 (400, non-default) the geometry matches
    targets built at that same floor. A stage that silently used the
    default 1.0 would fail here (the cluster is collinear, so the floor
    always binds on the minor axis)."""
    base, out = _floor_fixture(tmp_path, VAR_FLOOR_CFG)
    assert pipeline.stage_rebuild_catalog(
        {}, base, out, config=_floor_config(VAR_FLOOR_CFG)) == "ok"
    catdf = pd.read_csv(out / pipeline.RECON_SUBDIR /
                        pipeline.RECON_CATALOG_CSV)
    assert float(catdf.loc[0, "minor_axis_km"]) == pytest.approx(
        2.0 * 1.25 * math.sqrt(VAR_FLOOR_CFG))


def test_changed_var_floor_changes_the_outcome(tmp_path):
    """A deliberately different variance floor (default 1.0 vs targets at
    400) must propagate into the geometry and be caught by the comparison --
    a silently ignored floor must not pass."""
    base, out = _floor_fixture(tmp_path, VAR_FLOOR_CFG)
    with pytest.raises(PipelineError, match="differs"):
        pipeline.stage_rebuild_catalog({}, base, out,
                                       config=_floor_config(1.0))


# ---------------------------------------------------------------------------
# 2. final expected counts: the validate-catalog stage uses the YAML
# ---------------------------------------------------------------------------
def _synthetic_master(tmp_path):
    """Minimal schema-complete master catalog: 3 rows, 2 events, 3 dates,
    type counts {1: 1, 2: 1}."""
    rows = []
    for date, event, v3 in ((DAY, 1, 1), ("2001-07-02", 1, 1),
                            ("2001-07-10", 2, 2)):
        row = {}
        for col in cat.MASTER_COLUMNS:
            if col == "date":
                row[col] = date
            elif col in ("event_type_name",):
                row[col] = f"type-{v3}"
            elif col in ("event_type", "event_type_original", "type"):
                row[col] = v3
            elif col == "v3_type":
                row[col] = v3
            elif col in ("new_event_id", "event_id"):
                row[col] = event
            elif col in cat.MASTER_INT_COLUMNS:
                row[col] = 1
            else:
                row[col] = 1.0
        rows.append(row)
    df = pd.DataFrame(rows, columns=cat.MASTER_COLUMNS)
    base = tmp_path / "deposit"
    master_path = base / pipeline.MASTER_CSV
    master_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(master_path, index=False)
    return base


GOOD_COUNTS = {"ellipses": 3, "events": 2, "selected_days": 3,
               "type_counts": {1: 1, 2: 1}}
VALIDATE_STAGE = {"name": "validate-deposited-catalog",
                  "inputs": {"master_csv": pipeline.MASTER_CSV},
                  "params": {"expect_canonical_counts": True}}


def test_validate_catalog_uses_yaml_expected_counts(tmp_path):
    """The stage must take its totals from expected_counts: -- with the
    correct configured counts (which differ from the canonical constants
    760/51/395) the synthetic catalog PASSES; falling back to the module
    constants would fail."""
    base = _synthetic_master(tmp_path)
    assert cli._builtin_validate_catalog(
        VALIDATE_STAGE, base,
        config=complete_config(expected_counts=GOOD_COUNTS)) == "ok"


@pytest.mark.parametrize("bad", [
    {"ellipses": 4},                      # wrong rows/ellipses
    {"events": 3},                        # wrong events
    {"selected_days": 5},                 # wrong dates
    {"type_counts": {1: 2, 2: 1}},        # wrong type counts
])
def test_wrong_configured_counts_fail(tmp_path, bad):
    """Deliberately incorrect configured counts must FAIL the stage."""
    base = _synthetic_master(tmp_path)
    counts = dict(GOOD_COUNTS, **bad)
    with pytest.raises(cat.CatalogValidationError, match="expected"):
        cli._builtin_validate_catalog(
            VALIDATE_STAGE, base,
            config=complete_config(expected_counts=counts))


def test_wrong_configured_event_count_fails_parameters_csv(tmp_path):
    """expected_counts.events is enforced against the event-parameters CSV."""
    base = _synthetic_master(tmp_path)
    params_path = base / pipeline.EVENT_PARAMS_CSV
    params_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{c: 1 for c in cat.PARAMETERS_COLUMNS},
                  {**{c: 1 for c in cat.PARAMETERS_COLUMNS},
                   "new_event_id": 2}]).to_csv(params_path, index=False)
    stage = dict(VALIDATE_STAGE,
                 inputs={"master_csv": pipeline.MASTER_CSV,
                         "parameters_csv": pipeline.EVENT_PARAMS_CSV})
    assert cli._builtin_validate_catalog(
        stage, base,
        config=complete_config(expected_counts=GOOD_COUNTS)) == "ok"
    with pytest.raises(cat.CatalogValidationError, match="expected 3 events"):
        cli._builtin_validate_catalog(
            stage, base,
            config=complete_config(
                expected_counts=dict(GOOD_COUNTS, events=3,
                                     type_counts={1: 1, 2: 1})))


# ---------------------------------------------------------------------------
# 3. fixed categorical rules: one canonical value each, loud failure
# ---------------------------------------------------------------------------
def test_canonical_fixed_rules_pass():
    pipeline.validate_reconstruction_config(complete_config())


@pytest.mark.parametrize("key", sorted(pipeline.FIXED_RULES))
def test_changed_fixed_rule_fails_loudly(key):
    """Every fixed rule admits exactly its canonical value; an unsupported
    alternative is rejected loudly, never silently ignored."""
    fixed = dict(pipeline.FIXED_RULES)
    fixed[key] = "some_other_rule"
    with pytest.raises(ConfigError, match=key):
        pipeline.validate_reconstruction_config(
            complete_config(fixed_rules=fixed))


def test_changed_fixed_rule_fails_through_any_stage(tmp_path):
    """The guard also fires when a stage is invoked directly."""
    base, out = _floor_fixture(tmp_path, 1.0)
    config = _floor_config(1.0)
    config["fixed_rules"] = dict(pipeline.FIXED_RULES,
                                 exceedance_rule="tmax_gt_threshold")
    with pytest.raises(ConfigError, match="exceedance_rule"):
        pipeline.stage_rebuild_catalog({}, base, out, config=config)


# ---------------------------------------------------------------------------
# 4. unsupported overrides: nothing is silently ignored
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("params", [
    {"box_agg": "mean"},                  # provenance record, not operative
    {"dbscan_metric": "euclidean"},       # fixed rule, not operative
    {"review_seed": 1},                   # provenance seed, not operative
    {"no_such_parameter": 1},
])
def test_unsupported_operative_parameter_fails(params):
    with pytest.raises(ConfigError, match="parameters"):
        pipeline.validate_reconstruction_config(
            complete_config(parameters=params))


def test_unknown_top_level_section_fails():
    """A stray top-level section (e.g. the pre-V5 seeds:) must be rejected
    and directed to provenance:."""
    with pytest.raises(ConfigError, match="provenance"):
        pipeline.validate_reconstruction_config(
            complete_config(seeds={"review_seed": 1}))


def test_unknown_expected_count_key_fails():
    with pytest.raises(ConfigError, match="expected_counts"):
        pipeline.validate_reconstruction_config(
            complete_config(expected_counts={"structures": 760}))


# ---------------------------------------------------------------------------
# 5. complete schema: every key REQUIRED -- no silent module defaults
# ---------------------------------------------------------------------------
def test_empty_config_fails():
    """An empty/None config cannot pass validation: the schema requires the
    three sections in full, so nothing can run on silent module defaults."""
    with pytest.raises(ConfigError, match="empty"):
        pipeline.validate_reconstruction_config(None)
    with pytest.raises(ConfigError, match="empty"):
        pipeline.validate_reconstruction_config({})


@pytest.mark.parametrize("section", ["parameters", "fixed_rules",
                                     "expected_counts"])
def test_missing_section_fails(section):
    config = complete_config()
    del config[section]
    with pytest.raises(ConfigError, match=section):
        pipeline.validate_reconstruction_config(config)


@pytest.mark.parametrize("key", sorted(pipeline.OPERATIVE_PARAMETER_KEYS))
def test_missing_operative_parameter_fails(key):
    """Omitting ANY operative parameter fails loudly instead of silently
    falling back to the module default."""
    config = complete_config()
    del config["parameters"][key]
    with pytest.raises(ConfigError, match=key):
        pipeline.validate_reconstruction_config(config)


@pytest.mark.parametrize("key", sorted(pipeline.FIXED_RULES))
def test_missing_fixed_rule_fails(key):
    """Every canonical categorical rule must be declared explicitly."""
    config = complete_config()
    del config["fixed_rules"][key]
    with pytest.raises(ConfigError, match=key):
        pipeline.validate_reconstruction_config(config)


@pytest.mark.parametrize("key", sorted(pipeline.EXPECTED_COUNT_KEYS))
def test_missing_expected_count_fails(key):
    """Every expected count (incl. the derived theta_threshold) is
    required."""
    config = complete_config()
    del config["expected_counts"][key]
    with pytest.raises(ConfigError, match=key):
        pipeline.validate_reconstruction_config(config)


def test_missing_operative_key_fails_through_any_stage(tmp_path):
    """A stage invoked directly with a config missing an operative key must
    fail BEFORE running (never silently use the module default)."""
    base, out = _floor_fixture(tmp_path, VAR_FLOOR_CFG)
    config = _floor_config(VAR_FLOOR_CFG)
    del config["parameters"]["var_floor_km2"]
    with pytest.raises(ConfigError, match="var_floor_km2"):
        pipeline.stage_rebuild_catalog({}, base, out, config=config)


def test_bundled_config_passes_the_schema():
    """The shipped canonical config must itself satisfy the V5 schema."""
    import yaml
    with open(cli.bundled_config_path(), "r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    pipeline.validate_reconstruction_config(config)
    assert config["expected_counts"]["theta_threshold"] == 371
    assert config["parameters"]["var_floor_km2"] == 1.0
    assert "theta_threshold" not in config["parameters"]
