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
``ds.license``. These guards inspect metadata on a **newly generated** file, so
they fail on the generator rather than on a stale artifact.

Generation uses a 2x2x2 synthetic grid with the dimension expectations
monkeypatched down; the attribute-writing code path exercised is the real one.
"""
from __future__ import annotations

import importlib.util
import os
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
BUILDER = REPO / "scripts" / "deposit" / "build_processed_field_netcdf.py"

# The required notice, verbatim and without brackets.
REQUIRED_NOTICE = (
    "Contains modified Copernicus Climate Change Service information 2026.")
NOTICE_STEM = "Copernicus Climate Change Service information"
COVERAGE = "1940-2025"


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


def test_generated_source_carries_no_copernicus_notice(generated_attrs):
    """The faux notice must be gone from ds.source - the actual regression."""
    src = generated_attrs["source"]
    assert NOTICE_STEM not in src, (
        "ds.source still carries a Copernicus attribution notice; the notice "
        f"belongs only in ds.license. Got: {src!r}")
    assert f"{NOTICE_STEM} ({COVERAGE})" not in src
    assert "(1940-2025)." not in src


def test_generated_source_keeps_coverage_only_as_coverage(generated_attrs):
    src = generated_attrs["source"]
    assert COVERAGE in src, "ds.source no longer records the coverage interval"
    # the span must be introduced AS coverage, not as a notice year token
    assert "coverage" in src.lower(), (
        f"ds.source mentions {COVERAGE} without labelling it as coverage: {src!r}")


def test_generated_license_carries_the_verbatim_notice(generated_attrs):
    lic = generated_attrs["license"]
    assert REQUIRED_NOTICE in lic, (
        f"ds.license does not carry the verbatim 2026 notice. Got: {lic!r}")
    assert f"{NOTICE_STEM} {COVERAGE}" not in lic, (
        "ds.license states the coverage span where the notice year token "
        "belongs - this is the year-token defect")
    assert f"{NOTICE_STEM} ({COVERAGE})" not in lic
    assert "ecds.ecmwf.int/licences/licence-to-use-copernicus-products" in lic, (
        "ds.license does not cite the current Copernicus licence URL")
    assert COVERAGE in lic, "ds.license omits the coverage interval"


def test_no_generated_attribute_uses_a_year_range_as_the_notice_token(
        generated_attrs):
    """Sweep EVERY global attribute, not just the two we expect to carry it."""
    inspected = 0
    for name, value in generated_attrs.items():
        if not isinstance(value, str) or NOTICE_STEM not in value:
            continue
        inspected += 1
        assert f"{NOTICE_STEM} {COVERAGE}" not in value, (
            f"ds.{name} uses the coverage span as the notice year token")
        assert f"{NOTICE_STEM} ({COVERAGE})" not in value, (
            f"ds.{name} brackets a coverage span where the year token belongs")
        assert f"{NOTICE_STEM} 2026" in value, (
            f"ds.{name} carries a Copernicus notice with a wrong year token")
    assert inspected == 1, (
        f"expected exactly ONE attribute to carry the notice (license), "
        f"found {inspected}")


# ---------------------------------------------------------------------------
# The candidate archive's shipped NetCDF.
# ---------------------------------------------------------------------------
NC_MEMBER = "gridded/scorch_processed_daily_tmax_field_v1.0.0.nc"


def _archive_nc_attrs():
    """Global attributes of the NetCDF inside the candidate archive, or None."""
    archive = os.environ.get("SCORCH_DATA_ARCHIVE")
    if not archive:
        return None
    path = Path(archive).expanduser()
    if not path.is_file():
        return None
    import tempfile

    from netCDF4 import Dataset

    with zipfile.ZipFile(path) as zf:
        if NC_MEMBER not in zf.namelist():
            return None
        with tempfile.TemporaryDirectory() as td:
            local = Path(td) / "field.nc"
            with zf.open(NC_MEMBER) as src, open(local, "wb") as dst:
                while True:
                    buf = src.read(1 << 20)
                    if not buf:
                        break
                    dst.write(buf)
            ds = Dataset(local, "r")
            try:
                return {n: ds.getncattr(n) for n in ds.ncattrs()}
            finally:
                ds.close()


@pytest.mark.xfail(
    strict=True,
    reason="KNOWN RELEASE BLOCKER: the local v1.0.0 archive candidate was "
           "built BEFORE the ds.source/ds.license Copernicus corrections, so "
           "its shipped NetCDF still carries the stale notice. Regenerating "
           "that member and rebuilding the archive is gated on the Figure 1/4 "
           "artwork authorization (D6) and is a section 9 step. An XPASS here "
           "means the archive was rebuilt - delete this marker and the "
           "blocker record when that happens.")
def test_candidate_archive_netcdf_metadata_is_current():
    pytest.importorskip("netCDF4")
    attrs = _archive_nc_attrs()
    if attrs is None:
        pytest.skip("SCORCH_DATA_ARCHIVE not set or archive lacks the NetCDF "
                    "member - cannot inspect the shipped metadata")
    assert NOTICE_STEM not in attrs["source"], (
        "archive ds.source still carries a Copernicus notice")
    assert REQUIRED_NOTICE in attrs["license"], (
        "archive ds.license lacks the verbatim 2026 notice")
