"""The single authoritative metadata and structure contract for the deposit.

Every legal string the deposit must carry is defined here EXACTLY ONCE. The
producer (``build_processed_field_netcdf.py``) writes them and the release-gate
tests validate against them, both importing these same constants, so a notice
can never drift between what is written and what is checked.

Two things must never be confused, and an earlier revision confused them:

* the **notice year token**, ``2026`` - the year of use, frozen below and
  NEVER derived from the clock, because a clock-derived token would silently
  change the required legal wording every New Year;
* the **coverage interval** of the ERA5 data actually used, ``1940-2025``,
  which is legitimate wherever it is explicitly labelled as coverage and is
  never a substitute for the notice year token.

Design constraints, deliberately enforced:

* nothing here touches the filesystem or mutates anything;
* nothing here reads ``os.environ`` - callers pass values in explicitly;
* nothing here imports pytest or calls ``skip``/``xfail``/``fail``;
* validators aggregate EVERY defect into stable, sorted issue codes instead of
  stopping at the first one, so one run reports the full picture.
"""
from __future__ import annotations

import csv
import hashlib
import io
import posixpath
import re
import zipfile
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. The legal contract. Defined once; imported by producer and tests alike.
# ---------------------------------------------------------------------------
#: Temporal coverage of the ERA5 data actually used.
COVERAGE_INTERVAL = "1940-2025"

#: The notice year token: the year of USE. FROZEN - never ``date.today().year``.
NOTICE_YEAR = "2026"

#: Stem of the official modified-Copernicus notice, without the year token.
NOTICE_STEM = "Contains modified Copernicus Climate Change Service information"

#: The official notice, verbatim, with the frozen year token and full stop.
REQUIRED_NOTICE = f"{NOTICE_STEM} {NOTICE_YEAR}."

#: The official disclaimer that must accompany the notice.
REQUIRED_DISCLAIMER = (
    "Neither the European Commission nor ECMWF is responsible for any use "
    "that may be made of the Copernicus information or data it contains.")

#: The CURRENT licence URL for Copernicus products.
CURRENT_LICENCE_URL = (
    "https://ecds.ecmwf.int/licences/licence-to-use-copernicus-products")

#: The RETIRED host. Its presence anywhere in the metadata is a defect.
RETIRED_LICENCE_HOST = "cds.climate.copernicus.eu"

#: The clause limiting CC BY to the authors' own contribution.
AUTHORS_RIGHTS_CLAUSE = "covers only the authors' contribution"

#: Truthful pre-submission manuscript status, and the wording it replaces.
MANUSCRIPT_STATUS = "in preparation"
SUPERSEDED_MANUSCRIPT_STATUS = "in review"

#: The one canonical processed-field NetCDF member inside the deposit archive.
CANONICAL_NETCDF_RE = re.compile(
    r"^gridded/scorch_processed_daily_tmax_field_v\d+\.\d+\.\d+\.nc$")

#: The archive documents itself twice, so the member arithmetic is fixed:
#: every member is covered by SHA256SUMS except itself, and by
#: FILE_MANIFEST.csv except itself and SHA256SUMS.
SUMS_MEMBER = "SHA256SUMS"
MANIFEST_MEMBER = "FILE_MANIFEST.csv"
MANIFEST_COLUMNS = ("file", "bytes", "sha256", "n_rows", "description")

#: ``<64 hex>  <path>`` - GNU coreutils text mode, two spaces.
_SUMS_LINE_RE = re.compile(r"^(?P<digest>[0-9a-f]{64})  (?P<path>\S.*)$")

#: "Service information" followed by any punctuation/space run and a coverage
#: span - i.e. a coverage interval standing where the year token belongs.
#: Catches "information 1940-2025", "information (1940-2025)", "[1940-2025]",
#: "information, 1940-2025", en/em-dash variants, and so on.
_COVERAGE_AS_YEAR_TOKEN_RE = re.compile(
    r"Service information[\s\(\[\{,;:]*\d{4}\s*[-‐-―]\s*\d{4}")

#: Words that explicitly present a span as TEMPORAL/DATA COVERAGE. The span is
#: legitimate wherever one of these appears in the same attribute; it is a
#: defect only when it stands bare, or where a notice year token belongs.
#: Deliberately excludes "record" - the real ``source`` says "dataset of
#: record", which would otherwise wave the check through for free.
_COVERAGE_LABELS = ("coverage", "covering", "period", "season", "span")


