#!/usr/bin/env python3
"""Post-D6 release finalizer: a read-only PREFLIGHT and a gated FINALIZE.

The release is blocked on one thing that no amount of green tests can supply:
durable written authorization from coauthor Dr. Nasser Najibi to distribute the
author-created Figure 1 / Figure 4 artwork under CC BY 4.0. This module makes
that gate mechanical.

Two modes, deliberately asymmetric:

``preflight``
    Pure read-only. Verifies every invariant the finalization depends on and
    reports them. It NEVER writes to disk - reports go to stdout - so it is
    safe to run at any time, and running it can never half-apply anything.

``finalize``
    Rechecks every preflight invariant, then fetches the authorization LIVE
    from the GitHub API, rebuilds the deposit archive twice in temporary
    staging and requires the two builds to be byte-identical, recomputes the
    archive identity from the final bytes, applies the identity update as
    structured count-checked edits, revalidates in a disposable full copy of
    the repository, and only then commits the result to the working tree -
    transactionally, restoring the exact pre-run state on any failure.

Things this module will not do, by construction rather than by policy:

* it never commits, pushes, merges, tags, creates a release, publishes, or
  touches Zenodo - no such command is issued anywhere in this file;
* it has no D6 bypass. There is no flag, no environment variable and no local
  evidence file that can stand in for the live comment. Screenshots, pasted
  JSON and human attestations are not accepted inputs because they are not
  inputs at all;
* it never copies a provisional archive identity. Every value written is
  recomputed from the final bytes;
* it never rewrites the protected historical records, which document
  superseded artifacts as historical fact.

Design notes shared with :mod:`deposit_contract`: validators aggregate EVERY
defect into stable sorted issue codes instead of stopping at the first, so one
run reports the whole picture; nothing here imports pytest or calls skip/fail.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_CONTRACT = HERE / "finalizer_contract.json"

_DEPOSIT_DIR = HERE.parent / "deposit"
if str(_DEPOSIT_DIR) not in sys.path:
    sys.path.insert(0, str(_DEPOSIT_DIR))

from deposit_contract import (  # noqa: E402  (sys.path set up just above)
    archive_structure_issues,
    canonical_netcdf_members,
    netcdf_metadata_issues,
    read_archive_netcdf_attrs,
)

#: The confirmation phrase ``finalize`` requires. Typing it is not a safety
#: feature on its own - the D6 gate is - but it stops a stray shell-history
#: re-run from starting a build.
CONFIRM_PHRASE = "FINALIZE SCORCH RELEASE"

#: Trees excluded from the disposable validation copy: local staging areas
#: that are gigabytes large and are not part of the repository under test.
COPY_EXCLUDE = ("release_staging", "manuscript_revision_output",
                "__pycache__", ".pytest_cache")

#: Figure 1 / Figure 4 artwork wording, reusing the repository's own guard
#: vocabulary so this module cannot drift from the tests that police it.
ARTWORK_RX = re.compile(
    r"fig0[14]\b|Figure_0[14]|Figure [14](?!\d)|Fig\. [14](?!\d)", re.I)
PENDING_RX = re.compile(
    r"PENDING|not yet in force|EXCLUDED FROM THE CC BY|NOT Figure|"
    r"no CC BY|never be read as licensing|no public licence|"
    r"requires separate written authorization|has not been recorded|"
    r"no record may|must not|may not|forbidden|prohibited", re.I)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
class Report:
    """An accumulating result: sorted issue codes, details, and observations.

    ``ok`` is True only when no code was recorded. Codes are stable strings so
    callers and tests can assert on them without matching prose.
    """

    def __init__(self, mode):
        self.mode = mode
        self._codes = []
        self.detail = {}
        self.data = {}

    def fail(self, code, why):
        self._codes.append(code)
        self.detail.setdefault(code, why)
        return self

    def note(self, key, value):
        self.data[key] = value
        return self

    @property
    def codes(self):
        return sorted(set(self._codes))

    @property
    def ok(self):
        return not self._codes

    def as_dict(self):
        return {"mode": self.mode, "ok": self.ok, "codes": self.codes,
                "detail": self.detail, "observations": self.data}

    def to_json(self):
        return json.dumps(self.as_dict(), indent=2, sort_keys=True,
                          ensure_ascii=False, default=str)

    def to_text(self):
        lines = [f"SCORCH release finalizer - {self.mode}",
                 f"result: {'PASS' if self.ok else 'BLOCKED'}"]
        if self._codes:
            lines.append(f"blocking codes ({len(self.codes)}):")
            for code in self.codes:
                lines.append(f"  - {code}: {self.detail.get(code, '')}")
        lines.append("observations:")
        for key in sorted(self.data):
            lines.append(f"  {key}: {self.data[key]}")
        return "\n".join(lines)


class FinalizerError(Exception):
    """Raised to abort ``finalize`` and trigger the transactional restore."""

    def __init__(self, code, why):
        self.code = code
        self.why = why
        super().__init__(f"{code}: {why}")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def load_contract(path=None) -> dict:
    return json.loads(Path(path or DEFAULT_CONTRACT)
                      .read_text(encoding="utf-8"))


def git(repo_root, *args, check=True):
    proc = subprocess.run(["git", "-C", str(repo_root), *args],
                          capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise FinalizerError("GIT_COMMAND_FAILED",
                             f"git {' '.join(args)}: {proc.stderr.strip()}")
    return proc.stdout.strip()


def normalize_prose(text: str) -> str:
    """Whitespace-normalize so hard wrapping cannot defeat an exact match.

    Line endings and line breaks are not part of the authorization's meaning;
    a comment box may wrap it anywhere. Every other difference is preserved,
    so alteration and truncation still fail.
    """
    return " ".join(text.replace("\r\n", "\n").split())


# ---------------------------------------------------------------------------
# GitHub access. The real client shells out to the authenticated `gh` CLI;
# tests inject a fake by PASSING A CLIENT OBJECT, never via flag or env, so
# production has no injection surface at all.
# ---------------------------------------------------------------------------
class GitHubCLI:
    """Live GitHub API access through the authenticated ``gh`` CLI."""

    def _api(self, endpoint):
        proc = subprocess.run(["gh", "api", endpoint],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            raise FinalizerError(
                "GITHUB_API_UNAVAILABLE",
                f"gh api {endpoint} failed: {proc.stderr.strip()[:300]}")
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise FinalizerError("GITHUB_API_UNAVAILABLE",
                                 f"gh api {endpoint}: bad JSON: {exc}")

    def pull_request(self, owner, repo, number):
        return self._api(f"repos/{owner}/{repo}/pulls/{number}")

    def issue_comments(self, owner, repo, number):
        return self._api(
            f"repos/{owner}/{repo}/issues/{number}/comments?per_page=100")

    def issue_comment(self, owner, repo, comment_id):
        return self._api(
            f"repos/{owner}/{repo}/issues/comments/{comment_id}")


def find_authorization(github, contract):
    """Locate and validate the D6 authorization comment. Never guesses.

    Returns ``(record, issues)``. ``record`` is None unless a single live
    top-level comment on the contracted pull request, authored by the
    contracted login, carries the exact authorization text.
    """
    repo = contract["repository"]
    owner, name = repo["owner"], repo["name"]
    number = repo["pull_request"]
    want_login = contract["authorization"]["required_login"]
    want_text = normalize_prose(contract["authorization"]["text"])
    issues = []

    comments = github.issue_comments(owner, name, number)
    by_author = [c for c in comments
                 if str((c.get("user") or {}).get("login", "")).lower()
                 == want_login.lower()]
    if not by_author:
        issues.append(("RELEASE_BLOCKED_D6",
                       f"no top-level comment by {want_login} on "
                       f"{owner}/{name}#{number} ({len(comments)} comment(s) "
                       f"present)"))
        return None, issues

    matching = [c for c in by_author
                if want_text in normalize_prose(str(c.get("body", "")))]
    if not matching:
        issues.append(("AUTHZ_BODY_ALTERED",
                       f"{want_login} has commented on #{number} but no "
                       f"comment carries the exact authorization text; an "
                       f"altered or truncated body is not authorization"))
        return None, issues

    chosen = matching[0]
    # Re-fetch the specific comment: the listing could be stale, and a comment
    # that has since been deleted or edited must not authorize anything.
    live = github.issue_comment(owner, name, chosen["id"])
    live_login = str((live.get("user") or {}).get("login", ""))
    live_body = str(live.get("body", ""))
    if live_login.lower() != want_login.lower():
        issues.append(("AUTHZ_WRONG_AUTHOR",
                       f"comment {chosen['id']} is authored by "
                       f"{live_login!r}, not {want_login!r}"))
        return None, issues
    if want_text not in normalize_prose(live_body):
        issues.append(("AUTHZ_BODY_ALTERED",
                       f"comment {chosen['id']} no longer carries the exact "
                       f"authorization text on re-fetch"))
        return None, issues

    url = str(live.get("html_url", ""))
    if f"/{owner}/{name}/pull/{number}" not in url:
        issues.append(("AUTHZ_WRONG_TARGET",
                       f"comment permalink {url!r} does not belong to "
                       f"{owner}/{name} pull request {number}"))
        return None, issues

    record = {
        "comment_id": live["id"],
        "permalink": url,
        "login": live_login,
        "created_at": live.get("created_at"),
        "updated_at": live.get("updated_at"),
        "body": live_body,
        "body_sha256": sha256_bytes(live_body.encode("utf-8")),
    }
    return record, issues


# ---------------------------------------------------------------------------
# Archive identity
# ---------------------------------------------------------------------------
def current_identity(repo_root, contract) -> dict:
    """The identity the tracked records currently declare - never a constant.

    Reading it from the repository's own package record is what keeps this
    module free of pinned provisional values.
    """
    rec = json.loads((Path(repo_root) / contract["identity"]["package_record"])
                     .read_text(encoding="utf-8"))
    pkg = rec["relocation"]["packages"][contract["identity"]["package_id"]]
    return {"archive_filename": str(pkg["archive_filename"]),
            "archive_sha256": str(pkg["archive_sha256"]),
            "archive_bytes": str(pkg["archive_bytes"]),
            "content_root_hash": str(pkg["content_root_hash"])}


def archive_identity(path) -> dict:
    """Recompute the complete identity of an archive FROM ITS BYTES."""
    path = Path(path)
    data_sha = sha256_file(path)
    size = path.stat().st_size
    with zipfile.ZipFile(path) as zf:
        members = sorted({i.filename for i in zf.infolist() if not i.is_dir()})
        hashes = {m: sha256_bytes(zf.read(m)) for m in members}
    blob = "".join(f"{hashes[m]}  {m}\n" for m in sorted(members))
    return {"archive_filename": path.name,
            "archive_sha256": data_sha,
            "archive_bytes": str(size),
            "content_root_hash": sha256_bytes(blob.encode("utf-8")),
            "member_count": len(members),
            "member_hashes": hashes}


def archive_topology_issues(path, contract):
    """Structure, self-coverage, member arithmetic and NetCDF contract."""
    topo = contract["archive_topology"]
    issues = []
    structural = archive_structure_issues(path, topo["member_count"])
    detail = dict(getattr(structural, "detail", {}))
    for code in structural:
        issues.append((code, detail.get(code, "")))

    with zipfile.ZipFile(path) as zf:
        members = sorted({i.filename for i in zf.infolist() if not i.is_dir()})
        sums = [ln for ln in zf.read(topo["sums_member"])
                .decode("utf-8").splitlines() if ln.strip()]
        rows = list(csv.DictReader(io.StringIO(
            zf.read(topo["manifest_member"]).decode("utf-8"))))
        if len(sums) != topo["sums_entries"]:
            issues.append(("SUMS_ENTRY_COUNT",
                           f"{len(sums)} entries, expected "
                           f"{topo['sums_entries']}"))
        if len(rows) != topo["manifest_rows"]:
            issues.append(("MANIFEST_ROW_COUNT",
                           f"{len(rows)} rows, expected "
                           f"{topo['manifest_rows']}"))
        if topo["validator_member"] not in members:
            issues.append(("DEPOSIT_VALIDATOR_ABSENT",
                           f"{topo['validator_member']} is not a member"))

    nc = canonical_netcdf_members(path)
    if len(nc) != 1:
        issues.append(("ARCHIVE_NETCDF_MEMBER_COUNT",
                       f"expected 1 canonical NetCDF member, found {len(nc)}"))
    else:
        try:
            attrs = read_archive_netcdf_attrs(path, nc[0])
        except Exception as exc:            # noqa: BLE001 - reported, not raised
            issues.append(("NETCDF_UNREADABLE", f"{nc[0]}: {exc}"))
        else:
            meta = netcdf_metadata_issues(attrs or {})
            mdetail = dict(getattr(meta, "detail", {}))
            for code in meta:
                issues.append((code, mdetail.get(code, "")))
    return issues


def circular_identity_issues(archive_path, contract, identity):
    """No identity-bearing record may be an input to the archive it names.

    If one of the eight files were packed into the archive, updating it would
    change the archive, which would change the identity, which would require
    updating the file again. The same defect in miniature: no member may carry
    the archive's own hash.
    """
    issues = []
    eight = set(contract["identity"]["files"])
    with zipfile.ZipFile(archive_path) as zf:
        members = [i.filename for i in zf.infolist() if not i.is_dir()]
        overlap = sorted(eight & set(members))
        if overlap:
            issues.append(("CIRCULAR_IDENTITY",
                           f"identity-bearing files are archive members: "
                           f"{overlap}"))
        own = identity["archive_sha256"].encode("ascii")
        carriers = [m for m in members if own in zf.read(m)]
        if carriers:
            issues.append(("CIRCULAR_IDENTITY",
                           f"members carry the archive's own SHA-256: "
                           f"{carriers[:5]}"))
    return issues


def build_deterministic_zip(stage_dir, dest_path):
    """Write a ZIP whose bytes depend only on the staged file contents.

    Sorted member order, a frozen timestamp, fixed permissions and a fixed
    compression level. Two builds from identical inputs are byte-identical,
    which is what makes the double-build check meaningful rather than
    decorative.
    """
    stage_dir, dest_path = Path(stage_dir), Path(dest_path)
    rels = sorted(p.relative_to(stage_dir).as_posix()
                  for p in stage_dir.rglob("*") if p.is_file())
    with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED,
                         compresslevel=9) as zf:
        for rel in rels:
            info = zipfile.ZipInfo(rel, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            info.create_system = 3
            with open(stage_dir / rel, "rb") as src, zf.open(info, "w") as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
    return dest_path


# ---------------------------------------------------------------------------
# The identity update: structured, count-checked, never a global replace
# ---------------------------------------------------------------------------
class Edit:
    """One file's complete planned rewrite, with its per-field arithmetic."""

    def __init__(self, rel, original, updated, counts, changed):
        self.rel = rel
        self.original = original
        self.updated = updated
        self.counts = counts
        self.changed = changed

    @property
    def references(self):
        return sum(self.counts.values())


