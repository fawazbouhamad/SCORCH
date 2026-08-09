"""Adversarial proof that the required-archive release gate really is a gate.

A gate that reports success on a defective artifact is worse than no gate: it
launders a known problem into a green tick. Before this suite existed the
archive metadata guard carried an unconditional ``xfail(strict=True)``, so the
stale v1.0.0 candidate produced ``373 passed, 22 skipped, 1 xfailed`` and
``pytest`` exited **0** even with ``SCORCH_REQUIRE_ARCHIVE=1``.

So this file does not assert on the validator directly - a validator can always
be talked into agreeing with itself. It builds a *structurally real* synthetic
archive (the same 109 / 108 / 107 arithmetic as the deposit), proves the real
gate nodes go GREEN on it, then breaks exactly one invariant at a time and
re-runs **the actual gate node in a subprocess**, requiring each mutant to:

* exit NONZERO,
* be reported as FAILED (never skipped, never xfailed),
* and emit its expected stable issue code.

The subprocess always targets exact non-adversarial node IDs, so it can never
recursively collect this module.
"""
from __future__ import annotations

import csv
import hashlib
import io
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
_DEPOSIT_DIR = REPO / "scripts" / "deposit"
if str(_DEPOSIT_DIR) not in sys.path:
    sys.path.insert(0, str(_DEPOSIT_DIR))

from deposit_contract import (  # noqa: E402  (sys.path set up just above)
    AUTHORS_RIGHTS_CLAUSE,
    COVERAGE_INTERVAL,
    CURRENT_LICENCE_URL,
    MANIFEST_COLUMNS,
    MANIFEST_MEMBER,
    MANUSCRIPT_STATUS,
    REQUIRED_DISCLAIMER,
    REQUIRED_NOTICE,
    RETIRED_LICENCE_HOST,
    SUMS_MEMBER,
    archive_structure_issues,
    is_truthy_flag,
)

netCDF4 = pytest.importorskip("netCDF4")

MEMBER_COUNT = 109                     # payloads + SHA256SUMS + FILE_MANIFEST
PAYLOAD_COUNT = MEMBER_COUNT - 2       # 107
NC_MEMBER = "gridded/scorch_processed_daily_tmax_field_v1.0.0.nc"

#: The ONE explicit release gate: availability, structure and shipped metadata.
#: Both aliases point at it so each mutation below still reads as the specific
#: thing it breaks.
GATE_NODE = ("tests/test_archive_backed_verification.py"
             "::test_release_gate_archive_is_available_and_valid")
STRUCTURE_NODE = GATE_NODE
NETCDF_NODE = GATE_NODE

#: The whole archive-backed module, used to prove that a required-but-missing
#: archive yields exactly ONE ordinary failure with no fixture errors.
GATE_MODULE = "tests/test_archive_backed_verification.py"

# Windows MAX_PATH is 260 characters and pytest's tmp dirs nest deeply; a long
# basetemp silently turns unrelated passes into FileNotFoundError failures,
# which would make a mutant look like it failed for the right reason when it
# did not. Keep the subprocess basetemp short and outside the repository.
_SHORT_TMP_ROOT = Path(os.environ.get("TEMP") or "/tmp") / "sgx"

# Contract-satisfying attribute text, assembled from the SAME constants the
# producer uses, so a change to the contract cannot leave this fixture stale.
_GOOD_SOURCE = (
    "ERA5 hourly 2-m temperature (Hersbach et al., 2020). ERA5 coverage used: "
    f"{COVERAGE_INTERVAL} (warm seasons). Required Copernicus attribution: "
    "see the `license` attribute.")
_GOOD_LICENSE = (
    "CC BY 4.0 for the value added by the authors "
    "(https://creativecommons.org/licenses/by/4.0/), which "
    f"{AUTHORS_RIGHTS_CLAUSE}; the underlying ERA5 information is provided "
    f"under the licence to use Copernicus products, {CURRENT_LICENCE_URL}, "
    "and is not CC BY licensed by this deposit. ERA5 coverage used: "
    f"{COVERAGE_INTERVAL} (warm seasons). Required attribution: "
    f"{REQUIRED_NOTICE} {REQUIRED_DISCLAIMER}")


