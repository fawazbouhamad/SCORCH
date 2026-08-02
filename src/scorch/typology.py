"""Mechanical SCORCH event typology (Types 1-4).

``derive_type`` is a VERBATIM copy of the canonical rule in
``reclassify_event_types_global_max.py`` (released here as
``scripts/pipeline/reclassify_event_types_global_max.py``):

  Type 1: single-day event with exactly 1 ellipse.
  Type 2: single-day event with multiple (>1) ellipses.
  Type 3: multi-day event (>=2 days) whose days are CONSISTENT --
          every day has exactly 1 ellipse, OR every day has >1 ellipse.
  Type 4: multi-day event with MIXED structure -- at least one day with
          exactly 1 ellipse AND at least one other day with >1 ellipse.

(No event-day has 0 ellipses in the published catalog, so every day is 1
or >1.)
"""
from __future__ import annotations

import pandas as pd

# Canonical formatting of each type label (mirrors the canonical workbook).
TYPE_FIELDS = {
    1: dict(type="Type 1", event_type="Type 1", event_type_name="Independent",
            event_type_original="Independent"),
    2: dict(type="Type 2", event_type="Type 2",
            event_type_name="Spatially clustered",
            event_type_original="Independent Simultaneous"),
    3: dict(type="Type 3", event_type="Type 3",
            event_type_name="Temporally clustered",
            event_type_original="Back-to-Back"),
    4: dict(type="Type 4", event_type="Type 4", event_type_name="Mixed",
            event_type_original="Mixed Multi-Day"),
}
TYPE_NAME = {1: "Type 1", 2: "Type 2", 3: "Type 3", 4: "Type 4"}


def derive_type(daily_counts) -> int:
    """Mechanical type from an ordered list of per-day ellipse counts."""
    counts = list(daily_counts)
    n_days = len(counts)
    if n_days <= 1:
        return 1 if counts and counts[0] == 1 else 2
    all_one = all(c == 1 for c in counts)
    all_multi = all(c > 1 for c in counts)
    return 3 if (all_one or all_multi) else 4


def classify_events(master_df, event_col="new_event_id", date_col="date"):
    """Mechanically classify every event in a master ellipse catalog.

    Parameters
    ----------
    master_df : DataFrame with one row per ellipse, carrying at least the
        event id and date columns (the published master schema).
    event_col, date_col : column names (canonical defaults).

    Returns
    -------
    DataFrame with one row per event:
        event id, n_days, daily_sequence ("-"-joined per-day ellipse counts,
        days in ascending date order), derived_type (int 1-4), and the
        canonical label columns (type, event_type, event_type_name,
        event_type_original).
    """
    df = master_df[[event_col, date_col]].copy()
    df[date_col] = df[date_col].astype(str)
    counts = (df.groupby([event_col, date_col]).size().rename("n_ellipses")
                .reset_index()
                .sort_values([event_col, date_col]))
    rows = []
    for eid, g in counts.groupby(event_col):
        seq = g["n_ellipses"].tolist()
        t = derive_type(seq)
        rec = {
            event_col: eid,
            "n_days": len(seq),
            "daily_sequence": "-".join(map(str, seq)),
            "derived_type": int(t),
        }
        rec.update(TYPE_FIELDS[t])
        rows.append(rec)
    return pd.DataFrame(rows).sort_values(event_col).reset_index(drop=True)