def plan_identity_edits(repo_root, contract, old, new):
    """Plan the eight-file update, refusing anything that is not exact.

    Every field occurrence is verified at its contracted count BEFORE and
    AFTER substitution. A field whose old and new values coincide (the archive
    filename normally does) is still verified at its full count - it is a
    checked no-op, not an unchecked one.
    """
    repo_root = Path(repo_root)
    spec = contract["identity"]["files"]
    protected = set(contract["protected_historical_records"])
    edits = []

    for rel, fields in sorted(spec.items()):
        if rel in protected:
            raise FinalizerError(
                "EDIT_PROTECTED_RECORD",
                f"{rel} is a protected historical record and must never be "
                f"rewritten as a current pointer")
        path = repo_root / rel
        if not path.is_file():
            raise FinalizerError("EDIT_FILE_MISSING", f"{rel} is not a file")
        original = path.read_bytes()
        data = original
        counts, changed = {}, 0
        for field, expected in sorted(fields.items()):
            src = old[field].encode("utf-8")
            dst = new[field].encode("utf-8")
            found = data.count(src)
            if found != expected:
                raise FinalizerError(
                    "EDIT_REFERENCE_COUNT",
                    f"{rel}: {field} occurs {found} time(s), contract "
                    f"requires exactly {expected}")
            if src != dst:
                data = data.replace(src, dst)
                changed += expected
                stale = data.count(src)
                if stale:
                    raise FinalizerError(
                        "EDIT_AMBIGUOUS_OCCURRENCE",
                        f"{rel}: {stale} occurrence(s) of the superseded "
                        f"{field} survived substitution")
            if data.count(dst) < expected:
                raise FinalizerError(
                    "EDIT_REFERENCE_COUNT",
                    f"{rel}: after substitution {field} occurs "
                    f"{data.count(dst)} time(s), expected at least {expected}")
            counts[field] = expected
        _assert_structure_preserved(rel, original, data)
        edits.append(Edit(rel, original, data, counts, changed))

    if len(edits) != contract["identity"]["expected_file_count"]:
        raise FinalizerError(
            "EDIT_FILE_COUNT",
            f"planned {len(edits)} file(s), contract requires "
            f"{contract['identity']['expected_file_count']}")
    total = sum(e.references for e in edits)
    if total != contract["identity"]["expected_reference_count"]:
        raise FinalizerError(
            "EDIT_REFERENCE_COUNT",
            f"planned {total} reference(s), contract requires "
            f"{contract['identity']['expected_reference_count']}")
    return edits


