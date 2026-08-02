"""Mechanical Type 1-4 typology tests."""
import pandas as pd

from scorch.typology import derive_type, classify_events, TYPE_FIELDS


def _master(rows):
    """rows: list of (event_id, date, n_ellipses) -> synthetic master frame."""
    recs = []
    for eid, date, n in rows:
        for k in range(n):
            recs.append(dict(new_event_id=eid, date=date, cluster_id=k))
    return pd.DataFrame(recs)


def test_derive_type_rules():
    assert derive_type([1]) == 1              # single day, 1 ellipse
    assert derive_type([3]) == 2              # single day, >1 ellipse
    assert derive_type([1, 1, 1]) == 3        # multi-day, all 1
    assert derive_type([2, 4, 3, 2]) == 3     # multi-day, all >1: consistent
    assert derive_type([1, 3]) == 4           # mixed
    assert derive_type([2, 1, 2]) == 4        # mixed


def test_classify_events_each_type():
    df = _master([
        (1, "2000-06-01", 1),                              # T1
        (2, "2000-06-10", 3),                              # T2
        (3, "2000-06-20", 1), (3, "2000-06-21", 1),        # T3 (all ones)
        (4, "2000-07-01", 2), (4, "2000-07-02", 3),        # T3 (all multi)
        (5, "2000-07-10", 1), (5, "2000-07-11", 2),        # T4 (mixed)
    ])
    out = classify_events(df).set_index("new_event_id")
    assert out.loc[1, "derived_type"] == 1
    assert out.loc[2, "derived_type"] == 2
    assert out.loc[3, "derived_type"] == 3
    assert out.loc[4, "derived_type"] == 3
    assert out.loc[5, "derived_type"] == 4
    # canonical label columns populated
    assert out.loc[5, "event_type_name"] == "Mixed"
    assert out.loc[3, "type"] == "Type 3"
    assert out.loc[1, "event_type_original"] == "Independent"


def test_classify_events_event14_pattern():
    # The event-14 global-max pattern: multi-day counts 2-4-3-2 -> every day
    # has >1 ellipse -> consistent -> Type 3 (the documented T4 -> T3 flip).
    df = _master([
        (14, "2010-08-01", 2), (14, "2010-08-02", 4),
        (14, "2010-08-03", 3), (14, "2010-08-04", 2),
    ])
    out = classify_events(df).set_index("new_event_id")
    assert out.loc[14, "derived_type"] == 3
    assert out.loc[14, "daily_sequence"] == "2-4-3-2"


def test_classify_events_orders_days_by_date():
    # Days supplied out of order must still yield the date-ordered sequence.
    df = _master([
        (7, "2005-06-03", 2), (7, "2005-06-01", 1), (7, "2005-06-02", 2),
    ])
    out = classify_events(df).set_index("new_event_id")
    assert out.loc[7, "daily_sequence"] == "1-2-2"
    assert out.loc[7, "derived_type"] == 4


def test_type_fields_labels_match_canon():
    assert TYPE_FIELDS[2]["event_type_name"] == "Spatially clustered"
    assert TYPE_FIELDS[3]["event_type_original"] == "Back-to-Back"
    assert TYPE_FIELDS[4]["event_type_original"] == "Mixed Multi-Day"