# ---------------------------------------------------------------------------
# Building a structurally valid synthetic archive.
# ---------------------------------------------------------------------------
def _good_netcdf_bytes(tmp: Path, **overrides) -> bytes:
    """A tiny NetCDF whose global attributes satisfy the contract."""
    path = tmp / "synthetic.nc"
    if path.exists():
        path.unlink()
    ds = netCDF4.Dataset(path, "w", format="NETCDF4")
    try:
        ds.createDimension("t", 2)
        v = ds.createVariable("tmax", "f4", ("t",))
        v[:] = [1.0, 2.0]
        attrs = {
            "Conventions": "CF-1.10",
            "title": "Synthetic fixture for the release-gate exit-code suite",
            "institution": "University of Florida",
            "source": _GOOD_SOURCE,
            "references": ("Bouhamad and Najibi, SCORCH Framework (manuscript "
                           f"{MANUSCRIPT_STATUS})."),
            "license": _GOOD_LICENSE,
        }
        attrs.update(overrides)
        for name, value in attrs.items():
            ds.setncattr(name, value)
    finally:
        ds.close()
    data = path.read_bytes()
    path.unlink()
    return data


def _payloads(tmp: Path, **nc_overrides):
    """107 payload members: the canonical NetCDF plus 106 tiny fillers."""
    out = {NC_MEMBER: _good_netcdf_bytes(tmp, **nc_overrides)}
    for i in range(PAYLOAD_COUNT - 1):
        out[f"catalogs/filler_{i:03d}.csv"] = (
            f"id,value\n{i},synthetic\n".encode("utf-8"))
    assert len(out) == PAYLOAD_COUNT
    return out


def _sums_text(payloads, manifest_text=None):
    """108 entries: every member except SHA256SUMS itself.

    That includes FILE_MANIFEST.csv, so the manifest must be rendered first and
    hashed in - which is exactly the self-documenting shape the real archive
    has (109 = 107 payloads + SHA256SUMS + FILE_MANIFEST.csv).
    """
    manifest = (_manifest_text(payloads) if manifest_text is None
                else manifest_text)
    entries = dict(payloads)
    entries[MANIFEST_MEMBER] = manifest.encode("utf-8")
    return "".join(
        f"{hashlib.sha256(b).hexdigest()}  {p}\n"
        for p, b in sorted(entries.items()))


def _manifest_text(payloads):
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(MANIFEST_COLUMNS)
    for p, b in sorted(payloads.items()):
        w.writerow([p, len(b), hashlib.sha256(b).hexdigest(), 1, "synthetic"])
    return buf.getvalue()


def _write_archive(dest: Path, payloads, sums_text=None, manifest_text=None,
                   extra_members=(), duplicate=None):
    """Write a deposit-shaped ZIP. ``duplicate`` adds a second raw entry."""
    # The manifest is rendered FIRST because SHA256SUMS must hash it; a custom
    # manifest therefore stays consistent with the sums unless the test is
    # deliberately mutating the sums as well.
    manifest = (_manifest_text(payloads) if manifest_text is None
                else manifest_text)
    sums = _sums_text(payloads, manifest) if sums_text is None else sums_text
    if dest.exists():
        dest.unlink()
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for p, b in sorted(payloads.items()):
            zf.writestr(p, b)
        zf.writestr(SUMS_MEMBER, sums)
        zf.writestr(MANIFEST_MEMBER, manifest)
        for name, blob in extra_members:
            zf.writestr(name, blob)
        if duplicate is not None:
            name, blob = duplicate
            zf.writestr(name, blob)          # second entry, same raw name
    return dest


@pytest.fixture(scope="module")
def workdir(tmp_path_factory):
    return tmp_path_factory.mktemp("gate")


@pytest.fixture(scope="module")
def valid_archive(workdir):
    return _write_archive(workdir / "valid.zip", _payloads(workdir))