def _assert_structure_preserved(rel, original, updated):
    """A value swap must not change a record's shape.

    Byte substitution is blunt: it cannot tell a value from a fragment of a
    longer token. Re-parsing catches the case where it silently corrupted the
    container even though the counts looked right.
    """
    if rel.endswith(".json"):
        try:
            before = json.loads(original.decode("utf-8"))
            after = json.loads(updated.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FinalizerError("EDIT_STRUCTURE_BROKEN",
                                 f"{rel}: not valid JSON after edit: {exc}")
        if _shape(before) != _shape(after):
            raise FinalizerError("EDIT_STRUCTURE_BROKEN",
                                 f"{rel}: JSON shape changed")
    elif rel.endswith(".csv"):
        rows_b = list(csv.reader(io.StringIO(original.decode("utf-8"))))
        rows_a = list(csv.reader(io.StringIO(updated.decode("utf-8"))))
        if len(rows_b) != len(rows_a):
            raise FinalizerError(
                "EDIT_STRUCTURE_BROKEN",
                f"{rel}: row count changed {len(rows_b)} -> {len(rows_a)}")
        if rows_b and rows_a and rows_b[0] != rows_a[0]:
            raise FinalizerError("EDIT_STRUCTURE_BROKEN",
                                 f"{rel}: header row changed")
        if [len(r) for r in rows_b] != [len(r) for r in rows_a]:
            raise FinalizerError("EDIT_STRUCTURE_BROKEN",
                                 f"{rel}: column arity changed")
    else:
        if original.count(b"\n") != updated.count(b"\n"):
            raise FinalizerError("EDIT_STRUCTURE_BROKEN",
                                 f"{rel}: line count changed")


def _shape(node):
    if isinstance(node, dict):
        return {k: _shape(v) for k, v in sorted(node.items())}
    if isinstance(node, list):
        return [_shape(v) for v in node]
    return type(node).__name__


def plan_ccby_activation(repo_root, contract):
    """Plan the CC BY activation, or refuse because nobody authored it.

    Activation rewrites legal prose. The contract carries exact from/to pairs
    written by an author; this function applies them with the same arithmetic
    as the identity update and never invents wording of its own.
    """
    plan = contract.get("ccby_activation_plan") or {}
    if not plan.get("authored"):
        raise FinalizerError(
            "CCBY_ACTIVATION_PLAN_UNAUTHORED",
            "ccby_activation_plan.authored is false: no author-written "
            "activation wording exists, and this tool will not invent the "
            "licence prose for the Figure 1 / Figure 4 artwork")
    repo_root = Path(repo_root)
    records = set(contract["licence_records"])
    protected = set(contract["protected_historical_records"])
    staged = {}
    for item in plan["replacements"]:
        rel = item["file"]
        if rel in protected:
            raise FinalizerError("EDIT_PROTECTED_RECORD",
                                 f"{rel} is a protected historical record")
        if rel not in records:
            raise FinalizerError(
                "CCBY_ACTIVATION_SCOPE",
                f"{rel} is not one of the licence records; activation may not "
                f"touch anything else")
        path = repo_root / rel
        data = staged.get(rel, path.read_bytes())
        src = item["from"].encode("utf-8")
        dst = item["to"].encode("utf-8")
        found = data.count(src)
        if found != int(item["count"]):
            raise FinalizerError(
                "CCBY_ACTIVATION_COUNT",
                f"{rel}: activation source occurs {found} time(s), plan "
                f"declares {item['count']}")
        staged[rel] = data.replace(src, dst)

    edits = []
    for rel, updated in sorted(staged.items()):
        original = (repo_root / rel).read_bytes()
        _assert_third_party_rights_preserved(rel, original, updated, contract)
        edits.append(Edit(rel, original, updated, {"ccby_activation": 1}, 1))
    return edits


def _assert_third_party_rights_preserved(rel, original, updated, contract):
    """CC BY must reach the authors' artwork and nothing else.

    Every third-party rights token must survive the activation at exactly its
    original count. This is the leakage guard: a rewrite that dissolved the
    Copernicus notice or relicensed the GHCN material would otherwise look
    like a successful activation.
    """
    for token in contract["third_party_rights_tokens"]:
        raw = token.encode("utf-8")
        before, after = original.count(raw), updated.count(raw)
        if before != after:
            raise FinalizerError(
                "CCBY_THIRD_PARTY_LEAKAGE",
                f"{rel}: third-party rights token {token!r} occurred {before} "
                f"time(s) before activation and {after} after; activation may "
                f"not alter third-party rights")


class Transaction:
    """All-or-nothing application of planned edits, with byte-exact restore.

    Snapshots every file it will touch AND every protected record, applies the
    edits, then verifies. Any failure restores the exact original bytes of
    everything snapshotted, so a partial write cannot survive.
    """

    def __init__(self, repo_root, contract):
        self.repo_root = Path(repo_root)
        self.contract = contract
        self._snapshot = {}
        self.applied = False

    def _capture(self, rel):
        if rel not in self._snapshot:
            self._snapshot[rel] = (self.repo_root / rel).read_bytes()

    def apply(self, edits):
        protected = list(self.contract["protected_historical_records"])
        for rel in protected:
            self._capture(rel)
        for edit in edits:
            self._capture(edit.rel)
        try:
            for edit in edits:
                _atomic_write(self.repo_root / edit.rel, edit.updated)
            for rel in protected:
                if (self.repo_root / rel).read_bytes() != self._snapshot[rel]:
                    raise FinalizerError(
                        "PROTECTED_RECORD_MODIFIED",
                        f"{rel} changed during the transaction")
            for edit in edits:
                if (self.repo_root / edit.rel).read_bytes() != edit.updated:
                    raise FinalizerError(
                        "TRANSACTION_WRITE_MISMATCH",
                        f"{edit.rel} on disk does not match the planned bytes")
            self.applied = True
        except BaseException:
            self.rollback()
            raise

    def rollback(self):
        for rel, data in self._snapshot.items():
            _atomic_write(self.repo_root / rel, data)
        self.applied = False


def _atomic_write(target, data):
    tmp = target.with_name(target.name + ".finalizer-tmp")
    tmp.write_bytes(data)
    os.replace(tmp, target)


# ---------------------------------------------------------------------------
# Isolation diagnostics - the residual question the overlay left open
# ---------------------------------------------------------------------------
ISOLATION_PROBE = r"""
import json, os, sys
sys.path.insert(0, os.path.join(os.getcwd(), "tests"))
info = {
    "cwd": os.getcwd(),
    "sys_executable": sys.executable,
    "pythonpath": os.environ.get("PYTHONPATH", ""),
    "dont_write_bytecode": bool(sys.dont_write_bytecode),
    "pycache_prefix": sys.pycache_prefix,
    "sys_path_head": sys.path[:6],
}
try:
    import pytest
    info["pytest_version"] = pytest.__version__
    info["pytest_file"] = pytest.__file__
except Exception as exc:
    info["pytest_import_error"] = repr(exc)
for name in ("test_public_consistency_guards", "test_stale_provenance",
             "test_corrected_schematic_figures"):
    try:
        mod = __import__(name)
        info[name + "__file__"] = getattr(mod, "__file__", None)
        info[name + "__REPO"] = str(getattr(mod, "REPO", ""))
    except Exception as exc:
        info[name + "__error"] = repr(exc)
print(json.dumps(info))
"""


def isolation_diagnostics(root, python_exe):
    """Record exactly which tree an isolated run really resolved.

    The overlay run rendered one skipped module's path as the real worktree
    rather than the disposable copy. That was believed cosmetic but was never
    root-caused, so every isolated run now records repository root, working
    directory, PYTHONPATH, bytecode configuration and the resolved ``__file__``
    of the modules in question, and the answer is evidence rather than belief.
    """
    root = Path(root)
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = "src"
    proc = subprocess.run([str(python_exe), "-c", ISOLATION_PROBE],
                          cwd=str(root), env=env, capture_output=True,
                          text=True)
    out = {"repository_root": str(root), "probe_exit": proc.returncode}
    try:
        out.update(json.loads(proc.stdout.strip().splitlines()[-1]))
    except (ValueError, IndexError):
        out["probe_stdout"] = proc.stdout[-2000:]
        out["probe_stderr"] = proc.stderr[-2000:]
    return out


PYTEST_SUMMARY_PLUGIN = r'''
"""Test-support plugin: dump the exact pytest tally as JSON."""
import json, os


def pytest_configure(config):
    config._scorch_rootdir = str(config.rootdir)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    stats = terminalreporter.stats
    summary = {
        "rootdir": getattr(config, "_scorch_rootdir", ""),
        "invocation_dir": str(config.invocation_params.dir),
        "exit_status": int(exitstatus),
        "collected": int(getattr(terminalreporter, "_numcollected", 0)),
        "passed": len(stats.get("passed", [])),
        "failed": len(stats.get("failed", [])),
        "errors": len(stats.get("error", [])),
        "skipped": len(stats.get("skipped", [])),
        "xfailed": len(stats.get("xfailed", [])),
        "xpassed": len(stats.get("xpassed", [])),
    }
    target = os.environ.get("SCORCH_PYTEST_SUMMARY")
    if target:
        with open(target, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
'''


def run_validation(copy_root, python_exe, env_extra, summary_path):
    """Run the full suite in the disposable copy and return its exact tally."""
    copy_root = Path(copy_root)
    plugin_dir = copy_root / ".finalizer_plugin"
    plugin_dir.mkdir(exist_ok=True)
    (plugin_dir / "scorch_summary_plugin.py").write_text(
        PYTEST_SUMMARY_PLUGIN, encoding="utf-8")

    env = dict(os.environ)
    for drop in ("SCORCH_OUT_DIR", "SCORCH_CLEAN_OUT", "SCORCH_REPRO",
                 "SCORCH_ROOT", "SCORCH_RELEASE_ROOT", "SCORCH_WORKBOOK"):
        env.pop(drop, None)
    env.update({k: v for k, v in env_extra.items() if v})
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = os.pathsep.join(["src", str(plugin_dir)])
    env["SCORCH_PYTEST_SUMMARY"] = str(summary_path)

    with tempfile.TemporaryDirectory(prefix="scorchbt") as basetemp:
        proc = subprocess.run(
            [str(python_exe), "-m", "pytest", "tests",
             "-p", "no:cacheprovider", "-p", "scorch_summary_plugin",
             "--basetemp", basetemp, "-rsxX", "-q"],
            cwd=str(copy_root), env=env, capture_output=True, text=True)
    result = {"exit_code": proc.returncode,
              "tail": proc.stdout[-4000:] + proc.stderr[-2000:]}
    if Path(summary_path).is_file():
        result.update(json.loads(Path(summary_path).read_text("utf-8")))
    return result


# ---------------------------------------------------------------------------
# PREFLIGHT - read-only
# ---------------------------------------------------------------------------
def preflight(repo_root, expect_branch, expect_head, *, contract,
              github=None, candidate_archive=None, final_docx_dir=None,
              aptos_font=None):
    """Verify every invariant finalization depends on. Writes nothing, ever."""
    report = Report("preflight")
    root = Path(repo_root).resolve()
    repo = contract["repository"]

    report.note("repository_root", str(root))
    report.note("expected_branch", expect_branch)
    report.note("expected_head", expect_head)

    # --- git ---------------------------------------------------------------
    if not (root / ".git").exists():
        return report.fail("GIT_REPO_ROOT_MISMATCH",
                           f"{root} is not a git working tree")
    try:
        top = Path(git(root, "rev-parse", "--show-toplevel")).resolve()
        branch = git(root, "rev-parse", "--abbrev-ref", "HEAD")
        head = git(root, "rev-parse", "HEAD")
        status = git(root, "status", "--porcelain=v1")
    except FinalizerError as exc:
        return report.fail(exc.code, exc.why)

    report.note("actual_branch", branch)
    report.note("actual_head", head)
    if top != root:
        report.fail("GIT_REPO_ROOT_MISMATCH",
                    f"{root} resolves to working tree {top}")
    if branch != expect_branch:
        report.fail("GIT_BRANCH_MISMATCH",
                    f"on {branch!r}, expected {expect_branch!r}")
    if branch != repo["head_branch"]:
        report.fail("GIT_BRANCH_MISMATCH",
                    f"branch {branch!r} is not the contracted head branch "
                    f"{repo['head_branch']!r}")
    if head != expect_head:
        report.fail("GIT_HEAD_MISMATCH",
                    f"HEAD is {head}, expected {expect_head}")
    if status:
        report.fail("GIT_TREE_DIRTY",
                    f"working tree is not clean: {status.splitlines()[:5]}")

    remote_branch = git(root, "rev-parse",
                        f"refs/remotes/origin/{repo['head_branch']}",
                        check=False)
    report.note("remote_head", remote_branch)
    if remote_branch != head:
        report.fail("GIT_REMOTE_BRANCH_MISMATCH",
                    f"origin/{repo['head_branch']} is {remote_branch}, local "
                    f"HEAD is {head}")
    main = git(root, "rev-parse", f"refs/remotes/origin/{repo['base_branch']}",
               check=False)
    report.note("origin_main", main)
    if main != repo["expected_main_commit"]:
        report.fail("GIT_MAIN_MOVED",
                    f"origin/{repo['base_branch']} is {main}, expected "
                    f"{repo['expected_main_commit']}")
    tag_obj = git(root, "rev-parse", repo["expected_tag"], check=False)
    tag_commit = git(root, "rev-parse", f"{repo['expected_tag']}^{{commit}}",
                     check=False)
    report.note("tag_object", tag_obj)
    report.note("tag_commit", tag_commit)
    if tag_obj != repo["expected_tag_object"]:
        report.fail("GIT_TAG_MOVED",
                    f"tag object {tag_obj}, expected "
                    f"{repo['expected_tag_object']}")
    if tag_commit != repo["expected_tag_commit"]:
        report.fail("GIT_TAG_MOVED",
                    f"tag commit {tag_commit}, expected "
                    f"{repo['expected_tag_commit']}")

    # --- pull request and the D6 gate --------------------------------------
    client = github if github is not None else GitHubCLI()
    try:
        pr = client.pull_request(repo["owner"], repo["name"],
                                 repo["pull_request"])
        report.note("pr_state", pr.get("state"))
        report.note("pr_draft", pr.get("draft"))
        report.note("pr_merged", bool(pr.get("merged_at")))
        if str(pr.get("state", "")).lower() != "open":
            report.fail("PR_STATE_UNEXPECTED",
                        f"pull request state is {pr.get('state')!r}")
        if pr.get("merged_at"):
            report.fail("PR_STATE_UNEXPECTED",
                        f"pull request is merged at {pr.get('merged_at')}")
        if not pr.get("draft", False):
            report.fail("PR_STATE_UNEXPECTED", "pull request is not a draft")
        if str((pr.get("base") or {}).get("ref")) != repo["base_branch"]:
            report.fail("PR_STATE_UNEXPECTED", "unexpected base branch")
        if str((pr.get("head") or {}).get("ref")) != repo["head_branch"]:
            report.fail("PR_STATE_UNEXPECTED", "unexpected head branch")
        if str((pr.get("head") or {}).get("sha")) != head:
            report.fail("PR_STATE_UNEXPECTED",
                        f"pull request head {(pr.get('head') or {}).get('sha')}"
                        f" != local HEAD {head}")

        record, issues = find_authorization(client, contract)
        for code, why in issues:
            report.fail(code, why)
        report.note("d6_authorization_present", record is not None)
        if record is not None:
            report.note("d6_permalink", record["permalink"])
            report.note("d6_comment_id", record["comment_id"])
            report.note("d6_body_sha256", record["body_sha256"])
    except FinalizerError as exc:
        report.fail(exc.code, exc.why)

    # --- figures and donors ------------------------------------------------
    for rel, want in sorted(contract["figures"].items()):
        path = root / rel
        if not path.is_file():
            report.fail("FIGURE_IDENTITY_MISMATCH", f"{rel} is missing")
            continue
        got = sha256_file(path)
        if got != want:
            report.fail("FIGURE_IDENTITY_MISMATCH",
                        f"{rel}: {got} != pinned {want}")
    report.note("figures_verified", len(contract["figures"]))

    # --- the four pending-artwork markers ----------------------------------
    marked = []
    for rel in contract["licence_records"]:
        path = root / rel
        if not path.is_file():
            report.fail("PENDING_MARKER_COUNT", f"{rel} is missing")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if ARTWORK_RX.search(text) and PENDING_RX.search(text):
            marked.append(rel)
    report.note("pending_markers", marked)
    if len(marked) != contract["expected_pending_marker_count"]:
        report.fail("PENDING_MARKER_COUNT",
                    f"{len(marked)} licence record(s) withhold the artwork "
                    f"grant, expected "
                    f"{contract['expected_pending_marker_count']}: {marked}")

    # --- the eight-file / fifty-six-reference contract ---------------------
    try:
        old = current_identity(root, contract)
        report.note("current_identity", old)
        verify_identity_mapping(root, contract, old, report)
    except (FinalizerError, KeyError, ValueError) as exc:
        report.fail("IDENTITY_MAPPING_MISMATCH", str(exc))

    # --- protected historical records --------------------------------------
    for rel in contract["protected_historical_records"]:
        path = root / rel
        if not path.is_file():
            report.fail("PROTECTED_RECORD_MISSING", f"{rel} is missing")
            continue
        if contract["historical_netcdf_sha256"] not in path.read_text(
                encoding="utf-8", errors="replace"):
            report.fail("PROTECTED_RECORD_MODIFIED",
                        f"{rel} no longer carries the superseded NetCDF hash "
                        f"it exists to record as historical fact")
    report.note("protected_records",
                list(contract["protected_historical_records"]))

    # --- candidate archive, when the operator supplies one ------------------
    if candidate_archive:
        cand = Path(candidate_archive)
        if not cand.is_file():
            report.fail("ARCHIVE_CANDIDATE_MISSING", f"{cand} is not a file")
        else:
            ident = archive_identity(cand)
            report.note("candidate_archive", {
                "path": str(cand), "filename": ident["archive_filename"],
                "sha256": ident["archive_sha256"],
                "bytes": ident["archive_bytes"],
                "content_root_hash": ident["content_root_hash"],
                "member_count": ident["member_count"]})
            for code, why in archive_topology_issues(cand, contract):
                report.fail(code, why)
            for code, why in circular_identity_issues(cand, contract, ident):
                report.fail(code, why)
    else:
        report.note("candidate_archive", "not supplied (optional)")

    # --- FINAL-DOCX fixtures ------------------------------------------------
    docx_dir = final_docx_dir or os.environ.get("SCORCH_FINAL_DOCX_DIR", "")
    if not docx_dir:
        report.fail("DOCX_FIXTURE_MISSING",
                    "no FINAL-DOCX directory supplied "
                    "(--final-docx-dir or SCORCH_FINAL_DOCX_DIR)")
    else:
        ddir = Path(docx_dir)
        for name, want in sorted(contract["docx_fixtures"].items()):
            path = ddir / name
            if not path.is_file():
                report.fail("DOCX_FIXTURE_MISSING", f"{path} is missing")
                continue
            got = sha256_file(path)
            if got != want:
                report.fail("DOCX_FIXTURE_MISMATCH",
                            f"{name}: {got} != pinned {want}; the superseded "
                            f"pre-R5 pair must not be used")
        report.note("final_docx_dir", str(ddir))

    # --- the pinned font, which may never be substituted -------------------
    font = aptos_font or os.environ.get("SCORCH_APTOS_FONT", "").strip()
    if not font:
        report.fail("APTOS_FONT_MISSING",
                    "the pinned Aptos Regular face is not available "
                    "(SCORCH_APTOS_FONT unset); it is a non-redistributable "
                    "Microsoft 365 cloud font and NO SUBSTITUTE IS PERMITTED")
    elif not Path(font).is_file():
        report.fail("APTOS_FONT_MISSING", f"{font} is not a file")
    else:
        got = sha256_file(font)
        report.note("aptos_font", {"path": font, "sha256": got})
        if got != contract["aptos_font_sha256"]:
            report.fail("APTOS_FONT_MISMATCH",
                        f"{font} hashes {got}, the pinned face is "
                        f"{contract['aptos_font_sha256']}; a different face "
                        f"is a substitution, not the pinned font")

    # --- the activation plan nobody has authored ---------------------------
    if not (contract.get("ccby_activation_plan") or {}).get("authored"):
        report.fail("CCBY_ACTIVATION_PLAN_UNAUTHORED",
                    "no author-written CC BY activation wording exists in the "
                    "contract; the finalizer will not invent licence prose")

    return report


def verify_identity_mapping(root, contract, old, report):
    """Confirm the eight-file / fifty-six-reference map against the real tree.

    Also confirms the map is EXHAUSTIVE: a ninth tracked file carrying the
    identity would be left behind contradicting the archive, so finding one is
    a failure rather than a curiosity.
    """
    root = Path(root)
    spec = contract["identity"]["files"]
    files_ok, refs = 0, 0
    for rel, fields in sorted(spec.items()):
        path = root / rel
        if not path.is_file():
            report.fail("IDENTITY_MAPPING_MISMATCH", f"{rel} is missing")
            continue
        data = path.read_bytes()
        for field, expected in sorted(fields.items()):
            found = data.count(old[field].encode("utf-8"))
            if found != expected:
                report.fail("IDENTITY_MAPPING_MISMATCH",
                            f"{rel}: {field} occurs {found} time(s), contract "
                            f"requires {expected}")
            refs += found
        files_ok += 1
    report.note("identity_files", files_ok)
    report.note("identity_references", refs)
    if files_ok != contract["identity"]["expected_file_count"]:
        report.fail("IDENTITY_MAPPING_MISMATCH",
                    f"{files_ok} identity file(s), expected "
                    f"{contract['identity']['expected_file_count']}")
    if refs != contract["identity"]["expected_reference_count"]:
        report.fail("IDENTITY_MAPPING_MISMATCH",
                    f"{refs} reference(s), expected "
                    f"{contract['identity']['expected_reference_count']}")

    strays = []
    for rel in git(root, "ls-files").splitlines():
        if rel in spec or rel in contract["protected_historical_records"]:
            continue
        try:
            data = (root / rel).read_bytes()
        except OSError:
            continue
        if any(old[f].encode("utf-8") in data
               for f in ("archive_sha256", "content_root_hash")):
            strays.append(rel)
    if strays:
        report.fail("IDENTITY_MAPPING_MISMATCH",
                    f"tracked files carry the archive identity but are not in "
                    f"the contract: {strays}")


# ---------------------------------------------------------------------------
# FINALIZE - gated, transactional, and not runnable before D6
# ---------------------------------------------------------------------------
def finalize(repo_root, expect_branch, expect_head, *, contract, stage_dir,
             github=None, candidate_archive=None, final_docx_dir=None,
             aptos_font=None, python_exe=None, confirm=None):
    """Apply the release finalization, or change nothing at all."""
    report = Report("finalize")
    root = Path(repo_root).resolve()
    python_exe = python_exe or sys.executable

    if confirm != CONFIRM_PHRASE:
        return report.fail("CONFIRMATION_REQUIRED",
                           f"pass --confirm {CONFIRM_PHRASE!r} to proceed")

    # 1. Every preflight invariant, rechecked.
    pre = preflight(root, expect_branch, expect_head, contract=contract,
                    github=github, candidate_archive=candidate_archive,
                    final_docx_dir=final_docx_dir, aptos_font=aptos_font)
    report.note("preflight", pre.as_dict())
    for code in pre.codes:
        report.fail(code, pre.detail.get(code, ""))
    if not pre.ok:
        return report

    # 2-5. The authorization itself, fetched live and validated.
    client = github if github is not None else GitHubCLI()
    try:
        record, issues = find_authorization(client, contract)
    except FinalizerError as exc:
        return report.fail(exc.code, exc.why)
    for code, why in issues:
        report.fail(code, why)
    if record is None:
        return report.fail("RELEASE_BLOCKED_D6",
                           "no qualifying live authorization comment")
    report.note("authorization", record)

    transaction = Transaction(root, contract)
    try:
        # 6-7. The activation plan, which an author must have written.
        ccby_edits = plan_ccby_activation(root, contract)

        stage = Path(stage_dir)
        if not stage.is_dir():
            raise FinalizerError("STAGE_DIR_MISSING",
                                 f"{stage} is not a directory")
        with tempfile.TemporaryDirectory(prefix="scorch_finalize") as td:
            work = Path(td)
            # 8-11. Build twice; require byte-identical results.
            first = build_deterministic_zip(stage, work / "build-1.zip")
            second = build_deterministic_zip(stage, work / "build-2.zip")
            sha_first, sha_second = sha256_file(first), sha256_file(second)
            report.note("double_build",
                        {"first": sha_first, "second": sha_second})
            if sha_first != sha_second:
                raise FinalizerError(
                    "BUILD_NONDETERMINISTIC",
                    f"two builds from identical inputs differ: {sha_first} "
                    f"vs {sha_second}")

            final_name = contract["identity"]["final_archive_filename"]
            final_path = work / final_name
            os.replace(first, final_path)

            for code, why in archive_topology_issues(final_path, contract):
                raise FinalizerError(code, why)

            # 12. Identity recomputed from the FINAL bytes. Never copied.
            new = archive_identity(final_path)
            report.note("final_identity", {
                "archive_filename": new["archive_filename"],
                "archive_sha256": new["archive_sha256"],
                "archive_bytes": new["archive_bytes"],
                "content_root_hash": new["content_root_hash"],
                "member_count": new["member_count"]})
            if new["archive_filename"] != final_name:
                raise FinalizerError("BUILD_FILENAME",
                                     f"built {new['archive_filename']!r}")
            if sha256_file(final_path) != new["archive_sha256"]:
                raise FinalizerError(
                    "BYTES_MUTATED_AFTER_HASHING",
                    "the archive changed between hashing and use")

            for code, why in circular_identity_issues(final_path, contract,
                                                      new):
                raise FinalizerError(code, why)

            old = current_identity(root, contract)
            _assert_sidecar_members_unchanged(root, contract, new)

            # 13-14. The structured, count-checked identity update.
            identity_edits = plan_identity_edits(root, contract, old, new)
            report.note("identity_edit_summary",
                        {e.rel: {"references": e.references,
                                 "changed": e.changed}
                         for e in identity_edits})

            # 15-16. Validate in a disposable full copy, then require zero
            # failures, errors, xfails, xpasses AND skips.
            copy_root = work / "validation_copy"
            _copy_repository(root, copy_root)
            Transaction(copy_root, contract).apply(
                [Edit(e.rel, (copy_root / e.rel).read_bytes(), e.updated,
                      e.counts, e.changed)
                 for e in identity_edits + ccby_edits])
            report.note("isolation_diagnostics",
                        isolation_diagnostics(copy_root, python_exe))
            summary = run_validation(
                copy_root, python_exe,
                {"SCORCH_DATA_ARCHIVE": str(final_path),
                 "SCORCH_REQUIRE_ARCHIVE": "1",
                 "SCORCH_FINAL_DOCX_DIR": str(
                     final_docx_dir
                     or os.environ.get("SCORCH_FINAL_DOCX_DIR", "")),
                 "SCORCH_APTOS_FONT": str(
                     aptos_font or os.environ.get("SCORCH_APTOS_FONT", ""))},
                work / "pytest_summary.json")
            report.note("validation", summary)
            for key in ("failed", "errors", "xfailed", "xpassed", "skipped"):
                if summary.get(key, 1):
                    raise FinalizerError(
                        "VALIDATION_RUN_FAILED",
                        f"release acceptance requires zero {key}; the "
                        f"disposable run reported {summary.get(key)}")
            if summary.get("exit_code", 1) != 0:
                raise FinalizerError(
                    "VALIDATION_RUN_FAILED",
                    f"pytest exited {summary.get('exit_code')}")

            # 17. Only now does anything in the real tree change.
            transaction.apply(identity_edits + ccby_edits)
            destination = root.parent / final_name
            shutil.copy2(final_path, destination)
            if sha256_file(destination) != new["archive_sha256"]:
                raise FinalizerError(
                    "BYTES_MUTATED_AFTER_HASHING",
                    f"{destination} does not match the identity just written")
            report.note("final_archive_written", str(destination))
    except FinalizerError as exc:
        transaction.rollback()
        return report.fail(exc.code, exc.why)
    except BaseException as exc:                       # noqa: BLE001
        transaction.rollback()
        return report.fail("TRANSACTION_ROLLED_BACK", repr(exc))

    return report


def _assert_sidecar_members_unchanged(root, contract, new):
    """The 21 relocated members must be byte-identical after the rebuild.

    Their per-member hashes are pinned in the sidecar and are NOT part of the
    56-reference identity update. A rebuild that changed them would leave the
    sidecar quietly wrong.
    """
    rows = list(csv.DictReader(io.StringIO(
        (Path(root) / "docs/RELOCATED_ARTIFACTS.csv")
        .read_text(encoding="utf-8"))))
    if len(rows) != contract["archive_topology"]["relocation_rows"]:
        raise FinalizerError(
            "SIDECAR_ROW_COUNT",
            f"{len(rows)} sidecar rows, expected "
            f"{contract['archive_topology']['relocation_rows']}")
    drift = []
    for row in rows:
        member = row["archive_member_path"]
        got = new["member_hashes"].get(member)
        if got is None:
            drift.append(f"{member} absent from the rebuilt archive")
        elif got != row["member_sha256"]:
            drift.append(f"{member} {got} != sidecar {row['member_sha256']}")
    if drift:
        raise FinalizerError("SIDECAR_MEMBER_DRIFT", "; ".join(drift[:5]))


def _copy_repository(src, dest):
    """A real git checkout that retains gitignored artifacts.

    A ``git archive`` extract is not good enough: it has no ``.git`` (so the
    ``git ls-files`` guards fail outright) and no ``publication_outputs/``
    (so extra tests skip rather than run).
    """
    shutil.copytree(src, dest,
                    ignore=shutil.ignore_patterns(*COPY_EXCLUDE),
                    symlinks=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser():
    parser = argparse.ArgumentParser(
        prog="release_finalizer",
        description="SCORCH post-D6 release finalizer (preflight / finalize)")
    sub = parser.add_subparsers(dest="mode", required=True)

    def common(p):
        p.add_argument("--repo-root", required=True)
        p.add_argument("--expect-branch", required=True)
        p.add_argument("--expect-head", required=True)
        p.add_argument("--contract", default=str(DEFAULT_CONTRACT))
        p.add_argument("--candidate-archive")
        p.add_argument("--final-docx-dir")
        p.add_argument("--aptos-font")
        p.add_argument("--format", choices=("text", "json", "both"),
                       default="both")

    common(sub.add_parser("preflight",
                          help="read-only verification; writes nothing"))
    fin = sub.add_parser("finalize", help="gated, transactional finalization")
    common(fin)
    fin.add_argument("--stage-dir", required=True)
    fin.add_argument("--python", dest="python_exe", default=sys.executable)
    fin.add_argument("--confirm", default=None)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    contract = load_contract(args.contract)
    common = dict(contract=contract,
                  candidate_archive=args.candidate_archive,
                  final_docx_dir=args.final_docx_dir,
                  aptos_font=args.aptos_font)
    if args.mode == "preflight":
        report = preflight(args.repo_root, args.expect_branch,
                           args.expect_head, **common)
    else:
        report = finalize(args.repo_root, args.expect_branch,
                          args.expect_head, stage_dir=args.stage_dir,
                          python_exe=args.python_exe, confirm=args.confirm,
                          **common)
    if args.format in ("text", "both"):
        print(report.to_text())
    if args.format in ("json", "both"):
        print(report.to_json())
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
