"""Regional day selection and consecutive-day event construction.

The threshold rule is copied VERBATIM from the canonical
``3_PCA_Algorithm.py`` (research repository; superseded for public use by
this module and the ``scorch reproduce`` builtin stages):

  * per-day count of active heatwave boxes over the FULL warm-season calendar
    (days with no heatwave boxes count as 0),
  * threshold Theta = integer-like quantile at BIGDAY_QUANTILE = 0.975 with
    method "higher" (pandas ``Series.quantile(q, method="higher")``, identical
    to numpy's "higher" method),
  * a day is selected when its count ``>= Theta``.

For the published SCORCH catalog this yields Theta = 371 and 395 selected
days, which group into 51 events as maximal runs of consecutive calendar days.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Canonical constants (3_PCA_Algorithm.py USER SETTINGS)
BIGDAY_QUANTILE = 0.975
QUANTILE_METHOD = "higher"


def quantile_threshold_intlike(series: pd.Series, q: float,
                               method: str = "higher") -> float:
    """Verbatim copy of ``3_PCA_Algorithm.py:quantile_threshold_intlike``."""
    try:
        return float(series.quantile(q, method=method))           # pandas >= 2.0
    except TypeError:
        return float(series.quantile(q, interpolation=method))    # older pandas


def select_days(day_counts_all, q=BIGDAY_QUANTILE, method=QUANTILE_METHOD):
    """Select regionally extensive days from per-day heatwave-box counts.

    Parameters
    ----------
    day_counts_all : pd.Series
        Heatwave-box count per calendar day, indexed by date, covering the
        FULL calendar of candidate days (zeros included). This matches the
        canonical ``day_counts_hw.reindex(all_dates, fill_value=0)``.
    q, method : the canonical quantile (0.975) and method ("higher").

    Returns
    -------
    (selected_index, threshold) : selected days (DatetimeIndex or the input
    index type, in ascending order) and the threshold Theta.
    """
    eligible = pd.Series(day_counts_all)
    thr = quantile_threshold_intlike(eligible, q, method=method)
    big_days = eligible[eligible >= thr].index      # canonical: eligible >= thr
    return big_days, thr


def build_events(selected_days):
    """Group selected days into events = maximal runs of consecutive days.

    Parameters
    ----------
    selected_days : iterable of datetime-like values (the selected days).

    Returns
    -------
    DataFrame with columns ``date`` (Timestamp, ascending) and ``event_id``
    (1-based, ascending in time). A new event starts whenever the gap to the
    previous selected day exceeds one calendar day.
    """
    dates = pd.DatetimeIndex(sorted(pd.to_datetime(list(selected_days))))
    if len(dates) == 0:
        return pd.DataFrame({"date": pd.DatetimeIndex([]), "event_id": []})
    gaps = np.diff(dates.values).astype("timedelta64[D]").astype(int)
    new_event = np.concatenate([[True], gaps > 1])
    event_ids = np.cumsum(new_event)
    return pd.DataFrame({"date": dates, "event_id": event_ids.astype(int)})


def event_summary(events_df):
    """Per-event start/end/duration summary from :func:`build_events` output."""
    g = events_df.groupby("event_id")["date"]
    out = pd.DataFrame({
        "event_id": sorted(events_df["event_id"].unique()),
    })
    out["start_date"] = g.min().values
    out["end_date"] = g.max().values
    out["n_days"] = g.count().values
    return out
