"""Regression against the frozen canonical catalog (skipped when absent).

Looks for the canonical files first via the SCORCH_CANONICAL_DATA_DIR
environment variable, then by walking up from this file for the research
repository's frozen catalog directory layout. No absolute paths are
embedded; on machines without the frozen catalog every test here skips
with a clear message.
"""
import os
from pathlib import Path

import pandas as pd
import pytest

MASTER_NAME = "scorch_new_algorithm_master_cluster_ellipse_event_global_max.csv"
LABELS_NAME = "final_labels_event_global_max.csv"
PARAMS_NAME = "event_global_max_parameters.csv"

EXPECTED_TYPE_COUNTS = {1: 3, 2: 4, 3: 20, 4: 24}


def _find_canonical_dir():
    env = os.environ.get("SCORCH_CANONICAL_DATA_DIR")
    if env and (Path(env) / MASTER_NAME).exists():
        return Path(env)
    # A downloaded/extracted processed-data deposit (catalogs/ layout),
    # discovered via SCORCH_DATA_DIR or the default fetch destination.
    data_env = os.environ.get("SCORCH_DATA_DIR")
    roots = [Path(data_env)] if data_env else []
    for parent in Path(__file__).resolve().parents:
        roots.append(parent / "scorch_data")
    for root in roots:
        if not root or not root.exists():
            continue
        for cand in ([root / "catalogs"]
                     + [p / "catalogs" for p in sorted(root.glob("*"))
                        if p.is_dir()]):
            if (cand / MASTER_NAME).exists():
                return cand
    # The research repository's frozen catalog directory layout.
    for parent in Path(__file__).resolve().parents:
        cand = parent / "clean" / "data"
        if (cand / MASTER_NAME).exists():
            return cand
    return None


DATA_DIR = _find_canonical_dir()

pytestmark = pytest.mark.skipif(
    DATA_DIR is None,
    reason="canonical frozen catalog not available on this machine "
           "(set SCORCH_CANONICAL_DATA_DIR to enable)")


@pytest.fixture(scope="module")
def master():
    from scorch.catalog import load_master
    return load_master(DATA_DIR / MASTER_NAME)


@pytest.fixture(scope="module")
def params():
    return pd.read_csv(DATA_DIR / PARAMS_NAME)


@pytest.fixture(scope="module")
def labels():
    df = pd.read_csv(DATA_DIR / LABELS_NAME)
    df["date"] = df["date"].astype(str)
    return df


def test_canonical_counts(master):
    from scorch.catalog import validate_master
    summary = validate_master(master, expect_canonical_counts=True)
    assert summary["n_rows"] == 760
    assert summary["n_events"] == 51
    assert summary["n_dates"] == 395
    assert summary["type_counts"] == EXPECTED_TYPE_COUNTS


def test_params_v3_type_matches_master(master, params):
    """v1.0.1 metadata-only correction: the per-event parameter table's
    v3_type must equal the master catalog's per-event typology for all 51
    events. The frozen v1.0.0 parameter CSV carried a stale v3_type = 4 for
    event 14; the corrected value (and the mechanical typology) is 3.
    DBSCAN eps/minPts are unaffected."""
    m = (master.drop_duplicates("new_event_id")
               .set_index("new_event_id")["v3_type"].astype(int).sort_index())
    p = (params.set_index("new_event_id")["v3_type"].astype(int).sort_index())
    assert len(p) == 51
    mismatches = {int(e): (int(p[e]), int(m[e])) for e in p.index
                  if int(p[e]) != int(m[e])}
    assert not mismatches, (
        f"parameter-table v3_type disagrees with the master catalog: "
        f"{mismatches} (params, master)")
    assert int(p.loc[14]) == 3, "event 14 must carry the corrected v3_type=3"


def test_typology_recomputation_matches(master):
    from scorch.typology import classify_events
    derived = classify_events(master).set_index("new_event_id")
    stored = master.groupby("new_event_id")["v3_type"].first()
    for eid, stored_type in stored.items():
        assert derived.loc[eid, "derived_type"] == int(stored_type), (
            f"event {eid}: recomputed type "
            f"{derived.loc[eid, 'derived_type']} != stored {stored_type}")


def _sample_event_days(master, per_type=3):
    """~10-12 event-days across all four types (first day of sampled events)."""
    per_event = master.groupby("new_event_id")["v3_type"].first()
    days = []
    for t in (1, 2, 3, 4):
        for eid in per_event[per_event == t].index[:per_type]:
            dates = sorted(master.loc[master["new_event_id"] == eid, "date"]
                           .unique())
            days.append((int(eid), dates[0]))
    return days


def test_ellipse_geometry_recomputation(master, params, labels):
    """Recluster sampled days with the event-global-max parameters and refit
    ellipses with the packaged kernel; compare to the frozen master."""
    from scorch.clustering import cluster_day_cells
    from scorch.ellipses import fit_day_ellipses

    p = params.set_index("new_event_id")
    checked = 0
    for eid, date in _sample_event_days(master):
        eps = float(p.loc[eid, "event_global_eps_max"])
        minpts = int(p.loc[eid, "event_global_minpts_used"])

        day_cells = labels[labels["date"] == date]
        assert not day_cells.empty, f"no label cells for {date}"
        lon = day_cells["lon"].to_numpy(float)
        lat = day_cells["lat"].to_numpy(float)

        lab = cluster_day_cells(lon, lat, eps=eps, min_samples=minpts)
        rows = fit_day_ellipses(lon, lat, lab, sigma=1.25)

        ref = (master[(master["new_event_id"] == eid) &
                      (master["date"] == date)]
               .sort_values("cluster_id").reset_index(drop=True))
        assert len(rows) == len(ref), (
            f"event {eid} {date}: recomputed {len(rows)} ellipses, "
            f"master has {len(ref)}")
        for row in rows:
            r = ref.iloc[row["cluster_id"]]
            for pkg_key, csv_key in [("ellipse_area_km2", "ellipse_area_km2"),
                                     ("major_axis_km", "major_axis_km"),
                                     ("minor_axis_km", "minor_axis_km")]:
                assert row[pkg_key] == pytest.approx(
                    float(r[csv_key]), rel=1e-6), (
                    f"event {eid} {date} cluster {row['cluster_id']}: "
                    f"{pkg_key} {row[pkg_key]} != {r[csv_key]}")
            checked += 1
    assert checked > 0