class DepositContractError(Exception):
    """Raised with the COMPLETE sorted set of issue codes, never just one."""

    def __init__(self, issues, detail=None):
        self.issues = sorted(set(issues))
        self.detail = dict(detail or {})
        lines = [f"deposit contract violated ({len(self.issues)} issue(s)):"]
        for code in self.issues:
            why = self.detail.get(code)
            lines.append(f"  - {code}" + (f": {why}" if why else ""))
        super().__init__("\n".join(lines))


def is_truthy_flag(value) -> bool:
    """Explicit flag parsing.

    ``bool(os.getenv("X"))`` is wrong here: the string ``"0"`` is truthy in
    Python, so ``SCORCH_REQUIRE_ARCHIVE=0`` would silently ENABLE the hard
    gate. Callers read the environment; this stays pure.
    """
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# 2. NetCDF global-attribute predicates - nine, each with its own issue code.
# ---------------------------------------------------------------------------
def netcdf_metadata_issues(attrs):
    """Return the sorted issue codes for a mapping of NetCDF global attrs.

    Pure: no I/O, no environment, no exceptions for ordinary defects. An empty
    list means the metadata satisfies the contract.
    """
    issues, detail = [], {}

    def bad(code, why):
        issues.append(code)
        detail.setdefault(code, why)

    text = {k: v for k, v in attrs.items() if isinstance(v, str)}
    source = text.get("source", "")
    licence = text.get("license", "")
    references = text.get("references", "")
    everything = "\n".join(text.values())

    # (1) `source` states provenance and coverage and carries NO legal notice.
    if "Copernicus Climate Change Service information" in source:
        bad("NETCDF_SOURCE_CONTRACT",
            "ds.source carries a Copernicus legal notice; the notice has "
            "exactly one home, ds.license")
    elif "ERA5" not in source or COVERAGE_INTERVAL not in source:
        bad("NETCDF_SOURCE_CONTRACT",
            "ds.source must state ERA5 provenance and the "
            f"{COVERAGE_INTERVAL} coverage interval")

    # (2) Wherever the coverage span appears it is LABELLED as coverage.
    unlabelled = sorted(
        name for name, value in text.items()
        if COVERAGE_INTERVAL in value
        and not any(lab in value.lower() for lab in _COVERAGE_LABELS))
    if unlabelled:
        bad("NETCDF_COVERAGE_LABEL",
            f"{COVERAGE_INTERVAL} appears without any explicit temporal-"
            f"coverage label {_COVERAGE_LABELS} in: {unlabelled}")

    # (3) `license` carries the exact official notice AND the disclaimer.
    if REQUIRED_NOTICE not in licence:
        bad("NETCDF_NOTICE_EXACT",
            "ds.license lacks the exact notice " + repr(REQUIRED_NOTICE))
    elif REQUIRED_DISCLAIMER not in licence:
        bad("NETCDF_NOTICE_EXACT", "ds.license lacks the official disclaimer")

    # (4) The exact notice appears EXACTLY ONCE across all global attributes.
    occurrences = everything.count(REQUIRED_NOTICE)
    if occurrences != 1:
        bad("NETCDF_NOTICE_COUNT",
            f"the exact notice occurs {occurrences} time(s) across the global "
            "attributes; it must occur exactly once")

    # (5) The retired CDS host appears nowhere.
    if RETIRED_LICENCE_HOST in everything:
        carriers = sorted(n for n, v in text.items()
                          if RETIRED_LICENCE_HOST in v)
        bad("NETCDF_RETIRED_CDS_URL",
            f"retired host {RETIRED_LICENCE_HOST} present in: {carriers}")

    # (6) The current ECDS licence URL is cited in `license`.
    if CURRENT_LICENCE_URL not in licence:
        bad("NETCDF_CURRENT_ECDS_URL",
            f"ds.license does not cite {CURRENT_LICENCE_URL}")

    # (7) CC BY is scoped to the authors' contribution only.
    if AUTHORS_RIGHTS_CLAUSE not in licence:
        bad("NETCDF_AUTHORS_RIGHTS_SCOPE",
            "ds.license does not limit CC BY to the authors' contribution")

    # (8) A coverage span never stands where the year token belongs.
    offenders = sorted(n for n, v in text.items()
                       if _COVERAGE_AS_YEAR_TOKEN_RE.search(v))
    if offenders:
        bad("NETCDF_NOTICE_COVERAGE_YEAR",
            f"a coverage span stands in the notice year position in: "
            f"{offenders}")

    # (9) The manuscript is described truthfully as pre-submission.
    if SUPERSEDED_MANUSCRIPT_STATUS in references.lower():
        bad("NETCDF_REFERENCES_STATUS",
            f"ds.references still says {SUPERSEDED_MANUSCRIPT_STATUS!r}")
    elif MANUSCRIPT_STATUS not in references.lower():
        bad("NETCDF_REFERENCES_STATUS",
            f"ds.references does not state {MANUSCRIPT_STATUS!r}")

    return _finish(issues, detail)


