"""Method-A modal DBSCAN parameter selection and event-global-max derivation.

``round_half_up`` and ``select_modal`` are VERBATIM copies of the canonical
Method-A selection rule (originating in
the research repository's Method-A selection (``select_modal``)
and re-exported unchanged by ``scripts/six_task_review/common.py``, the single
source of truth used by the published pipeline).

Canonical parameter grid (63 combinations):
    eps          : 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0   (grid-cell units)
    min_samples  : 4, 5, 6, 7, 8, 9, 10, 11, 12

Selection rule per day:
    * count DBSCAN components (label -1 = noise, excluded) for every combo,
    * modal component count, preferring nonzero counts when any exist,
    * on ties, KEEP ALL combos of ALL tied modal counts, then average their
      eps and min_samples,
    * min_samples is rounded HALF-UP with a floor of 1.

Event-global-max derivation (``build_event_global_max_master.py``):
    * event_global_eps_max     = max over the event's days of the daily
      averaged eps (kept continuous),
    * event_global_minpts_used = max over the event's days of the daily
      ROUNDED min_samples (the true per-day integer actually applied).
      The decimal max-raw and its ceiling are recorded for audit only.
"""
from __future__ import annotations

import math
from collections import Counter

import numpy as np
import pandas as pd

from .clustering import cluster_day_cells

# Canonical constants (scripts/six_task_review/common.py)
EPS_GRID = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
MIN_SAMPLES_GRID = [4, 5, 6, 7, 8, 9, 10, 11, 12]
GRID_STEP = 1.0
NOISE = -1


def round_half_up(x: float) -> int:
    return int(math.floor(float(x) + 0.5))


def select_modal(grid_rows: list) -> dict:
    """Modal-count selection with the canonical tie-averaging rule.

    grid_rows: list of dicts with keys 'eps', 'min_samples', 'n_components'.
    """
    counts = [r["n_components"] for r in grid_rows]
    nonzero = [c for c in counts if c > 0]
    pool = nonzero if nonzero else counts
    freq = Counter(pool)
    maxf = max(freq.values())
    tied = sorted([v for v, f in freq.items() if f == maxf])
    combos = [r for r in grid_rows if r["n_components"] in tied]
    avg_eps = float(np.mean([r["eps"] for r in combos]))
    raw_ms = float(np.mean([r["min_samples"] for r in combos]))
    rounded_ms = max(1, round_half_up(raw_ms))
    return dict(modal_counts=tied, n_modal_values=len(tied),
                is_tie=int(len(tied) > 1), modal_frequency=int(maxf),
                n_combos_averaged=len(combos),
                avg_eps=avg_eps, raw_avg_min_samples=raw_ms,
                rounded_min_samples=rounded_ms)


def compute_day_grid(lon, lat, eps_grid=None, min_samples_grid=None,
                     grid_step=GRID_STEP):
    """Run DBSCAN over the full canonical parameter grid for one day.

    Returns a list of dicts {eps, min_samples, n_components}, where
    n_components excludes the noise label (-1), computed on the precomputed
    grid-cell Euclidean distance matrix (the canonical Method-A metric).
    """
    if eps_grid is None:
        eps_grid = EPS_GRID
    if min_samples_grid is None:
        min_samples_grid = MIN_SAMPLES_GRID
    rows = []
    for eps in eps_grid:
        for ms in min_samples_grid:
            labels = cluster_day_cells(lon, lat, eps=eps, min_samples=ms,
                                       grid_step=grid_step)
            n_comp = len(set(labels.tolist()) - {NOISE})
            rows.append(dict(eps=float(eps), min_samples=int(ms),
                             n_components=int(n_comp)))
    return rows


def select_day_parameters(lon, lat, eps_grid=None, min_samples_grid=None,
                          grid_step=GRID_STEP):
    """Canonical per-day parameter selection: grid sweep + modal selection."""
    grid_rows = compute_day_grid(lon, lat, eps_grid=eps_grid,
                                 min_samples_grid=min_samples_grid,
                                 grid_step=grid_step)
    return select_modal(grid_rows)


def event_global_max_parameters(day_params: pd.DataFrame,
                                event_col="new_event_id",
                                eps_col="avg_eps",
                                raw_minpts_col="raw_avg_min_samples",
                                rounded_minpts_col="rounded_min_samples"):
    """Derive the event-global-maximum DBSCAN parameters per event.

    Mirrors ``build_event_global_max_master.py``:
        event_global_eps_max        = max(daily averaged eps)
        event_global_minpts_used    = max(daily ROUNDED min_samples)  [PRIMARY]
        event_global_minpts_max_raw = max(daily raw mean min_samples) [audit]
        event_global_minpts_ceil_raw= max(1, ceil(max_raw))           [audit]

    Parameters
    ----------
    day_params : DataFrame with one row per event-day carrying the daily
        selected parameters (column names configurable via the *_col args).

    Returns
    -------
    DataFrame with one row per event.
    """
    grp = day_params.groupby(event_col)
    ev = grp.agg(
        event_global_eps_max=(eps_col, "max"),
        event_global_minpts_max_raw=(raw_minpts_col, "max"),
        event_global_minpts_max_rounded=(rounded_minpts_col, "max"),
    ).reset_index()
    # PRIMARY rule: max of the true per-day integer min_samples actually applied.
    ev["event_global_minpts_used"] = ev["event_global_minpts_max_rounded"].astype(int)
    # Audit-only alternative (decimals-only rule); NOT used for clustering.
    ev["event_global_minpts_ceil_raw"] = ev["event_global_minpts_max_raw"].apply(
        lambda r: max(1, int(math.ceil(float(r)))))
    return ev
