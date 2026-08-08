"""Connected end-to-end reconstruction: processed daily field -> catalog.

Every canonical pipeline stage is implemented here as a builtin stage that
``scorch reproduce`` runs directly against the extracted processed-data
deposit. The chain is GENUINELY CONNECTED: starting from the deposited CF
NetCDF field and the algorithm configuration, every stage writes its newly
generated outputs under ``<out-dir>/reconstruction/`` and every later stage
reads ONLY those newly generated intermediates (plus the deposited field).
The deposited final catalogs are used exclusively as FINAL COMPARISON
TARGETS -- never as upstream inputs to later reconstructed stages.

  field-products       (a) verify thresholds + the authoritative exceedance
                       indicator of the deposited CF NetCDF daily field
  relabel-heatwaves    (b) rerun the grid-level heatwave labelling from the
                       authoritative exceedance field; compare heatwave_id;
                       (c) derive daily regional heatwave coverage
                       -> reconstruction/heatwave_labels_relabelled.npz
                       -> reconstruction/daily_regional_coverage.csv
  select-days-events   (d) NHW >= Theta = 371 day selection + consecutive
                       compound-event construction from the NEW coverage
                       -> reconstruction/selected_days_events.csv
  daily-dbscan-params  (e) Method-A modal DBSCAN parameter selection for all
                       395 NEWLY selected days, on the NEWLY relabelled cells
                       -> reconstruction/daily_selected_parameters.csv
  event-global-params  (f) event-global-maximum parameter derivation from the
                       NEWLY computed daily parameters (51 events)
                       -> reconstruction/event_global_max_parameters.csv
  rebuild-catalog      (g) cluster every NEWLY selected day with the NEWLY
                       derived event parameters; (h) fit the PCA ellipses
                       -> reconstruction/structure_labels.csv
                       -> reconstruction/master_cluster_ellipse_catalog.csv
  classify-reconstructed (i, j) typology of the NEWLY reconstructed catalog
                       -> reconstruction/event_typology.csv

Each stage RAISES ``PipelineError`` on any missing input or any mismatch with
the deposited comparison target -- nothing is silently skipped.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import selection
from ._kernel import clustering as _kc
from ._kernel import ellipse_pca as _ke
from .dbscan_params import (EPS_GRID, MIN_SAMPLES_GRID, NOISE, select_modal,
                            event_global_max_parameters)
from .labeling import label_heatwaves

FIELD_NC = "gridded/scorch_processed_daily_tmax_field_v1.0.0.nc"

# Deposited files used ONLY as comparison targets (never as stage inputs).
EXTENT_CSV = "gridded/fig02_daily_extent.csv"
LABELS_CSV = "catalogs/final_labels_event_global_max.csv"
SELECTED_CSV = "selected_days/selected_days_395.csv"
EVENT_PARAMS_CSV = "catalogs/event_global_max_parameters.csv"
MASTER_CSV = ("catalogs/"
              "scorch_new_algorithm_master_cluster_ellipse_event_global_max.csv")

# Newly generated intermediates (under <out-dir>/reconstruction/).
RECON_SUBDIR = "reconstruction"
RECON_LABELS_NPZ = "heatwave_labels_relabelled.npz"
RECON_COVERAGE_CSV = "daily_regional_coverage.csv"
RECON_SELECTED_CSV = "selected_days_events.csv"
RECON_DAILY_PARAMS_CSV = "daily_selected_parameters.csv"
RECON_EVENT_PARAMS_CSV = "event_global_max_parameters.csv"
RECON_STRUCT_LABELS_CSV = "structure_labels.csv"
RECON_CATALOG_CSV = "master_cluster_ellipse_catalog.csv"
RECON_WEIGHTED_CSV = "weighted_centroids.csv"
RECON_TYPOLOGY_CSV = "event_typology.csv"

SIGMA = 1.25
VAR_FLOOR_KM2 = 1.0
THETA_EXPECTED = 371
N_SELECTED_EXPECTED = 395
N_EVENTS_EXPECTED = 51
N_ELLIPSES_EXPECTED = 760
TYPE_COUNTS_EXPECTED = {1: 3, 2: 4, 3: 20, 4: 24}

# --- configuration schema (V6) -------------------------------------------
# The reconstruction YAML has exactly four operative/documented sections:
#   parameters:      numeric/grid values the stages CONSUME (every key below
#                    is read by at least one stage; unknown keys are an
#                    error, and EVERY key is REQUIRED -- a missing operative
#                    key fails loudly instead of silently falling back to a
#                    module default)
#   fixed_rules:     categorical algorithm rules with exactly ONE supported
#                    canonical value each -- the implementation implements
#                    precisely these rules; every rule must be declared and
#                    any other value fails loudly
#   expected_counts: expected results, including the DERIVED threshold Theta
#                    (theta_threshold is derived from bigday_quantile +
#                    bigday_quantile_method, so it is an expected value, not
#                    an independent operative input); every key is REQUIRED
#   provenance:      documentation-only records (provider-level grid-cell
#                    aggregation, script seeds); NOT consumed by the fast
#                    route and never algorithm-affecting here
OPERATIVE_PARAMETER_KEYS = frozenset({
    "sigma", "var_floor_km2", "grid_step_deg", "p95_quantile",
    "bigday_quantile", "bigday_quantile_method",
    "heatwave_min_len_days", "heatwave_min_exceed_days",
    "dbscan_eps_grid", "dbscan_min_samples_grid",
})
FIXED_RULES = {
    "exceedance_rule": "tmax_ge_threshold",
    "heatwave_split_rule": "two_consecutive_zeros",
    "heatwave_gap_rule": "unlimited_single_zero_bridging",
    "dbscan_metric": "precomputed_euclidean_grid_cell_distance",
    "dbscan_selection": "modal_component_count_prefer_nonzero",
    "dbscan_tie_rule": "keep_all_combos_of_all_tied_modal_counts_then_average",
    "dbscan_min_samples_rounding": "half_up_min_1",
    "event_global_eps_rule": "max_daily_avg_eps",
    "event_global_minpts_rule": "max_daily_rounded_minpts",
}
EXPECTED_COUNT_KEYS = frozenset({
    "valid_one_degree_cells", "warm_season_days", "theta_threshold",
    "selected_days", "events", "ellipses", "type_counts",
})
_KNOWN_TOP_LEVEL_KEYS = frozenset({
    "name", "base_dir", "parameters", "fixed_rules", "expected_counts",
    "provenance", "stages",
})


class PipelineError(RuntimeError):
    """A reconstruction stage failed: missing input or canonical mismatch."""


class ConfigError(PipelineError):
    """The loaded reconstruction configuration is invalid or unsupported."""


def validate_reconstruction_config(config):
    """Validate a loaded reconstruction config against the V6 schema.

    The schema is CLOSED and COMPLETE, so no algorithm-affecting field can
    be silently ignored OR silently defaulted:

      * unknown keys under ``parameters:`` are rejected (so a value that no
        stage consumes cannot masquerade as an operative parameter), and
        EVERY operative parameter is REQUIRED -- a config that omits one
        fails loudly here instead of running on a module default,
      * every ``fixed_rules:`` entry must be present and must carry its
        single supported canonical value -- the stages implement exactly
        these rules, so an absent or alternative rule fails loudly,
      * every ``expected_counts:`` key (including the derived
        ``theta_threshold``) is required; unknown keys and unknown
        top-level sections are rejected (e.g. a stray ``seeds:`` section
        must move to ``provenance:``).
    """
    if not config:
        raise ConfigError(
            "empty reconstruction config: the schema requires the "
            "parameters:, fixed_rules: and expected_counts: sections with "
            "every key present -- missing operative keys fail loudly "
            "rather than silently using module defaults")
    unknown_top = sorted(set(config) - _KNOWN_TOP_LEVEL_KEYS)
    if unknown_top:
        raise ConfigError(
            f"unknown top-level config section(s) {unknown_top}: operative "
            "values belong under parameters:, canonical categorical rules "
            "under fixed_rules:, expected results under expected_counts:, "
            "and documentation-only records (e.g. seeds) under provenance:")
    missing_sections = [s for s in ("parameters", "fixed_rules",
                                    "expected_counts") if s not in config]
    if missing_sections:
        raise ConfigError(
            f"required config section(s) missing: {missing_sections}. The "
            "reconstruction schema requires parameters:, fixed_rules: and "
            "expected_counts: to be present and complete.")
    params = config["parameters"] or {}
    unknown = sorted(set(params) - OPERATIVE_PARAMETER_KEYS)
    if unknown:
        raise ConfigError(
            f"unsupported key(s) under parameters: {unknown}. Only "
            f"{sorted(OPERATIVE_PARAMETER_KEYS)} are consumed as operative "
            "parameters; categorical rules belong under fixed_rules:, "
            "derived/expected values (incl. theta_threshold) under "
            "expected_counts:, and provenance records under provenance:")
    missing = sorted(OPERATIVE_PARAMETER_KEYS - set(params))
    if missing:
        raise ConfigError(
            f"missing operative parameter(s) under parameters: {missing}. "
            "Every operative parameter is REQUIRED: a missing key fails "
            "loudly instead of silently using a module default.")
    fixed = config["fixed_rules"] or {}
    unknown_fixed = sorted(set(fixed) - set(FIXED_RULES))
    if unknown_fixed:
        raise ConfigError(
            f"unknown fixed_rules key(s): {unknown_fixed}. Supported rules: "
            f"{sorted(FIXED_RULES)}")
    missing_fixed = sorted(set(FIXED_RULES) - set(fixed))
    if missing_fixed:
        raise ConfigError(
            f"missing fixed_rules key(s): {missing_fixed}. Every canonical "
            "categorical rule must be declared with its single supported "
            "value; an absent rule cannot be silently assumed.")
    for key, canonical in FIXED_RULES.items():
        if str(fixed[key]) != canonical:
            raise ConfigError(
                f"fixed_rules.{key} = {fixed[key]!r} is not supported: the "
                f"implementation implements exactly {canonical!r} and no "
                "alternative rule. Changing this value requires changing "
                "the code; it cannot be reconfigured.")
    expected = config["expected_counts"] or {}
    unknown_exp = sorted(set(expected) - EXPECTED_COUNT_KEYS)
    if unknown_exp:
        raise ConfigError(
            f"unknown expected_counts key(s): {unknown_exp}. Supported: "
            f"{sorted(EXPECTED_COUNT_KEYS)}")
    missing_exp = sorted(EXPECTED_COUNT_KEYS - set(expected))
    if missing_exp:
        raise ConfigError(
            f"missing expected_counts key(s): {missing_exp}. Every "
            "expected count (including the derived theta_threshold) is "
            "REQUIRED.")


def _cfg_params_expected(config):
    """(parameters, expected_counts) view used by every builtin stage.

    Validates the config first, so every stage -- whether reached through
    ``run_reproduction`` or called directly -- rejects incomplete configs,
    unsupported parameters, non-canonical fixed rules and unknown sections
    loudly. Because validation requires the COMPLETE schema, the returned
    mappings carry every operative parameter and expected count; stages
    index them directly and never fall back to module defaults.
    """
    validate_reconstruction_config(config)
    return config["parameters"], config["expected_counts"]


def _require(path: Path, what: str) -> Path:
    if not path.exists():
        raise PipelineError(
            f"required input missing: {what} ({path}). The stage cannot run; "
            "fetch/extract the processed-data deposit first "
            "(scorch fetch-data --doi 10.5281/zenodo.21717752), pass the correct "
            "--base-dir, and run the earlier reconstruction stages in "
            "order.")
    return path


def _recon_dir(out_dir) -> Path:
    d = Path(out_dir) / RECON_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _open_field(base: Path):
    """Open the deposited CF NetCDF field. Returns (dataset, dates, lat, lon)."""
    try:
        from netCDF4 import Dataset, num2date
    except ImportError as exc:                                # pragma: no cover
        raise PipelineError(
            "netCDF4 is required for the field stages: pip install "
            "'scorch-heatwaves[download]' or 'netCDF4'") from exc
    nc = _require(base / FIELD_NC, "processed daily field NetCDF")
    ds = Dataset(nc, "r")
    t = ds.variables["time"]
    dates = np.array([d.strftime("%Y-%m-%d")
                      for d in num2date(t[:], t.units, t.calendar)])
    lat = np.asarray(ds.variables["lat"][:], dtype=float)
    lon = np.asarray(ds.variables["lon"][:], dtype=float)
    return ds, dates, lat, lon


def _load_recon_labels(out_dir):
    """Load the relabelled heatwave field written by relabel-heatwaves."""
    npz_path = Path(out_dir) / RECON_SUBDIR / RECON_LABELS_NPZ
    _require(npz_path, "relabelled heatwave field (run relabel-heatwaves)")
    with np.load(npz_path, allow_pickle=False) as z:
        return (z["labels"], z["dates"].astype(str), z["lat"], z["lon"])


def _day_cells(labels, dates, lat, lon, day: str):
    """Heatwave-labelled grid cells (heatwave_id > 0) of one day.

    Returned in the CANONICAL longitude-major order (ascending lon, then
    ascending lat), which is the cell order of the canonical pipeline. The
    order is load-bearing: DBSCAN assigns a border point reachable from two
    clusters to whichever core point reaches it first, so a different input
    order can yield a different (equally valid) partition of border cells.
    Emitting the canonical order here reproduces the canonical catalog partition
    exactly, deterministically, from the field alone.
    """
    i = int(np.where(dates == day)[0][0])
    jj, ii = np.where(labels[i].T > 0)          # transpose -> lon-major scan
    return lon[jj], lat[ii]


# ---------------------------------------------------------------------------
# Stage: field-products  (a)
# ---------------------------------------------------------------------------
def stage_field_products(stage, base_dir, out_dir=None, config=None):
    """Verify the deposited daily field: threshold recomputation and the
    authoritative exceedance indicator (tmax >= tmax_p95_threshold)."""
    params, expected = _cfg_params_expected(config)
    n_days_exp = int(expected["warm_season_days"])
    n_cells_exp = int(expected["valid_one_degree_cells"])
    p95_q = float(params["p95_quantile"])
    base = Path(base_dir)
    ds, dates, lat, lon = _open_field(base)
    try:
        tmax = np.asarray(ds.variables["tmax"][:], dtype=np.float64)
        thr = np.asarray(ds.variables["tmax_p95_threshold"][:], dtype=np.float64)
        ex = np.asarray(ds.variables["exceedance"][:])
    finally:
        ds.close()

    n_time, n_lat, n_lon = tmax.shape
    if n_time != n_days_exp or n_lat * n_lon != n_cells_exp:
        raise PipelineError(
            f"field dimensions {n_time} x {n_lat * n_lon} != "
            f"{n_days_exp} x {n_cells_exp}")

    # (a) thresholds: recompute the per-cell warm-season p95 (pandas default
    # linear interpolation, the canonical heatwave-algorithm rule).
    p95 = np.quantile(tmax, p95_q, axis=0, method="linear")
    dmax = float(np.abs(p95 - thr).max())
    if dmax > 2e-3:
        raise PipelineError(
            f"p95 threshold recomputation differs by up to {dmax:.6f} degC "
            "(tolerance 2e-3; float32 storage)")

    # (a) authoritative exceedance: stored indicator vs tmax >= threshold.
    # The indicator was computed on the float64 source values; recomputing
    # from the float32 values stored in the file may disagree ONLY where the
    # value sits within float32 resolution of the threshold (documented in
    # the file metadata).
    disagree = (tmax >= thr[None]).astype(np.int8) != ex
    real_bad = int((disagree & (np.abs(tmax - thr[None]) > 1e-3)).sum())
    flips = int(disagree.sum())
    if real_bad:
        raise PipelineError(
            f"exceedance indicator mismatch on {real_bad} entries beyond "
            "float32 resolution of the threshold")
    print(f"  [ok] field verified: thresholds (max diff {dmax:.2e} degC); "
          f"authoritative exceedance confirmed ({flips} documented "
          "float32-borderline entries)")
    return "ok"


# ---------------------------------------------------------------------------
# Stage: relabel-heatwaves  (b) + (c)
# ---------------------------------------------------------------------------
def stage_relabel_heatwaves(stage, base_dir, out_dir=None, config=None):
    """(b) Rerun the grid-level heatwave labelling from the authoritative
    exceedance field with the canonical rule and compare heatwave_id;
    (c) derive the daily regional heatwave coverage from the NEW labels."""
    params, _ = _cfg_params_expected(config)
    min_len = int(params["heatwave_min_len_days"])
    min_ones = int(params["heatwave_min_exceed_days"])
    base = Path(base_dir)
    ds, dates, lat, lon = _open_field(base)
    try:
        ex = np.asarray(ds.variables["exceedance"][:])
        hw_dep = np.asarray(ds.variables["heatwave_id"][:])
    finally:
        ds.close()
    n_time, n_lat, n_lon = ex.shape

    idx = pd.DatetimeIndex(pd.to_datetime(dates))
    labels_new = np.zeros((n_time, n_lat, n_lon), dtype=np.int16)
    for i in range(n_lat):
        for j in range(n_lon):
            series = pd.Series(ex[:, i, j].astype(int), index=idx)
            lab, _ = label_heatwaves(series, min_len=min_len,
                                     min_ones=min_ones)
            labels_new[:, i, j] = lab.to_numpy().astype(np.int16)

    # (b) comparison target: the deposited heatwave_id field.
    n_diff = int((labels_new != hw_dep).sum())
    if n_diff:
        raise PipelineError(
            f"relabelled heatwave_id differs from the deposited field on "
            f"{n_diff} (day, cell) entries")

    # (c) daily regional coverage from the NEW labels + authoritative
    # exceedance.
    n_hw = (labels_new > 0).reshape(n_time, -1).sum(axis=1)
    n_exceed = (ex == 1).reshape(n_time, -1).sum(axis=1)
    n_hw_exceed = ((labels_new > 0) & (ex == 1)).reshape(n_time, -1).sum(axis=1)
    coverage = pd.DataFrame({"date": dates, "n_hw": n_hw,
                             "n_exceed": n_exceed,
                             "n_hw_exceed": n_hw_exceed})

    # Comparison target: the deposited daily-extent table.
    ref = pd.read_csv(_require(base / EXTENT_CSV,
                               "daily extent comparison table"))
    ref = ref.sort_values("date").reset_index(drop=True)
    if list(ref["date"]) != list(dates):
        raise PipelineError("field date axis differs from the deposited "
                            "daily-extent table")
    for col in ("n_hw", "n_exceed", "n_hw_exceed"):
        bad = int((ref[col].to_numpy() != coverage[col].to_numpy()).sum())
        if bad:
            raise PipelineError(
                f"daily coverage column {col}: {bad} mismatching days vs "
                "the deposited table")

    recon = _recon_dir(out_dir)
    np.savez_compressed(recon / RECON_LABELS_NPZ, labels=labels_new,
                        dates=np.array(dates, dtype="U10"), lat=lat, lon=lon)
    coverage.to_csv(recon / RECON_COVERAGE_CSV, index=False)
    print(f"  [ok] heatwave labelling rerun for all {n_lat * n_lon} cells: "
          "heatwave_id identical to the deposited field; daily coverage "
          f"derived for {n_time} days (matches the deposited table) -> "
          f"{RECON_SUBDIR}/{RECON_COVERAGE_CSV}")
    return "ok"


# ---------------------------------------------------------------------------
# Stage: select-days-events  (d)
# ---------------------------------------------------------------------------
def stage_select_days_events(stage, base_dir, out_dir=None, config=None):
    """(d) Regional selection (NHW >= Theta) and consecutive compound-event
    construction from the NEWLY derived daily coverage. The selection
    quantile/method come from the loaded config; Theta is DERIVED from them
    and verified against expected_counts.theta_threshold (canonical:
    Theta = 371 -> 395 days -> 51 events)."""
    params, expected = _cfg_params_expected(config)
    theta_exp = int(expected["theta_threshold"])
    q = float(params["bigday_quantile"])
    method = str(params["bigday_quantile_method"])
    n_sel_exp = int(expected["selected_days"])
    n_ev_exp = int(expected["events"])
    base = Path(base_dir)
    recon = _recon_dir(out_dir)
    cov = pd.read_csv(_require(recon / RECON_COVERAGE_CSV,
                               "reconstructed daily coverage "
                               "(run relabel-heatwaves)"))
    counts = pd.Series(cov["n_hw"].to_numpy(), index=cov["date"])
    selected, theta = selection.select_days(counts, q=q, method=method)
    if int(theta) != theta_exp:
        raise PipelineError(f"Theta = {theta} != {theta_exp}")
    if len(selected) != n_sel_exp:
        raise PipelineError(
            f"{len(selected)} selected days != {n_sel_exp}")

    events = selection.build_events(selected)
    n_events = int(events["event_id"].nunique())
    if n_events != n_ev_exp:
        raise PipelineError(f"{n_events} events != {n_ev_exp}")

    out = pd.DataFrame({
        "date": pd.to_datetime(events["date"]).dt.strftime("%Y-%m-%d"),
        "new_event_id": events["event_id"].astype(int),
    })

    # Comparison target: the deposited selected-days table.
    dep = pd.read_csv(_require(base / SELECTED_CSV,
                               "selected-days comparison table"))
    dep_days = sorted(dep["date"].astype(str))
    if dep_days != sorted(out["date"]):
        raise PipelineError("selected-day set differs from the deposited "
                            "selected_days_395.csv")
    dep_map = dep.assign(date=dep["date"].astype(str)).set_index("date")[
        "new_event_id"]
    got_map = out.set_index("date")["new_event_id"]
    if not (dep_map.sort_index() == got_map.sort_index()).all():
        raise PipelineError("event grouping differs from the deposited "
                            "selected_days_395.csv new_event_id column")

    out.to_csv(recon / RECON_SELECTED_CSV, index=False)
    print(f"  [ok] Theta = {int(theta)}; {len(out)} selected days; "
          f"{n_events} events from the reconstructed coverage - all match "
          f"the deposit -> {RECON_SUBDIR}/{RECON_SELECTED_CSV}")
    return "ok"


# ---------------------------------------------------------------------------
# Stage: daily-dbscan-params  (e)
# ---------------------------------------------------------------------------
def _day_grid(lon, lat, eps_grid=None, min_samples_grid=None, grid_step=1.0):
    """DBSCAN component-count grid for one day (shared distances).

    Canonical grid: 63 combinations (eps 1.0..4.0 x min_samples 4..12); the
    configured route passes the grids from the loaded YAML."""
    from sklearn.cluster import DBSCAN
    eps_grid = EPS_GRID if eps_grid is None else eps_grid
    min_samples_grid = (MIN_SAMPLES_GRID if min_samples_grid is None
                        else min_samples_grid)
    D = _kc.pairwise_distance_cells(np.asarray(lon, float),
                                    np.asarray(lat, float),
                                    grid_step=float(grid_step),
                                    chebyshev=False)
    rows = []
    for eps in eps_grid:
        for ms in min_samples_grid:
            labels = DBSCAN(eps=float(eps), min_samples=int(ms),
                            metric="precomputed").fit_predict(D)
            n_comp = len(set(labels.tolist()) - {NOISE})
            rows.append(dict(eps=float(eps), min_samples=int(ms),
                             n_components=int(n_comp)))
    return rows


def stage_daily_dbscan_params(stage, base_dir, out_dir=None, config=None):
    """(e) Method-A modal parameter selection for every NEWLY selected day,
    computed on the NEWLY relabelled heatwave cells; verified against the
    canonical per-day parameters stored in the deposited master catalog.
    The eps / min_samples grids and grid step come from the loaded config."""
    params, expected = _cfg_params_expected(config)
    eps_grid = [float(e) for e in params["dbscan_eps_grid"]]
    ms_grid = [int(m) for m in params["dbscan_min_samples_grid"]]
    grid_step = float(params["grid_step_deg"])
    n_sel_exp = int(expected["selected_days"])
    base = Path(base_dir)
    recon = _recon_dir(out_dir)
    sel = pd.read_csv(_require(recon / RECON_SELECTED_CSV,
                               "reconstructed selected days "
                               "(run select-days-events)"))
    labels, dates, lat, lon = _load_recon_labels(out_dir)

    # Comparison target: canonical per-day parameters in the deposited master.
    master = pd.read_csv(_require(base / MASTER_CSV,
                                  "master catalog comparison target"))
    ref = master.groupby("date").first()[
        ["canonical_daily_eps", "canonical_daily_minpts_raw",
         "canonical_daily_minpts_used"]]

    days = sel["date"].astype(str).tolist()
    out_rows = []
    n_checked = 0
    for d in days:
        dlon, dlat = _day_cells(labels, dates, lat, lon, d)
        s = select_modal(_day_grid(dlon, dlat, eps_grid=eps_grid,
                                   min_samples_grid=ms_grid,
                                   grid_step=grid_step))
        out_rows.append(dict(date=d, avg_eps=s["avg_eps"],
                             raw_avg_min_samples=s["raw_avg_min_samples"],
                             rounded_min_samples=s["rounded_min_samples"],
                             modal_counts="-".join(map(str, s["modal_counts"])),
                             n_combos_averaged=s["n_combos_averaged"],
                             is_tie=s["is_tie"]))
        if d in ref.index:
            r = ref.loc[d]
            if (abs(s["avg_eps"] - r["canonical_daily_eps"]) > 1e-9
                    or abs(s["raw_avg_min_samples"]
                           - r["canonical_daily_minpts_raw"]) > 1e-9
                    or int(s["rounded_min_samples"])
                    != int(r["canonical_daily_minpts_used"])):
                raise PipelineError(
                    f"daily DBSCAN parameters differ on {d}: recomputed "
                    f"eps={s['avg_eps']:.6f}/raw={s['raw_avg_min_samples']:.6f}"
                    f"/used={s['rounded_min_samples']} vs catalog "
                    f"{r['canonical_daily_eps']:.6f}"
                    f"/{r['canonical_daily_minpts_raw']:.6f}"
                    f"/{int(r['canonical_daily_minpts_used'])}")
            n_checked += 1
    if n_checked != n_sel_exp:
        raise PipelineError(
            f"only {n_checked}/{n_sel_exp} reconstructed days "
            "could be verified against the catalog comparison target")
    pd.DataFrame(out_rows).to_csv(recon / RECON_DAILY_PARAMS_CSV, index=False)
    print(f"  [ok] daily Method-A parameters recomputed for {len(days)} "
          f"reconstructed days; {n_checked}/{n_sel_exp} verified "
          f"exactly -> {RECON_SUBDIR}/{RECON_DAILY_PARAMS_CSV}")
    return "ok"


# ---------------------------------------------------------------------------
# Stage: event-global-params  (f)
# ---------------------------------------------------------------------------
def stage_event_global_params(stage, base_dir, out_dir=None, config=None):
    """(f) Event-global-maximum parameters derived from the NEWLY computed
    daily parameters; verified against the deposited event parameters."""
    _, expected = _cfg_params_expected(config)
    n_ev_exp = int(expected["events"])
    base = Path(base_dir)
    recon = _recon_dir(out_dir)
    daily = pd.read_csv(_require(recon / RECON_DAILY_PARAMS_CSV,
                                 "reconstructed daily parameters "
                                 "(run daily-dbscan-params)"))
    sel = pd.read_csv(_require(recon / RECON_SELECTED_CSV,
                               "reconstructed selected days "
                               "(run select-days-events)"))
    day = daily.merge(sel, on="date", validate="one_to_one")
    derived = event_global_max_parameters(day)

    # Comparison target: the deposited event parameters.
    dep = pd.read_csv(_require(base / EVENT_PARAMS_CSV,
                               "event parameters comparison table"))
    m = derived.merge(dep, on="new_event_id", suffixes=("_new", "_dep"))
    if len(m) != n_ev_exp:
        raise PipelineError(f"{len(m)} events joined != {n_ev_exp}")
    bad = m[(abs(m["event_global_eps_max_new"]
                 - m["event_global_eps_max_dep"]) > 1e-9)
            | (m["event_global_minpts_used_new"].astype(int)
               != m["event_global_minpts_used_dep"].astype(int))]
    if len(bad):
        raise PipelineError(
            "event-global parameters differ for events: "
            + ", ".join(str(e) for e in bad["new_event_id"].tolist()))

    derived.to_csv(recon / RECON_EVENT_PARAMS_CSV, index=False)
    print(f"  [ok] event-global-max parameters derived from the "
          f"reconstructed daily results for all {len(m)} events; all match "
          f"the deposit -> {RECON_SUBDIR}/{RECON_EVENT_PARAMS_CSV}")
    return "ok"


# ---------------------------------------------------------------------------
# Stage: rebuild-catalog  (g) + (h)
# ---------------------------------------------------------------------------
def _partition(labels, lon, lat):
    """Cluster membership as a set of frozenset(cells) plus the noise set."""
    comps = {}
    noise = set()
    for lo, la, lab in zip(lon, lat, labels):
        if lab == NOISE:
            noise.add((float(lo), float(la)))
        else:
            comps.setdefault(int(lab), set()).add((float(lo), float(la)))
    return set(map(frozenset, comps.values())), noise


def stage_rebuild_catalog(stage, base_dir, out_dir=None, config=None):
    """(g) Cluster every NEWLY selected day with the NEWLY derived
    event-global parameters on the NEWLY relabelled heatwave cells;
    (h) fit the canonical PCA ellipses (sigma from the loaded config).
    Verified against the deposited labels and master catalog (comparison
    targets only)."""
    from sklearn.cluster import DBSCAN
    params, expected = _cfg_params_expected(config)
    sigma = float(params["sigma"])
    var_floor = float(params["var_floor_km2"])
    grid_step = float(params["grid_step_deg"])
    n_ell_exp = int(expected["ellipses"])
    base = Path(base_dir)
    recon = _recon_dir(out_dir)
    labels_f, dates_f, lat_f, lon_f = _load_recon_labels(out_dir)
    sel = pd.read_csv(_require(recon / RECON_SELECTED_CSV,
                               "reconstructed selected days"))
    ev_params = pd.read_csv(_require(recon / RECON_EVENT_PARAMS_CSV,
                                     "reconstructed event parameters "
                                     "(run event-global-params)"))
    day_event = dict(zip(sel["date"].astype(str),
                         sel["new_event_id"].astype(int)))
    ev_eps = dict(zip(ev_params["new_event_id"].astype(int),
                      ev_params["event_global_eps_max"]))
    ev_ms = dict(zip(ev_params["new_event_id"].astype(int),
                     ev_params["event_global_minpts_used"].astype(int)))

    # Comparison targets: deposited per-cell labels + master catalog.
    dep_labels = pd.read_csv(_require(base / LABELS_CSV,
                                      "final labels comparison table"))
    dep_by_day = {d: sub for d, sub in dep_labels.assign(
        date=dep_labels["date"].astype(str)).groupby("date")}
    master = pd.read_csv(_require(base / MASTER_CSV,
                                  "master catalog comparison target"))

    label_rows = []
    cat_rows = []
    n_structures = 0
    n_label_days_ok = 0
    geo_max_rel = 0.0
    for d in sel["date"].astype(str):
        lon, lat = _day_cells(labels_f, dates_f, lat_f, lon_f, d)
        ev = day_event[d]
        D = _kc.pairwise_distance_cells(lon, lat, grid_step=grid_step,
                                        chebyshev=False)
        day_labels = DBSCAN(eps=float(ev_eps[ev]), min_samples=int(ev_ms[ev]),
                            metric="precomputed").fit_predict(D)
        for lo, la, lab in zip(lon, lat, day_labels):
            label_rows.append((d, ev, float(lo), float(la), int(lab)))

        # (g) label comparison: identical partition (order-independent)
        new_parts, new_noise = _partition(day_labels, lon, lat)
        if d not in dep_by_day:
            raise PipelineError(f"day {d} missing from the deposited labels")
        sub = dep_by_day[d]
        dep_parts, dep_noise = _partition(sub["label"].to_numpy(),
                                          sub["lon"].to_numpy(dtype=float),
                                          sub["lat"].to_numpy(dtype=float))
        if new_parts != dep_parts or new_noise != dep_noise:
            raise PipelineError(
                f"cluster partition differs from deposited labels on {d}")
        n_label_days_ok += 1

        # (h) ellipse geometry per component vs catalog rows for this day
        cat = master[master["date"].astype(str) == d]
        got = []
        for comp in sorted(new_parts, key=lambda s: sorted(s)):
            clon = np.array([c[0] for c in comp])
            clat = np.array([c[1] for c in comp])
            got.append(_ke.evaluate_cluster_ellipse(clon, clat, sigma,
                                                    var_floor=var_floor))
        if len(got) != len(cat):
            raise PipelineError(
                f"{len(got)} components vs {len(cat)} catalog rows on {d}")
        n_structures += len(got)
        # match by centroid nearest neighbour, then compare geometry.
        # The recomputed values are UNWEIGHTED PCA origins, so match against
        # the catalog's preserved unweighted origin columns when present
        # (post-remediation catalogs report the Tmax-weighted location in the
        # generic centroid_lon/centroid_lat aliases).
        if "centroid_lon_unweighted" in cat.columns:
            cat_pts = cat[["centroid_lon_unweighted",
                           "centroid_lat_unweighted"]].to_numpy(dtype=float)
        else:
            cat_pts = cat[["centroid_lon",
                           "centroid_lat"]].to_numpy(dtype=float)
        used = set()
        for k, e in enumerate(got):
            dists = np.hypot(cat_pts[:, 0] - e["centroid_lon"],
                             cat_pts[:, 1] - e["centroid_lat"])
            j = int(np.argmin(dists))
            if j in used or dists[j] > 1e-6:
                raise PipelineError(
                    f"no matching catalog centroid on {d} "
                    f"(nearest {dists[j]:.3e} deg)")
            used.add(j)
            row = cat.iloc[j]
            for col, val in (("major_axis_km", e["major_axis_km"]),
                             ("minor_axis_km", e["minor_axis_km"]),
                             ("ellipse_area_km2", e["ellipse_area_km2"]),
                             ("orientation_deg", e["orientation_deg"])):
                ref = float(row[col])
                rel = abs(val - ref) / max(1e-12, abs(ref))
                geo_max_rel = max(geo_max_rel, rel)
                if rel > 1e-6:
                    raise PipelineError(
                        f"{col} differs on {d}: {val!r} vs {ref!r} "
                        f"(rel {rel:.2e})")
            cat_rows.append(dict(
                date=d, new_event_id=ev, structure_index=k,
                n_cells=e["n_cells"],
                centroid_lon=e["centroid_lon"],
                centroid_lat=e["centroid_lat"],
                major_axis_km=e["major_axis_km"],
                minor_axis_km=e["minor_axis_km"],
                ellipse_area_km2=e["ellipse_area_km2"],
                orientation_deg=e["orientation_deg"],
                sigma=sigma))

    if n_structures != n_ell_exp:
        raise PipelineError(
            f"{n_structures} structures != {n_ell_exp}")
    pd.DataFrame(label_rows, columns=["date", "new_event_id", "lon", "lat",
                                      "label"]).to_csv(
        recon / RECON_STRUCT_LABELS_CSV, index=False)
    pd.DataFrame(cat_rows).to_csv(recon / RECON_CATALOG_CSV, index=False)
    print(f"  [ok] {n_label_days_ok} reconstructed days clustered with the "
          f"newly derived event parameters: partitions identical; "
          f"{n_structures} structures; ellipse geometry max relative diff "
          f"{geo_max_rel:.2e} -> {RECON_SUBDIR}/{RECON_CATALOG_CSV}")
    return "ok"


# ---------------------------------------------------------------------------
# Stage: weighted-centroids  (h2)  [pre-release v1.0.0 remediation]
# ---------------------------------------------------------------------------
def stage_weighted_centroids(stage, base_dir, out_dir=None, config=None):
    """(h2) STRICT post-PCA raw-Celsius Tmax-weighted centroid stage.

    Reads the member Tmax values of every reconstructed structure from the
    deposited CF NetCDF field (units checked), computes the raw-Celsius
    Tmax-weighted centroid with the strict kernel (no clipping, no
    transformation, no unweighted fallback), reconstructs the rigid
    translation fields, and compares EVERY remediation column of the
    canonical corrected master catalog: generic centroid aliases
    (centroid_lon/lat, centroid_x/y, x/y, lon/lat) must equal the weighted
    location; pca_origin_*/centroid_*_unweighted must equal the unweighted
    PCA origin; weight diagnostics and geodesic displacement fields must
    match. The weighted stage must run exactly once per structure (760)."""
    from ._kernel import tmax_weighted_centroid as twc
    _, expected = _cfg_params_expected(config)
    n_ell_exp = int(expected["ellipses"])
    base = Path(base_dir)
    recon = _recon_dir(out_dir)
    struct = pd.read_csv(_require(recon / RECON_STRUCT_LABELS_CSV,
                                  "reconstructed structure labels "
                                  "(run rebuild-catalog)"))
    struct["date"] = struct["date"].astype(str)
    master = pd.read_csv(_require(base / MASTER_CSV,
                                  "master catalog comparison target"))
    master["date"] = master["date"].astype(str)
    required_cols = [
        "cluster_id", "centroid_lon", "centroid_lat", "centroid_x",
        "centroid_y", "x", "y", "lon", "lat",
        "pca_origin_lon_unweighted", "pca_origin_lat_unweighted",
        "centroid_lon_unweighted", "centroid_lat_unweighted",
        "centroid_lon_tmax_weighted", "centroid_lat_tmax_weighted",
        "tmax_weight_sum_c", "tmax_min_c", "tmax_max_c", "tmax_mean_c",
        "tmax_sd_c", "centroid_displacement_km",
        "centroid_displacement_bearing_deg"]
    missing_cols = [c for c in required_cols if c not in master.columns]
    if missing_cols:
        raise PipelineError(
            f"master catalog lacks remediation columns {missing_cols}; "
            "the deposit is pre-remediation (unweighted) and cannot pass "
            "the weighted-centroid comparison")

    ds, dates_f, lat_f, lon_f = _open_field(base)
    try:
        tvar = ds.variables["tmax"]
        units = str(getattr(tvar, "units", "")).lower()
        if units not in ("degc", "celsius", "degrees_celsius", "deg_c"):
            raise PipelineError(
                f"Tmax field units are '{units}', not degrees Celsius; "
                "refusing to weight")

        def _close(a, b, rel=1e-9, absol=1e-9):
            return abs(a - b) <= max(absol, rel * abs(b))

        out_rows = []
        n_calls = 0
        worst = 0.0
        for day, day_struct in struct.groupby("date"):
            i = int(np.where(dates_f == day)[0][0])
            sl = np.ma.filled(np.ma.masked_invalid(tvar[i]), np.nan)
            tmax_day = {}
            for yi, la in enumerate(lat_f.tolist()):
                for xi, lo in enumerate(lon_f.tolist()):
                    v = float(sl[yi, xi])
                    if np.isfinite(v):
                        tmax_day[(lo, la)] = v
            cat = master[master["date"] == day]
            comps = sorted(set(day_struct["label"].astype(int)) - {-1})
            if len(comps) != len(cat):
                raise PipelineError(
                    f"{len(comps)} components vs {len(cat)} catalog rows "
                    f"on {day}")
            used = set()
            for lab in comps:
                mem = day_struct[day_struct["label"].astype(int) == lab]
                mlon = mem["lon"].to_numpy(dtype=float)
                mlat = mem["lat"].to_numpy(dtype=float)
                w = []
                for lo, la in zip(mlon.tolist(), mlat.tolist()):
                    key = (float(lo), float(la))
                    if key not in tmax_day:
                        raise PipelineError(
                            f"member cell {key} has no Tmax on {day}")
                    w.append(tmax_day[key])
                wc = twc.tmax_weighted_centroid(
                    mlon, mlat, w, context=f"{day} component {lab}")
                n_calls += 1
                o_lon, o_lat = float(mlon.mean()), float(mlat.mean())
                disp_km, disp_bearing = twc.geodesic_displacement_km(
                    o_lon, o_lat, wc["lon_w"], wc["lat_w"])
                # match the catalog row by the weighted location
                dists = np.hypot(
                    cat["centroid_lon_tmax_weighted"].to_numpy(float)
                    - wc["lon_w"],
                    cat["centroid_lat_tmax_weighted"].to_numpy(float)
                    - wc["lat_w"])
                j = int(np.argmin(dists))
                if j in used or dists[j] > 1e-6:
                    raise PipelineError(
                        f"no matching catalog structure on {day} "
                        f"(nearest {dists[j]:.3e} deg)")
                used.add(j)
                row = cat.iloc[j]
                checks = [
                    ("pca_origin_lon_unweighted", o_lon),
                    ("pca_origin_lat_unweighted", o_lat),
                    ("centroid_lon_unweighted", o_lon),
                    ("centroid_lat_unweighted", o_lat),
                    ("centroid_lon_tmax_weighted", wc["lon_w"]),
                    ("centroid_lat_tmax_weighted", wc["lat_w"]),
                    ("centroid_lon", wc["lon_w"]),
                    ("centroid_lat", wc["lat_w"]),
                    ("centroid_x", wc["lon_w"]), ("centroid_y", wc["lat_w"]),
                    ("x", wc["lon_w"]), ("y", wc["lat_w"]),
                    ("lon", wc["lon_w"]), ("lat", wc["lat_w"]),
                    ("tmax_weight_sum_c", wc["weight_sum_c"]),
                    ("tmax_min_c", wc["tmax_min_c"]),
                    ("tmax_max_c", wc["tmax_max_c"]),
                    ("tmax_mean_c", wc["tmax_mean_c"]),
                    ("tmax_sd_c", wc["tmax_sd_c"]),
                    ("centroid_displacement_km", disp_km),
                    ("centroid_displacement_bearing_deg", disp_bearing),
                ]
                for col, val in checks:
                    ref = float(row[col])
                    err = abs(val - ref) / max(1e-12, abs(ref))
                    worst = max(worst, err)
                    if not _close(val, ref):
                        raise PipelineError(
                            f"{col} differs on {day} structure {lab}: "
                            f"recomputed {val!r} vs catalog {ref!r}")
                # a production location column equal to the unweighted origin
                # (while a nonzero displacement exists) is the original defect
                if disp_km > 1e-6 and _close(float(row["centroid_lon"]),
                                             o_lon) \
                        and _close(float(row["centroid_lat"]), o_lat):
                    raise PipelineError(
                        f"generic centroid on {day} structure {lab} equals "
                        "the unweighted origin: the catalog is NOT "
                        "Tmax-weighted")
                out_rows.append(dict(
                    date=day, cluster_id=int(row["cluster_id"]),
                    n_member_cells=int(len(mem)),
                    pca_origin_lon_unweighted=o_lon,
                    pca_origin_lat_unweighted=o_lat,
                    centroid_lon_tmax_weighted=wc["lon_w"],
                    centroid_lat_tmax_weighted=wc["lat_w"],
                    tmax_weight_sum_c=wc["weight_sum_c"],
                    tmax_min_c=wc["tmax_min_c"],
                    tmax_max_c=wc["tmax_max_c"],
                    tmax_mean_c=wc["tmax_mean_c"],
                    tmax_sd_c=wc["tmax_sd_c"],
                    centroid_displacement_km=disp_km,
                    centroid_displacement_bearing_deg=disp_bearing))
    finally:
        ds.close()

    if n_calls != n_ell_exp:
        raise PipelineError(
            f"weighted stage ran {n_calls} times, expected {n_ell_exp}")
    pd.DataFrame(out_rows).to_csv(recon / RECON_WEIGHTED_CSV, index=False)
    print(f"  [ok] weighted stage executed {n_calls}/{n_ell_exp} times; "
          f"all remediation columns match the canonical corrected catalog "
          f"(worst rel diff {worst:.2e}) -> {RECON_SUBDIR}/"
          f"{RECON_WEIGHTED_CSV}")
    return "ok"


# ---------------------------------------------------------------------------
# Stage: classify-reconstructed  (i) + (j)
# ---------------------------------------------------------------------------
def stage_classify_reconstructed(stage, base_dir, out_dir=None, config=None):
    """(i) Classify the events of the NEWLY reconstructed catalog; (j) write
    the typology output. Verified against the deposited master's stored
    types (comparison target). Expected type counts come from the loaded
    config (canonical: 3/4/20/24)."""
    from .typology import classify_events
    _, expected = _cfg_params_expected(config)
    type_counts_exp = {int(k): int(v)
                       for k, v in expected["type_counts"].items()}
    base = Path(base_dir)
    recon = _recon_dir(out_dir)
    cat = pd.read_csv(_require(recon / RECON_CATALOG_CSV,
                               "reconstructed ellipse catalog "
                               "(run rebuild-catalog)"))
    derived = classify_events(cat)
    counts = derived["derived_type"].value_counts().to_dict()
    counts = {int(k): int(v) for k, v in counts.items()}
    if counts != type_counts_exp:
        raise PipelineError(
            f"reconstructed type counts {counts} != {type_counts_exp}")

    # Comparison target: stored types in the deposited master catalog.
    master = pd.read_csv(_require(base / MASTER_CSV,
                                  "master catalog comparison target"))
    stored = master.groupby("new_event_id")["v3_type"].first()
    merged = derived.set_index("new_event_id")["derived_type"]
    n_match = int((stored.reindex(merged.index) == merged).sum())
    if n_match != len(merged):
        raise PipelineError(
            f"typology of the reconstructed catalog matches only "
            f"{n_match}/{len(merged)} deposited event types")

    derived.to_csv(recon / RECON_TYPOLOGY_CSV, index=False)
    print(f"  [ok] {len(merged)} reconstructed events classified "
          f"(counts T1..T4 = {counts.get(1)}/{counts.get(2)}/"
          f"{counts.get(3)}/{counts.get(4)}); all match the deposited "
          f"types -> {RECON_SUBDIR}/{RECON_TYPOLOGY_CSV}")
    return "ok"


PIPELINE_STAGES = {
    "field_products": stage_field_products,
    "relabel_heatwaves": stage_relabel_heatwaves,
    "select_days_events": stage_select_days_events,
    "daily_dbscan_params": stage_daily_dbscan_params,
    "event_global_params": stage_event_global_params,
    "rebuild_catalog": stage_rebuild_catalog,
    "weighted_centroids": stage_weighted_centroids,
    "classify_reconstructed": stage_classify_reconstructed,
}
