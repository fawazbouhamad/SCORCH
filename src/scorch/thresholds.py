"""Per-box aggregation, p95 thresholds, and exceedance flags.

Extracted from the research repository's canonical ``2_Heatwave_Algorithm.py``
(released here as ``scripts/pipeline/build_master_dataset.py``).
The numerical logic (1-degree box assignment with centres at .5, mean
aggregation of the 0.25-degree cells falling in each box, per-box 95th
percentile with the pandas default linear interpolation, and the
``val >= thr_p95`` exceedance rule) is copied unchanged; only the I/O and
module-global configuration were replaced by explicit function arguments.

Canonical defaults (SCORCH study domain):
    lat 10-46 N, lon 20-70 E, warm season Apr-Sep (months 4..9),
    BOX_AGG = "mean", all available years as baseline.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Canonical region of interest (2_Heatwave_Algorithm.py USER CONFIG)
LAT_MIN, LAT_MAX = 10.0, 46.0
LON_MIN, LON_MAX = 20.0, 70.0
MONTHS = [4, 5, 6, 7, 8, 9]


def aggregate_to_one_degree(df, agg="mean",
                            lat_min=LAT_MIN, lat_max=LAT_MAX,
                            lon_min=LON_MIN, lon_max=LON_MAX):
    """Aggregate sub-degree cell values to 1-degree boxes (centres at .5).

    Parameters
    ----------
    df : DataFrame with columns ``date``, ``lat``, ``lon``, ``val``
        Long-format daily values on the native (e.g. 0.25-degree) grid.
        Rows with NaN ``val`` are dropped, as in the canonical script.
    agg : {"mean", "max"}
        Canonical SCORCH uses ``"mean"`` (BOX_AGG = "mean").

    Returns
    -------
    DataFrame with columns ``date``, ``lat1``, ``lon1``, ``val`` -- one row
    per (date, 1-degree box), matching
    ``2_Heatwave_Algorithm.py:to_boxes_dataframe`` applied day by day.
    """
    df = df[["date", "lat", "lon", "val"]].dropna(subset=["val"]).copy()

    # Assign to 1-degree cells centered at .5 (canonical formula)
    df["lat1"] = np.floor(df["lat"]) + 0.5
    df["lon1"] = np.floor(df["lon"]) + 0.5

    # Keep only boxes fully inside region bounds
    df = df[(df["lat1"].between(lat_min, lat_max)) &
            (df["lon1"].between(lon_min, lon_max))]

    # Aggregate within each 1-degree cell (per day)
    if str(agg).lower() == "max":
        out = df.groupby(["date", "lat1", "lon1"], as_index=False)["val"].max()
    else:
        out = df.groupby(["date", "lat1", "lon1"], as_index=False)["val"].mean()

    out["date"] = pd.to_datetime(out["date"])
    return out[["date", "lat1", "lon1", "val"]]


def compute_p95_thresholds(all_box_daily, baseline_years=None, months=None):
    """Compute per-box p95 thresholds.

    Verbatim logic from ``2_Heatwave_Algorithm.py:compute_p95_thresholds``:
    pandas ``quantile(0.95)`` with its default (linear) interpolation over the
    baseline subset.

    Parameters
    ----------
    all_box_daily : DataFrame [date, lat1, lon1, val]
    baseline_years : optional (y0, y1) inclusive year range (None = all years)
    months : optional list of calendar months to keep (canonical: 4..9).
        ``None`` uses the canonical warm-season months. Pass an empty list or
        ``"all"`` to disable month filtering.

    Returns
    -------
    DataFrame [lat1, lon1, thr_p95]
    """
    df = all_box_daily.copy()
    df["date"] = pd.to_datetime(df["date"])

    if baseline_years is not None:
        y0, y1 = baseline_years
        df = df[(df["date"].dt.year >= y0) & (df["date"].dt.year <= y1)]

    if months is None:
        months = MONTHS
    if months != "all" and len(months) > 0:
        df = df[df["date"].dt.month.isin(months)]

    thr = df.groupby(["lat1", "lon1"], as_index=False)["val"].quantile(0.95)
    thr = thr.rename(columns={"val": "thr_p95"})
    return thr


def label_exceedance(all_box_daily, thresholds=None):
    """Join thresholds and build the 0/1 exceedance flag.

    Verbatim rule from the canonical script: ``exceed = (val >= thr_p95)``.

    Parameters
    ----------
    all_box_daily : DataFrame [date, lat1, lon1, val]
    thresholds : optional DataFrame [lat1, lon1, thr_p95]
        If None, thresholds are computed from ``all_box_daily`` with
        :func:`compute_p95_thresholds` (canonical all-years baseline).

    Returns
    -------
    DataFrame [date, lat1, lon1, val, thr_p95, exceed]
    """
    if thresholds is None:
        thresholds = compute_p95_thresholds(all_box_daily)
    df = all_box_daily.merge(thresholds, on=["lat1", "lon1"], how="left")
    if df["thr_p95"].isna().any():
        missing = df[df["thr_p95"].isna()][["lat1", "lon1"]].drop_duplicates()
        raise RuntimeError(
            f"Missing thresholds for some boxes (no baseline data?):\n{missing}")
    df["exceed"] = (df["val"] >= df["thr_p95"]).astype(int)
    return df