# ---------------------------------------------------------------------------
# Driving the REAL gate node in a subprocess.
# ---------------------------------------------------------------------------
def _run_gate(node, archive, require=True, tmp_name="run"):
    env = {k: v for k, v in os.environ.items() if not k.startswith("SCORCH_")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    src = str(REPO / "src")
    env["PYTHONPATH"] = (src + os.pathsep + env["PYTHONPATH"]
                         if env.get("PYTHONPATH") else src)
    if archive is not None:
        env["SCORCH_DATA_ARCHIVE"] = str(archive)
    if require:
        env["SCORCH_REQUIRE_ARCHIVE"] = "1"

    base = _SHORT_TMP_ROOT / tmp_name
    base.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", node, "-p", "no:cacheprovider",
         "--basetemp", str(base), "-rA", "-q"],
        cwd=REPO, env=env, capture_output=True, text=True, timeout=900)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


_SUMMARY_RE = re.compile(
    r"(\d+) (passed|failed|skipped|error|errors|xfailed|xpassed)")


def _counts(out):
    """Outcome counts from pytest's summary line, defaulting to zero."""
    tail = [ln for ln in out.splitlines()
            if re.search(r"\b\d+ (passed|failed|error|errors|skipped)\b", ln)]
    counts = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0,
              "xfailed": 0, "xpassed": 0}
    if tail:
        for n, word in _SUMMARY_RE.findall(tail[-1]):
            counts["errors" if word == "error" else word] = int(n)
    return counts


def _assert_failed(code, out, expected_issue, label):
    c = _counts(out)
    assert code != 0, (
        f"{label}: gate exited 0 on a defective archive - this is exactly the "
        f"false-green the gate must prevent.\n{out[-3000:]}")
    assert c["failed"] >= 1, (
        f"{label}: nonzero exit but no ordinary FAILED result ({c}).\n"
        f"{out[-3000:]}")
    assert c["errors"] == 0, (
        f"{label}: produced {c['errors']} test ERROR(s); a release gate must "
        f"fail cleanly, not collapse in fixture setup.\n{out[-3000:]}")
    assert c["xfailed"] == 0 and c["xpassed"] == 0, (
        f"{label}: outcome was absorbed as an xfail ({c}).\n{out[-3000:]}")
    assert expected_issue in out, (
        f"{label}: expected issue code {expected_issue} not emitted.\n"
        f"{out[-3000:]}")


# ---------------------------------------------------------------------------
# 0. The flag parser itself.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("value,expected", [
    ("1", True), ("true", True), ("TRUE", True), ("yes", True), ("on", True),
    (" 1 ", True),
    ("0", False), ("false", False), ("no", False), ("off", False),
    ("", False), (None, False),
])
def test_flag_parsing_is_explicit(value, expected):
    """``bool(os.getenv("X"))`` would call "0" true; this must not."""
    assert is_truthy_flag(value) is expected


# ---------------------------------------------------------------------------
# 1. The synthetic archive is genuinely valid - otherwise every mutant below
#    would "fail for the right reason" by accident.
# ---------------------------------------------------------------------------
def test_synthetic_archive_is_structurally_valid(valid_archive):
    assert list(archive_structure_issues(valid_archive, MEMBER_COUNT)) == []


def test_valid_synthetic_archive_passes_the_structure_gate(valid_archive):
    code, out = _run_gate(STRUCTURE_NODE, valid_archive, tmp_name="okstruct")
    assert code == 0, f"valid synthetic archive failed the gate:\n{out[-3000:]}"
    assert "1 passed" in out, out[-2000:]


def test_valid_synthetic_archive_passes_the_netcdf_gate(valid_archive):
    code, out = _run_gate(NETCDF_NODE, valid_archive, tmp_name="oknc")
    assert code == 0, f"valid synthetic archive failed the gate:\n{out[-3000:]}"
    assert "1 passed" in out, out[-2000:]