def check_netcdf_metadata(attrs) -> None:
    """Raise :class:`DepositContractError` carrying EVERY issue, or return."""
    issues, detail = _split(netcdf_metadata_issues(attrs))
    if issues:
        raise DepositContractError(issues, detail)


# ---------------------------------------------------------------------------
# 3. Archive structure - read-only, never extracts, never mutates.
# ---------------------------------------------------------------------------
def archive_structure_issues(archive_path, expected_member_count):
    """Validate the deposit ZIP's structure and self-coverage records.

    Opens the ZIP read-only and reads members into memory; it never extracts to
    disk and never writes to the archive. ``expected_member_count`` comes from
    the repository's own package record, so the count is exact without being
    duplicated here.
    """
    issues, detail = [], {}

    def bad(code, why):
        issues.append(code)
        detail.setdefault(code, why)

    path = Path(archive_path)
    if not path.is_file():
        return _finish(["ARCHIVE_REQUIRED_MISSING"],
                       {"ARCHIVE_REQUIRED_MISSING": f"no such archive: {path}"})

    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        return _finish(["ARCHIVE_ZIP_CORRUPT"],
                       {"ARCHIVE_ZIP_CORRUPT": f"cannot open: {exc}"})

    with zf:
        infos = zf.infolist()
        raw_names = [i.filename for i in infos if not i.is_dir()]

        # Duplicate RAW names, detected BEFORE any set/dict construction -
        # a set would silently absorb exactly the defect we are hunting.
        seen, dupes = set(), set()
        for name in raw_names:
            (dupes if name in seen else seen).add(name)
        if dupes:
            bad("ARCHIVE_DUPLICATE_RAW_MEMBER",
                f"duplicate raw member names: {sorted(dupes)[:5]}")

        # Unsafe paths: absolute, drive-qualified, backslashed, or escaping.
        unsafe = sorted(
            n for n in raw_names
            if n.startswith(("/", "\\")) or ":" in n.split("/")[0]
            or posixpath.normpath(n).startswith("../")
            or "\\" in n)
        if unsafe:
            bad("ARCHIVE_UNSAFE_MEMBER_PATH", f"unsafe members: {unsafe[:5]}")

        # Normalized-path collisions are a DIFFERENT defect from raw duplicates:
        # "a/b.csv" and "a/./b.csv" are distinct raw names for one target.
        norm_seen, norm_collisions = {}, set()
        for name in raw_names:
            key = posixpath.normpath(name).lower()
            if key in norm_seen and norm_seen[key] != name:
                norm_collisions.add(key)
            norm_seen.setdefault(key, name)
        if norm_collisions:
            bad("ARCHIVE_NORMALIZED_PATH_COLLISION",
                f"paths colliding once normalized: "
                f"{sorted(norm_collisions)[:5]}")

        members = sorted(set(raw_names))
        if len(members) != expected_member_count:
            bad("ARCHIVE_MEMBER_COUNT",
                f"{len(members)} unique file members, expected "
                f"{expected_member_count}")

        try:
            first_bad = zf.testzip()
        except (zipfile.BadZipFile, OSError) as exc:
            first_bad = str(exc)
        if first_bad:
            bad("ARCHIVE_ZIP_CORRUPT", f"CRC failure at {first_bad}")

        nc_members = [m for m in members if CANONICAL_NETCDF_RE.match(m)]
        if len(nc_members) != 1:
            bad("ARCHIVE_NETCDF_MEMBER_COUNT",
                f"expected exactly 1 canonical processed NetCDF member, found "
                f"{len(nc_members)}: {nc_members[:5]}")

        member_set = set(members)
        blobs, sizes = {}, {}
        # The two self-describing catalogs are small and are needed verbatim
        # below; keeping their bytes from this single guarded pass means a
        # CRC failure in either is reported as corruption rather than escaping
        # as an unhandled BadZipFile from a second, unguarded read.
        catalog_bytes = {}
        for m in members:
            try:
                data = zf.read(m)
            except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
                bad("ARCHIVE_ZIP_CORRUPT", f"cannot read {m}: {exc}")
                continue
            blobs[m] = hashlib.sha256(data).hexdigest()
            sizes[m] = len(data)
            if m in (SUMS_MEMBER, MANIFEST_MEMBER):
                catalog_bytes[m] = data

        # ---- SHA256SUMS -------------------------------------------------
        sums = {}
        if SUMS_MEMBER not in member_set:
            bad("SUMS_COVERAGE", f"{SUMS_MEMBER} is absent")
        elif SUMS_MEMBER not in catalog_bytes:
            pass                      # unreadable; ARCHIVE_ZIP_CORRUPT logged
        else:
            lines = [ln for ln in catalog_bytes[SUMS_MEMBER]
                     .decode("utf-8", "replace").splitlines() if ln.strip()]
            malformed = [ln for ln in lines if not _SUMS_LINE_RE.match(ln)]
            if malformed:
                bad("SUMS_LINE_FORMAT",
                    f"{len(malformed)} malformed line(s), first: "
                    f"{malformed[0][:80]!r}")
            expected_sums = expected_member_count - 1
            if len(lines) != expected_sums:
                bad("SUMS_ENTRY_COUNT",
                    f"{len(lines)} non-blank entries, expected {expected_sums}")

            # Duplicates BEFORE dict construction, for the same reason as above.
            paths, seen_p, dup_p = [], set(), set()
            for ln in lines:
                m = _SUMS_LINE_RE.match(ln)
                if not m:
                    continue
                p = m.group("path").strip()
                paths.append(p)
                (dup_p if p in seen_p else seen_p).add(p)
                sums[p] = m.group("digest")
            if dup_p:
                bad("SUMS_DUPLICATE_PATH",
                    f"duplicate paths in {SUMS_MEMBER}: {sorted(dup_p)[:5]}")
            elif len(set(paths)) != expected_sums:
                bad("SUMS_ENTRY_COUNT",
                    f"{len(set(paths))} unique paths, expected {expected_sums}")

            missing = sorted(member_set - set(paths) - {SUMS_MEMBER})
            extra = sorted(set(paths) - member_set)
            if SUMS_MEMBER in paths:
                bad("SUMS_COVERAGE", f"{SUMS_MEMBER} must not cover itself")
            if missing:
                bad("SUMS_COVERAGE", f"members absent from sums: {missing[:5]}")
            if extra:
                bad("SUMS_COVERAGE", f"sums list absent members: {extra[:5]}")

            mismatched = sorted(p for p, d in sums.items()
                                if p in blobs and blobs[p] != d)
            if mismatched:
                bad("SUMS_DIGEST_MISMATCH",
                    f"digest disagrees with member bytes: {mismatched[:5]}")

        # ---- FILE_MANIFEST.csv ------------------------------------------
        if MANIFEST_MEMBER not in member_set:
            bad("MANIFEST_COVERAGE", f"{MANIFEST_MEMBER} is absent")
        elif MANIFEST_MEMBER not in catalog_bytes:
            pass                      # unreadable; ARCHIVE_ZIP_CORRUPT logged
        else:
            reader = csv.DictReader(io.StringIO(
                catalog_bytes[MANIFEST_MEMBER].decode("utf-8", "replace")))
            rows = list(reader)
            fields = tuple(reader.fieldnames or ())
            if fields != MANIFEST_COLUMNS:
                bad("MANIFEST_SCHEMA",
                    f"columns {fields} != required {MANIFEST_COLUMNS}")
            expected_rows = expected_member_count - 2
            if len(rows) != expected_rows:
                bad("MANIFEST_ROW_COUNT",
                    f"{len(rows)} data rows, expected {expected_rows}")

            mpaths, seen_m, dup_m = [], set(), set()
            for r in rows:
                p = (r.get("file") or "").strip()
                mpaths.append(p)
                (dup_m if p in seen_m else seen_m).add(p)
            if dup_m:
                bad("MANIFEST_DUPLICATE_PATH",
                    f"duplicate paths in {MANIFEST_MEMBER}: "
                    f"{sorted(dup_m)[:5]}")
            elif len(set(mpaths)) != expected_rows:
                bad("MANIFEST_ROW_COUNT",
                    f"{len(set(mpaths))} unique paths, expected {expected_rows}")

            payload = member_set - {SUMS_MEMBER, MANIFEST_MEMBER}
            missing = sorted(payload - set(mpaths))
            extra = sorted(set(mpaths) - member_set)
            if set(mpaths) & {SUMS_MEMBER, MANIFEST_MEMBER}:
                bad("MANIFEST_COVERAGE",
                    "manifest must not cover the two catalog files")
            if missing:
                bad("MANIFEST_COVERAGE",
                    f"payloads absent from manifest: {missing[:5]}")
            if extra:
                bad("MANIFEST_COVERAGE",
                    f"manifest lists absent members: {extra[:5]}")

            bad_bytes, bad_hash = [], []
            for r in rows:
                p = (r.get("file") or "").strip()
                if p not in blobs:
                    continue
                try:
                    declared = int(str(r.get("bytes", "")).strip())
                except (TypeError, ValueError):
                    bad_bytes.append(p)
                    continue
                if declared != sizes[p]:
                    bad_bytes.append(p)
                if (r.get("sha256") or "").strip() != blobs[p]:
                    bad_hash.append(p)
            if bad_bytes:
                bad("MANIFEST_BYTES_MISMATCH",
                    f"declared byte counts wrong for: {sorted(bad_bytes)[:5]}")
            if bad_hash:
                bad("MANIFEST_DIGEST_MISMATCH",
                    f"declared digests wrong for: {sorted(bad_hash)[:5]}")

            # ---- cross-catalog arithmetic -------------------------------
            if (SUMS_MEMBER in member_set
                    and len(members) != len(set(mpaths)) + 2):
                bad("CATALOG_ARITHMETIC",
                    f"{len(members)} members != {len(set(mpaths))} payloads + "
                    f"{SUMS_MEMBER} + {MANIFEST_MEMBER}")

    return _finish(issues, detail)


