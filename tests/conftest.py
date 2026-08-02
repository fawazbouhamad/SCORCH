"""Shared test helpers for the complete (V6) reconstruction config schema.

The V6 schema is complete as well as closed: every operative parameter,
every fixed rule and every expected count is REQUIRED, so a partial config
can no longer run on silent module defaults. Tests that exercise a single
knob therefore build a fully populated config with :func:`complete_config`
and override only the values under test.
"""
import copy

from scorch import pipeline

# The canonical operative parameters of the shipped fast route (kept in sync
# with configs/reproduction_fast.yaml; test overrides replace single values).
CANONICAL_PARAMETERS = {
    "sigma": 1.25,
    "var_floor_km2": 1.0,
    "grid_step_deg": 1.0,
    "p95_quantile": 0.95,
    "bigday_quantile": 0.975,
    "bigday_quantile_method": "higher",
    "heatwave_min_len_days": 3,
    "heatwave_min_exceed_days": 3,
    "dbscan_eps_grid": [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0],
    "dbscan_min_samples_grid": [4, 5, 6, 7, 8, 9, 10, 11, 12],
}

CANONICAL_EXPECTED_COUNTS = {
    "valid_one_degree_cells": 1800,
    "warm_season_days": 15738,
    "theta_threshold": 371,
    "selected_days": 395,
    "events": 51,
    "ellipses": 760,
    "type_counts": {1: 3, 2: 4, 3: 20, 4: 24},
}


def complete_config(parameters=None, expected_counts=None, fixed_rules=None,
                    **top_level):
    """A schema-complete reconstruction config with selective overrides.

    ``parameters`` / ``expected_counts`` are merged over the canonical
    values (so a test can override one key and stay schema-complete);
    ``fixed_rules`` REPLACES the canonical rules when given (so a test can
    provide a deliberately broken rule set). Extra keyword arguments become
    additional top-level sections (e.g. ``stages=[...]``).
    """
    config = {
        "parameters": {**copy.deepcopy(CANONICAL_PARAMETERS),
                       **(parameters or {})},
        "fixed_rules": (dict(pipeline.FIXED_RULES) if fixed_rules is None
                        else dict(fixed_rules)),
        "expected_counts": {**copy.deepcopy(CANONICAL_EXPECTED_COUNTS),
                            **(expected_counts or {})},
    }
    config.update(top_level)
    return config
