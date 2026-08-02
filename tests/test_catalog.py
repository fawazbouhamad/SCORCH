"""Catalog schema-validation tests on a small synthetic fixture."""
from pathlib import Path

import pandas as pd
import pytest

from scorch import catalog as cat

FIXTURE = Path(__file__).parent / "fixtures" / "master_fixture.csv"
PARAMS_FIXTURE = Path(__file__).parent / "fixtures" / "parameters_fixture.csv"


def test_fixture_loads_and_validates():
    df = cat.load_master(FIXTURE)
    summary = cat.validate_master(df)          # schema only, no count check
    assert summary["n_rows"] == 4
    assert summary["n_events"] == 2
    assert summary["n_dates"] == 3
    assert summary["type_counts"] == {1: 1, 4: 1}


def test_canonical_count_expectation_fails_on_fixture():
    df = cat.load_master(FIXTURE)
    with pytest.raises(cat.CatalogValidationError, match="expected 760 rows"):
        cat.validate_master(df, expect_canonical_counts=True)


def test_missing_column_rejected():
    df = cat.load_master(FIXTURE).drop(columns=["ellipse_area_km2"])
    with pytest.raises(cat.CatalogValidationError, match="missing required"):
        cat.validate_master(df)


def test_non_numeric_int_column_rejected():
    df = cat.load_master(FIXTURE)
    df["cluster_id"] = df["cluster_id"].astype(object)
    df.loc[0, "cluster_id"] = "not-a-number"
    with pytest.raises(cat.CatalogValidationError, match="cluster_id"):
        cat.validate_master(df)


def test_bad_date_rejected():
    df = cat.load_master(FIXTURE)
    df.loc[0, "date"] = "not-a-date"
    with pytest.raises(cat.CatalogValidationError, match="date"):
        cat.validate_master(df)


def test_event_parameters_fixture_validates():
    df = cat.load_event_parameters(PARAMS_FIXTURE)
    assert cat.validate_event_parameters(df) == {"n_events": 2}


def test_event_parameters_duplicate_rejected():
    df = cat.load_event_parameters(PARAMS_FIXTURE)
    df = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    with pytest.raises(cat.CatalogValidationError, match="duplicated"):
        cat.validate_event_parameters(df)


def test_export_master_roundtrip(tmp_path):
    df = cat.load_master(FIXTURE)
    out = tmp_path / "roundtrip.csv"
    cat.export_master(df, out)
    df2 = cat.load_master(out)
    assert list(df2.columns) == list(df.columns)
    assert df2.shape == df.shape
