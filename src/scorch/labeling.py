"""Per-box heatwave labelling of a 0/1 daily exceedance series.

``ensure_datetime_index`` and ``label_heatwaves`` are VERBATIM copies of the
functions in the research repository's canonical ``2_Heatwave_Algorithm.py``
(released here as ``scripts/pipeline/build_master_dataset.py``)
(the algorithm that produced the canonical catalog). Do not modify them.

Canonical rules (min_len=3, min_ones=3, allow_unlimited_single_zeros=True):
  * split candidate segments at any two consecutive zeros ("00"),
  * trim each segment so it starts and ends with an exceedance day,
  * qualify if trimmed length >= 3 days AND >= 3 exceedance days,
  * unlimited single-zero gaps are bridged inside an event.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def ensure_datetime_index(series_like):
    """
    Ensure the input Series has a DatetimeIndex (robust against RangeIndex).
    Raises if conversion is impossible.
    """
    s = pd.Series(series_like)
    try:
        idx = pd.DatetimeIndex(s.index)
    except Exception as e:
        raise ValueError(
            "Expected a DatetimeIndex for the exceedance series. "
            "Make sure to set_index('date') before passing."
        ) from e

    if idx.tz is not None:
        idx = idx.tz_convert(None)

    s.index = idx
    if s.index.isna().any():
        raise ValueError("DatetimeIndex contains NaT values.")
    return s


def label_heatwaves(
    exceed_series,
    min_len=3,
    min_ones=3,  # UPDATED: require at least 3 exceedance days
    allow_unlimited_single_zeros=True
):
    """
    Label heatwaves in a 0/1 daily exceedance series.

    UPDATED BEHAVIOR:
    - Split by any "00" (two consecutive zeros).
    - For each segment, trim leading/trailing zeros so events START and END with '1'.
    - An event qualifies if:
        * trimmed length >= min_len
        * ones_count >= min_ones
      Unlimited single-zero gaps allowed inside the event if allow_unlimited_single_zeros=True.

    Returns
    -------
    labels : pd.Series of heatwave_id (0 if not in any), aligned to input index
    episodes : list of tuples (hw_id, start_date, end_date, length_days, ones_count, zeros_count)
    """
    s = ensure_datetime_index(exceed_series).astype(int)
    idx = s.index
    vals = s.values

    zero = (vals == 0)

    # Positions of the first zero in each "00"
    double_zero_breaks = np.where((zero[:-1]) & (zero[1:]))[0]

    # Build raw segments between "00" breaks (inclusive indices)
    boundaries = [-1] + double_zero_breaks.tolist() + [len(s) - 1]
    raw_segments = []
    for a, b in zip(boundaries[:-1], boundaries[1:]):
        i0, i1 = a + 1, b
        if i0 <= i1:
            raw_segments.append((i0, i1))

    hw_id = 0
    labels = pd.Series(0, index=idx, dtype=int)
    episodes = []

    for (i0, i1) in raw_segments:
        seg_vals = vals[i0:i1 + 1]

        # If there are no 1s, nothing to label
        if seg_vals.sum() == 0:
            continue

        # TRIM so event starts at first 1 and ends at last 1
        ones_pos = np.where(seg_vals == 1)[0]
        j0 = i0 + int(ones_pos[0])
        j1 = i0 + int(ones_pos[-1])

        event_vals = vals[j0:j1 + 1]
        ones_count  = int(event_vals.sum())
        zeros_count = int((event_vals == 0).sum())
        length_days = int(j1 - j0 + 1)

        if allow_unlimited_single_zeros:
            ok = (length_days >= min_len) and (ones_count >= min_ones)
        else:
            ok = (length_days >= min_len) and (ones_count >= min_ones) and (zeros_count <= 1)

        if ok:
            hw_id += 1
            labels.iloc[j0:j1 + 1] = hw_id
            episodes.append((
                hw_id,
                idx[j0].date(),
                idx[j1].date(),
                length_days,
                ones_count,
                zeros_count
            ))

    return labels, episodes


# Public, descriptive alias used by the package API.
identify_heatwaves = label_heatwaves
