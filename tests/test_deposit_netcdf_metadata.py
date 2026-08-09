"""Copernicus attribution metadata in the deposit NetCDF.

The processed-field NetCDF carries the required Copernicus notice. Two distinct
things must never be confused, and an earlier revision confused them:

* the **notice year token**, which is the year of use - ``2026`` - and must
  appear verbatim and without brackets;
* the **coverage interval** of the ERA5 data actually used, ``1940-2025``.

``ds.source`` used to end with "Contains modified Copernicus Climate Change
Service information (1940-2025)", which is neither: it is the notice wording
carrying a parenthesised coverage range where the year token belongs. It was a
second, drifting copy of a notice that has exactly one authoritative home,
``ds.license``.

This module validates the **generator**: a newly written file, so a defect
fails on the code that produces it rather than on a stale artifact.

The **shipped member** of the archive candidate is validated by the single
explicit release gate in ``tests/test_archive_backed_verification.py``, using
this same contract (``scripts/deposit/deposit_contract.py``), so a defect
cannot be acceptable in one population and not the other.

That gate previously lived here under an unconditional ``xfail(strict=True)``,
which meant a stale archive was absorbed as an expected failure and ``pytest``
still exited 0 even under ``SCORCH_REQUIRE_ARCHIVE=1``. The marker is gone and
the check now has exactly one home.

Generation uses a 2x2 grid with the dimension expectations monkeypatched down;
the attribute-writing code path exercised is the real one.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
BUILDER = REPO / "scripts" / "deposit" / "build_processed_field_netcdf.py"
_DEPOSIT_DIR = REPO / "scripts" / "deposit"
if str(_DEPOSIT_DIR) not in sys.path:
    sys.path.insert(0, str(_DEPOSIT_DIR))

from deposit_contract import (  # noqa: E402  (sys.path set up just above)
    COVERAGE_INTERVAL,
    NOTICE_STEM,
    REQUIRED_NOTICE,
    check_netcdf_metadata,
    netcdf_metadata_issues,
)


def _load_builder():
    spec = importlib.util.spec_from_file_location("_scorch_nc_builder", BUILDER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def builder():
    pytest.importorskip("netCDF4")
    pytest.importorskip("pandas")
    assert BUILDER.is_file(), f"{BUILDER} is missing"
    return _load_builder()


@pytest.fixture(scope="module")
def generated_attrs(builder, tmp_path_factory):
    """Global attributes of a NetCDF written by the real generator."""
    import pandas as pd
    from netCDF4 import Dataset

    tmp = tmp_path_factory.mktemp("nc_meta")
    # The generator chunks the time axis at 183 (one warm season), and netCDF4
    # rejects a chunksize larger than its dimension, so the synthetic time axis
    # must be at least that long. 183 x 2 x 2 = 732 rows, which is trivial.
    dates = [str(d.date()) for d in
             pd.date_range("1940-04-01", periods=183, freq="D")]
    lats, lons = [10.5, 11.5], [20.5, 21.5]

    rows = []
    for i, d in enumerate(dates):
        for la in lats:
            for lo in lons:
                thr = 40.0 + la          # per-cell constant, as the real table is
                val = thr + (1.0 if i % 2 == 0 else -1.0)
                rows.append({"date": d, "lat1": la, "lon1": lo, "val": val,
                             "thr_p95": thr, "exceed": int(val >= thr),
                             "heatwave_id": 1 if val >= thr else 0})
    csv_path = tmp / "synthetic_master.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)

    builder.N_TIME_EXPECTED = len(dates)
    builder.N_LAT_EXPECTED = len(lats)
    builder.N_LON_EXPECTED = len(lons)

    out = tmp / "field.nc"
    builder.build(csv_path, out)
    assert out.is_file(), "generator produced no NetCDF"

    ds = Dataset(out, "r")
    try:
        return {name: ds.getncattr(name) for name in ds.ncattrs()}
    finally:
        ds.close()


# ---------------------------------------------------------------------------
# 1. The generator satisfies the whole contract.
# ---------------------------------------------------------------------------
def test_generated_metadata_satisfies_the_full_contract(generated_attrs):
    """Every one of the nine predicates, on freshly generated attributes."""
    check_netcdf_metadata(generated_attrs)


def test_generated_source_carries_no_copernicus_notice(generated_attrs):
    """The faux notice must be gone from ds.source - the actual regression."""
    src = generated_attrs["source"]
    assert NOTICE_STEM not in src, (
        "ds.source still carries a Copernicus attribution notice; the notice "
        f"belongs only in ds.license. Got: {src!r}")
    assert "NETCDF_SOURCE_CONTRACT" not in netcdf_metadata_issues(
        generated_attrs)


def test_generated_source_keeps_coverage_only_as_coverage(generated_attrs):
    src = generated_attrs["source"]
    assert COVERAGE_INTERVAL in src, (
        "ds.source no longer records the coverage interval")
    assert "coverage" in src.lower(), (
        f"ds.source mentions {COVERAGE_INTERVAL} without labelling it as "
        f"coverage: {src!r}")


def test_generated_license_carries_the_verbatim_notice(generated_attrs):
    lic = generated_attrs["license"]
    assert REQUIRED_NOTICE in lic, (
        f"ds.license does not carry the verbatim notice. Got: {lic!r}")


def test_the_contract_is_not_vacuous():
    """A validator that never fires would make every gate above meaningless."""
    stale = {
        "source": "ERA5 1940-2025 coverage. Contains modified Copernicus "
                  "Climate Change Service information (1940-2025).",
        "license": "CC BY 4.0. See https://cds.climate.copernicus.eu/x. "
                   "Contains modified Copernicus Climate Change Service "
                   "information 1940-2025.",
        "references": "SCORCH Framework (in review).",
    }
    issues = netcdf_metadata_issues(stale)
    for expected in ("NETCDF_SOURCE_CONTRACT", "NETCDF_NOTICE_EXACT",
                     "NETCDF_RETIRED_CDS_URL", "NETCDF_CURRENT_ECDS_URL",
                     "NETCDF_AUTHORS_RIGHTS_SCOPE",
                     "NETCDF_NOTICE_COVERAGE_YEAR",
                     "NETCDF_REFERENCES_STATUS"):
        assert expected in issues, f"{expected} not detected on stale metadata"
    assert list(issues) == sorted(set(issues)), (
        "issue codes must be sorted and unique")


# ---------------------------------------------------------------------------
# 2. The SHIPPED archive member is not checked here.
#
# It is checked by the single explicit release gate,
# ``tests/test_archive_backed_verification.py::
#   test_release_gate_archive_is_available_and_valid``,
# which validates availability, structure and shipped metadata together using
# this same contract. Keeping a second, independent archive assertion here
# would report the identical defect twice and make a release run ambiguous
# about how many things are actually wrong. This module now covers exactly one
# thing: that the GENERATOR emits compliant metadata.
# ---------------------------------------------------------------------------