# ---------------------------------------------------------------------------
# 2. Required-archive plumbing.
# ---------------------------------------------------------------------------
def test_required_but_no_archive_supplied_fails():
    code, out = _run_gate(NETCDF_NODE, None, require=True, tmp_name="noarch")
    _assert_failed(code, out, "ARCHIVE_REQUIRED_MISSING", "no archive supplied")


def test_required_but_archive_path_missing_fails(workdir):
    code, out = _run_gate(NETCDF_NODE, workdir / "absent.zip", require=True,
                          tmp_name="absent")
    _assert_failed(code, out, "ARCHIVE_REQUIRED_MISSING", "absent archive")


def test_supplied_but_invalid_archive_fails_even_when_not_required(workdir):
    """A supplied-but-broken archive must never be skipped away."""
    broken = workdir / "notazip.zip"
    broken.write_bytes(b"this is not a zip file")
    code, out = _run_gate(STRUCTURE_NODE, broken, require=False,
                          tmp_name="notreq")
    _assert_failed(code, out, "ARCHIVE_ZIP_CORRUPT",
                   "supplied invalid archive without the flag")


def test_no_archive_and_not_required_is_a_clean_skip():
    """The one legitimate skip: source-only checkout, nothing required."""
    code, out = _run_gate(GATE_NODE, None, require=False, tmp_name="skip")
    assert code == 0, out[-2000:]
    assert "1 skipped" in out, out[-2000:]


# ---------------------------------------------------------------------------
# 2b. Whole-module shape: ONE ordinary failure, never a pile of setup errors.
# ---------------------------------------------------------------------------
def test_required_missing_yields_one_failure_and_no_errors():
    """A module-scoped fixture that failed would error every dependent test."""
    code, out = _run_gate(GATE_MODULE, None, require=True, tmp_name="modmiss")
    c = _counts(out)
    _assert_failed(code, out, "ARCHIVE_REQUIRED_MISSING", "module/required")
    assert c["failed"] == 1, (
        f"expected exactly ONE explicit release-gate failure, got {c}.\n"
        f"{out[-3000:]}")
    assert c["errors"] == 0 and c["xfailed"] == 0 and c["xpassed"] == 0, c
    assert "Blocked because the explicit archive release gate reported" in out, (
        "dependent diagnostics must skip with the precise blocked reason")


def test_supplied_invalid_yields_one_failure_and_no_errors(workdir):
    """A corrupt supplied archive: one failure, diagnostics skip, no errors."""
    broken = workdir / "modbroken.zip"
    broken.write_bytes(b"not a zip at all")
    code, out = _run_gate(GATE_MODULE, broken, require=True,
                          tmp_name="modbad")
    c = _counts(out)
    _assert_failed(code, out, "ARCHIVE_ZIP_CORRUPT", "module/invalid")
    assert c["failed"] == 1, (
        f"expected exactly ONE explicit release-gate failure, got {c}.\n"
        f"{out[-3000:]}")
    assert c["errors"] == 0 and c["xfailed"] == 0 and c["xpassed"] == 0, c


# ---------------------------------------------------------------------------
# 3. Structural mutants - one broken invariant each.
# ---------------------------------------------------------------------------
def _mutant(workdir, name, **kw):
    payloads = kw.pop("payloads", None) or _payloads(workdir)
    return _write_archive(workdir / f"{name}.zip", payloads, **kw)


