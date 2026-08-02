"""Regional day selection tests: integer-like P97.5 'higher' and events."""
import numpy as np
import pandas as pd
import pytest

from scorch.selection import (
    quantile_threshold_intlike,
    select_days,
    build_events,
    event_summary,
)


def test_quantile_matches_numpy_method_higher():
    rng = np.random.default_rng(20260617)
    counts = pd.Series(rng.integers(0, 500, size=1000).astype(float))
    thr = quantile_threshold_intlike(counts, 0.975, method="higher")
    expected = float(np.quantile(counts.to_numpy(), 0.975, method="higher"))
    assert thr == expected
    # "higher" returns an actual observed value, hence integer-like here.
    assert thr == int(thr)


def test_quantile_higher_small_series():
    counts = pd.Series([0.0, 0.0, 1.0, 2.0, 100.0])
    # 0.975 quantile with method 'higher' picks the smallest observation whose
    # cumulative position is >= q: here the maximum.
    assert quantile_threshold_intlike(counts, 0.975) == 100.0


def test_select_days_ge_threshold():
    dates = pd.date_range("2000-04-01", periods=40, freq="D")
    values = np.zeros(40)
    values[10] = 500.0
    values[20] = 400.0
    counts = pd.Series(values, index=dates)
    selected, thr = select_days(counts, q=0.975, method="higher")
    expected_thr = float(np.quantile(values, 0.975, method="higher"))
    assert thr == expected_thr
    # Selection is `count >= thr`, on the full zero-filled calendar.
    assert list(selected) == list(dates[values >= expected_thr])


def test_build_events_consecutive_runs():
    days = (list(pd.date_range("2000-06-01", periods=3, freq="D")) +   # run 1
            [pd.Timestamp("2000-06-10")] +                             # run 2
            list(pd.date_range("2000-07-01", periods=2, freq="D")))    # run 3
    ev = build_events(days)
    assert ev["event_id"].tolist() == [1, 1, 1, 2, 3, 3]
    summ = event_summary(ev)
    assert summ["n_days"].tolist() == [3, 1, 2]
    assert summ.loc[0, "start_date"] == pd.Timestamp("2000-06-01")
    assert summ.loc[0, "end_date"] == pd.Timestamp("2000-06-03")


def test_build_events_unsorted_input_and_empty():
    days = [pd.Timestamp("2000-06-02"), pd.Timestamp("2000-06-01")]
    ev = build_events(days)
    assert ev["event_id"].tolist() == [1, 1]
    assert build_events([]).empty


def test_build_events_season_break_not_consecutive():
    # Sep 30 -> Apr 1 of next year is a >1 day gap: separate events.
    days = [pd.Timestamp("2000-09-30"), pd.Timestamp("2001-04-01")]
    ev = build_events(days)
    assert ev["event_id"].tolist() == [1, 2]
