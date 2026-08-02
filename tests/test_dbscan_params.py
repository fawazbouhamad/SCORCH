"""Method-A modal parameter selection and event-global-max rule tests."""
import numpy as np
import pandas as pd
import pytest

from scorch.dbscan_params import (
    EPS_GRID,
    MIN_SAMPLES_GRID,
    round_half_up,
    select_modal,
    compute_day_grid,
    select_day_parameters,
    event_global_max_parameters,
)


def _rows(spec):
    """spec: list of (eps, min_samples, n_components)."""
    return [dict(eps=e, min_samples=m, n_components=n) for e, m, n in spec]


def test_round_half_up():
    assert round_half_up(4.5) == 5
    assert round_half_up(6.5) == 7
    assert round_half_up(6.49) == 6
    assert round_half_up(7.0) == 7


def test_select_modal_simple_mode():
    rows = _rows([(1.0, 4, 2), (1.5, 5, 2), (2.0, 6, 3)])
    sel = select_modal(rows)
    assert sel["modal_counts"] == [2]
    assert sel["is_tie"] == 0
    assert sel["n_combos_averaged"] == 2
    assert sel["avg_eps"] == pytest.approx((1.0 + 1.5) / 2)
    assert sel["raw_avg_min_samples"] == pytest.approx(4.5)
    assert sel["rounded_min_samples"] == 5  # half-up


def test_select_modal_prefers_nonzero():
    rows = _rows([(1.0, 4, 0), (1.5, 5, 0), (2.0, 6, 0), (2.5, 7, 1)])
    sel = select_modal(rows)
    assert sel["modal_counts"] == [1]
    assert sel["n_combos_averaged"] == 1
    assert sel["avg_eps"] == pytest.approx(2.5)
    assert sel["rounded_min_samples"] == 7


def test_select_modal_all_zero_falls_back():
    rows = _rows([(1.0, 4, 0), (1.5, 6, 0)])
    sel = select_modal(rows)
    assert sel["modal_counts"] == [0]
    assert sel["n_combos_averaged"] == 2
    assert sel["rounded_min_samples"] == 5


def test_select_modal_tie_keeps_all_then_averages():
    # counts 1 and 2 each appear twice: tie -> average over ALL four combos.
    rows = _rows([(1.0, 4, 1), (1.5, 5, 1), (2.0, 6, 2), (4.0, 12, 2)])
    sel = select_modal(rows)
    assert sel["modal_counts"] == [1, 2]
    assert sel["is_tie"] == 1
    assert sel["n_combos_averaged"] == 4
    assert sel["avg_eps"] == pytest.approx(np.mean([1.0, 1.5, 2.0, 4.0]))
    assert sel["raw_avg_min_samples"] == pytest.approx(np.mean([4, 5, 6, 12]))
    assert sel["rounded_min_samples"] == 7  # mean 6.75 -> half-up 7


def test_select_modal_rounding_floor_of_one():
    rows = _rows([(1.0, 0, 1)])  # artificial: raw mean 0 -> floor to 1
    assert select_modal(rows)["rounded_min_samples"] == 1


def _two_blob_day():
    """Two 4x4 one-degree blobs, 20 cells apart: 2 clear DBSCAN components."""
    cells = []
    for lo in range(4):
        for la in range(4):
            cells.append((25.5 + lo, 30.5 + la))
            cells.append((45.5 + lo, 30.5 + la))
    lon = np.array([c[0] for c in cells])
    lat = np.array([c[1] for c in cells])
    return lon, lat


def test_compute_day_grid_shape_and_counts():
    lon, lat = _two_blob_day()
    rows = compute_day_grid(lon, lat)
    assert len(rows) == len(EPS_GRID) * len(MIN_SAMPLES_GRID) == 63
    counts = {r["n_components"] for r in rows}
    # Every combo resolves the two well-separated blobs or nothing.
    assert counts <= {0, 2}
    assert 2 in counts


def test_select_day_parameters_matches_manual_modal():
    lon, lat = _two_blob_day()
    rows = compute_day_grid(lon, lat)
    sel = select_day_parameters(lon, lat)
    assert sel == select_modal(rows)
    assert sel["modal_counts"] == [2]
    combos = [r for r in rows if r["n_components"] == 2]
    assert sel["avg_eps"] == pytest.approx(
        np.mean([r["eps"] for r in combos]))
    assert sel["rounded_min_samples"] == max(
        1, round_half_up(np.mean([r["min_samples"] for r in combos])))


def test_event_global_max_rule():
    day_params = pd.DataFrame({
        "new_event_id": [1, 1, 1, 2],
        "avg_eps": [2.0, 3.5, 2.5, 1.0],
        "raw_avg_min_samples": [6.2, 5.9, 7.4, 4.0],
        "rounded_min_samples": [6, 6, 7, 4],
    })
    ev = event_global_max_parameters(day_params).set_index("new_event_id")
    # eps = max of the daily AVERAGED eps values (kept continuous)
    assert ev.loc[1, "event_global_eps_max"] == pytest.approx(3.5)
    # minpts_used = max of the daily ROUNDED integers (primary rule)
    assert ev.loc[1, "event_global_minpts_used"] == 7
    # audit columns: max raw and its ceiling
    assert ev.loc[1, "event_global_minpts_max_raw"] == pytest.approx(7.4)
    assert ev.loc[1, "event_global_minpts_ceil_raw"] == 8
    # one-day event reproduces its own day exactly
    assert ev.loc[2, "event_global_eps_max"] == pytest.approx(1.0)
    assert ev.loc[2, "event_global_minpts_used"] == 4
