"""Archive-BACKED verification: open the actual ZIP, do not trust declarations.

The relocation guards in ``test_public_consistency_guards.py`` check that the
sidecar and the manifest agree *with each other*. That is necessary and not
sufficient: two records can agree perfectly about an archive neither has opened.
These tests open the real ZIP and verify the declarations against its bytes.

Activated by ``SCORCH_DATA_ARCHIVE`` pointing at the archive candidate. When it
is unset the tests SKIP with an explicit reason, which is correct for a
source-only checkout. Setting ``SCORCH_REQUIRE_ARCHIVE=1`` turns that skip into
a FAILURE: the final release gate must supply the archive and may not pass this
file by skipping it.

What is verified:

* the complete ZIP SHA-256 and byte count;
* the exact member set and member count - derived from the archive's own
  coverage records rather than a hardcoded path list, so it stays exact;
* the content-root hash, per the definition recorded in the manifest;
* SHA256SUMS and FILE_MANIFEST coverage, including every recorded member hash
  and byte count;
* all 21 relocated members: presence, SHA-256 and byte count;
* the declared CRLF/LF relationship for every relocated text member, proven by
  transforming the member bytes and reproducing the other byte identity;
* a fresh extraction, followed by the archive's own ``validate_deposit.py``.

Nothing here writes to the archive.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PACKAGE_ID = "PKG-DATA-V1"
TOTAL_RELOCATIONS = 21
SUMS_MEMBER = "SHA256SUMS"
MANIFEST_MEMBER = "FILE_MANIFEST.csv"


def _read(rel):
    return (REPO / rel).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def package():
    manifest = json.loads(
        _read("remediation/corrected_outputs/SHA256_MANIFEST.json"))
    return manifest["relocation"]["packages"][PACKAGE_ID]


@pytest.fixture(scope="module")
def sidecar():
    with open(REPO / "docs/RELOCATED_ARTIFACTS.csv", encoding="utf-8",
              newline="") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def archive_path(package):
    """The archive, or an explicit skip / failure when it is not supplied."""
    raw = os.environ.get("SCORCH_DATA_ARCHIVE")
    required = os.environ.get("SCORCH_REQUIRE_ARCHIVE") == "1"
    if not raw:
        msg = ("SCORCH_DATA_ARCHIVE is not set, so the archive-backed gate did "
               "not run. Point it at the v1.0.0 data-archive candidate "
               f"({package['archive_filename']}).")
        if required:
            pytest.fail("SCORCH_REQUIRE_ARCHIVE=1 but " + msg)
        pytest.skip(msg)
    path = Path(raw).expanduser()
    if not path.is_file():
        msg = f"SCORCH_DATA_ARCHIVE points at a missing file: {path}"
        if required:
            pytest.fail(msg)
        pytest.skip(msg)
    return path


@pytest.fixture(scope="module")
def zf(archive_path):
    with zipfile.ZipFile(archive_path) as handle:
        yield handle


@pytest.fixture(scope="module")
def members(zf):
    return sorted(n for n in zf.namelist() if not n.endswith("/"))


@pytest.fixture(scope="module")
def member_hashes(zf, members):
    return {m: hashlib.sha256(zf.read(m)).hexdigest() for m in members}


def _sums_map(zf):
    out = {}
    for line in zf.read(SUMS_MEMBER).decode("utf-8").splitlines():
        if not line.strip():
            continue
        digest, _, path = line.partition("  ")
        out[path.strip().lstrip("*")] = digest.strip()
    return out


def _manifest_rows(zf):
    return list(csv.DictReader(
        io.StringIO(zf.read(MANIFEST_MEMBER).decode("utf-8"))))


# ---------------------------------------------------------------------------
# 1. The container itself.
# ---------------------------------------------------------------------------
def test_archive_sha256_and_byte_count(archive_path, package):
    size = archive_path.stat().st_size
    assert size == package["archive_bytes"], (
        f"archive is {size} bytes, manifest declares "
        f"{package['archive_bytes']}")
    h = hashlib.sha256()
    with open(archive_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    assert h.hexdigest() == package["archive_sha256"], (
        f"archive SHA-256 {h.hexdigest()} != declared "
        f"{package['archive_sha256']}")
    assert archive_path.name == package["archive_filename"]


def test_member_count_is_exact(members, package):
    assert len(members) == package["member_count"], (
        f"archive holds {len(members)} members, manifest declares "
        f"{package['member_count']}")
    assert len(set(members)) == len(members), "duplicate member names"


def test_member_set_is_exactly_what_the_archive_declares(zf, members):
    """Exact member set, derived from the archive's own coverage records.

    The archive documents itself twice: SHA256SUMS covers every member except
    itself, and FILE_MANIFEST.csv covers every member except itself and
    SHA256SUMS. Pinning those two relationships makes the member set exact
    without hardcoding 109 paths that would rot on the next rebuild.
    """
    sums_paths = set(_sums_map(zf))
    man_paths = {r["file"] for r in _manifest_rows(zf)}
    assert set(members) - sums_paths == {SUMS_MEMBER}, (
        f"SHA256SUMS must cover every member except itself; unexplained: "
        f"{sorted(set(members) - sums_paths - {SUMS_MEMBER})}")
    assert not sums_paths - set(members), (
        f"SHA256SUMS lists absent members: {sorted(sums_paths - set(members))}")
    assert sums_paths - man_paths == {MANIFEST_MEMBER}, (
        f"FILE_MANIFEST must cover everything SHA256SUMS does except itself; "
        f"unexplained: {sorted(sums_paths - man_paths - {MANIFEST_MEMBER})}")
    assert not man_paths - sums_paths, (
        f"FILE_MANIFEST lists paths absent from SHA256SUMS: "
        f"{sorted(man_paths - sums_paths)}")


# ---------------------------------------------------------------------------
# 2. The content-root hash, per the recorded definition.
# ---------------------------------------------------------------------------
def test_content_root_hash(members, member_hashes, package):
    definition = package["content_root_hash_definition"]
    assert "sorted by member_path" in definition
    blob = "".join(f"{member_hashes[m]}  {m}\n" for m in sorted(members))
    root = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    assert root == package["content_root_hash"], (
        f"content-root hash {root} != declared {package['content_root_hash']}")


# ---------------------------------------------------------------------------
# 3. The archive's own coverage records agree with its bytes.
# ---------------------------------------------------------------------------
def test_sha256sums_matches_every_member(zf, member_hashes):
    sums = _sums_map(zf)
    assert sums, "SHA256SUMS is empty"
    bad = [p for p, d in sums.items() if member_hashes.get(p) != d]
    assert not bad, f"SHA256SUMS disagrees with member bytes: {bad[:5]}"


def test_file_manifest_matches_every_member(zf, member_hashes):
    rows = _manifest_rows(zf)
    assert rows, "FILE_MANIFEST.csv is empty"
    checked = 0
    for r in rows:
        path = r["file"]
        assert path in member_hashes, f"FILE_MANIFEST lists absent {path}"
        assert member_hashes[path] == r["sha256"], f"{path}: hash mismatch"
        assert zf.getinfo(path).file_size == int(r["bytes"]), (
            f"{path}: byte count mismatch")
        checked += 1
    assert checked == len(rows) and checked > 0


# ---------------------------------------------------------------------------
# 4. All 21 relocated members really are in the archive, byte for byte.
# ---------------------------------------------------------------------------
def test_every_relocated_member_is_present_and_correct(sidecar, member_hashes,
                                                       zf, package):
    assert len(sidecar) == TOTAL_RELOCATIONS
    checked = 0
    for row in sidecar:
        member = row["archive_member_path"]
        assert row["archive_filename"] == package["archive_filename"]
        assert row["archive_sha256"] == package["archive_sha256"]
        assert member in member_hashes, (
            f"{row['old_repository_path']} is declared relocated to {member}, "
            f"which is NOT in the archive")
        assert member_hashes[member] == row["member_sha256"], (
            f"{member}: archive hash {member_hashes[member]} != declared "
            f"{row['member_sha256']}")
        assert zf.getinfo(member).file_size == int(row["member_bytes"]), (
            f"{member}: archive byte count {zf.getinfo(member).file_size} != "
            f"declared {row['member_bytes']}")
        checked += 1
    assert checked == TOTAL_RELOCATIONS, (
        f"verified {checked} relocated members, expected {TOTAL_RELOCATIONS}")


# ---------------------------------------------------------------------------
# 5. The declared CRLF/LF relationship, PROVEN on the member bytes.
# ---------------------------------------------------------------------------
def test_declared_eol_relationship_holds_on_member_bytes(sidecar, zf):
    """Reproduce the other byte identity by transforming the member bytes."""
    binary_checked = text_checked = 0
    for row in sidecar:
        member = row["archive_member_path"]
        data = zf.read(member)
        repo_sha = row["repository_sha256"]
        hist_sha = row["historical_byte_identity_sha256"]
        actual = hashlib.sha256(data).hexdigest()

        if repo_sha == hist_sha:
            # declared binary: both byte identities are the same bytes
            assert "binary" in row["eol_relationship"].lower(), (
                f"{member}: identical identities but the EOL relationship does "
                f"not say binary: {row['eol_relationship']}")
            assert actual == repo_sha, f"{member}: member bytes differ"
            binary_checked += 1
            continue

        # Declared text, with an EOL transform between the two identities. The
        # archive may carry EITHER form; the row declares which, and both
        # directions are proven by transforming the member bytes we just read.
        form = row["archive_member_byte_form"]
        if form == "repository_normalized_bytes":
            assert actual == repo_sha, (
                f"{member}: declared repository-normalized but its bytes hash "
                f"to {actual}, not {repo_sha}")
            assert b"\r\n" not in data, (
                f"{member}: declared LF-normalized but contains CRLF")
            transformed = data.replace(b"\n", b"\r\n")
            want, direction = hist_sha, "LF->CRLF"
        elif form == "historical_windows_worktree_bytes":
            assert actual == hist_sha, (
                f"{member}: declared historical Windows-worktree bytes but its "
                f"bytes hash to {actual}, not {hist_sha}")
            assert b"\r\n" in data, (
                f"{member}: declared CRLF form but contains no CRLF")
            # normalize CRLF -> LF without touching any lone LF already present
            transformed = data.replace(b"\r\n", b"\n")
            want, direction = repo_sha, "CRLF->LF"
        else:
            raise AssertionError(
                f"{member}: unexpected declared byte form {form!r}")

        assert hashlib.sha256(transformed).hexdigest() == want, (
            f"{member}: the {direction} transform does not reproduce the other "
            f"declared byte identity, so the declared EOL relationship "
            f"({row['eol_relationship']}) is NOT proven")
        text_checked += 1

    assert binary_checked + text_checked == TOTAL_RELOCATIONS
    assert text_checked, "no text member was EOL-verified - guard was vacuous"
    assert binary_checked, "no binary member was verified - guard was vacuous"


# ---------------------------------------------------------------------------
# 6. Fresh extraction, then the archive's own validator.
# ---------------------------------------------------------------------------
def test_fresh_extraction_passes_validate_deposit(archive_path, tmp_path,
                                                  package):
    dest = tmp_path / "extracted"
    dest.mkdir()
    with zipfile.ZipFile(archive_path) as handle:
        handle.extractall(dest)

    validator = dest / "validate_deposit.py"
    assert validator.is_file(), (
        "the archive does not ship validate_deposit.py, so it cannot "
        "self-validate")
    proc = subprocess.run([sys.executable, str(validator)], cwd=dest,
                          capture_output=True, text=True)
    out = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, (
        f"validate_deposit.py failed on a fresh extraction (exit "
        f"{proc.returncode}):\n{out[-3000:]}")
    fails = [ln for ln in out.splitlines() if "FAIL" in ln.upper()]
    assert not fails, f"validator reported FAIL lines: {fails[:5]}"
    assert package["publication_state"].lower().startswith("built locally"), (
        "the package record must keep recording that this archive is local")