def check_archive_structure(archive_path, expected_member_count) -> None:
    """Raise :class:`DepositContractError` carrying EVERY issue, or return."""
    issues, detail = _split(
        archive_structure_issues(archive_path, expected_member_count))
    if issues:
        raise DepositContractError(issues, detail)


def read_archive_netcdf_attrs(archive_path, member):
    """Global attributes of a NetCDF member, read WITHOUT extracting in-repo.

    Uses a system temporary directory only because the netCDF4 C library needs
    a real file handle; nothing is written inside the repository and the
    archive is opened read-only.
    """
    import tempfile

    from netCDF4 import Dataset

    with zipfile.ZipFile(Path(archive_path)) as zf:
        if member not in zf.namelist():
            return None
        with tempfile.TemporaryDirectory() as td:
            local = Path(td) / "member.nc"
            with zf.open(member) as src, open(local, "wb") as dst:
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


def canonical_netcdf_members(archive_path):
    """Every member matching the canonical processed-field NetCDF pattern."""
    with zipfile.ZipFile(Path(archive_path)) as zf:
        return sorted(n for n in zf.namelist() if CANONICAL_NETCDF_RE.match(n))


# ---------------------------------------------------------------------------
# Internals: keep (code, detail) paired while presenting a sorted code list.
# ---------------------------------------------------------------------------
class _Issues(list):
    """A sorted, de-duplicated list of issue codes that also carries details."""

    def __init__(self, codes, detail):
        super().__init__(sorted(set(codes)))
        self.detail = detail


def _finish(issues, detail):
    return _Issues(issues, detail)


def _split(result):
    return list(result), getattr(result, "detail", {})