def test_corrupt_zip_fails(workdir):
    good = _mutant(workdir, "corrupt")
    blob = bytearray(good.read_bytes())
    blob[len(blob) // 2] ^= 0xFF          # flip a bit inside the payload area
    corrupt = workdir / "corrupt_hit.zip"
    corrupt.write_bytes(bytes(blob))
    code, out = _run_gate(STRUCTURE_NODE, corrupt, tmp_name="corrupt")
    _assert_failed(code, out, "ARCHIVE_ZIP_CORRUPT", "corrupt ZIP")


def test_duplicate_zip_member_fails(workdir):
    p = _payloads(workdir)
    arch = _mutant(workdir, "dupmember", payloads=p,
                   duplicate=("catalogs/filler_000.csv",
                              b"id,value\n999,dupe\n"))
    code, out = _run_gate(STRUCTURE_NODE, arch, tmp_name="dupmem")
    _assert_failed(code, out, "ARCHIVE_DUPLICATE_RAW_MEMBER",
                   "duplicate ZIP member")


def test_wrong_member_count_fails(workdir):
    p = _payloads(workdir)
    p.pop("catalogs/filler_005.csv")
    arch = _mutant(workdir, "shortcount", payloads=p)
    code, out = _run_gate(STRUCTURE_NODE, arch, tmp_name="shortcnt")
    _assert_failed(code, out, "ARCHIVE_MEMBER_COUNT", "member count 108")


def test_extra_member_count_fails(workdir):
    arch = _mutant(workdir, "longcount",
                   extra_members=[("catalogs/surplus.csv", b"id\n1\n")])
    code, out = _run_gate(STRUCTURE_NODE, arch, tmp_name="longcnt")
    _assert_failed(code, out, "ARCHIVE_MEMBER_COUNT", "member count 110")


def test_unsafe_member_path_fails(workdir):
    arch = _mutant(workdir, "unsafe",
                   extra_members=[("../escape.csv", b"id\n1\n")])
    code, out = _run_gate(STRUCTURE_NODE, arch, tmp_name="unsafe")
    _assert_failed(code, out, "ARCHIVE_UNSAFE_MEMBER_PATH", "escaping path")


def test_zero_canonical_netcdf_members_fails(workdir):
    p = _payloads(workdir)
    p["gridded/not_the_canonical_name.nc"] = p.pop(NC_MEMBER)
    arch = _mutant(workdir, "nonc", payloads=p)
    code, out = _run_gate(STRUCTURE_NODE, arch, tmp_name="nonc")
    _assert_failed(code, out, "ARCHIVE_NETCDF_MEMBER_COUNT", "zero NetCDF")


def test_multiple_canonical_netcdf_members_fails(workdir):
    p = _payloads(workdir)
    p.pop("catalogs/filler_001.csv")
    p["gridded/scorch_processed_daily_tmax_field_v9.9.9.nc"] = p[NC_MEMBER]
    arch = _mutant(workdir, "twonc", payloads=p)
    code, out = _run_gate(STRUCTURE_NODE, arch, tmp_name="twonc")
    _assert_failed(code, out, "ARCHIVE_NETCDF_MEMBER_COUNT", "two NetCDFs")


# ---- SHA256SUMS ----------------------------------------------------------
def test_malformed_sums_line_fails(workdir):
    p = _payloads(workdir)
    lines = _sums_text(p).splitlines(keepends=True)
    lines[3] = "not-a-digest catalogs/filler_002.csv\n"
    arch = _mutant(workdir, "sumsformat", payloads=p, sums_text="".join(lines))
    code, out = _run_gate(STRUCTURE_NODE, arch, tmp_name="sumsfmt")
    _assert_failed(code, out, "SUMS_LINE_FORMAT", "malformed sums line")


def test_duplicate_sums_entry_fails(workdir):
    p = _payloads(workdir)
    lines = _sums_text(p).splitlines(keepends=True)
    lines[4] = lines[3]                   # same path twice, count preserved
    arch = _mutant(workdir, "sumsdupe", payloads=p, sums_text="".join(lines))
    code, out = _run_gate(STRUCTURE_NODE, arch, tmp_name="sumsdup")
    _assert_failed(code, out, "SUMS_DUPLICATE_PATH", "duplicate sums path")


def test_wrong_sums_count_fails(workdir):
    p = _payloads(workdir)
    lines = _sums_text(p).splitlines(keepends=True)[:-1]
    arch = _mutant(workdir, "sumscount", payloads=p, sums_text="".join(lines))
    code, out = _run_gate(STRUCTURE_NODE, arch, tmp_name="sumscnt")
    _assert_failed(code, out, "SUMS_ENTRY_COUNT", "107 sums entries")


def test_sums_missing_coverage_fails(workdir):
    p = _payloads(workdir)
    lines = [ln for ln in _sums_text(p).splitlines(keepends=True)
             if "filler_007.csv" not in ln]
    lines.append(f"{'0' * 64}  catalogs/ghost.csv\n")   # keep the count at 108
    arch = _mutant(workdir, "sumsmiss", payloads=p, sums_text="".join(lines))
    code, out = _run_gate(STRUCTURE_NODE, arch, tmp_name="sumsmiss")
    _assert_failed(code, out, "SUMS_COVERAGE", "sums missing a real member")


def test_sums_digest_mismatch_fails(workdir):
    p = _payloads(workdir)
    lines = _sums_text(p).splitlines(keepends=True)
    lines[2] = "f" * 64 + lines[2][64:]
    arch = _mutant(workdir, "sumsdigest", payloads=p, sums_text="".join(lines))
    code, out = _run_gate(STRUCTURE_NODE, arch, tmp_name="sumsdig")
    _assert_failed(code, out, "SUMS_DIGEST_MISMATCH", "wrong digest")


# ---- FILE_MANIFEST.csv ---------------------------------------------------
def test_manifest_schema_violation_fails(workdir):
    p = _payloads(workdir)
    text = _manifest_text(p).splitlines(keepends=True)
    text[0] = "path,bytes,sha256,n_rows,description\n"
    arch = _mutant(workdir, "manschema", payloads=p,
                   manifest_text="".join(text))
    code, out = _run_gate(STRUCTURE_NODE, arch, tmp_name="manschema")
    _assert_failed(code, out, "MANIFEST_SCHEMA", "renamed column")


def test_duplicate_manifest_row_fails(workdir):
    p = _payloads(workdir)
    rows = _manifest_text(p).splitlines(keepends=True)
    rows[5] = rows[4]                     # same path twice, count preserved
    arch = _mutant(workdir, "mandupe", payloads=p, manifest_text="".join(rows))
    code, out = _run_gate(STRUCTURE_NODE, arch, tmp_name="mandup")
    _assert_failed(code, out, "MANIFEST_DUPLICATE_PATH", "duplicate row")


def test_wrong_manifest_row_count_fails(workdir):
    p = _payloads(workdir)
    rows = _manifest_text(p).splitlines(keepends=True)[:-1]
    arch = _mutant(workdir, "mancount", payloads=p, manifest_text="".join(rows))
    code, out = _run_gate(STRUCTURE_NODE, arch, tmp_name="mancnt")
    _assert_failed(code, out, "MANIFEST_ROW_COUNT", "106 manifest rows")


def test_manifest_missing_coverage_fails(workdir):
    p = _payloads(workdir)
    rows = [r for r in _manifest_text(p).splitlines(keepends=True)
            if "filler_009.csv" not in r]
    rows.append(f"catalogs/ghost.csv,1,{'0' * 64},1,synthetic\n")
    arch = _mutant(workdir, "manmiss", payloads=p, manifest_text="".join(rows))
    code, out = _run_gate(STRUCTURE_NODE, arch, tmp_name="manmiss")
    _assert_failed(code, out, "MANIFEST_COVERAGE", "manifest missing a payload")


def test_manifest_covers_a_catalog_file_fails(workdir):
    p = _payloads(workdir)
    rows = _manifest_text(p).splitlines(keepends=True)
    rows[1] = f"{SUMS_MEMBER},1,{'0' * 64},1,synthetic\n"
    arch = _mutant(workdir, "mancat", payloads=p, manifest_text="".join(rows))
    code, out = _run_gate(STRUCTURE_NODE, arch, tmp_name="mancat")
    _assert_failed(code, out, "MANIFEST_COVERAGE", "manifest covers SHA256SUMS")


def test_manifest_byte_count_mismatch_fails(workdir):
    p = _payloads(workdir)
    rows = _manifest_text(p).splitlines(keepends=True)
    parts = rows[2].split(",")
    parts[1] = str(int(parts[1]) + 1)
    rows[2] = ",".join(parts)
    arch = _mutant(workdir, "manbytes", payloads=p, manifest_text="".join(rows))
    code, out = _run_gate(STRUCTURE_NODE, arch, tmp_name="manbytes")
    _assert_failed(code, out, "MANIFEST_BYTES_MISMATCH", "byte count off by 1")


def test_manifest_digest_mismatch_fails(workdir):
    p = _payloads(workdir)
    rows = _manifest_text(p).splitlines(keepends=True)
    parts = rows[2].split(",")
    parts[2] = "a" * 64
    rows[2] = ",".join(parts)
    arch = _mutant(workdir, "manhash", payloads=p, manifest_text="".join(rows))
    code, out = _run_gate(STRUCTURE_NODE, arch, tmp_name="manhash")
    _assert_failed(code, out, "MANIFEST_DIGEST_MISMATCH", "wrong manifest hash")


# ---------------------------------------------------------------------------
# 4. One independent mutation per NetCDF predicate - all nine.
# ---------------------------------------------------------------------------
NETCDF_MUTANTS = [
    # (label, attribute overrides, expected issue code)
    ("source_carries_notice",
     {"source": _GOOD_SOURCE + " " + REQUIRED_NOTICE},
     "NETCDF_SOURCE_CONTRACT"),
    ("coverage_unlabelled",
     {"source": f"ERA5 hourly 2-m temperature, {COVERAGE_INTERVAL}."},
     "NETCDF_COVERAGE_LABEL"),
    ("notice_not_exact",
     {"license": _GOOD_LICENSE.replace(REQUIRED_NOTICE,
                                       "Contains Copernicus data 2026.")},
     "NETCDF_NOTICE_EXACT"),
    ("notice_twice",
     {"comment": f"Coverage {COVERAGE_INTERVAL}. {REQUIRED_NOTICE}"},
     "NETCDF_NOTICE_COUNT"),
    ("retired_cds_url",
     {"license": _GOOD_LICENSE + f" See https://{RETIRED_LICENCE_HOST}/x."},
     "NETCDF_RETIRED_CDS_URL"),
    ("missing_ecds_url",
     {"license": _GOOD_LICENSE.replace(CURRENT_LICENCE_URL,
                                       "https://example.invalid/licence")},
     "NETCDF_CURRENT_ECDS_URL"),
    ("rights_not_scoped",
     {"license": _GOOD_LICENSE.replace(AUTHORS_RIGHTS_CLAUSE,
                                       "covers everything in this deposit")},
     "NETCDF_AUTHORS_RIGHTS_SCOPE"),
    ("coverage_as_year_token",
     {"license": _GOOD_LICENSE.replace(
         REQUIRED_NOTICE,
         "Contains modified Copernicus Climate Change Service information "
         f"({COVERAGE_INTERVAL}).")},
     "NETCDF_NOTICE_COVERAGE_YEAR"),
    ("references_in_review",
     {"references": "Bouhamad and Najibi, SCORCH Framework (in review)."},
     "NETCDF_REFERENCES_STATUS"),
]


@pytest.mark.parametrize("label,overrides,issue", NETCDF_MUTANTS,
                         ids=[m[0] for m in NETCDF_MUTANTS])
def test_each_netcdf_predicate_is_independently_enforced(
        workdir, label, overrides, issue):
    """Break exactly one predicate; the real gate node must go red on it."""
    payloads = _payloads(workdir, **overrides)
    arch = _write_archive(workdir / f"nc_{label}.zip", payloads)
    # The structural contract must still hold, so the failure below can only be
    # attributed to the metadata predicate under test.
    assert list(archive_structure_issues(arch, MEMBER_COUNT)) == [], (
        f"{label}: the mutant broke the STRUCTURE too, so a metadata failure "
        f"would not be attributable")
    code, out = _run_gate(NETCDF_NODE, arch, tmp_name=f"nc{label[:8]}")
    _assert_failed(code, out, issue, label)
