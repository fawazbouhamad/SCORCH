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

# Set BEFORE any import that could materialize a cache. preflight claims to
# change nothing on disk, and a __pycache__ directory created as a side effect
# of importing would falsify that claim. This governs every import below,
# including the deposit package. It cannot govern the import of THIS module by
# a caller - that decision is made before this line runs - so the tests set the
# same flag before importing it, and the CLI runs as a script, never cached.
sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
DEFAULT_CONTRACT = HERE / "finalizer_contract.json"

#: The ONLY contract path production reads, relative to the repository root.
#: There is no CLI override; see load_trusted_contract.
TRACKED_CONTRACT_REL = "scripts/release/finalizer_contract.json"

_DEPOSIT_DIR = HERE.parent / "deposit"
if str(_DEPOSIT_DIR) not in sys.path:
    sys.path.insert(0, str(_DEPOSIT_DIR))

import artwork_licence_state as _artwork  # noqa: E402  (same directory)

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


class RollbackError(FinalizerError):
    """The restore itself failed. The tree may be partially written.

    This is the one failure that cannot be reported as a clean refusal: a
    caller that swallowed it would tell the operator nothing was written while
    the working tree was half-updated.
    """

    def __init__(self, failures):
        self.failures = list(failures)
        super().__init__(
            "ROLLBACK_FAILED",
            f"{len(self.failures)} file(s) could not be restored: "
            f"{self.failures[:5]}")


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


def _reject_duplicate_keys(pairs):
    """``object_pairs_hook`` that refuses duplicate keys.

    ``json.loads`` silently keeps the LAST value for a repeated key. A licence
    record that ended up with two ``"license"`` keys would parse cleanly and
    report whichever one happened to come second, so a duplicate is treated as
    corruption rather than as a style question.
    """
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"duplicate key {key!r}")
        seen[key] = value
    return seen


def loads_strict(text):
    """Parse JSON, rejecting duplicate keys anywhere in the document."""
    return json.loads(text, object_pairs_hook=_reject_duplicate_keys)


def load_contract(path=None) -> dict:
    """Read a contract from an explicit path. NOT a production entry point.

    Production uses :func:`load_trusted_contract`. This exists so unit tests
    can load the shipped contract directly, which is a Python call rather than
    an operator-facing surface.
    """
    return loads_strict(Path(path or DEFAULT_CONTRACT)
                        .read_text(encoding="utf-8"))


def load_trusted_contract(repo_root):
    """Load the contract production is allowed to trust, or refuse.

    The contract decides who may authorize the release, what text counts as
    authorization, which assets the licence reaches and what the activation may
    touch. If an operator could pass ``--contract other.json``, every one of
    those could be redefined from outside the repository, and the D6 gate would
    be decoration. So production reads exactly one path - the tracked contract
    inside the verified worktree - and requires:

    * the path resolves inside the repository to exactly TRACKED_CONTRACT_REL
      (no symlink, no ``..`` escape);
    * git tracks it;
    * its bytes on disk equal the blob at HEAD.

    Returns ``(contract, identity)``. Raises FinalizerError on any mismatch.
    """
    root = Path(repo_root).resolve()
    path = (root / TRACKED_CONTRACT_REL)
    resolved = path.resolve()
    try:
        rel = resolved.relative_to(root).as_posix()
    except ValueError:
        raise FinalizerError(
            "CONTRACT_PATH_ESCAPE",
            f"{resolved} resolves outside the repository root {root}")
    if rel != TRACKED_CONTRACT_REL:
        raise FinalizerError(
            "CONTRACT_PATH_ESCAPE",
            f"{TRACKED_CONTRACT_REL} resolves to {rel}; a link or redirect is "
            f"not the tracked contract")
    if not resolved.is_file():
        raise FinalizerError("CONTRACT_MISSING", f"{resolved} is not a file")

    tracked = git(root, "ls-files", "--error-unmatch", TRACKED_CONTRACT_REL,
                  check=False)
    if not tracked:
        raise FinalizerError(
            "CONTRACT_UNTRACKED",
            f"{TRACKED_CONTRACT_REL} is not tracked by git; an untracked "
            f"contract is an external contract")

    disk = resolved.read_bytes()
    proc = subprocess.run(
        ["git", "-C", str(root), "cat-file", "blob",
         f"HEAD:{TRACKED_CONTRACT_REL}"], capture_output=True,
        env=_git_env())
    if proc.returncode != 0:
        raise FinalizerError(
            "CONTRACT_NOT_AT_HEAD",
            f"cannot read HEAD:{TRACKED_CONTRACT_REL}: "
            f"{proc.stderr.decode('utf-8', 'replace').strip()[:200]}")
    blob = proc.stdout
    identity = {
        "path": TRACKED_CONTRACT_REL,
        "disk_sha256": sha256_bytes(disk),
        "disk_bytes": len(disk),
        "head_blob_sha256": sha256_bytes(blob),
        "head_blob_bytes": len(blob),
        "head_blob_id": git(root, "rev-parse", f"HEAD:{TRACKED_CONTRACT_REL}",
                            check=False),
    }
    if disk != blob:
        raise FinalizerError(
            "CONTRACT_NOT_AT_HEAD",
            f"{TRACKED_CONTRACT_REL} on disk ({identity['disk_sha256']}, "
            f"{len(disk)} B) differs from the blob at HEAD "
            f"({identity['head_blob_sha256']}, {len(blob)} B); production runs "
            f"only against a committed contract")
    try:
        contract = loads_strict(disk.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise FinalizerError("CONTRACT_UNPARSABLE",
                             f"{TRACKED_CONTRACT_REL}: {exc}")
    # THE production contract, by definition: tracked, committed, and
    # byte-equal to the blob at the expected head. TEST-ONLY wording
    # reaching here would mean the repository was about to assert a
    # copyright licence over a coauthor's artwork in prose whose own
    # text says it is not real.
    for code, why in _artwork.synthetic_wording_issues(contract):
        raise FinalizerError(code, why)
    return contract, identity


def git(repo_root, *args, check=True):
    """Run one git command under the SANITIZED environment.

    Every ``rev-parse``, ``status``, ``ls-files``, ``cat-file`` and ``clone``
    this module issues goes through here or through ``_git_capture``, so an
    ambient ``GIT_DIR`` cannot make the finalizer describe a repository the
    operator did not name. See ``_git_env``.
    """
    proc = subprocess.run(["git", "-C", str(repo_root), *args],
                          capture_output=True, text=True,
                          env=_git_env())
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
#: The ONLY host the authorization may come from. ``gh`` resolves a default
#: host from ``GH_HOST`` and from its own config, so an ambient enterprise host
#: could otherwise answer the authorization query - with a body its operator
#: controls. The host is passed explicitly and the ambient variables that could
#: redirect it are removed from the child environment.
GITHUB_HOST = "github.com"


class GitHubCLI:
    """Live GitHub API access through the authenticated ``gh`` CLI."""

    def _api(self, endpoint, paginate=False):
        env = dict(os.environ)
        for drop in ("GH_HOST", "GH_ENTERPRISE_TOKEN", "GH_REPO",
                     "GITHUB_API_URL", "GH_CONFIG_DIR"):
            env.pop(drop, None)
        argv = ["gh", "api", "--hostname", GITHUB_HOST]
        if paginate:
            # --paginate with --slurp so every page is returned as ONE JSON
            # array. Without it a pull request with more than 100 comments
            # returns only the first page - and a revocation posted after the
            # grant is exactly the comment that lands on a later one.
            argv += ["--paginate", "--slurp"]
        argv.append(endpoint)
        proc = subprocess.run(argv, capture_output=True, text=True, env=env)
        if proc.returncode != 0:
            raise FinalizerError(
                "GITHUB_API_UNAVAILABLE",
                f"gh api {endpoint} failed: {proc.stderr.strip()[:300]}")
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise FinalizerError("GITHUB_API_UNAVAILABLE",
                                 f"gh api {endpoint}: bad JSON: {exc}")
        if paginate and payload and isinstance(payload[0], list):
            # --slurp yields a list OF PAGES; flatten to a single sequence.
            return [item for page in payload for item in page]
        return payload

    def pull_request(self, owner, repo, number):
        return self._api(f"repos/{owner}/{repo}/pulls/{number}")

    def issue_comments(self, owner, repo, number):
        return self._api(
            f"repos/{owner}/{repo}/issues/{number}/comments?per_page=100",
            paginate=True)

    def issue_comment(self, owner, repo, comment_id):
        return self._api(
            f"repos/{owner}/{repo}/issues/comments/{comment_id}")


def parse_comment_time(value):
    """A comment timestamp, or None. Shared with the receipt validator."""
    return _artwork.parse_timestamp(value)


def _authorization_target_issue(live, owner, name, number,
                                contract_issue_url=None):
    """Confirm the comment is a top-level issue comment on the right PR.

    Returns ``(code, why)`` or ``(None, None)``. A review comment, a comment on
    another pull request, and a comment in a fork are all different objects
    that can carry identical text.
    """
    from urllib.parse import urlparse

    if live.get("pull_request_review_id") is not None:
        return ("AUTHZ_WRONG_TARGET",
                f"comment {live.get('id')} is a pull request REVIEW comment, "
                f"not the contracted top-level issue comment")

    # Parsed, not substring-matched. "https://evil.example/fawazbouhamad/
    # SCORCH/pull/1#issuecomment-1" contains every expected token and is not
    # this repository; only the HOST decides whose comment this is.
    url = str(live.get("html_url", ""))
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return ("AUTHZ_WRONG_TARGET", f"permalink {url!r} is not HTTPS")
    if parsed.netloc.lower() != GITHUB_HOST:
        return ("AUTHZ_WRONG_TARGET",
                f"permalink host {parsed.netloc!r} is not {GITHUB_HOST}; a "
                f"foreign host whose path mentions {owner}/{name} is not "
                f"{owner}/{name}")
    if parsed.path != f"/{owner}/{name}/pull/{number}":
        return ("AUTHZ_WRONG_TARGET",
                f"permalink path {parsed.path!r} is not "
                f"/{owner}/{name}/pull/{number}")
    want_fragment = f"issuecomment-{live.get('id')}"
    if parsed.fragment != want_fragment:
        return ("AUTHZ_WRONG_TARGET",
                f"permalink fragment {parsed.fragment!r} is not exactly "
                f"{want_fragment!r}; the permalink names a different comment "
                f"from the one being read")

    # EXACT, not endswith. "https://evil.example/x/repos/owner/name/issues/1"
    # ends with the expected path and is not the GitHub API.
    issue_url = str(live.get("issue_url", ""))
    want_issue = (contract_issue_url
                  or f"https://api.github.com/repos/{owner}/{name}"
                     f"/issues/{number}")
    if not issue_url:
        return ("AUTHZ_WRONG_TARGET",
                f"comment {live.get('id')} carries no issue_url; a top-level "
                f"issue comment always does")
    if issue_url != want_issue:
        return ("AUTHZ_WRONG_TARGET",
                f"issue_url {issue_url!r} is not exactly {want_issue!r}")
    return (None, None)


def find_authorization(github, contract):
    """Locate and validate the D6 authorization comment. Never guesses.

    Returns ``(record, issues)``. ``record`` is None unless a live top-level
    issue comment on the contracted pull request, authored by the contracted
    login, carries EXACTLY the authorization text.

    Exact equality, not containment. Containment reads

        "<the exact paragraph> However, I revoke this authorization."

    as a grant, because the required text is genuinely a substring of it. So
    is a comment that quotes the paragraph in order to reject it, and one that
    prefixes it with "do not act on this yet". Only whitespace is normalized -
    a comment box may wrap the paragraph anywhere - and nothing else is.

    The comment is then fetched live TWICE by id and checked for exact equality
    on both reads, and the two reads must agree with each other: a comment
    edited or deleted between them authorizes nothing.
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

    # SUPERSESSION, by the author's LATEST ACTIVITY - not by creation order.
    #
    # Ordering on `created_at` alone reads the timeline as if comments were
    # immutable. They are not. An author can EDIT a comment posted before the
    # grant, turning it into a revocation or a qualification, and that edit
    # lands with an OLD created_at and a NEW updated_at. Under creation
    # ordering the grant was still "latest", the revocation sat quietly in the
    # past, and the release proceeded against the author's current position.
    #
    # A comment's activity time is therefore max(created_at, updated_at): the
    # last moment the author did something to it. Ties break on comment id,
    # which is monotonic and gives a total, deterministic order - equal
    # timestamps can never make the outcome depend on the order the API
    # happened to return the page in.
    unparsable = []

    def _activity(comment):
        created = parse_comment_time(comment.get("created_at"))
        updated = parse_comment_time(comment.get("updated_at"))
        stamps = [s for s in (created, updated) if s is not None]
        if created is None or updated is None:
            unparsable.append(
                f"comment {comment.get('id')} carries created_at="
                f"{comment.get('created_at')!r} updated_at="
                f"{comment.get('updated_at')!r}")
        return max(stamps) if stamps else None

    def _ordering_key(comment):
        stamp = _activity(comment)
        return (stamp is not None, stamp, int(comment.get("id") or 0))

    ordered = sorted(by_author, key=_ordering_key)
    if unparsable:
        # CONSERVATIVE. If any of the author's comments carries a timestamp
        # that cannot be parsed, the activity order cannot be established, and
        # an unorderable timeline is refused rather than guessed at.
        issues.append((
            "AUTHZ_TIMESTAMP_UNPARSABLE",
            f"{want_login} has comment(s) whose timestamps are not real "
            f"ISO-8601 UTC instants, so the order of their activity cannot be "
            f"established and a later revocation could not be detected: "
            f"{sorted(set(unparsable))[:3]}"))
        return None, issues

    latest = ordered[-1]
    if normalize_prose(str(latest.get("body", ""))) != want_text:
        exact = [c for c in ordered
                 if normalize_prose(str(c.get("body", ""))) == want_text]
        if exact:
            issues.append((
                "AUTHZ_SUPERSEDED_OR_QUALIFIED",
                f"{want_login} posted the exact authorization in comment "
                f"{exact[-1].get('id')} but their latest activity is comment "
                f"{latest.get('id')} (created {latest.get('created_at')}, last "
                f"edited {latest.get('updated_at')}), which is not the "
                f"authorization text; a grant followed - or preceded and then "
                f"EDITED INTO - a revocation or qualification by the same "
                f"author is not authorization"))
        else:
            issues.append((
                "AUTHZ_BODY_ALTERED",
                f"{want_login} has commented on #{number} but their latest "
                f"activity is not EXACTLY the authorization text; an altered, "
                f"truncated, prefixed, qualified or revoked body is not "
                f"authorization"))
        return None, issues

    chosen = latest

    # Belt and braces: NOTHING by this author may have activity at or after the
    # grant's own except the grant itself. The ordering above already implies
    # it, but stating it separately means a future change to the ordering key
    # cannot quietly reintroduce the defect.
    chosen_key = _ordering_key(chosen)
    later = [c for c in by_author
             if _ordering_key(c) >= chosen_key and c.get("id") != chosen.get("id")]
    if later:
        issues.append((
            "AUTHZ_SUPERSEDED_OR_QUALIFIED",
            f"{want_login} has activity at or after the grant in comment(s) "
            f"{[c.get('id') for c in later][:3]} that is not the exact "
            f"authorization text"))
        return None, issues

    # Two independent live re-fetches by id. The listing may be stale, and a
    # comment edited or deleted between the reads must not authorize anything.
    reads = []
    for _ in range(int(contract["authorization"].get(
            "live_fetches_required", 2))):
        live = github.issue_comment(owner, name, chosen["id"])
        live_login = str((live.get("user") or {}).get("login", ""))
        if live_login.lower() != want_login.lower():
            issues.append(("AUTHZ_WRONG_AUTHOR",
                           f"comment {chosen['id']} is authored by "
                           f"{live_login!r}, not {want_login!r}"))
            return None, issues
        if normalize_prose(str(live.get("body", ""))) != want_text:
            issues.append(("AUTHZ_BODY_ALTERED",
                           f"comment {chosen['id']} is not EXACTLY the "
                           f"authorization text on re-fetch"))
            return None, issues
        code, why = _authorization_target_issue(
            live, owner, name, number,
            contract["authorization"].get("expected_issue_url"))
        if code:
            issues.append((code, why))
            return None, issues
        reads.append(live)

    agreement = contract["authorization"].get(
        "cross_read_agreement_fields") or ["id", "body", "updated_at",
                                           "html_url"]
    for field in agreement:
        if len({json.dumps(r.get(field), sort_keys=True, default=str)
                for r in reads}) != 1:
            issues.append(("AUTHZ_MUTATED_DURING_READ",
                           f"comment {chosen['id']} changed field {field!r} "
                           f"between two live reads; it is being edited and "
                           f"cannot be relied on"))
            return None, issues

    live = reads[-1]
    live_login = str((live.get("user") or {}).get("login", ""))
    live_body = str(live.get("body", ""))
    url = str(live.get("html_url", ""))

    record = {
        "comment_id": live["id"],
        "permalink": url,
        "login": live_login,
        "created_at": live.get("created_at"),
        "updated_at": live.get("updated_at"),
        "body": live_body,
        "body_sha256": sha256_bytes(live_body.encode("utf-8")),
        "issue_url": str(live.get("issue_url", "")),
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
    """Structure, self-coverage, member arithmetic and NetCDF contract.

    Every defect is aggregated into a code. A missing or corrupt ZIP, a missing
    SHA256SUMS or FILE_MANIFEST.csv and an unreadable manifest are ordinary
    reportable states, not tracebacks: this runs against artifacts that may be
    half-built, and an uncaught BadZipFile mid-finalization tells the operator
    nothing about what else was wrong.
    """
    topo = contract["archive_topology"]
    issues = []
    path = Path(path)
    if not path.is_file():
        return [("ARCHIVE_MISSING", f"{path} is not a file")]

    structural = archive_structure_issues(path, topo["member_count"])
    detail = dict(getattr(structural, "detail", {}))
    want_nc = int(topo.get("expected_netcdf_members", 1))
    for code in structural:
        if code == "ARCHIVE_NETCDF_MEMBER_COUNT" and want_nc != 1:
            # deposit_contract is shared with the deposit builder and hard-codes
            # the real deposit's single canonical NetCDF member. Where THIS
            # contract declares a different count - only a synthetic deposit
            # does; the real contract declares 1 - the contract is authoritative
            # and the same condition is re-checked below against want_nc, so
            # nothing goes unchecked.
            continue
        issues.append((code, detail.get(code, "")))

    try:
        with zipfile.ZipFile(path) as zf:
            members = sorted({i.filename for i in zf.infolist()
                              if not i.is_dir()})
            for key, label, expected in (
                    ("sums_member", "SUMS_ENTRY_COUNT", topo["sums_entries"]),
                    ("manifest_member", "MANIFEST_ROW_COUNT",
                     topo["manifest_rows"])):
                member = topo[key]
                if member not in members:
                    issues.append((f"ARCHIVE_{key.upper()}_ABSENT",
                                   f"{member} is not a member"))
                    continue
                try:
                    raw = zf.read(member).decode("utf-8")
                except (KeyError, UnicodeDecodeError, zipfile.BadZipFile,
                        OSError, RuntimeError) as exc:
                    issues.append((f"ARCHIVE_{key.upper()}_UNREADABLE",
                                   f"{member}: {exc}"))
                    continue
                if key == "sums_member":
                    count = len([ln for ln in raw.splitlines() if ln.strip()])
                else:
                    try:
                        count = len(list(csv.DictReader(io.StringIO(raw))))
                    except csv.Error as exc:
                        issues.append(("ARCHIVE_MANIFEST_MEMBER_UNREADABLE",
                                       f"{member}: {exc}"))
                        continue
                if count != expected:
                    issues.append((label, f"{count}, expected {expected}"))
            for key in ("validator_member", "licence_member"):
                member = topo.get(key)
                if member and member not in members:
                    issues.append((
                        "DEPOSIT_VALIDATOR_ABSENT" if key == "validator_member"
                        else "ARCHIVE_LICENCE_MEMBER_ABSENT",
                        f"{member} is not a member"))
    except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
        issues.append(("ARCHIVE_UNREADABLE", f"{path}: {exc}"))
        return issues

    # How many canonical NetCDF members the deposit must carry. Contract-
    # driven rather than hard-coded so a synthetic deposit can declare zero;
    # the real contract declares one and is checked exactly as before.
    want_nc = int(topo.get("expected_netcdf_members", 1))
    nc = canonical_netcdf_members(path)
    if len(nc) != want_nc:
        issues.append(("ARCHIVE_NETCDF_MEMBER_COUNT",
                       f"expected {want_nc} canonical NetCDF member(s), "
                       f"found {len(nc)}"))
    elif want_nc:
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


#: Marker distinguishing the archive's own LICENSE.txt from a tracked file in
#: an activation plan. The archive member is not a repository path, and the two
#: must not be confused when scope is being checked.
ARCHIVE_FILE_PREFIX = "archive:"


def verify_superseded_archive(repo_root, contract):
    """The superseded official archive must be present and byte-identical.

    It is the archive the tracked records currently point at, and it shares its
    FILENAME with the archive being released. Nothing about a finalization is
    allowed to consume it: not a build, not a placement, and above all not the
    move-aside/delete that a same-named destination would trigger.
    """
    spec = contract.get("superseded_official_archive") or {}
    rel = spec.get("path")
    if not rel:
        return [("SUPERSEDED_ARCHIVE_UNPINNED",
                 "the contract does not pin the superseded archive's path")]
    path = Path(repo_root) / rel
    if not path.is_file():
        return [("SUPERSEDED_ARCHIVE_MISSING", f"{rel} is not a file")]
    issues = []
    size = path.stat().st_size
    if size != spec["bytes"]:
        issues.append(("SUPERSEDED_ARCHIVE_MODIFIED",
                       f"{rel} is {size} B, pinned {spec['bytes']}"))
    got = sha256_file(path)
    if got != spec["sha256"]:
        issues.append(("SUPERSEDED_ARCHIVE_MODIFIED",
                       f"{rel} hashes {got}, pinned {spec['sha256']}"))
    return issues


def assert_destination_does_not_collide(repo_root, contract, destination):
    """The release destination must not be the superseded archive's path.

    The released archive is called ``scorch_processed_data_v1.0.0.zip`` and so
    is the superseded one. Writing the new archive into the directory holding
    the old one therefore overwrites - and, on the move-aside path, DELETES -
    the artifact the repository still points at. The operator must supply a
    different destination.
    """
    spec = contract.get("superseded_official_archive") or {}
    rel = spec.get("path")
    if not rel:
        return
    old = (Path(repo_root) / rel).resolve()
    new = Path(destination).resolve()
    if old == new:
        raise FinalizerError(
            "RELEASE_DESTINATION_COLLIDES_WITH_SUPERSEDED",
            f"the release destination {new} is the superseded official "
            f"archive itself. The released archive shares its filename, so "
            f"this would destroy the artifact the tracked records still point "
            f"at. Supply a --release-staging directory that does not contain "
            f"{Path(rel).name}.")


def verify_technical_source(path, contract):
    """Confirm the candidate really is the pinned pre-D6 technical source.

    It is a LOCAL, UNPUBLISHED, PRE-D6 working artifact and nothing else. It is
    not the released identity - that is recomputed from the final bytes after
    the licence transition and the rebuild - and it is not evidence of
    publication or deposit.
    """
    spec = contract["technical_source_candidate"]
    path = Path(path)
    issues = []
    if not path.is_file():
        return [("TECHNICAL_SOURCE_MISSING", f"{path} is not a file")]
    if path.name != spec["filename"]:
        issues.append(("TECHNICAL_SOURCE_MISMATCH",
                       f"{path.name!r} is not the pinned technical source "
                       f"{spec['filename']!r}"))
    size = path.stat().st_size
    if size != spec["bytes"]:
        issues.append(("TECHNICAL_SOURCE_MISMATCH",
                       f"{size} bytes, pinned {spec['bytes']}"))
    got = sha256_file(path)
    if got != spec["sha256"]:
        issues.append(("TECHNICAL_SOURCE_MISMATCH",
                       f"sha256 {got} != pinned {spec['sha256']}"))
        return issues
    try:
        ident = archive_identity(path)
    except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
        return issues + [("TECHNICAL_SOURCE_UNREADABLE", f"{path}: {exc}")]
    if ident["content_root_hash"] != spec["content_root_hash"]:
        issues.append(("TECHNICAL_SOURCE_MISMATCH",
                       f"content root {ident['content_root_hash']} != pinned "
                       f"{spec['content_root_hash']}"))
    topo = spec["topology"]
    if ident["member_count"] != topo["member_count"]:
        issues.append(("TECHNICAL_SOURCE_MISMATCH",
                       f"{ident['member_count']} members, pinned "
                       f"{topo['member_count']}"))
    return issues


#: The ONLY members a licence activation may change. Everything else in the
#: rebuilt archive must be byte-identical to the verified technical source.
AUTHORIZED_MEMBER_CHANGES = ("LICENSE.txt", "FILE_MANIFEST.csv", "SHA256SUMS")


def extract_archive(path, dest):
    """Extract every member, refusing any path that escapes ``dest``.

    Containment is decided by ``Path.relative_to``, not by a string prefix. A
    prefix test says ``/tmp/extract-evil`` is inside ``/tmp/extract`` because
    the characters line up, which is exactly the sibling-directory traversal
    an attacker-supplied member name would use.
    """
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename
            if name.startswith("/") or name.startswith("\\") or \
                    (len(name) > 1 and name[1] == ":"):
                raise FinalizerError(
                    "ARCHIVE_MEMBER_PATH_ESCAPE",
                    f"member {name!r} is an absolute path")
            target = (dest / name).resolve()
            try:
                target.relative_to(root)
            except ValueError:
                raise FinalizerError(
                    "ARCHIVE_MEMBER_PATH_ESCAPE",
                    f"member {name!r} resolves to {target}, outside the "
                    f"extraction root {root}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
    return dest


def _assert_no_unauthorized_member_drift(final_path, source_path, contract):
    """Every member must match the verified source except the three allowed.

    A licence activation changes LICENSE.txt, and regenerating the manifests
    changes FILE_MANIFEST.csv and SHA256SUMS. Nothing else has any business
    differing: if a payload file changed, something other than the licence
    transition edited the deposit, and that must not ship.
    """
    allowed = set(AUTHORIZED_MEMBER_CHANGES)
    with zipfile.ZipFile(source_path) as zf:
        source = {i.filename: sha256_bytes(zf.read(i.filename))
                  for i in zf.infolist() if not i.is_dir()}
    with zipfile.ZipFile(final_path) as zf:
        final = {i.filename: sha256_bytes(zf.read(i.filename))
                 for i in zf.infolist() if not i.is_dir()}

    added = sorted(set(final) - set(source))
    removed = sorted(set(source) - set(final))
    changed = sorted(m for m in set(final) & set(source)
                     if final[m] != source[m] and m not in allowed)
    unchanged_but_expected = sorted(
        m for m in allowed & set(final) & set(source)
        if final[m] == source[m])

    problems = []
    if added:
        problems.append(f"members added: {added[:5]}")
    if removed:
        problems.append(f"members removed: {removed[:5]}")
    if changed:
        problems.append(f"unauthorized member changes: {changed[:5]}")
    if problems:
        raise FinalizerError("ARCHIVE_MEMBER_DRIFT", "; ".join(problems))
    return {"authorized_changes": sorted(allowed & set(final)),
            "unchanged_authorized_members": unchanged_but_expected,
            "members_compared": len(final)}


def apply_archive_licence_transition(stage_root, contract, transition):
    """Rewrite the archive's own LICENSE.txt with the authored from/to pair.

    The archive carries its own licence notice. Activating CC BY in the four
    tracked records while the shipped deposit still says PENDING would publish
    a contradiction, so the archive member transitions with them or not at all.
    """
    member = contract["archive_topology"]["licence_member"]
    path = Path(stage_root) / member
    if not path.is_file():
        raise FinalizerError("ARCHIVE_LICENCE_MEMBER_ABSENT",
                             f"{member} is not present in the staged archive")
    original = path.read_bytes()
    src = transition["from"].encode("utf-8")
    dst = transition["to"].encode("utf-8")
    found = original.count(src)
    if found != int(transition["count"]):
        raise FinalizerError(
            "CCBY_ACTIVATION_COUNT",
            f"{member}: activation source occurs {found} time(s), plan "
            f"declares {transition['count']}")
    updated = original.replace(src, dst)
    _assert_third_party_rights_preserved(member, original, updated, contract)
    path.write_bytes(updated)
    return {"member": member, "before_sha256": sha256_bytes(original),
            "after_sha256": sha256_bytes(updated), "occurrences": found}


def regenerate_archive_manifests(stage_root, contract):
    """Rebuild FILE_MANIFEST.csv and SHA256SUMS from the staged tree.

    The licence transition changed a member's bytes, so every digest that
    covers it is now stale. Regenerating is the only honest option: editing the
    old sums to match would be asserting a hash rather than computing one.
    """
    stage_root = Path(stage_root)
    deposit_dir = str(_DEPOSIT_DIR)
    if deposit_dir not in sys.path:
        sys.path.insert(0, deposit_dir)
    import rebuild_processed_deposit_manifests as rebuilder

    try:
        rebuilder.rebuild(stage_root)
    except SystemExit as exc:
        # The rebuilder reports coverage failures with sys.exit(), which is a
        # BaseException and would otherwise sail past an ordinary handler and
        # abort finalization without the transactional restore running.
        raise FinalizerError("MANIFEST_REBUILD_FAILED",
                             f"manifest rebuild refused: {exc}")
    except Exception as exc:                       # noqa: BLE001 - reported
        raise FinalizerError("MANIFEST_REBUILD_FAILED", repr(exc))

    topo = contract["archive_topology"]
    manifest = stage_root / topo["manifest_member"]
    sums = stage_root / topo["sums_member"]
    for path in (manifest, sums):
        if not path.is_file():
            raise FinalizerError("MANIFEST_REBUILD_FAILED",
                                 f"{path.name} was not regenerated")
    rows = list(csv.DictReader(io.StringIO(
        manifest.read_text(encoding="utf-8"))))
    entries = [ln for ln in sums.read_text(encoding="utf-8").splitlines()
               if ln.strip()]
    members = [p for p in stage_root.rglob("*") if p.is_file()]
    counts = {"manifest_rows": len(rows), "sums_entries": len(entries),
              "member_count": len(members)}
    for key in ("manifest_rows", "sums_entries", "member_count"):
        if counts[key] != topo[key]:
            raise FinalizerError(
                "ARCHIVE_TOPOLOGY_DRIFT",
                f"after regeneration {key} is {counts[key]}, the contract "
                f"requires exactly {topo[key]}")
    return counts


def run_deposit_validator(stage_root, contract, python_exe=None):
    """Execute the archive's OWN shipped validator and require a clean pass."""
    stage_root = Path(stage_root)
    validator = stage_root / contract["archive_topology"]["validator_member"]
    if not validator.is_file():
        raise FinalizerError("DEPOSIT_VALIDATOR_ABSENT",
                             f"{validator.name} is not in the staged archive")
    # Sanitized exactly as strictly as the pytest validation environment, and
    # by the SAME construction: an isolated HOME and an allow-list, not a
    # three-prefix deny-list. The previous filter removed SCORCH*, PYTEST* and
    # PYTHON* and inherited everything else - GH_TOKEN, GIT_DIR, GIT_INDEX_FILE,
    # COVERAGE_PROCESS_START, XDG_CONFIG_HOME, MPLCONFIGDIR - so the shipped
    # validator ran against the operator's git repository, the operator's API
    # credentials and the operator's coverage instrumentation while reporting
    # on the staged deposit. An ambient PYTHONOPTIMIZE=2 additionally strips
    # `assert` statements, so a validator whose checks are assertions would
    # print its pass verdict having verified nothing.
    env = _hermetic_env(_isolated_home())
    for key in _CLEAR_ALWAYS:
        env.pop(key, None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    proc = subprocess.run([str(python_exe or sys.executable), str(validator)],
                          cwd=str(stage_root), env=env, capture_output=True,
                          text=True)
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    spec = contract["archive_topology"].get("validator_verdict") or {}
    pass_line = spec.get("pass_line", "PASS")
    fail_line = spec.get("fail_line", "FAIL")

    # ANCHORED whole-line verdicts. Counting substrings is not enough: both
    # "BYPASS" and "COMPASS" contain "PASS", so a validator printing either
    # would have read as a pass. The real validator prints "[ok] ..." lines and
    # ends with a bare verdict line, which is what is matched here.
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    verdicts = [ln for ln in lines if ln in (pass_line, fail_line)]

    if proc.returncode != 0:
        raise FinalizerError(
            "DEPOSIT_VALIDATOR_FAILED",
            f"{validator.name} exited {proc.returncode}: {out[-500:]}")
    if fail_line in verdicts:
        raise FinalizerError(
            "DEPOSIT_VALIDATOR_FAILED",
            f"{validator.name} exited 0 but printed a {fail_line} verdict"
            f"{' alongside ' + pass_line if pass_line in verdicts else ''}: "
            f"{out[-500:]}")
    want = int(spec.get("expected_verdict_lines", 1))
    if len(verdicts) != want:
        raise FinalizerError(
            "DEPOSIT_VALIDATOR_AMBIGUOUS",
            f"{validator.name} exited 0 with {len(verdicts)} verdict line(s), "
            f"expected exactly {want}; silence is not a pass and a verdict "
            f"embedded in a longer word is not a verdict: "
            f"{out[-500:] or '<no output>'}")
    if spec.get("must_be_last_non_empty_line", True) and \
            lines[-1] != pass_line:
        raise FinalizerError(
            "DEPOSIT_VALIDATOR_AMBIGUOUS",
            f"{validator.name} did not end with the terminal verdict "
            f"{pass_line!r}; its last non-empty line was {lines[-1]!r}")
    return {"exit_code": proc.returncode, "verdict": pass_line,
            "verdict_lines": len(verdicts), "terminal_line": lines[-1],
            "output_lines": len(lines), "tail": out[-500:]}


def build_release_archive(candidate, contract, work_dir, *,
                          archive_transition=None, python_exe=None):
    """Produce the final archive from the verified technical source.

    The previous implementation zipped whatever directory it was pointed at and
    called two builds from THE SAME staging a determinism proof. It proved the
    writer was deterministic; it proved nothing about the inputs. Here the
    source is the pinned candidate, and the two builds come from two
    INDEPENDENT fresh extractions, so an extraction that is not reproducible
    fails rather than passing unnoticed.
    """
    work = Path(work_dir)
    report = {}

    # 1. Verify the operator's candidate ONCE, then take a private snapshot of
    #    the verified bytes and build only from that. Verifying a path and then
    #    reading it repeatedly is a time-of-check/time-of-use hole: the file can
    #    be replaced between the check and either build.
    for code, why in verify_technical_source(candidate, contract):
        raise FinalizerError(code, why)
    snapshot = work / "verified_source.zip"
    shutil.copy2(candidate, snapshot)
    spec = contract["technical_source_candidate"]
    snapshot_sha_before = sha256_file(snapshot)
    if snapshot_sha_before != spec["sha256"]:
        raise FinalizerError(
            "TECHNICAL_SOURCE_MISMATCH",
            f"the private snapshot hashes {snapshot_sha_before}, the pinned "
            f"technical source is {spec['sha256']}")
    report["verified_source_snapshot"] = {
        "sha256": snapshot_sha_before,
        "bytes": snapshot.stat().st_size,
    }

    built = []
    for index in (1, 2):
        stage = extract_archive(snapshot, work / f"extract-{index}")
        if archive_transition is not None:
            report["archive_licence"] = apply_archive_licence_transition(
                stage, contract, archive_transition)
        report["topology"] = regenerate_archive_manifests(stage, contract)
        if index == 1:
            report["validator"] = run_deposit_validator(stage, contract,
                                                        python_exe)
        built.append(build_deterministic_zip(stage,
                                             work / f"build-{index}.zip"))

    # 2. The snapshot must be unchanged after both builds. If it moved, the two
    #    builds did not have the same input and the determinism check below
    #    would be comparing two different things.
    snapshot_sha_after = sha256_file(snapshot)
    report["verified_source_snapshot"]["sha256_after"] = snapshot_sha_after
    if snapshot_sha_after != snapshot_sha_before:
        raise FinalizerError(
            "TECHNICAL_SOURCE_MUTATED",
            f"the verified source snapshot changed during the build: "
            f"{snapshot_sha_before} -> {snapshot_sha_after}")

    first, second = built
    sha_first, sha_second = sha256_file(first), sha256_file(second)
    report["double_build"] = {"first": sha_first, "second": sha_second}
    if sha_first != sha_second:
        raise FinalizerError(
            "BUILD_NONDETERMINISTIC",
            f"two builds from independent fresh extractions of the verified "
            f"snapshot differ: {sha_first} vs {sha_second}")

    final_name = contract["identity"]["final_archive_filename"]
    final_path = work / final_name
    os.replace(first, final_path)
    for code, why in archive_topology_issues(final_path, contract):
        raise FinalizerError(code, why)

    # 3. Nothing but the three authorized members may differ from the source.
    report["member_drift"] = _assert_no_unauthorized_member_drift(
        final_path, snapshot, contract)
    return final_path, report


# ---------------------------------------------------------------------------
# The identity update: structured, count-checked, never a global replace
# ---------------------------------------------------------------------------
class Edit:
    """One file's complete planned rewrite, with its per-field arithmetic."""

    def __init__(self, rel, original, updated, counts, changed,
                 creates=False):
        self.rel = rel
        self.original = original
        self.updated = updated
        self.counts = counts
        self.changed = changed
        #: True only for an edit that is ALLOWED to bring a new file into
        #: existence - in practice the D6 receipt alone. Every other edit
        #: rewrites a file that must already be there, so a write to a missing
        #: path stays an error rather than silently creating one.
        self.creates = creates

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
        # Strict: json.loads keeps the LAST of a repeated key, so an edit that
        # duplicated "license" in the deposit metadata record would parse
        # cleanly and quietly publish whichever copy came second.
        try:
            before = loads_strict(original.decode("utf-8"))
            after = loads_strict(updated.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
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


#: Bare markers an activation may never use as its whole source block. A plan
#: whose ``from`` is simply "PENDING" would rewrite every unrelated occurrence
#: in the file - acceptance criteria, funding status, anything - so a complete
#: sentence-level block is required instead of a global word replacement.
BARE_MARKERS = {"pending", "not yet in force", "cc by", "cc by 4.0",
                "ccby", "licence", "license", "figure 1", "figure 4",
                "in force", "authorized", "authorised"}

#: An activation source block must be at least this long. A short fragment
#: cannot carry enough context to be the specific claim being retired.
MIN_ACTIVATION_BLOCK = 40


def plan_ccby_activation(repo_root, contract, base=None):
    """TEST-ONLY wording is refused before a plan is even considered."""
    for code, why in _artwork.synthetic_wording_issues(contract):
        raise FinalizerError(code, why)
    return _plan_ccby_activation(repo_root, contract, base)


def _plan_ccby_activation(repo_root, contract, base=None):
    """Plan the CC BY activation, or refuse because nobody authored it.

    Activation rewrites legal prose. The contract carries exact from/to pairs
    written by an author; this function applies them with the same arithmetic
    as the identity update and never invents wording of its own.

    Returns ``(tracked_edits, archive_transition)``. The activation must cover
    ALL FIVE licence surfaces - the four tracked records and the archive's own
    LICENSE.txt - because activating four of them and shipping a deposit that
    still reads PENDING publishes a contradiction.

    ``base`` supplies already-edited bytes for files another planner has
    changed, so a file carrying BOTH the archive identity and the licence
    wording is composed from one original instead of being written twice.
    """
    plan = contract.get("ccby_activation_plan") or {}
    if not plan.get("authored"):
        raise FinalizerError(
            "CCBY_ACTIVATION_PLAN_UNAUTHORED",
            "ccby_activation_plan.authored is false: no author-written "
            "activation wording exists, and this tool will not invent the "
            "licence prose for the Figure 1 / Figure 4 artwork")
    replacements = list(plan.get("replacements") or [])
    if not replacements:
        raise FinalizerError(
            "CCBY_ACTIVATION_PLAN_EMPTY",
            "the activation plan is authored but carries no replacements")

    # An authored plan must come with the markers that let the classifier
    # RECOGNISE what it produced. Without them every rewritten record becomes
    # unclassifiable, the state machine reports LICENCE_STATE_UNREADABLE, and
    # the activation could never be confirmed to have taken effect.
    active_markers = [m for m in
                      ((contract.get("artwork_licence_markers") or {})
                       .get("active") or []) if m]
    if not active_markers:
        raise FinalizerError(
            "CCBY_ACTIVE_MARKERS_MISSING",
            "the activation plan is authored but "
            "artwork_licence_markers.active is empty; the classifier would "
            "not recognise the activated wording, so the new state could "
            "never be verified")

    # Each marker must be a COMPLETE AFFIRMATIVE SCOPED CLAUSE - not a generic
    # token like "CC BY 4.0", which appears in sentences that DENY the grant.
    for marker in active_markers:
        for code, why in _artwork.active_marker_shape_issues(marker):
            raise FinalizerError(code, why)

    # ...and must be ABSENT from every record before activation. A marker that
    # already appears somewhere would make the pre-activation tree classify as
    # ACTIVE, so activation could not be distinguished from doing nothing.
    for rel in contract["licence_records"]:
        path = Path(repo_root) / rel
        if not path.is_file():
            continue
        blocks = _artwork.normalized_blocks(
            path.read_text(encoding="utf-8", errors="replace"))
        for marker in active_markers:
            if _artwork.normalize_prose(marker) in blocks:
                raise FinalizerError(
                    "CCBY_ACTIVE_MARKER_PRE_EXISTING",
                    f"{rel} already contains the active marker {marker!r} "
                    f"before activation; the marker cannot distinguish the "
                    f"activated state from the current one")

    # The active publication row must itself carry a marker block.
    active_row = ((contract.get("publication_outputs_artwork_row") or {})
                  .get("active") or "")
    row_blocks = _artwork.normalized_blocks(active_row)
    if not any(_artwork.normalize_prose(m) in row_blocks
               for m in active_markers):
        raise FinalizerError(
            "CCBY_ACTIVE_MARKER_ABSENT",
            f"publication_outputs_artwork_row.active carries none of the "
            f"active markers {active_markers}; the published row would not "
            f"classify as ACTIVE")

    repo_root = Path(repo_root)
    records = list(contract["licence_records"])
    protected = set(contract["protected_historical_records"])
    archive_member = contract["archive_topology"]["licence_member"]
    archive_key = ARCHIVE_FILE_PREFIX + archive_member
    base = dict(base or {})
    staged = {}
    archive_transition = None
    covered = []

    for item in replacements:
        rel = item["file"]
        src_text, dst_text = item["from"], item["to"]
        if len(src_text) < MIN_ACTIVATION_BLOCK or \
                src_text.strip().lower() in BARE_MARKERS:
            raise FinalizerError(
                "CCBY_ACTIVATION_BLOCK_TOO_BROAD",
                f"{rel}: activation source {src_text[:60]!r} is a bare marker "
                f"or too short; a complete source block is required so that "
                f"activation is not a global word replacement")
        if int(item["count"]) != 1:
            raise FinalizerError(
                "CCBY_ACTIVATION_COUNT",
                f"{rel}: each complete activation source block must occur "
                f"exactly once, plan declares {item['count']}")
        if rel in covered:
            raise FinalizerError(
                "CCBY_ACTIVATION_DUPLICATE_SURFACE",
                f"{rel} has more than one authored transition; each of the "
                f"five licence surfaces must have exactly one")
        dst_blocks = _artwork.normalized_blocks(dst_text)
        if not any(_artwork.normalize_prose(m) in dst_blocks
                   for m in active_markers):
            raise FinalizerError(
                "CCBY_ACTIVE_MARKER_ABSENT",
                f"{rel}: the authored destination block carries none of the "
                f"active markers {active_markers}; the classifier would not "
                f"recognise it as an activated record")
        covered.append(rel)

        if rel == archive_key:
            if archive_transition is not None:
                raise FinalizerError(
                    "CCBY_ACTIVATION_SCOPE",
                    f"{archive_key} has more than one transition")
            archive_transition = dict(item)
            continue

        if rel in protected:
            raise FinalizerError("EDIT_PROTECTED_RECORD",
                                 f"{rel} is a protected historical record")
        if rel not in records:
            raise FinalizerError(
                "CCBY_ACTIVATION_SCOPE",
                f"{rel} is not one of the licence records; activation may not "
                f"touch anything else")
        path = repo_root / rel
        if rel in staged:
            data = staged[rel]
        elif rel in base:
            data = base[rel]
        else:
            data = path.read_bytes()
        src = src_text.encode("utf-8")
        dst = dst_text.encode("utf-8")
        found = data.count(src)
        if found != 1:
            raise FinalizerError(
                "CCBY_ACTIVATION_COUNT",
                f"{rel}: activation source occurs {found} time(s), the "
                f"complete source block must occur exactly once")
        staged[rel] = data.replace(src, dst)

    missing = [r for r in records if r not in covered]
    if missing:
        raise FinalizerError(
            "CCBY_ACTIVATION_PARTIAL",
            f"the activation plan does not cover {missing}; all four tracked "
            f"licence records must transition together")
    if archive_transition is None:
        raise FinalizerError(
            "CCBY_ACTIVATION_PARTIAL",
            f"the activation plan does not cover {archive_key}; the archive's "
            f"own licence notice must transition with the tracked records")

    extra = sorted(set(covered) - set(records) - {archive_key})
    if extra:
        raise FinalizerError(
            "CCBY_ACTIVATION_SCOPE",
            f"the activation plan carries transitions for {extra}, which are "
            f"not licence surfaces")

    edits = []
    for rel, updated in sorted(staged.items()):
        prior = base.get(rel)
        original = prior if prior is not None else (repo_root / rel).read_bytes()
        _assert_third_party_rights_preserved(rel, original, updated, contract)
        _assert_excluded_scope_unchanged(rel, original, updated, contract)
        _assert_structure_preserved(rel, original, updated)
        edits.append(Edit(rel, original, updated,
                          {"ccby_activation": 1}, 1))
    return edits, archive_transition


def _sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+|\n", text) if s.strip()]


def _assert_excluded_scope_unchanged(rel, original, updated, contract):
    """The activation may not extend CC BY over anything but the artwork.

    Preserving third-party rights TOKEN COUNTS proves the activation did not
    delete the Copernicus notice. It does not prove the activation did not
    ADD a CC BY claim over the ERA5 data, the GHCN observations, the pinned
    font or the software - none of which the coauthor's artwork authorization
    covers. So for every excluded category, the number of sentences asserting
    CC BY alongside it must not increase.
    """
    spec = contract.get("ccby_excluded_scope") or {}
    tokens = spec.get("tokens") or []
    if not tokens:
        return
    before = _sentences(original.decode("utf-8", "replace"))
    after = _sentences(updated.decode("utf-8", "replace"))
    for token in tokens:
        was = sum(1 for s in before if token in s and CCBY_RX.search(s))
        now = sum(1 for s in after if token in s and CCBY_RX.search(s))
        if now > was:
            raise FinalizerError(
                "CCBY_SCOPE_WIDENED",
                f"{rel}: activation added {now - was} sentence(s) asserting "
                f"CC BY alongside {token!r}; the authorization covers the "
                f"Figure 1 / Figure 4 artwork and nothing else")


def compose_edits(identity_edits, ccby_edits):
    """Merge the two edit sets so a shared file is written ONCE.

    ``assets/manuscript_final/README.md`` carries both the archive identity and
    the licence wording. Applying two independently-planned rewrites of it in
    sequence silently discards whichever was written first - the identity
    update, as it happens, because the licence edit lands second. The licence
    planner is given the identity planner's output as its base, so the licence
    edit already contains the identity change and simply supersedes it here.
    """
    by_rel = {}
    order = []
    for edit in identity_edits:
        by_rel[edit.rel] = edit
        order.append(edit.rel)
    for edit in ccby_edits:
        if edit.rel in by_rel:
            prior = by_rel[edit.rel]
            merged = Edit(edit.rel, prior.original, edit.updated,
                          {**prior.counts, **edit.counts},
                          prior.changed + edit.changed)
            by_rel[edit.rel] = merged
        else:
            by_rel[edit.rel] = edit
            order.append(edit.rel)
    return [by_rel[rel] for rel in order]


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


# ---------------------------------------------------------------------------
# The licensing state machine
# ---------------------------------------------------------------------------
#: The only two coherent states. Anything else - some records transitioned and
#: some not, an active claim with no receipt, a receipt with pending records -
#: is INCONSISTENT and must never be published.
PENDING = _artwork.PENDING
ACTIVE = _artwork.ACTIVE
INCONSISTENT = _artwork.INCONSISTENT

CCBY_RX = _artwork.CCBY_RX
_artwork_licence_claim = _artwork.classify_claim


def licence_state(repo_root, contract, *, archive_licence_text=None,
                  record=None):
    """Report the artwork licence state across ALL FIVE surfaces.

    Delegates to :mod:`artwork_licence_state`, which the publication builder
    and the repository guards also use. One implementation, so the finalizer,
    the builder and the guards cannot drift into disagreeing about whether the
    artwork is licensed - and so that ACTIVE means a receipt that VALIDATES
    rather than a file that merely exists.
    """
    return _artwork.artwork_licence_state(
        repo_root, contract, archive_licence_text=archive_licence_text,
        record=record)


# ---------------------------------------------------------------------------
# The durable authorization receipt
# ---------------------------------------------------------------------------
def receipt_bytes(receipt) -> bytes:
    """Canonical serialization: sorted keys, one trailing newline."""
    return (json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=False)
            + "\n").encode("utf-8")


def build_authorization_receipt(repo_root, contract, record, *, starting_head,
                                activated_at):
    """Assemble the durable record of the authorization that licensed the art.

    A stdout report is not a receipt. Once CC BY is in force over the Figure 1
    and Figure 4 artwork, the repository has to be able to show WHICH comment,
    by WHICH account, at WHICH time, over WHICH files, licensed it - years
    later, from the tree alone, without the GitHub API and without this tool.
    """
    root = Path(repo_root)
    artwork = {}
    for rel in contract["ccby_artwork_paths"]:
        path = root / rel
        if not path.is_file():
            raise FinalizerError(
                "RECEIPT_ARTWORK_MISSING",
                f"{rel} is licensed by this receipt but is not in the tree")
        artwork[rel] = sha256_file(path)
    repo = contract["repository"]
    return {
        "schema_version": contract["authorization_receipt"]["schema_version"],
        "repository": f"{repo['owner']}/{repo['name']}",
        "pull_request": repo["pull_request"],
        "permalink": record["permalink"],
        "issue_url": record.get("issue_url", ""),
        "comment_id": record["comment_id"],
        "login": record["login"],
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
        "body": record["body"],
        "body_sha256": record["body_sha256"],
        "licensed_artwork": artwork,
        "activated_at": activated_at,
        "finalizer_version": contract["finalizer_version"],
        "starting_head": starting_head,
    }


def validate_authorization_receipt(receipt, contract, record, *,
                                   starting_head, repo_root=None):
    """Aggregate every defect in a receipt. Returns sorted issue tuples.

    Delegates the schema, login, body, timestamp, permalink-host and
    artwork-scope checks to :mod:`artwork_licence_state`, which the builder
    and the guards also use, then adds the two facts only a live finalization
    knows: the starting HEAD it claims, and agreement with the comment fetched
    moments ago.

    Validated in the disposable copy BEFORE the real transaction writes it, so
    a malformed receipt is caught while nothing has been touched.
    """
    root = Path(repo_root) if repo_root is not None else Path(".")
    issues = list(_artwork.validate_receipt(receipt, contract, root,
                                            record=record))
    if isinstance(receipt, dict) and "starting_head" in receipt:
        if receipt["starting_head"] != starting_head:
            issues.append(("RECEIPT_STARTING_HEAD",
                           f"receipt records starting_head "
                           f"{receipt['starting_head']!r}, this run started at "
                           f"{starting_head!r}"))
    return sorted(set(issues))


def _assert_protected_blobs_intact(repo_root, contract):
    """Verify the tracked GIT BLOBS of the protected records, not the checkout.

    Two different identities are in play and must not be conflated. The blob is
    the portable repository fact (LF). The working-tree bytes are whatever the
    platform checked out - CRLF here, because .gitattributes normalizes to LF
    in the repository. A Windows checkout hash is not a portable identity, so
    the contract pins both and this function checks the blob, while the
    transaction snapshots and restores the real current bytes.
    """
    root = Path(repo_root)
    pins = contract.get("protected_historical_record_identities") or {}
    issues = []
    for rel in contract["protected_historical_records"]:
        pin = pins.get(rel)
        if not pin:
            continue
        blob_id = git(root, "rev-parse", f"HEAD:{rel}", check=False)
        if blob_id != pin["git_blob_sha1"]:
            issues.append((
                "PROTECTED_RECORD_BLOB_MOVED",
                f"{rel}: HEAD blob {blob_id or '<absent>'} != pinned "
                f"{pin['git_blob_sha1']}"))
            continue
        proc = subprocess.run(["git", "-C", str(root), "cat-file", "blob",
                               f"HEAD:{rel}"], capture_output=True,
                              env=_git_env())
        blob = proc.stdout
        if sha256_bytes(blob) != pin["git_blob_sha256"]:
            issues.append((
                "PROTECTED_RECORD_BLOB_MOVED",
                f"{rel}: blob sha256 {sha256_bytes(blob)} != pinned "
                f"{pin['git_blob_sha256']}"))
        if len(blob) != pin["git_blob_bytes"]:
            issues.append((
                "PROTECTED_RECORD_BLOB_MOVED",
                f"{rel}: blob is {len(blob)} B, pinned {pin['git_blob_bytes']}"))
        path = root / rel
        if path.is_file() and pin.get("eol_relationship") == \
                "crlf_worktree_of_lf_blob":
            work = path.read_bytes()
            if work != blob and work.replace(b"\r\n", b"\n") != blob:
                issues.append((
                    "PROTECTED_RECORD_EOL_UNEXPECTED",
                    f"{rel}: working-tree bytes are neither the blob nor a "
                    f"CRLF rendering of it; the difference is not EOL-only"))
    return issues


#: Exclusive, no-clobber, no-follow creation flags. ``O_EXCL`` makes the open
#: fail if ANYTHING is already at the path - including a symlink planted
#: between a precheck and this call - and ``O_NOFOLLOW`` refuses to write
#: through one where the platform implements it.
_EXCL_FLAGS = (os.O_WRONLY | os.O_CREAT | os.O_EXCL
               | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))


def _write_new(path, data, *, exists_code, exists_why,
               journal=None):
    """Create ``path`` exclusively without following links, and fill it.

    There is no variant of this that overwrites. Every write this module makes
    to a path it does not already own goes through here, so "the destination
    was occupied" is always a refusal and never a silent clobber.
    """
    try:
        fd = os.open(str(path), _EXCL_FLAGS, 0o600)
    except FileExistsError:
        raise FinalizerError(exists_code, exists_why)
    except OSError as exc:
        # Not every "something is already there" arrives as FileExistsError. A
        # DIRECTORY at the path raises IsADirectoryError on POSIX and
        # PermissionError on Windows, and a link the platform refuses to follow
        # raises ELOOP. All of them mean the same thing - the path is occupied
        # by an object this run did not create - and all of them must be
        # reported as the occupancy refusal rather than as a generic write
        # failure, because the distinction changes what an operator goes and
        # looks at.
        if os.path.lexists(str(path)):
            raise FinalizerError(exists_code, f"{exists_why} ({exc})")
        raise FinalizerError("TRANSACTION_UNWRITABLE",
                             f"{path} could not be created exclusively: {exc}")
    # IDENTITY IS TAKEN FROM THE OPEN HANDLE, here, now - never by reading the
    # pathname back afterwards. Between this function returning and any later
    # look at the name, the object can be replaced; an identity captured from
    # the descriptor is about the object that was actually created.
    written = 0
    digest = hashlib.sha256()
    dev = ino = None
    try:
        info = os.fstat(fd)
        dev, ino = info.st_dev, info.st_ino
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            written = len(data)
            digest.update(data)
    except BaseException:
        # NOT unlinked. A write error leaves an object this run created but
        # whose contents it cannot vouch for, and deleting a pathname on the
        # way out of an error is the same check-then-delete this module has
        # removed everywhere else. It is journalled as unconfirmed, retained,
        # and reported; a human removes it.
        created = _Created(Path(path), None, written, dev, ino)
        if journal is not None:
            journal.adopt_unconfirmed(created, why="an interrupted exclusive "
                                                   "write")
        raise
    created = _Created(Path(path), digest.hexdigest(), written, dev, ino)
    if journal is not None:
        journal.adopt(created)
    return created


def _link_no_clobber(source, destination, *, exists_code, exists_why):
    """Put ``source``'s bytes at ``destination`` ONLY if nothing is there.

    ``os.link`` fails when the destination exists, so a file recreated by
    another process after our precheck is refused rather than destroyed.
    ``os.replace`` would have overwritten it without a word.
    """
    try:
        os.link(str(source), str(destination))
    except FileExistsError:
        raise FinalizerError(exists_code, exists_why)
    except OSError as exc:
        raise FinalizerError(
            "TRANSACTION_UNWRITABLE",
            f"{source} could not be placed at {destination}: {exc}")
    return Path(destination)


def _git_admin_dir(repo_root):
    """The real git administrative directory for ``repo_root``.

    ``.git`` is NOT always a directory. In a LINKED WORKTREE it is a small file
    containing ``gitdir: <path>``, and this repository is checked out exactly
    that way. Testing ``(root / ".git").is_dir()`` and falling back to the
    worktree root would then put run-owned lock and recovery files INSIDE the
    working tree - which is an untracked change in the tree the run is
    verifying is clean, and would abort the finalization it was meant to
    protect. ``git rev-parse --absolute-git-dir`` answers correctly for a
    normal checkout, a linked worktree and a submodule alike.

    Returns None when git cannot answer; callers then refuse rather than
    guessing a location inside the tree.
    """
    root = Path(repo_root)
    answer = git(root, "rev-parse", "--absolute-git-dir", check=False)
    if answer:
        candidate = Path(answer)
        if candidate.is_dir():
            return candidate
    plain = root / ".git"
    return plain if plain.is_dir() else None


def _run_owned_dir(repo_root, name, code):
    """A run-owned path inside the git admin directory, or a refusal."""
    admin = _git_admin_dir(repo_root)
    if admin is None:
        raise FinalizerError(
            code,
            f"the git administrative directory for {repo_root} could not be "
            f"resolved, so this run has nowhere outside the working tree to "
            f"put its own files; it will not create them inside the tree it "
            f"is verifying is clean")
    return admin / name


def _read_regular_file(path):
    """Read ``path`` without following a link, or None if it is not there.

    ``open()`` follows symlinks, so a snapshot taken through one records the
    bytes of the LINK TARGET, and a "byte-exact restore" then writes them into
    an unrelated file. Only a regular file is read; anything else - a symlink,
    a directory, a FIFO - is a refusal rather than a value.
    """
    import stat as _stat
    path = Path(path)
    try:
        info = os.lstat(str(path))
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise FinalizerError("TRANSACTION_TARGET_UNREADABLE",
                             f"{path} could not be inspected: {exc}")
    if not _stat.S_ISREG(info.st_mode):
        raise FinalizerError(
            "TRANSACTION_TARGET_NOT_REGULAR",
            f"{path} is not a regular file (mode {info.st_mode:#o}); this run "
            f"does not read or write through links or special files")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(
        os, "O_BINARY", 0)
    fd = os.open(str(path), flags)
    with os.fdopen(fd, "rb") as handle:
        return handle.read()


def sha256_regular_no_follow(path, *, code, what):
    """Hash ``path`` only if it is a REGULAR FILE, without following a link.

    ``sha256_file`` is a plain ``open()``, so pointing it at the release
    destination hashed whatever a symlink or junction there resolved to - and
    the run then moved "the predecessor" aside, snapshotted it and, on a
    rollback, restored it. Everything downstream was byte-exact about the wrong
    object.

    So the destination is classified before it is read: ``lstat`` must say
    regular file, the descriptor is opened no-follow where the platform has it,
    and the OPEN HANDLE is required to be the same object the name described.
    """
    import stat as _stat
    path = Path(path)
    try:
        info = os.lstat(str(path))
    except OSError as exc:
        raise FinalizerError(code, f"{what} could not be inspected: {exc}")
    if not _stat.S_ISREG(info.st_mode):
        raise FinalizerError(
            code,
            f"{what} is not a regular file (mode {info.st_mode:#o}); this run "
            f"will not hash, move or restore through a link or a special "
            f"object at {path}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(
        os, "O_BINARY", 0)
    try:
        fd = os.open(str(path), flags)
    except OSError as exc:
        raise FinalizerError(code, f"{what} could not be opened: {exc}")
    digest = hashlib.sha256()
    size = 0
    try:
        opened = os.fstat(fd)
        if not _stat.S_ISREG(opened.st_mode):
            raise FinalizerError(
                code, f"{what} is not a regular file once opened")
        if opened.st_ino and (opened.st_dev, opened.st_ino) != (
                info.st_dev, info.st_ino):
            raise FinalizerError(
                code,
                f"{what} was replaced between being classified and being "
                f"opened; the object read would not be the object checked")
        with os.fdopen(fd, "rb") as handle:
            fd = None
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
                size += len(chunk)
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:                                 # pragma: no cover
                pass
    return digest.hexdigest(), size


class _Created(os.PathLike):
    """What a writer actually created, as the writer saw it.

    Ownership is decided from THIS, never from a later look at the pathname.
    The digest and the byte count come from the bytes the writer put through
    its own descriptor, and ``dev``/``ino`` come from ``fstat`` on that
    descriptor - so "is the object at this path still the one I made?" is a
    question about an identity captured at creation, not about whatever the
    name happens to resolve to now.

    ``sha256 is None`` means the writer could not vouch for the contents (an
    interrupted ``_write_new``). Such a file is retained and reported; it is
    never removed on a guess.
    """

    __slots__ = ("path", "sha256", "bytes", "dev", "ino")

    def __init__(self, path, sha256, size, dev=None, ino=None):
        self.path = Path(path)
        self.sha256 = sha256
        self.bytes = size
        self.dev = dev
        self.ino = ino

    def __fspath__(self):
        return str(self.path)

    def __str__(self):
        return str(self.path)

    def __repr__(self):                                     # pragma: no cover
        return f"_Created({self.path!s}, sha256={self.sha256}, bytes={self.bytes})"


def _unlink_owned(path, what="a run-owned temporary", failures=None):
    """Remove a name THIS RUN created exclusively and never published.

    The distinction this module now draws, and the reason the rule terminates:

    * a name that was ever a REAL TARGET - a tracked file, the release
      destination, the move-aside copy, a lock - can be replaced by somebody
      else between any inspection and any removal, so it is never unlinked by
      path. It is moved into quarantine and the object that MOVED is judged;
    * a name this run created with ``O_EXCL`` inside its own directory and
      never told anybody about - a staging slot, a reservation placeholder, a
      quarantine slot whose contents have already been accounted for - has no
      such window, and unlinking it is where the recursion stops.

    Either way the deletion is CHECKED. The previous ``_unlink_quietly``
    swallowed every error, so a temporary that would not delete was reported
    as cleaned up.
    """
    sink = _CLEANUP_FAILURES if failures is None else failures
    try:
        os.unlink(str(path))
    except FileNotFoundError:
        return True
    except OSError as exc:
        sink.append(f"{what} ({path}) could not be removed: {exc}")
        return False
    if os.path.lexists(str(path)):
        sink.append(f"{what} ({path}) still exists after removal")
        return False
    return True


class _RunTemporaries:
    """The identity of every temporary THIS RUN created, and its safe removal.

    Removing a temporary used to be an unconditional ``unlink`` of a pathname.
    For the staging slots that was nearly safe: they live in a 0700 run-owned
    directory under an unpredictable name. For the release temporary beside the
    destination it was not - that path is in the staging directory, anything
    can reach it, and the run deleted whatever was sitting there at cleanup
    time whether or not it was still the file it had written.

    So every temporary is JOURNALLED when it is created, and every later
    removal - on the success path, on the exception path and in the rollback
    alike - quarantines the object first and compares what actually moved
    against that journalled identity. A mismatch, or anything that is not a
    regular file, is preserved and reported rather than deleted.
    """

    def __init__(self, run_id):
        self.run_id = run_id
        #: str(path) -> {"sha256": ..., "bytes": ...}
        self.identities = {}
        self.failures = []
        #: str(path) -> where the bytes found there were preserved
        self.retained = {}

    def adopt(self, created):
        """Journal a ``_Created`` handed over by the writer that made it.

        There is deliberately no variant that takes a pathname and works out
        the identity by reading it: that is the reread this whole mechanism
        exists to avoid.
        """
        self.identities[str(created.path)] = {
            "sha256": created.sha256, "bytes": created.bytes,
            "dev": created.dev, "ino": created.ino, "confirmed": True}
        return created

    def adopt_unconfirmed(self, created, *, why):
        """Journal an object this run created but cannot vouch for.

        It will never be deleted. The cleanup retains it and reports where it
        is, because "this run made it" and "this run knows what is in it" are
        different claims and only the second licenses a removal.
        """
        self.identities[str(created.path)] = {
            "sha256": None, "bytes": created.bytes, "dev": created.dev,
            "ino": created.ino, "confirmed": False, "why": why}
        return created

    @property
    def unresolved(self):
        """Temporaries this run journalled and has not accounted for."""
        return dict(self.identities)

    def discard(self, path, *, what):
        """Quarantine, compare against the journal, then remove. Or preserve.

        Returns True only when the object actually there was this run's
        temporary AND it is now genuinely gone.
        """
        path = Path(path)
        identity = self.identities.get(str(path))
        if not os.path.lexists(str(path)):
            self.identities.pop(str(path), None)
            return True
        # A SHORT sibling, not a suffix on the original name. Appending
        # ".cleanup-<run id>.quarantine" to a staging slot whose name
        # already carries a sanitized repository-relative path overflowed
        # the Windows 260-character path limit - which Windows reports as
        # ENOENT, so the cleanup failed with "no such file or directory"
        # for a file that was plainly there. The name still has to be
        # unpredictable and unique to this run, so it is a digest of both.
        tag = hashlib.sha256(
            (str(path) + "|" + self.run_id).encode("utf-8")).hexdigest()[:12]
        slot = path.parent / f".q{tag}"
        try:
            taken = _quarantine(path, slot, code="TEMPORARY_QUARANTINE_FAILED",
                                why=f"{what} could not be quarantined")
        except FinalizerError as exc:
            self.failures.append(exc.why)
            return False
        if taken.state == "absent":
            self.identities.pop(str(path), None)
            return True
        if not taken.regular:
            where = _return_to_place(taken, path)
            self.retained[str(path)] = where or str(taken.slot)
            self.failures.append(
                f"{what} ({path}) was {taken.why or 'not a regular file'} at "
                f"cleanup time; it is preserved at {where or taken.slot} and "
                f"was NOT deleted")
            return False
        if identity is not None and not identity.get("confirmed", True):
            where = _return_to_place(taken, path)
            self.retained[str(path)] = where or str(taken.slot)
            self.failures.append(
                f"{what} ({path}) was left by an interrupted write "
                f"({identity.get('why')}), so this run cannot vouch for its "
                f"contents and will not delete it; it is retained at "
                f"{where or taken.slot}")
            return False
        got = sha256_bytes(taken.data)
        if identity is None:
            # Never journalled: this run cannot show the object is its own, so
            # it does not get to delete it.
            where = _return_to_place(taken, path)
            self.retained[str(path)] = where or str(taken.slot)
            self.failures.append(
                f"{what} ({path}) was never journalled by this run, so it "
                f"cannot be shown to be this run's to remove; it is preserved "
                f"at {where or taken.slot}")
            return False
        if got != identity["sha256"]:
            where = _return_to_place(taken, path)
            self.retained[str(path)] = where or str(taken.slot)
            self.failures.append(
                f"{what} ({path}) no longer held the bytes this run wrote "
                f"({got} != {identity['sha256']}); what was there is preserved "
                f"at {where or taken.slot} and was NOT deleted")
            return False
        removed = _unlink_owned(taken.slot, f"the quarantined {what}",
                                self.failures)
        self.identities.pop(str(path), None)
        return removed


def _rmtree_checked(path, what):
    """Remove a run-owned tree and REPORT what could not be removed.

    An error-ignoring recursive delete was the last place this module still hid
    a failure. A recovery directory that would not delete is not a
    tidiness problem: it means the last intact copies of somebody's bytes are
    still on disk under a path nobody has been told about, and the operator has
    been shown a report that says the run cleaned up after itself.
    """
    failures = []
    root = Path(path)
    if not os.path.lexists(str(root)):
        return failures
    # Walked and removed explicitly rather than through ``shutil.rmtree``.
    # Its error callback is the only way to see what failed, and the spelling
    # of that callback changed under us (``onerror`` is deprecated in 3.12 in
    # favour of ``onexc``); a deprecation warning is a poor foundation for the
    # one mechanism that reports where somebody's last intact bytes are.
    for parent, dirs, files in os.walk(str(root), topdown=False,
                                       followlinks=False):
        for name in files:
            try:
                os.unlink(os.path.join(parent, name))
            except OSError as exc:
                failures.append(f"{os.path.join(parent, name)}: {exc}")
        for name in dirs:
            target = os.path.join(parent, name)
            try:
                if os.path.islink(target):
                    os.unlink(target)
                else:
                    os.rmdir(target)
            except OSError as exc:
                failures.append(f"{target}: {exc}")
    try:
        os.rmdir(str(root))
    except OSError as exc:
        failures.append(f"{root}: {exc}")
    if os.path.lexists(str(root)):
        failures.append(f"{root} still exists after removal")
    if failures:
        note = f"{what} could not be removed: " + "; ".join(failures[:5])
        _CLEANUP_FAILURES.append(note)
    return failures


# ---------------------------------------------------------------------------
# Quarantine: the ONLY way this module removes an object it did not just
# create.
#
# Every deletion here used to be a check-then-delete: hash the destination,
# decide the bytes are ours, unlink the PATHNAME. A concurrent writer
# replacing the object inside that window had its work silently deleted,
# because `unlink` names a path and the path no longer named the object that
# was verified. `Transaction.rollback`, `_rollback_output`, the post-commit
# predecessor cleanup and `_Lock.release` were all shaped exactly like that.
#
# The replacement never verifies a pathname and then unlinks it. It reserves a
# run-owned slot exclusively, MOVES whatever is at the path onto that slot in
# one atomic rename, and only then inspects the object that actually moved. If
# the object is this run's own it may be dropped - by unlinking the slot, a
# name no other process can hold. If it is anybody else's it is preserved
# exactly as it arrived and its recovery path is reported.
# ---------------------------------------------------------------------------
class _Taken:
    """The outcome of one quarantine move."""

    __slots__ = ("state", "data", "slot", "regular", "why")

    def __init__(self, state, data=None, slot=None, regular=False, why=None):
        #: "absent" | "taken"
        self.state = state
        #: The bytes of the object that moved, or None when it is not a
        #: regular file (a symlink, a directory, a device) or unreadable.
        self.data = data
        self.slot = slot
        self.regular = regular
        self.why = why

    def matches(self, expected):
        """True only for a REGULAR file holding exactly ``expected`` bytes."""
        return self.state == "taken" and self.regular and self.data == expected


def _quarantine(path, slot, *, code, why):
    """Atomically move whatever is at ``path`` into the reserved ``slot``.

    The slot is created first, exclusively and without following links, so the
    rename can only ever clobber this run's own empty placeholder. What is
    inspected afterwards is the object that MOVED, never the pathname it came
    from - which is the whole point: between an inspection of a pathname and a
    deletion of that pathname, the object can be replaced.
    """
    path = Path(path)
    slot = Path(slot)
    _write_new(slot, b"", exists_code=code,
               exists_why=f"{why}: the quarantine slot {slot} was occupied")
    try:
        os.replace(str(path), str(slot))
    except FileNotFoundError:
        _unlink_owned(slot, "an unused quarantine reservation")
        return _Taken("absent")
    except OSError as exc:
        _unlink_owned(slot, "an unused quarantine reservation")
        raise FinalizerError(
            code, f"{why}: {path} could not be moved into quarantine: {exc}")
    try:
        data = _read_regular_file(slot)
    except FinalizerError as exc:
        # A symlink, a directory or a device moved. It is preserved in the
        # slot exactly as it arrived; nothing is read through it.
        return _Taken("taken", None, slot, False, exc.why)
    except OSError as exc:                                  # pragma: no cover
        return _Taken("taken", None, slot, False, str(exc))
    return _Taken("taken", data, slot, True)


def _return_to_place(taken, path):
    """Put a quarantined object back where it came from, NO-CLOBBER.

    Used when the object turned out not to be this run's to remove. If the
    pathname has been re-occupied in the meantime the object stays in
    quarantine - restoring it would overwrite whatever now holds the name, and
    that is the data loss this whole mechanism exists to prevent. The caller
    reports whichever path the bytes ended up at.
    """
    if taken.state != "taken" or taken.slot is None:
        return None
    try:
        _link_no_clobber(taken.slot, path,
                         exists_code="QUARANTINE_PATH_REOCCUPIED",
                         exists_why=f"{path} was re-occupied")
    except (FinalizerError, OSError):
        return str(taken.slot)
    # The bytes are back under their own name; the extra link is this run's.
    _unlink_owned(taken.slot, "the emptied quarantine slot")
    return str(path)


class _TargetJournal:
    """What the transaction knows about ONE tracked target.

    The journal is the whole basis of the rollback. It records the identity of
    the bytes that were there before, the identity of the bytes this run
    intends to leave, whether this run ACTUALLY WROTE the target, and where the
    immutable recovery copy of the original lives. A rollback that reasons from
    anything else - from the plan, from the edits, from what "should" be on
    disk - restores bytes over a concurrent writer's work.
    """

    __slots__ = ("rel", "original", "original_sha256", "original_bytes",
                 "expected", "expected_sha256", "written", "recovery_path",
                 "moved_aside", "creates", "preserved")

    def __init__(self, rel, original, expected, creates=False):
        self.rel = rel
        self.original = original
        self.original_sha256 = (None if original is None
                                else sha256_bytes(original))
        self.original_bytes = None if original is None else len(original)
        self.expected = expected
        self.expected_sha256 = (None if expected is None
                                else sha256_bytes(expected))
        self.written = False
        self.recovery_path = None
        self.moved_aside = False
        self.creates = creates
        #: Set when rollback found bytes it did not write and left them alone.
        self.preserved = None

    def as_dict(self):
        return {
            "rel": self.rel,
            "original_sha256": self.original_sha256,
            "original_bytes": self.original_bytes,
            "expected_sha256": self.expected_sha256,
            "written": self.written,
            "moved_aside": self.moved_aside,
            "creates": self.creates,
            "recovery_path": (str(self.recovery_path)
                              if self.recovery_path else None),
            "preserved": self.preserved,
        }


class Transaction:
    """All-or-nothing application of planned edits, with byte-exact restore.

    The previous implementation wrote every target through a PREDICTABLE
    sibling, ``<target>.finalizer-tmp``, opened with an ordinary write. That
    name could be pre-created as a symlink to an unrelated file and the write
    would follow it and destroy that file; a plain regular file left there by
    an interrupted run was silently truncated and reused. Both are gone. This
    transaction:

    * stages every postimage inside a run-owned recovery directory, created
      exclusively, on the same filesystem as the worktree;
    * MOVES an existing tracked target into that directory rather than
      overwriting it, and verifies the bytes that actually moved;
    * places the postimage only while the destination is still absent, using a
      no-clobber link, so a file recreated in the window is refused;
    * keeps a per-target journal - original identity, expected identity,
      whether it was really written, and the immutable recovery copy - and
      rolls back FROM THE JOURNAL rather than from the plan.

    Rollback restores a target only when its current state is demonstrably
    this run's own work. Anything else is somebody's data: it is preserved and
    reported instead of being overwritten by a "repair".
    """

    def __init__(self, repo_root, contract, run_id=None):
        self.repo_root = Path(repo_root)
        self.contract = contract
        self.run_id = run_id or new_run_id()
        self.journal = {}
        self._order = []
        self._protected = {}
        self._recovery_dir = None
        self._created_dirs = []
        self.applied = False
        self.rollback_failures = []
        self.recovery_paths = {}
        self._rolled_back = False
        self._rollback_result = None
        #: rel -> the quarantine slot holding bytes this run wrote, retained
        #: until the rollback outcome is verified.
        self._quarantined = {}
        #: The identity of every temporary this transaction creates, so a
        #: later cleanup can prove an object is its own before removing it.
        self._temps = _RunTemporaries(self.run_id)

    # -- staging ----------------------------------------------------------
    def _recovery_root(self):
        """A run-owned directory on the worktree's own filesystem.

        Inside the git ADMINISTRATIVE DIRECTORY deliberately: ``os.replace``
        and ``os.link`` only work within one filesystem, and a directory in the
        working tree would itself show up as an untracked change in the tree
        this run is verifying is clean. The location is resolved with
        ``git rev-parse``, not by assuming ``.git`` is a directory - in a linked
        worktree it is a file.
        """
        if self._recovery_dir is None:
            path = _run_owned_dir(
                self.repo_root, f"scorch_finalizer_recovery_{self.run_id}",
                "TRANSACTION_UNWRITABLE")
            try:
                os.mkdir(str(path), 0o700)
            except FileExistsError:
                raise FinalizerError(
                    "TRANSACTION_RECOVERY_OCCUPIED",
                    f"{path} already exists; this run will not reuse a "
                    f"recovery directory it did not create")
            except OSError as exc:
                raise FinalizerError(
                    "TRANSACTION_UNWRITABLE",
                    f"the recovery directory {path} could not be created: "
                    f"{exc}")
            self._recovery_dir = path
        return self._recovery_dir

    def _slot(self, rel, kind):
        """A run-unique, unpredictable path inside the recovery directory."""
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", rel)
        return self._recovery_root() / (
            f"{kind}.{len(self._order):03d}.{self.run_id}.{safe}")

    def _capture(self, rel, expected=None, creates=False):
        """Record the ACTUAL CURRENT BYTES, or None if the file is absent.

        None is a real state, not a missing value: the D6 receipt does not
        exist before the transaction, and restoring that state means deleting
        it again rather than writing something back.

        For the protected historical records this deliberately captures what
        the platform checked out - CRLF on Windows - rather than the LF git
        blob. Byte-for-byte restoration has to mean the bytes that were really
        there; the tracked blob identity is verified separately.
        """
        if rel in self.journal:
            return self.journal[rel]
        entry = _TargetJournal(rel, _read_regular_file(self.repo_root / rel),
                               expected, creates)
        self.journal[rel] = entry
        self._order.append(rel)
        return entry

    def apply(self, edits):
        """Write every edit, or write none of them and raise.

        This method does NOT roll back. It records what it did in the journal
        and raises; :meth:`rollback` is the single owner of undoing, and the
        caller invokes it once. The previous inner-plus-outer arrangement ran
        the restore twice - once here, once in the finalizer's handler - and
        the second pass reasoned about a tree the first had already changed.
        """
        protected = list(self.contract["protected_historical_records"])
        for rel in protected:
            self._protected[rel] = _read_regular_file(self.repo_root / rel)
        for edit in edits:
            self._capture(edit.rel, edit.updated, edit.creates)

        # The last possible check, and the only one that cannot be raced: the
        # bytes THIS transaction snapshotted must be the bytes the edit was
        # planned against. An outer check confirms the world before an archive
        # build; this confirms it after, with nothing left to happen in
        # between. Without it a change landing in that window is silently
        # overwritten by a plan computed from the file's older contents.
        for edit in edits:
            captured = self.journal[edit.rel].original
            if captured != edit.original:
                raise FinalizerError(
                    "CONCURRENT_MODIFICATION",
                    f"{edit.rel} changed between planning and the "
                    f"transaction: snapshot is "
                    f"{'absent' if captured is None else sha256_bytes(captured)}"
                    f", the edit was planned against "
                    f"{'absent' if edit.original is None else sha256_bytes(edit.original)}")

        for edit in edits:
            entry = self.journal[edit.rel]
            self._write_target(entry)
            self.recovery_paths[edit.rel] = (str(entry.recovery_path)
                                             if entry.recovery_path else None)

        for rel in protected:
            if _read_regular_file(self.repo_root / rel) != self._protected[rel]:
                raise FinalizerError(
                    "PROTECTED_RECORD_MODIFIED",
                    f"{rel} changed during the transaction")
        for edit in edits:
            if _read_regular_file(self.repo_root / edit.rel) != edit.updated:
                raise FinalizerError(
                    "TRANSACTION_WRITE_MISMATCH",
                    f"{edit.rel} on disk does not match the planned bytes")
        # A temporary this run could not account for STOPS the transaction.
        # It is not a tidiness footnote: it means either an object of this
        # run's making is still on disk with contents it cannot vouch for,
        # or something replaced one of its temporaries while it worked. Both
        # are reasons to unwind rather than to carry on and release.
        if self._temps.failures:
            raise FinalizerError(
                "TEMPORARY_CLEANUP_FAILED",
                "; ".join(self._temps.failures[:4]))
        self.applied = True

    def _write_target(self, entry):
        """Move the old bytes aside, then place the new ones no-clobber."""
        target = self.repo_root / entry.rel

        # Re-read immediately before touching it. The pre-apply sweep checked
        # every target, but writes happen one at a time and a file can change
        # while an earlier one is being written.
        current = _read_regular_file(target)
        if current != entry.original:
            raise FinalizerError(
                "CONCURRENT_MODIFICATION",
                f"{entry.rel} changed during the transaction, after it was "
                f"snapshotted and before it was replaced")

        if entry.original is None:
            # A NEW file - in practice the D6 receipt alone. A path that
            # appears concurrently must be preserved and must refuse the run;
            # it is emphatically not something to write through.
            if not entry.creates:
                raise FinalizerError(
                    "TRANSACTION_TARGET_MISSING",
                    f"{entry.rel} does not exist and this edit is not allowed "
                    f"to create it")
            if os.path.lexists(str(target)):
                raise FinalizerError(
                    "RECEIPT_APPEARED_CONCURRENTLY",
                    f"{entry.rel} appeared between the snapshot and the write; "
                    f"this run preserves it and refuses rather than writing "
                    f"through it")
            self._ensure_parent(target)
            staged = _write_new(
                self._slot(entry.rel, "stage"), entry.expected,
                exists_code="TRANSACTION_STAGING_OCCUPIED",
                exists_why=f"the staging slot for {entry.rel} was occupied",
                journal=self._temps)
            try:
                _link_no_clobber(
                    staged, target,
                    exists_code="RECEIPT_APPEARED_CONCURRENTLY",
                    exists_why=(
                        f"{entry.rel} was created by another process while "
                        f"this run was staging it; the concurrent file is "
                        f"preserved and this run refuses"))
            finally:
                self._temps.discard(
                    staged, what=f"the staging slot for {entry.rel}")
            entry.written = True
            return

        # An EXISTING tracked target. Move it into the run-owned recovery
        # directory - never overwrite it in place - and verify what actually
        # moved before anything is put back in its place.
        recovery = self._slot(entry.rel, "orig")
        # Reserve the recovery name exclusively so the rename below can only
        # ever clobber this run's own empty placeholder, never a planted file.
        _write_new(recovery, b"",
                   exists_code="TRANSACTION_RECOVERY_OCCUPIED",
                   exists_why=f"the recovery slot {recovery} was occupied",
                   journal=self._temps)
        try:
            os.replace(str(target), str(recovery))
        except OSError as exc:
            self._temps.discard(
                recovery, what=f"the recovery reservation for {entry.rel}")
            raise FinalizerError(
                "TRANSACTION_UNWRITABLE",
                f"{entry.rel} could not be moved aside: {exc}")
        entry.recovery_path = recovery
        entry.moved_aside = True

        moved = _read_regular_file(recovery)
        if moved != entry.original:
            # A concurrent writer won the race. The bytes that really moved are
            # already safe in the recovery directory; the journal is corrected
            # to describe THEM, so the rollback restores what was actually
            # displaced rather than a stale snapshot of it.
            entry.original = moved
            entry.original_sha256 = (None if moved is None
                                     else sha256_bytes(moved))
            entry.original_bytes = None if moved is None else len(moved)
            raise FinalizerError(
                "CONCURRENT_MODIFICATION",
                f"{entry.rel} was rewritten by another process between the "
                f"snapshot and the move-aside; the moved bytes are preserved "
                f"at {recovery} and this run refuses")

        staged = _write_new(
            self._slot(entry.rel, "stage"), entry.expected,
            exists_code="TRANSACTION_STAGING_OCCUPIED",
            exists_why=f"the staging slot for {entry.rel} was occupied",
            journal=self._temps)
        try:
            _link_no_clobber(
                staged, target,
                exists_code="TRANSACTION_TARGET_RECREATED",
                exists_why=(
                    f"{entry.rel} was recreated after this run moved it aside; "
                    f"this run refuses to overwrite bytes it did not write. "
                    f"The original is preserved at {recovery}"))
        finally:
            self._temps.discard(
                staged, what=f"the staging slot for {entry.rel}")
        entry.written = True

    def _ensure_parent(self, target):
        if target.parent.is_dir():
            return
        missing = []
        probe = target.parent
        while not probe.is_dir():
            missing.append(probe)
            probe = probe.parent
        for path in reversed(missing):
            path.mkdir()
            self._created_dirs.append(path)

    # -- the single rollback owner ----------------------------------------
    def rollback(self):
        """Undo this run's writes FROM THE JOURNAL, then prove it. Idempotent.

        Calling it twice is safe and returns the first result: a second pass
        must not re-derive anything from a tree the first one already changed.

        A target is restored only when its current state is demonstrably this
        run's own: absent where we created it, or holding exactly the bytes we
        wrote. If it holds anything else, those bytes belong to somebody else -
        they are LEFT ALONE, the original recovery copy is retained, the
        failure is recorded, and the caller reports ``ROLLBACK_FAILED`` with
        the recovery paths instead of "repairing" over live work.

        The protected historical records are never rewritten here. They are
        verification-only: this run may confirm they are intact and report it
        if they are not, but a rollback that writes to a historical record is
        rewriting history to tidy up after itself.
        """
        if self._rolled_back:
            return self._rollback_result
        self._rolled_back = True
        failures = []
        restored = []
        preserved = {}

        for rel in reversed(self._order):
            entry = self.journal[rel]
            target = self.repo_root / rel
            recovery = entry.recovery_path
            if recovery:
                self.recovery_paths[rel] = str(recovery)

            try:
                current = _read_regular_file(target)
            except (OSError, FinalizerError) as exc:
                entry.preserved = "the target could not be read"
                preserved[rel] = str(recovery) if recovery else None
                failures.append(f"{rel}: unreadable before restore: {exc}")
                continue

            if entry.written:
                # QUARANTINE, then inspect what moved. The previous shape -
                # compare `current` against the expected bytes, then unlink the
                # PATHNAME - deleted a concurrent replacement that arrived
                # between the comparison and the unlink, because the pathname
                # no longer named the object that had been compared.
                try:
                    taken = _quarantine(
                        target, self._slot(rel, "quarantine"),
                        code="ROLLBACK_QUARANTINE_FAILED",
                        why=f"{rel} could not be quarantined for removal")
                except FinalizerError as exc:
                    entry.preserved = "the target could not be quarantined"
                    preserved[rel] = str(recovery) if recovery else None
                    failures.append(f"{rel}: {exc.why}")
                    continue
                if taken.matches(entry.expected):
                    # This run's own bytes. RETAINED in quarantine until the
                    # restore below has been verified; dropped only when the
                    # whole rollback comes back clean.
                    self._quarantined[rel] = taken.slot
                elif taken.state == "taken":
                    # NOT our bytes. Somebody wrote here after we did. They are
                    # put back under their own name, or kept in quarantine if
                    # the name has been taken again, and either way reported.
                    where = _return_to_place(taken, target)
                    entry.preserved = ("concurrent bytes at the target were "
                                       "left in place")
                    preserved[rel] = where or (str(recovery) if recovery
                                               else None)
                    failures.append(
                        f"{rel}: the target no longer holds the bytes this run "
                        f"wrote, so it is not this run's to remove; the "
                        f"concurrent bytes are preserved at "
                        f"{where or taken.slot} and the original remains at "
                        f"{recovery if recovery else '<no recovery copy>'}")
                    continue
            elif current is not None and entry.original is None:
                # We never wrote, and something is there that was not there
                # before. It arrived independently; it is not ours to delete.
                entry.preserved = "a file appeared at the target"
                preserved[rel] = str(recovery) if recovery else None
                failures.append(
                    f"{rel}: a file appeared at the target that this run did "
                    f"not write; it is preserved rather than removed")
                continue
            elif current is not None and entry.moved_aside:
                # We moved the original aside but never placed ours, and the
                # destination has been recreated by someone else.
                entry.preserved = "the target was recreated after move-aside"
                preserved[rel] = str(recovery) if recovery else None
                failures.append(
                    f"{rel}: the target was recreated after this run moved the "
                    f"original aside; the recreated bytes are preserved and "
                    f"the original remains at {recovery}")
                continue

            if entry.original is None:
                # Restoring "did not exist" means the path stays empty.
                if os.path.lexists(str(target)):
                    failures.append(f"{rel}: created file survived rollback")
                else:
                    restored.append(rel)
                continue

            if recovery is None or not Path(recovery).is_file():
                failures.append(
                    f"{rel}: no recovery copy is available to restore from")
                continue
            try:
                _link_no_clobber(
                    recovery, target,
                    exists_code="ROLLBACK_TARGET_OCCUPIED",
                    exists_why=(f"{rel} was occupied during the restore; the "
                                f"original remains at {recovery}"))
            except FinalizerError as exc:
                entry.preserved = "the target was occupied during restore"
                preserved[rel] = str(recovery)
                failures.append(f"{rel}: not restored: {exc.why}")
                continue
            except OSError as exc:
                # Nothing escapes the rollback. An exception leaving here is
                # reported to the caller as "the run refused and wrote
                # nothing", which is precisely the lie this method exists to
                # make impossible.
                entry.preserved = "the target could not be restored"
                preserved[rel] = str(recovery)
                failures.append(f"{rel}: not restored: {exc}")
                continue
            restored.append(rel)

        # Verify, do not assume - and verify against the JOURNAL's identity.
        for rel in self._order:
            entry = self.journal[rel]
            if entry.preserved:
                continue
            try:
                current = _read_regular_file(self.repo_root / rel)
            except (OSError, FinalizerError) as exc:
                failures.append(f"{rel}: unreadable after rollback: {exc}")
                continue
            if current != entry.original:
                failures.append(
                    f"{rel}: restored bytes differ from the recorded original "
                    f"({'absent' if current is None else sha256_bytes(current)}"
                    f" != {entry.original_sha256 or 'absent'})")

        # The protected records are CHECKED, never rewritten.
        for rel, data in sorted(self._protected.items()):
            try:
                current = _read_regular_file(self.repo_root / rel)
            except (OSError, FinalizerError) as exc:
                failures.append(f"{rel}: protected record unreadable: {exc}")
                continue
            if current != data:
                failures.append(
                    f"{rel}: the protected historical record changed during "
                    f"this run; it is verification-only and this rollback will "
                    f"not rewrite a historical record to tidy up after itself")

        for path in reversed(self._created_dirs):
            try:
                path.rmdir()
            except OSError:
                pass
        self._created_dirs = []
        failures.extend(self._temps.failures)
        self._temps.failures = []
        for path, where in sorted(self._temps.retained.items()):
            preserved.setdefault(path, where)
        self.applied = False
        self.rollback_failures = list(failures)
        # The quarantined postimages are THIS RUN'S OWN bytes, held back until
        # the outcome was verified. Only a clean rollback drops them, and it
        # drops them by unlinking a run-owned slot - never by unlinking a
        # pathname somebody else could have taken over.
        if not failures:
            for rel, slot in sorted(self._quarantined.items()):
                _unlink_owned(slot, f"the quarantined postimage of {rel}",
                              failures)
            self._quarantined = {}
        else:
            for rel, slot in sorted(self._quarantined.items()):
                if os.path.lexists(str(slot)):
                    preserved.setdefault(rel, str(slot))
        result = {"restored": sorted(restored), "failures": failures,
                  "preserved": preserved,
                  "quarantined": {rel: str(slot)
                                  for rel, slot in self._quarantined.items()},
                  "recovery_paths": dict(self.recovery_paths),
                  "journal": {rel: self.journal[rel].as_dict()
                              for rel in self._order}}
        self._rollback_result = result
        if failures:
            raise RollbackError(failures)
        return result

    def discard_recovery(self):
        """Drop the recovery directory. ONLY after a verified outcome.

        Never acts while any journal entry preserved somebody else's bytes:
        those recovery copies are then the last intact originals, and their
        paths have been reported to the operator.
        """
        if self._recovery_dir is None:
            return
        if any(e.preserved for e in self.journal.values()):
            return
        if self._quarantined:
            # Bytes are still held back pending a verified outcome.
            return
        if (self._temps.unresolved or self._temps.retained
                or self._temps.failures):
            # A temporary this run created is still on disk, or was left
            # where it was because its identity could not be confirmed. The
            # recovery directory may be the only place its provenance is
            # written down, so it is kept and reported rather than swept up
            # alongside it.
            self.rollback_failures = list(self.rollback_failures) + [
                f"the recovery directory is retained at {self._recovery_dir}: "
                f"unresolved temporaries "
                f"{sorted(self._temps.unresolved) + sorted(self._temps.retained)}"]
            return
        failures = _rmtree_checked(self._recovery_dir,
                                   "the transaction recovery directory")
        if failures:
            # Reported, not swallowed: the directory still holds the only
            # copies of the originals and the operator has to know where.
            self.rollback_failures = list(self.rollback_failures) + failures
            return
        self._recovery_dir = None


# ---------------------------------------------------------------------------
# Isolation diagnostics - the residual question the overlay left open
# ---------------------------------------------------------------------------
#: Default modules the isolation probe must resolve INSIDE the disposable copy.
#: Each must report both its ``__file__`` and its ``REPO``; a missing answer is
#: a gate failure, not a footnote. Contract-driven via
#: ``isolation_probe_modules`` so a synthetic tree can declare its own.
ISOLATION_PROBE_MODULES = ("test_public_consistency_guards",
                           "test_stale_provenance",
                           "test_corrected_schematic_figures")


def isolation_probe_modules(contract):
    return tuple(contract.get("isolation_probe_modules")
                 or ISOLATION_PROBE_MODULES)

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
for name in json.loads(os.environ["SCORCH_ISOLATION_MODULES"]):
    try:
        mod = __import__(name)
        info[name + "__file__"] = getattr(mod, "__file__", None)
        info[name + "__REPO"] = str(getattr(mod, "REPO", ""))
    except Exception as exc:
        info[name + "__error"] = repr(exc)
print(json.dumps(info))
"""


def isolation_diagnostics(root, python_exe, modules=None):
    """Record exactly which tree an isolated run really resolved.

    The overlay run rendered one skipped module's path as the real worktree
    rather than the disposable copy. That was believed cosmetic but was never
    root-caused, so every isolated run now records repository root, working
    directory, PYTHONPATH, bytecode configuration and the resolved ``__file__``
    of the modules in question, and the answer is evidence rather than belief.
    """
    root = Path(root)
    with tempfile.TemporaryDirectory(prefix="scorch_probe_home") as home:
        return _run_isolation_probe(root, python_exe, modules, home)


def _run_isolation_probe(root, python_exe, modules, home):
    env = _hermetic_env(home)
    env["PYTHONPATH"] = "src"
    env["SCORCH_ISOLATION_MODULES"] = json.dumps(
        list(modules or ISOLATION_PROBE_MODULES))
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


def isolation_acceptance_issues(info, copy_root, modules=None):
    """The isolation probe is a GATE, not a diagnostic printout.

    Recording that a run resolved its modules outside the disposable copy, and
    then accepting the release anyway, tests whichever tree the probe actually
    found. If the answer is wrong the release is not validated - so the answer
    is enforced.
    """
    issues = []
    root = Path(copy_root).resolve()
    if not info:
        return [("ISOLATION_UNVERIFIED", "no isolation diagnostics recorded")]
    if int(info.get("probe_exit", 1)) != 0:
        issues.append(("ISOLATION_PROBE_FAILED",
                       f"probe exited {info.get('probe_exit')}: "
                       f"{str(info.get('probe_stderr'))[:200]}"))
        return issues

    def inside(value):
        """Containment by path semantics, not by string prefix.

        ``startswith`` says ``/tmp/copy-evil`` is inside ``/tmp/copy``.
        """
        try:
            Path(str(value)).resolve().relative_to(root)
            return True
        except (ValueError, OSError):
            return False

    if not inside(info.get("cwd", "")):
        issues.append(("ISOLATION_WRONG_TREE",
                       f"probe cwd {info.get('cwd')!r} is not inside the "
                       f"disposable copy {root}"))
    if not info.get("dont_write_bytecode"):
        issues.append(("ISOLATION_BYTECODE_ENABLED",
                       "the validation run would write bytecode caches"))

    # EVERY probe error is a gate failure. A module that failed to import was
    # not validated, and recording that as an observation while accepting the
    # release is exactly the gap this closes.
    for key in sorted(info):
        if key.endswith("__error") or key == "pytest_import_error":
            issues.append(("ISOLATION_PROBE_FAILED",
                           f"{key}: {info[key]}"))

    for module in (modules or ISOLATION_PROBE_MODULES):
        file_key, repo_key = f"{module}__file__", f"{module}__REPO"
        if not info.get(file_key):
            issues.append(("ISOLATION_MODULE_UNRESOLVED",
                           f"{file_key} was not reported; the run cannot show "
                           f"which {module} it executed"))
        elif not inside(info[file_key]):
            issues.append(("ISOLATION_WRONG_TREE",
                           f"{file_key} resolved to {info[file_key]!r}, "
                           f"outside the disposable copy"))
        if not info.get(repo_key):
            issues.append(("ISOLATION_MODULE_UNRESOLVED",
                           f"{repo_key} was not reported"))
        elif not inside(info[repo_key]):
            issues.append(("ISOLATION_WRONG_TREE",
                           f"{repo_key} is {info[repo_key]!r}, outside the "
                           f"disposable copy; the module resolved a different "
                           f"repository root"))
    return issues


PYTEST_SUMMARY_PLUGIN = r'''
"""Test-support plugin: dump the exact pytest tally and node-ID sets as JSON.

Counts alone cannot tell "557 passed because 557 ran" from "557 passed because
the other 300 were quietly deselected". So the COLLECTED node IDs and the
EXECUTED node IDs are both recorded and compared by the caller.
"""
import json, os, sys

_COLLECTED = []
_EXECUTED = set()


def pytest_configure(config):
    config._scorch_rootdir = str(config.rootdir)


def pytest_collection_modifyitems(session, config, items):
    _COLLECTED.extend(item.nodeid for item in items)


def pytest_deselected(items):
    # Deselection is recorded rather than tolerated; the caller rejects any.
    for item in items:
        _EXECUTED.discard(getattr(item, "nodeid", ""))


def pytest_runtest_logreport(report):
    if report.when == "setup":
        _EXECUTED.add(report.nodeid)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    stats = terminalreporter.stats
    collected = sorted(_COLLECTED)
    executed = sorted(_EXECUTED)
    summary = {
        "rootdir": getattr(config, "_scorch_rootdir", ""),
        "invocation_dir": str(config.invocation_params.dir),
        "sys_executable": sys.executable,
        "cwd": os.getcwd(),
        "exit_status": int(exitstatus),
        "collected": int(getattr(terminalreporter, "_numcollected", 0)),
        "passed": len(stats.get("passed", [])),
        "failed": len(stats.get("failed", [])),
        "errors": len(stats.get("error", [])),
        "skipped": len(stats.get("skipped", [])),
        "xfailed": len(stats.get("xfailed", [])),
        "xpassed": len(stats.get("xpassed", [])),
        "collected_nodeids": collected,
        "executed_nodeids": executed,
        "collected_nodeid_count": len(collected),
        "executed_nodeid_count": len(executed),
        "not_executed": sorted(set(collected) - set(executed)),
        "executed_not_collected": sorted(set(executed) - set(collected)),
    }
    target = os.environ.get("SCORCH_PYTEST_SUMMARY")
    if target:
        with open(target, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
'''

#: Environment that must be CLEARED before the disposable run. Anything the
#: operator's shell happens to carry can otherwise redirect the suite at real
#: data, silently add options, or load a plugin that changes what runs.
_CLEAR_ALWAYS = ("PYTEST_ADDOPTS", "PYTEST_PLUGINS",
                 "PYTEST_DISABLE_PLUGIN_AUTOLOAD", "PYTHONPATH",
                 "PYTHONSTARTUP", "PYTHONWARNINGS", "PYTEST_CURRENT_TEST")

#: Whole families of inherited variables that can change what a child run does
#: without changing a single line of it. GIT_* redirects which repository,
#: index, author and config a `git` call sees - GIT_DIR and GIT_INDEX_FILE
#: alone can make the repository guards inspect a different repository
#: entirely. GH_* redirects the API host and token. COVERAGE_*, XDG_* and
#: MPLBACKEND/MPLCONFIGDIR reach into instrumentation, config discovery and
#: plotting.
_CLEAR_PREFIXES = ("SCORCH", "PYTEST", "PYTHON", "GIT_", "GH_", "GITHUB_",
                   "COVERAGE", "XDG_", "MPL", "MATPLOTLIB")
_CLEAR_EXACT = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_CONFIG",
                "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CEILING_"
                "DIRECTORIES", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
                "GIT_OBJECT_DIRECTORY", "GIT_COMMON_DIR", "GIT_NAMESPACE",
                "GH_TOKEN", "GITHUB_TOKEN", "MPLBACKEND", "MPLCONFIGDIR",
                "COVERAGE_FILE", "COVERAGE_PROCESS_START", "PIP_CONFIG_FILE",
                "VIRTUAL_ENV", "CONDA_PREFIX")


#: The ONLY ambient variables any child inherits. APPDATA and LOCALAPPDATA are
#: deliberately NOT here: on Windows they are where `gh` keeps its hosts file
#: and its token, where pip keeps its configuration and where a great deal of
#: tooling keeps state, so passing the operator's through was the same hole as
#: passing the operator's HOME through. They are redirected into the isolated
#: home by `_isolated_home_vars` instead.
_ENV_ALLOWLIST = ("PATH", "SYSTEMROOT", "SystemRoot", "COMSPEC", "ComSpec",
                  "WINDIR", "windir", "TEMP", "TMP", "TMPDIR", "OS", "PATHEXT",
                  "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
                  "LANG", "LC_ALL", "TZ")

#: Subdirectories every isolated home gets, so a child that writes to one of
#: the redirected locations finds it already there.
_HOME_SUBDIRS = ("", ".config", ".cache", ".local/share", ".matplotlib",
                 "AppData/Roaming", "AppData/Local", "gitconfig.d",
                 "norepo")


def _isolated_home_vars(home):
    """Point every per-user location at ``home``. Nothing is inherited.

    Redirecting HOME alone was not enough on Windows. ``APPDATA`` and
    ``LOCALAPPDATA`` are separate roots that git, `gh` and pip all read, and
    the operator's were being passed straight through.

    ``GIT_CONFIG_GLOBAL`` and ``GIT_CONFIG_SYSTEM`` are pointed at files inside
    the home rather than merely left unset, because "unset" means "look in the
    default place" and the default place is derived from HOME - which a child
    could recompute. Naming the files removes the question: an
    ``url.<base>.insteadOf`` rule cannot come from a configuration file that is
    not read.
    """
    home = Path(home)
    return {
        "HOME": str(home),
        "USERPROFILE": str(home),
        "HOMEDRIVE": home.drive or "",
        "HOMEPATH": str(home)[len(home.drive):] or str(home),
        "APPDATA": str(home / "AppData" / "Roaming"),
        "LOCALAPPDATA": str(home / "AppData" / "Local"),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "XDG_DATA_HOME": str(home / ".local" / "share"),
        "MPLCONFIGDIR": str(home / ".matplotlib"),
        "GIT_CONFIG_GLOBAL": str(home / "gitconfig.d" / "global.gitconfig"),
        "GIT_CONFIG_SYSTEM": str(home / "gitconfig.d" / "system.gitconfig"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }


#: Variables the finalizer SETS ITSELF to a fixed value. A child holding one of
#: these at exactly this value is not carrying an inherited control, whatever
#: the ambient environment happens to say - and treating it as one was a false
#: positive that made the environment self-test depend on the operator's shell.
#: A child holding one of these at any OTHER value is still a leak.
FINALIZER_OWNED_FIXED = {
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONNOUSERSITE": "1",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_OPTIONAL_LOCKS": "0",
    "SCORCH_REQUIRE_ARCHIVE": "1",
}


def _hermetic_env(home):
    """A MINIMAL child environment with an isolated HOME.

    Built by allowing a small set of variables through rather than by removing
    a list of known-bad ones: a deny-list is only ever as complete as the last
    person to think about it, and the entries that mattered - PYTHONOPTIMIZE,
    GIT_DIR, MPLCONFIGDIR - were each discovered after the fact.

    HOME and USERPROFILE point at a directory created for this run, so nothing
    the child does reads or writes the operator's real dotfiles: not
    ``~/.gitconfig`` (which can set core.hooksPath, or an alias that shadows a
    git subcommand), not ``~/.config/gh``, not the matplotlib font cache.
    """
    env = {}
    for key in _ENV_ALLOWLIST:
        if key in os.environ:
            env[key] = os.environ[key]
    # Belt and braces, applied to the ALLOW-LIST ITSELF and before anything is
    # set deliberately: nothing from the families above can survive the
    # allow-list today, but this keeps the intent enforced if it ever grows.
    for key in list(env):
        upper = key.upper()
        if upper in _CLEAR_EXACT or upper.startswith(_CLEAR_PREFIXES):
            env.pop(key, None)
    env.update(_isolated_home_vars(home))
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    return env


#: The isolated HOME shared by every hermetic child of THIS process. Created
#: once, lazily: `git` is called dozens of times in a preflight and a fresh
#: temporary home per call would be both slow and litter.
_PROCESS_HOME = None

#: Cleanup that could not be completed, recorded rather than swallowed.
_CLEANUP_FAILURES = []


def _isolated_home():
    """A process-owned HOME directory for hermetic children.

    Nothing a child reads from ``~`` is then the operator's: not ``.gitconfig``
    (which can set ``core.hooksPath``, ``core.fsmonitor``, ``credential.helper``
    or an alias that shadows a git subcommand), not ``.config/gh``, not the
    matplotlib font cache.
    """
    global _PROCESS_HOME
    if _PROCESS_HOME is None or not Path(_PROCESS_HOME).is_dir():
        base = Path(tempfile.mkdtemp(prefix="scorch_finalizer_home_"))
        for sub in _HOME_SUBDIRS:
            (base / sub).mkdir(parents=True, exist_ok=True)
        # Empty, present, and OURS. `git` reads whatever GIT_CONFIG_GLOBAL
        # names; naming an empty file we created is stronger than naming
        # nothing, because "nothing" sends it back to a default path.
        for name in ("global.gitconfig", "system.gitconfig"):
            target = base / "gitconfig.d" / name
            if not target.exists():
                target.write_text("", encoding="utf-8")
        _PROCESS_HOME = base
        import atexit
        atexit.register(_rmtree_checked, base, "the process isolated HOME")
    return _PROCESS_HOME


def _git_env():
    """The environment EVERY git subprocess runs under.

    ``git`` was the last inherited-control hole. ``GIT_DIR`` and
    ``GIT_INDEX_FILE`` alone point ``rev-parse``, ``status`` and ``ls-files`` at
    a different repository from the one the operator named on the command line,
    so a preflight could report a clean tree at the expected head while
    describing something else entirely; ``GIT_CONFIG_GLOBAL`` and a hostile
    ``~/.gitconfig`` can add an alias, a hook path or a textconv filter that
    changes what any of them print. The environment is therefore built by
    ALLOWING a small set of variables through, exactly as the pytest validation
    environment is.

    There is NO network exception. Retaining the operator's real HOME for
    ``git ls-remote`` was a hole rather than a convenience: a global
    ``url.<other>.insteadOf https://github.com/`` rewrites the URL before the
    connection is made, so the "live" refs a finalization gated itself on could
    be served by any host the operator's configuration nominated - and the
    whole point of that check is that it is not gateable. Global and system
    configuration are therefore neutralised, not inherited, and the live-ref
    check names its URL explicitly from the trusted contract; see
    ``live_remote_state``.
    """
    env = {}
    for key in _ENV_ALLOWLIST:
        if key in os.environ:
            env[key] = os.environ[key]
    for key in list(env):
        upper = key.upper()
        if upper in _CLEAR_EXACT or upper.startswith(_CLEAR_PREFIXES):
            env.pop(key, None)
    env.update(_isolated_home_vars(_isolated_home()))
    # Never write to the index or the reflog just by looking at the tree.
    env["GIT_OPTIONAL_LOCKS"] = "0"
    # STOP UPWARD DISCOVERY at the isolated home. The home is a temporary
    # directory, and a temporary directory is wherever TMPDIR says - which
    # can perfectly well be inside somebody else's git repository. Without
    # a ceiling, a command run there with no repository of its own walks
    # up and finds that one, and reads its configuration: a .git/config
    # carrying url.<elsewhere>.insteadOf would redirect the live-ref check
    # after all the trouble taken to neutralise the global one.
    env["GIT_CEILING_DIRECTORIES"] = str(_isolated_home())
    return env


#: The ambient control families no validation child may inherit.
_CONTROL_PREFIXES = ("SCORCH", "PYTEST", "PYTHON", "GIT_", "GH_", "GITHUB_",
                     "COVERAGE", "XDG_", "MPL", "MATPLOTLIB")


def ambient_control_leaks(child_env, ambient=None):
    """Every ambient control VALUE that survived into ``child_env``.

    The test of a sanitized environment is not that it looks clean but that no
    value in it came from outside. A name the finalizer sets itself is fine; the
    same name carrying the operator's value is the leak.

    One correction over the first version of this check: a variable the
    finalizer sets to a FIXED value - ``PYTHONDONTWRITEBYTECODE=1`` above all -
    is not a leak merely because the operator's shell happens to set the same
    name to the same value. Reporting it as one made the self-test's verdict
    depend on the environment it was supposed to be independent of, and would
    have failed the run of any operator who exports it. The distinction is
    kept honest in both directions: such a variable arriving with any value
    OTHER than the one the finalizer sets is still reported.
    """
    ambient = os.environ if ambient is None else ambient
    leaks = {}
    for key, value in dict(child_env).items():
        upper = key.upper()
        if not (upper in _CLEAR_EXACT or upper.startswith(_CONTROL_PREFIXES)):
            continue
        if FINALIZER_OWNED_FIXED.get(upper) == value:
            continue                    # this run set it, to this exact value
        if key in ambient and ambient[key] == value:
            leaks[key] = value
    return leaks


def _pinned_interpreter_issues(python_exe, contract):
    """A non-default interpreter must be PINNED, or it is not trusted.

    ``--python`` let an operator name any executable, and the finalizer then
    accepted that executable's validator output and pytest summary as proof
    that the release passed. A wrapper that prints a clean summary is a
    two-line script. Production therefore runs ``sys.executable``; anything
    else has to match an identity the trusted contract pins, and if the
    contract pins none, there is nothing to check it against and it is refused.
    """
    want = str(python_exe or "")
    if not want or os.path.realpath(want) == os.path.realpath(sys.executable):
        return []
    pin = (contract or {}).get("trusted_interpreter") or {}
    pinned_path = pin.get("realpath")
    pinned_sha = pin.get("sha256")
    if not pinned_path and not pinned_sha:
        return [("INTERPRETER_UNTRUSTED",
                 f"{want} is not the running interpreter ({sys.executable}) "
                 f"and the trusted contract pins no interpreter identity to "
                 f"check it against; the validator and pytest output of an "
                 f"unverified executable are not evidence")]
    issues = []
    if pinned_path and os.path.realpath(want) != os.path.realpath(pinned_path):
        issues.append(("INTERPRETER_UNTRUSTED",
                       f"{want} is not the pinned interpreter {pinned_path}"))
    if pinned_sha:
        try:
            got = sha256_file(want)
        except OSError as exc:
            return issues + [("INTERPRETER_UNTRUSTED",
                              f"{want} could not be hashed: {exc}")]
        if got != pinned_sha:
            issues.append(("INTERPRETER_UNTRUSTED",
                           f"{want} hashes {got}, the contract pins "
                           f"{pinned_sha}"))
    return issues


def run_validation(copy_root, python_exe, final_archive, extraction, *,
                   final_docx_dir=None, aptos_font=None, summary_path):
    """Run the full suite in the disposable copy against the FINAL archive.

    The previous version validated against whatever data the ambient
    environment pointed at and only cleared six SCORCH_* variables by name. A
    release is accepted on the strength of this run, so it is pinned instead:
    every SCORCH_* variable is cleared, the ones that matter are set
    explicitly to the freshly extracted final archive, and the inherited
    pytest configuration is removed rather than inherited.
    """
    copy_root = Path(copy_root)
    plugin_dir = copy_root / ".finalizer_plugin"
    plugin_dir.mkdir(exist_ok=True)
    (plugin_dir / "scorch_summary_plugin.py").write_text(
        PYTEST_SUMMARY_PLUGIN, encoding="utf-8")

    # A MINIMAL environment with an isolated HOME, built by allowing variables
    # through rather than by naming bad ones. Stripping "SCORCH*, PYTEST*,
    # PYTHON*" left GIT_DIR, GIT_INDEX_FILE, GH_TOKEN, COVERAGE_PROCESS_START,
    # XDG_CONFIG_HOME and MPLCONFIGDIR inherited - and GIT_DIR alone points the
    # repository guards at a different repository from the one under test.
    home = copy_root.parent / f"hermetic_home_{copy_root.name}"
    for sub in ("", ".config", ".cache", ".local/share", ".matplotlib"):
        (home / sub).mkdir(parents=True, exist_ok=True)
    env = _hermetic_env(home)
    for key in _CLEAR_ALWAYS:
        env.pop(key, None)

    env.update({
        "SCORCH_DATA_ARCHIVE": str(final_archive),
        "SCORCH_DATA_DIR": str(extraction),
        "SCORCH_CANONICAL_DATA_DIR": str(extraction),
        "SCORCH_REQUIRE_ARCHIVE": "1",
        "SCORCH_OUT_DIR": str(copy_root / "publication_outputs"),
        "SCORCH_PYTEST_SUMMARY": str(summary_path),
    })
    if final_docx_dir:
        env["SCORCH_FINAL_DOCX_DIR"] = str(final_docx_dir)
    if aptos_font:
        env["SCORCH_APTOS_FONT"] = str(aptos_font)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = os.pathsep.join(["src", str(plugin_dir)])
    # Nothing loads itself into this run. Any plugin installed in the ambient
    # interpreter could deselect, reorder, xfail or skip tests, and the release
    # is accepted on the strength of what this run actually executed.
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"

    with tempfile.TemporaryDirectory(prefix="scorchbt") as basetemp:
        proc = subprocess.run(
            [str(python_exe), "-m", "pytest", "tests",
             "-p", "no:cacheprovider", "-p", "scorch_summary_plugin",
             "--basetemp", basetemp, "-rsxX", "-q"],
            cwd=str(copy_root), env=env, capture_output=True, text=True)
    result = {"exit_code": proc.returncode,
              "repository_root": str(copy_root),
              "data_archive": str(final_archive),
              "data_dir": str(extraction),
              "tail": proc.stdout[-4000:] + proc.stderr[-2000:]}
    if Path(summary_path).is_file():
        result.update(json.loads(Path(summary_path).read_text("utf-8")))
    return result


def frozen_collection_issues(summary, contract):
    """The run must collect EXACTLY the frozen release node-ID set.

    "574 passed" is only meaningful against a known denominator. Without a
    frozen set, deleting a test makes the suite greener, and a conditional
    skip that hides a test is indistinguishable from a test that never
    existed.
    """
    spec = (contract or {}).get("release_test_collection") or {}
    want_count = spec.get("node_id_count")
    want_hash = spec.get("sorted_node_ids_sha256")
    if want_count is None or want_hash is None:
        return [("RELEASE_COLLECTION_UNFROZEN",
                 "release_test_collection is not frozen in the trusted "
                 "contract; a release cannot be accepted against an unknown "
                 "denominator")]
    collected = sorted(summary.get("collected_nodeids") or [])
    got_hash = sha256_bytes(("\n".join(collected) + "\n").encode("utf-8"))
    issues = []
    if len(collected) != want_count:
        issues.append(("RELEASE_COLLECTION_DRIFT",
                       f"collected {len(collected)} node ids, the frozen "
                       f"release set has {want_count}"))
    if got_hash != want_hash:
        issues.append(("RELEASE_COLLECTION_DRIFT",
                       f"collected node-ID hash {got_hash} != frozen "
                       f"{want_hash}"))
    return issues


def validation_acceptance_issues(summary, contract=None):
    """Release acceptance: zero of everything, and nothing left unrun."""
    issues = list(frozen_collection_issues(summary, contract)) \
        if contract is not None else []
    for key in ("failed", "errors", "xfailed", "xpassed", "skipped"):
        value = summary.get(key, 1)
        if value:
            issues.append((
                "VALIDATION_RUN_FAILED",
                f"release acceptance requires zero {key}; the disposable run "
                f"reported {value}"))
    if summary.get("exit_code", 1) != 0:
        issues.append(("VALIDATION_RUN_FAILED",
                       f"pytest exited {summary.get('exit_code')}"))
    not_run = summary.get("not_executed")
    if not_run:
        issues.append((
            "VALIDATION_INCOMPLETE",
            f"{len(not_run)} collected test(s) did not execute - a -k filter, "
            f"a deselection or a plugin removed them: {not_run[:5]}"))
    stray = summary.get("executed_not_collected")
    if stray:
        issues.append(("VALIDATION_INCOMPLETE",
                       f"executed tests that were never collected: {stray[:5]}"))
    if not summary.get("collected_nodeids"):
        issues.append(("VALIDATION_INCOMPLETE",
                       "no node IDs were collected; the run proved nothing"))
    return issues


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

    # LIVE, from the server. refs/remotes/* is a cached answer from the last
    # fetch: if main moved five minutes ago the cache still says what it said,
    # and a gate resting on it is resting on nothing.
    try:
        refs = live_remote_state(root, contract)
        report.note("live_remote_refs", refs)
    except FinalizerError as exc:
        report.fail(exc.code, exc.why)
        refs = {}

    remote_branch = refs.get(f"refs/heads/{repo['head_branch']}", "")
    report.note("remote_head", remote_branch)
    if remote_branch != head:
        report.fail("GIT_REMOTE_BRANCH_MISMATCH",
                    f"live origin/{repo['head_branch']} is "
                    f"{remote_branch or '<absent>'}, local HEAD is {head}")
    main = refs.get(f"refs/heads/{repo['base_branch']}", "")
    report.note("origin_main", main)
    if main != repo["expected_main_commit"]:
        report.fail("GIT_MAIN_MOVED",
                    f"live origin/{repo['base_branch']} is "
                    f"{main or '<absent>'}, expected "
                    f"{repo['expected_main_commit']}")
    tag_obj = refs.get(f"refs/tags/{repo['expected_tag']}", "")
    tag_commit = refs.get(f"refs/tags/{repo['expected_tag']}^{{}}", "")
    report.note("tag_object", tag_obj)
    report.note("tag_commit", tag_commit)
    if tag_obj != repo["expected_tag_object"]:
        report.fail("GIT_TAG_MOVED",
                    f"live tag object {tag_obj or '<absent>'}, expected "
                    f"{repo['expected_tag_object']}")
    if tag_commit != repo["expected_tag_commit"]:
        report.fail("GIT_TAG_MOVED",
                    f"live tag commit {tag_commit or '<absent>'}, expected "
                    f"{repo['expected_tag_commit']}")

    # The superseded official archive, which shares its filename with the one
    # being released and must survive both outcomes untouched.
    for code, why in verify_superseded_archive(root, contract):
        report.fail(code, why)
    report.note("superseded_archive",
                (contract.get("superseded_official_archive") or {}).get("path"))

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
    for code, why in _assert_protected_blobs_intact(root, contract):
        report.fail(code, why)

    # --- the receipt must not pre-exist -------------------------------------
    spec = contract.get("authorization_receipt") or {}
    if spec.get("tracked_path"):
        report.note("authorization_receipt_path", spec["tracked_path"])
        # The same containment rule the state helper, the builder and the
        # guards apply. `is_file()` follows links, so a symlink at the
        # contracted path reported "no receipt here" when it pointed at
        # nothing and "a receipt is here" when it pointed anywhere at all.
        receipt_file, receipt_path_issues = _artwork.resolve_receipt_path(
            root, contract)
        for code, why in receipt_path_issues:
            report.fail(code, why)
        present = receipt_file is not None or bool(receipt_path_issues) \
            or os.path.lexists(str(root / spec["tracked_path"]))
        report.note("authorization_receipt_present", present)
        if present and spec.get("must_not_exist_before_authorization"):
            report.fail(
                "RECEIPT_PREMATURE",
                f"{spec['tracked_path']} already exists but no authorization "
                f"has been recorded by this run; a receipt that predates the "
                f"authorization it claims to record is not evidence")

    # --- candidate archive, when the operator supplies one ------------------
    if not candidate_archive:
        report.note("candidate_archive", "not supplied (optional)")
    else:
        cand = Path(candidate_archive)
        ident = None
        if not cand.is_file():
            report.fail("ARCHIVE_CANDIDATE_MISSING", f"{cand} is not a file")
        else:
            try:
                ident = archive_identity(cand)
            # ORDINARY Exception, never BaseException: a valid ZIP using an
            # unsupported compression method raises NotImplementedError, and
            # enumerating exception types by hand kept missing one. Catching
            # BaseException would swallow KeyboardInterrupt and SystemExit,
            # which must still propagate.
            except Exception as exc:              # noqa: BLE001 - reported
                # preflight AGGREGATES codes; it never raises at the operator.
                # Corrupt candidate bytes are an ordinary reportable state, and
                # a BadZipFile traceback out of a read-only preflight tells the
                # operator nothing about what else was wrong.
                report.fail("ARCHIVE_CANDIDATE_CORRUPT",
                            f"{cand} could not be read as a ZIP archive: "
                            f"{type(exc).__name__}: {exc}")
        if ident is None:
            report.note("candidate_archive",
                        {"path": str(cand), "readable": False})
        else:
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
            for code, why in verify_technical_source(cand, contract):
                report.fail(code, why)
            report.note("technical_source_status",
                        contract["technical_source_candidate"]["status"])

    # --- the licensing state machine ---------------------------------------
    try:
        state, state_issues, state_detail = licence_state(root, contract)
        report.note("licence_state", state)
        report.note("licence_state_detail", state_detail)
        if state != PENDING:
            for code, why in state_issues:
                report.fail(code, why)
            if state == ACTIVE:
                report.fail(
                    "LICENCE_STATE_UNEXPECTED",
                    "the tracked records already assert an active CC BY grant "
                    "over the Figure 1 / Figure 4 artwork; this run has not "
                    "recorded an authorization")
    except OSError as exc:
        report.fail("LICENCE_STATE_UNREADABLE", str(exc))

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
def _verified_non_repository():
    """A directory inside the isolated home PROVED not to be in a repo.

    Belt and braces with GIT_CEILING_DIRECTORIES: the ceiling stops the
    upward walk, and this confirms the walk finds nothing even so. If the
    directory turns out to be inside a repository the run refuses, rather
    than asking a question whose answer somebody else's configuration
    gets to shape.
    """
    where = Path(_isolated_home()) / "norepo"
    where.mkdir(parents=True, exist_ok=True)
    probe = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=str(where),
        capture_output=True, text=True, env=_git_env())
    if probe.returncode == 0:
        raise FinalizerError(
            "GIT_REMOTE_UNAVAILABLE",
            f"the isolated working directory {where} is inside the git "
            f"repository {probe.stdout.strip()}; a configuration-free "
            f"live-ref check cannot be made from inside a repository "
            f"whose configuration this run has not verified")
    return where


def live_remote_url(contract):
    """The one URL the live-ref check may talk to, from the trusted contract.

    By default it is built from ``repository.owner`` and ``repository.name``
    against the fixed ``github.com`` host - the same constant the authorization
    client is pinned to. Nothing in that is read from git configuration, from a
    remote name or from the environment, so there is nothing for an
    ``url.<base>.insteadOf`` rule to act on.

    ``repository.remote_url`` may name it explicitly instead. That is not a
    loophole: the contract is read from the COMMITTED blob at HEAD and its
    identity is verified before anything else happens, so overriding this means
    committing the override into the repository under review - the opposite of
    an ambient redirection. It exists because a synthetic tree under test has a
    local origin and no GitHub, and a live-ref check that could only ever be
    exercised against the real remote would not be exercised at all. The real
    contract does not set it.
    """
    repo = contract["repository"]
    explicit = repo.get("remote_url")
    if explicit:
        return str(explicit)
    owner = str(repo["owner"])
    name = str(repo["name"])
    for part in (owner, name):
        if not re.fullmatch(r"[A-Za-z0-9._-]+", part):
            raise FinalizerError(
                "GIT_REMOTE_UNAVAILABLE",
                f"the contract's repository identity {part!r} is not a plain "
                f"GitHub path segment; this run will not assemble a URL from "
                f"it")
    return f"https://{GITHUB_HOST}/{owner}/{name}.git"


def live_remote_state(repo_root, contract):
    """Read the remote from the REMOTE, not from stale local remote-refs.

    ``refs/remotes/origin/main`` is a cached answer from the last fetch. If
    main moved five minutes ago, the cache still says what it said, and a
    finalization gated on it would be gated on nothing. ``git ls-remote`` asks
    the server.
    """
    repo = contract["repository"]
    # NOT `origin`, and NOT from inside the repository.
    #
    # `origin` is a name resolved through configuration, and so is the URL it
    # resolves to: a single global `url.<elsewhere>.insteadOf
    # https://github.com/` rewrites the destination before the connection is
    # opened, and the "live" refs this finalization gates itself on would be
    # whatever that host chose to serve. Retaining the operator's HOME for this
    # one call - which the previous revision did, to keep credential helpers
    # working - left exactly that door open.
    #
    # So the URL is derived from the TRUSTED CONTRACT and passed literally; the
    # command runs OUTSIDE any repository, so no `.git/config` is read either;
    # and global and system configuration are neutralised by `_git_env`
    # pointing GIT_CONFIG_GLOBAL and GIT_CONFIG_SYSTEM at empty run-owned
    # files. There is no configuration left that could rewrite it.
    url = live_remote_url(contract)
    env = _git_env()
    where = _verified_non_repository()
    proc = subprocess.run(
        ["git", "ls-remote", url,
         f"refs/heads/{repo['base_branch']}",
         f"refs/heads/{repo['head_branch']}",
         f"refs/tags/{repo['expected_tag']}",
         f"refs/tags/{repo['expected_tag']}^{{}}"],
        cwd=str(where), capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        # No credential helper is offered and none will be: an
        # authenticated live-ref check would need configuration this run
        # deliberately does not read. Anonymous access failing is a
        # BLOCKER to be reported, not something to work around.
        raise FinalizerError(
            "GIT_REMOTE_UNAVAILABLE",
            f"git ls-remote {url} failed under anonymous, "
            f"configuration-free access: {proc.stderr.strip()[:300]}")
    refs = {}
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) == 2:
            refs[parts[1].strip()] = parts[0].strip()
    return refs


def _assert_live_refs_unmoved(repo_root, contract, head, report=None):
    """Fail if main, the head branch or the tag moved on the server."""
    repo = contract["repository"]
    refs = live_remote_state(repo_root, contract)
    if report is not None:
        report.note("live_remote_refs", refs)
    checks = [
        ("GIT_MAIN_MOVED", f"refs/heads/{repo['base_branch']}",
         repo["expected_main_commit"]),
        ("GIT_REMOTE_BRANCH_MISMATCH", f"refs/heads/{repo['head_branch']}",
         head),
        ("GIT_TAG_MOVED", f"refs/tags/{repo['expected_tag']}",
         repo["expected_tag_object"]),
        ("GIT_TAG_MOVED", f"refs/tags/{repo['expected_tag']}^{{}}",
         repo["expected_tag_commit"]),
    ]
    for code, ref, want in checks:
        got = refs.get(ref)
        if got != want:
            raise FinalizerError(
                code, f"live {ref} is {got or '<absent>'}, expected {want}")


def _utc_now_iso():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def finalize(repo_root, expect_branch, expect_head, *, contract,
             candidate_archive, release_staging, github=None,
             final_docx_dir=None, aptos_font=None, python_exe=None,
             confirm=None, activated_at=None):
    """Apply the release finalization, or change nothing at all."""
    report = Report("finalize")
    root = Path(repo_root).resolve()
    python_exe = python_exe or sys.executable

    if confirm != CONFIRM_PHRASE:
        return report.fail("CONFIRMATION_REQUIRED",
                           f"pass --confirm {CONFIRM_PHRASE!r} to proceed")

    # An interpreter other than the running one is trusted only if the
    # contract pins its identity. Production never supplies one.
    for code, why in _pinned_interpreter_issues(python_exe, contract):
        report.fail(code, why)
    if not report.ok:
        return report
    report.note("interpreter", str(python_exe))

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

    run_id = new_run_id()
    # Cleanup state is PER RUN. `_CLEANUP_FAILURES` is module-level so that
    # an at-exit sweep can still record into it, and leaving it populated
    # from an earlier run in the same process would have attached somebody
    # else's stale warning to this run's report - or, worse, made a clean
    # run look dirty and a dirty one unremarkable.
    del _CLEANUP_FAILURES[:]
    temporaries = _RunTemporaries(run_id)
    transaction = Transaction(root, contract, run_id=run_id)
    final_name = contract["identity"]["final_archive_filename"]
    staging = Path(release_staging)
    destination = staging / final_name
    displaced = None          # a pre-existing output archive, moved aside
    placed = False
    predecessor = None        # a PRIVATE verified copy of that predecessor
    pred_dir = None           # its own temp dir, outliving the build workspace
    owned_tmp = None          # the output temporary THIS run created
    placed_sha256 = None      # the bytes THIS run placed at the destination
    keep_snapshot = False     # retain the snapshot when rollback is unverified
    committed = False         # past the terminal commit point
    locks = []
    report.note("run_id", run_id)
    try:
        if not staging.is_dir():
            raise FinalizerError(
                "RELEASE_STAGING_MISSING",
                f"{staging} is not a directory; the release destination is "
                f"explicit and is never derived from the repository's parent")

        # 0a. EXCLUSIVE LOCKS on both the worktree and the staging area,
        #     taken before the long finalization and held through the commit
        #     point or a verified rollback. A second finalizer fails here,
        #     normally, having touched nothing: no build, no move-aside, no
        #     transaction. An unaccounted lock is never removed or reused.
        locks = _acquire_finalizer_locks(root, staging, run_id)
        report.note("locks_held", [str(lock.path) for lock in locks])

        # 0. The released archive shares its FILENAME with the superseded one.
        #    A destination resolving to the superseded archive's path would
        #    move it aside and then delete it on success.
        assert_destination_does_not_collide(root, contract, destination)
        # Checked HERE, before anything is built or written, and again
        # immediately before placement.
        _assert_no_stale_release_temporaries(destination, run_id)
        for code, why in verify_superseded_archive(root, contract):
            raise FinalizerError(code, why)

        # 1. The server's answer, not the last fetch's cached answer.
        _assert_live_refs_unmoved(root, contract, expect_head, report)

        # 2. Validate the activation plan BEFORE an expensive build, and take
        #    the archive licence transition from it.
        _, archive_transition = plan_ccby_activation(root, contract)

        with tempfile.TemporaryDirectory(prefix="scorch_finalize") as td:
            work = Path(td)

            # 3. Build from the pinned technical source: extract, transition
            #    the archive licence, regenerate both manifest systems, run the
            #    shipped validator, and build twice from INDEPENDENT fresh
            #    extractions.
            final_path, build_report = build_release_archive(
                candidate_archive, contract, work,
                archive_transition=archive_transition, python_exe=python_exe)
            report.note("archive_build", build_report)

            # 4. Identity recomputed from the FINAL bytes. Never copied.
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
            for code, why in circular_identity_issues(final_path, contract,
                                                      new):
                raise FinalizerError(code, why)

            old = current_identity(root, contract)
            if new["archive_sha256"] == old["archive_sha256"]:
                raise FinalizerError(
                    "ARCHIVE_IDENTITY_UNCHANGED",
                    "the rebuilt archive is byte-identical to the superseded "
                    "one; the licence transition did not reach the deposit")
            _assert_sidecar_members_unchanged(root, contract, new)

            # 5. Compose: identity first, then licence on top of its output,
            #    so a file carrying both is written exactly once.
            identity_edits = plan_identity_edits(root, contract, old, new)
            base = {e.rel: e.updated for e in identity_edits}
            ccby_edits, _ = plan_ccby_activation(root, contract, base=base)
            edits = compose_edits(identity_edits, ccby_edits)
            report.note("edit_summary",
                        {e.rel: {"references": e.references,
                                 "changed": e.changed} for e in edits})

            # 6. The durable receipt, built and validated in the copy first.
            #    The EFFECTIVE activation time is the moment the authorization
            #    last stood as written - the comment's UPDATED_AT, not its
            #    created_at. An authorization edited after posting would
            #    otherwise carry activated_at < updated_at and violate the
            #    receipt's own ordering rule. Using a comment timestamp (rather
            #    than the wall clock) keeps the receipt validated in the
            #    disposable copy byte-identical to the one written to the real
            #    tree, and makes the receipt reproducible.
            effective_at = activated_at or record["updated_at"]
            receipt = build_authorization_receipt(
                root, contract, record, starting_head=expect_head,
                activated_at=effective_at)
            receipt_rel = contract["authorization_receipt"]["tracked_path"]
            receipt_issues = validate_authorization_receipt(
                receipt, contract, record, starting_head=expect_head,
                repo_root=root)
            if receipt_issues:
                raise FinalizerError(receipt_issues[0][0],
                                     receipt_issues[0][1])
            receipt_edit = Edit(receipt_rel, None, receipt_bytes(receipt),
                                {"receipt": 1}, 1, creates=True)
            report.note("authorization_receipt",
                        {"path": receipt_rel,
                         "body_sha256": receipt["body_sha256"],
                         "comment_id": receipt["comment_id"]})

            # 7. Validate in a disposable full copy against a FRESH extraction
            #    of the final archive, then require zero of everything.
            copy_root = work / "validation_copy"
            report.note("validation_tree",
                        _copy_repository(root, copy_root, contract,
                                         expected_head=expect_head,
                                         expected_branch=expect_branch))
            Transaction(copy_root, contract).apply(
                [Edit(e.rel,
                      (copy_root / e.rel).read_bytes()
                      if (copy_root / e.rel).is_file() else None,
                      e.updated, e.counts, e.changed, e.creates)
                 for e in edits + [receipt_edit]])

            state, state_issues, state_detail = licence_state(
                copy_root, contract,
                archive_licence_text=_archive_member_text(
                    final_path, contract["archive_topology"]["licence_member"]))
            report.note("licence_state", {"state": state,
                                          "detail": state_detail})
            if state != ACTIVE or state_issues:
                raise FinalizerError(
                    "LICENCE_STATE_INCONSISTENT",
                    f"after activation the state is {state}: {state_issues}")

            extraction = extract_archive(final_path, work / "final_extract")
            report.note("isolation_diagnostics",
                        isolation_diagnostics(
                            copy_root, python_exe,
                            isolation_probe_modules(contract)))
            summary = run_validation(
                copy_root, python_exe, final_path, extraction,
                final_docx_dir=final_docx_dir, aptos_font=aptos_font,
                summary_path=work / "pytest_summary.json")
            report.note("validation", summary)
            for code, why in validation_acceptance_issues(summary, contract):
                raise FinalizerError(code, why)
            for code, why in isolation_acceptance_issues(
                    report.data.get("isolation_diagnostics") or {}, copy_root,
                    isolation_probe_modules(contract)):
                raise FinalizerError(code, why)

            # 8. Immediately before writing: re-fetch the authorization, recheck
            #    the live refs and the PR, and confirm nothing on disk moved.
            fresh, fresh_issues = find_authorization(client, contract)
            if fresh is None or fresh_issues:
                raise FinalizerError(
                    "AUTHZ_WITHDRAWN_BEFORE_WRITE",
                    f"the authorization no longer qualifies at write time: "
                    f"{fresh_issues}")
            # EVERY identity field of the authorization, not four of them. An
            # edit that changes only `updated_at`, moves the permalink to a
            # different comment, or repoints `issue_url` at another issue is a
            # different authorization from the one that was validated, and the
            # receipt about to be written records all of these.
            for field in ("comment_id", "login", "body", "body_sha256",
                          "created_at", "updated_at", "permalink",
                          "issue_url"):
                if fresh[field] != record[field]:
                    raise FinalizerError(
                        "AUTHZ_CHANGED_BEFORE_WRITE",
                        f"authorization {field} changed between validation "
                        f"and write: {record[field]!r} -> {fresh[field]!r}")
            _assert_live_refs_unmoved(root, contract, expect_head)

            # Local git state, rechecked here rather than trusted from before
            # the build.
            if git(root, "rev-parse", "HEAD") != expect_head:
                raise FinalizerError("GIT_HEAD_MISMATCH",
                                     "HEAD moved during finalization")
            if git(root, "rev-parse", "--abbrev-ref", "HEAD") != expect_branch:
                raise FinalizerError("GIT_BRANCH_MISMATCH",
                                     "the branch changed during finalization")
            dirty = git(root, "status", "--porcelain=v1")
            if dirty:
                raise FinalizerError(
                    "GIT_TREE_DIRTY",
                    f"the working tree became dirty during finalization: "
                    f"{dirty.splitlines()[:5]}")

            # The COMPLETE pull request state, not three fields of it.
            repo_spec = contract["repository"]
            pr_now = client.pull_request(repo_owner(contract),
                                         repo_name(contract),
                                         repo_spec["pull_request"])
            pr_checks = [
                (str(pr_now.get("state", "")).lower() != "open", "not open"),
                (bool(pr_now.get("merged_at")), "merged"),
                (not pr_now.get("draft", False), "no longer a draft"),
                (str((pr_now.get("base") or {}).get("ref"))
                 != repo_spec["base_branch"], "base ref changed"),
                (str((pr_now.get("base") or {}).get("sha"))
                 not in ("", "None", repo_spec["expected_main_commit"]),
                 "base sha changed"),
                (str((pr_now.get("head") or {}).get("ref"))
                 != repo_spec["head_branch"], "head ref changed"),
                (str((pr_now.get("head") or {}).get("sha")) != expect_head,
                 "head sha changed"),
            ]
            broken = [why for bad, why in pr_checks if bad]
            if broken:
                raise FinalizerError(
                    "PR_STATE_UNEXPECTED",
                    f"the pull request moved between validation and write: "
                    f"{broken}")

            # The trusted contract, the artwork, the protected records and both
            # archives - all rechecked with nothing left to happen afterwards.
            _, live_contract_identity = load_trusted_contract(root)
            report.note("trusted_contract_at_write", live_contract_identity)
            for rel, want in sorted(contract["figures"].items()):
                got = sha256_file(root / rel)
                if got != want:
                    raise FinalizerError(
                        "FIGURE_IDENTITY_MISMATCH",
                        f"{rel} changed during finalization: {got} != {want}")
            for code, why in _assert_protected_blobs_intact(root, contract):
                raise FinalizerError(code, why)
            for code, why in verify_superseded_archive(root, contract):
                raise FinalizerError(code, why)
            for code, why in verify_technical_source(candidate_archive,
                                                     contract):
                raise FinalizerError(code, why)
            for name, want in sorted(contract["docx_fixtures"].items()):
                path = Path(final_docx_dir or "") / name
                if not path.is_file() or sha256_file(path) != want:
                    raise FinalizerError(
                        "DOCX_FIXTURE_MISMATCH",
                        f"{name} is no longer the pinned FINAL fixture")
            font = str(aptos_font or "")
            if not font or not Path(font).is_file() or \
                    sha256_file(font) != contract["aptos_font_sha256"]:
                raise FinalizerError(
                    "APTOS_FONT_MISMATCH",
                    "the pinned Aptos Regular face is no longer available")
            for edit in edits:
                current = root / edit.rel
                if not current.is_file() or current.read_bytes() != \
                        edit.original:
                    raise FinalizerError(
                        "CONCURRENT_MODIFICATION",
                        f"{edit.rel} changed on disk after it was planned")
            # lexists, not exists: a DANGLING symlink at the contracted path
            # answers False to exists() and would have been written through.
            if os.path.lexists(str(root / receipt_rel)):
                raise FinalizerError(
                    "RECEIPT_PREMATURE",
                    f"{receipt_rel} appeared before this run wrote it")
            for code, why in _artwork.resolve_receipt_path(root, contract)[1]:
                raise FinalizerError(code, why)
            if sha256_file(final_path) != new["archive_sha256"]:
                raise FinalizerError(
                    "BYTES_MUTATED_AFTER_HASHING",
                    "the built archive changed between hashing and placement")

            # 9. Only now does anything outside the temporary directory change.
            transaction.apply(edits + [receipt_edit])

            # Run-unique temporaries. A predictable name can be created by
            # another process between the last stale check and our own open;
            # a unique one plus O_EXCL means we either create it or fail.
            tmp_out, displaced_path = release_temp_paths(destination, run_id)
            _assert_no_stale_release_temporaries(destination, run_id)

            if os.path.lexists(destination):
                # A PRIVATE verified copy, kept outside the staging directory.
                # The move-aside file sits next to the destination where
                # anything could reach it; restoring from a tampered
                # move-aside would be a byte-inexact "rollback".
                pred_dir = Path(tempfile.mkdtemp(prefix="scorch_predecessor"))
                # CLASSIFIED BEFORE IT IS READ. `sha256_file` follows
                # links, so a symlink or junction left at the release
                # destination made this run snapshot, move aside and
                # later restore an object somewhere else entirely.
                pred_sha, pred_bytes = sha256_regular_no_follow(
                    destination, code="RELEASE_DESTINATION_NOT_REGULAR",
                    what="the existing release destination")
                predecessor = {
                    "path": pred_dir / "predecessor.zip",
                    "sha256": pred_sha,
                    "bytes": pred_bytes,
                }
                shutil.copy2(destination, predecessor["path"])
                if sha256_file(predecessor["path"]) != predecessor["sha256"]:
                    raise FinalizerError(
                        "PREDECESSOR_SNAPSHOT_FAILED",
                        "the private predecessor snapshot does not match the "
                        "archive it was taken from")
                again, _again_bytes = sha256_regular_no_follow(
                    destination, code="RELEASE_DESTINATION_NOT_REGULAR",
                    what="the existing release destination")
                if again != predecessor["sha256"]:
                    raise FinalizerError(
                        "PREDECESSOR_MUTATED",
                        "the destination changed while it was being "
                        "snapshotted; another process is writing to it")
                # NO-CLOBBER move-aside. os.replace alone would overwrite
                # whatever sits at the displaced path - a file or a symlink
                # planted there after the stale-temporary sweep. The name is
                # therefore RESERVED first with an exclusive, no-follow create,
                # so the rename can only ever clobber this run's own empty
                # placeholder.
                _write_new(
                    displaced_path, b"", journal=temporaries,
                    exists_code="RELEASE_STAGING_STALE_TEMP",
                    exists_why=(
                        f"{displaced_path} appeared between the stale-temporary "
                        f"check and the move-aside; this run refuses to write "
                        f"through it or move the predecessor onto it"))
                displaced = displaced_path
                try:
                    os.replace(destination, displaced)
                except OSError as exc:
                    temporaries.discard(
                        displaced,
                        what="the move-aside reservation")
                    displaced = None
                    raise FinalizerError(
                        "RELEASE_STAGING_UNWRITABLE",
                        f"the predecessor could not be moved aside: {exc}")
                # IMMEDIATELY AFTER the move. If the bytes that were actually
                # moved are not the bytes we snapshotted, a concurrent writer
                # won the race. What was moved is PRESERVED - intact, where it
                # is - a separate verified second snapshot is taken beside the
                # original one rather than over it, and this run REFUSES.
                if sha256_file(displaced) != predecessor["sha256"]:
                    predecessor = _snapshot_moved_predecessor(
                        displaced, predecessor, pred_dir, run_id)
                    raise FinalizerError(
                        "PREDECESSOR_MUTATED",
                        f"the destination was rewritten by another process "
                        f"between the snapshot and the move-aside; the moved "
                        f"bytes ({predecessor['moved_sha256']}) are preserved "
                        f"intact and this run refuses rather than overwriting "
                        f"them. Second snapshot: "
                        f"{predecessor.get('second_snapshot_path') or 'NOT TAKEN - the intact moved file at ' + str(displaced) + ' is the recovery copy'}")

            # From here a temporary of OUR making may exist. A partial copy2
            # that raises before placement must still be cleaned up, even when
            # there was no predecessor at all.
            owned_tmp = tmp_out
            # The journal is handed to the WRITER, which records what it
            # actually wrote - complete or partial - from its own
            # descriptor. Nothing here reads the pathname back.
            _exclusive_copy(final_path, tmp_out, journal=temporaries)

            # NO-CLOBBER placement, through the SAME primitive the tracked-file
            # transaction uses. os.replace would silently overwrite a
            # destination recreated after the move-aside; a link fails if the
            # target exists, so a concurrent recreation is refused rather than
            # destroyed.
            _link_no_clobber(
                tmp_out, destination,
                exists_code="RELEASE_DESTINATION_RECREATED",
                exists_why=(
                    f"{destination} was recreated after the move-aside; this "
                    f"run refuses to overwrite bytes it did not write"))
            placed = True
            # Remembered so a rollback can tell OUR bytes from a concurrent
            # writer's, and refuse to delete the latter.
            placed_sha256 = new["archive_sha256"]
            # NOT a raw unlink. This path is in the staging directory, where
            # anything can reach it; the temporary is removed through the
            # journal, which quarantines it and compares what actually moved
            # against the bytes this run wrote there.
            if not temporaries.discard(tmp_out,
                                       what="the release output temporary"):
                raise FinalizerError(
                    "RELEASE_TEMPORARY_NOT_OURS",
                    "; ".join(temporaries.failures[-2:]))
            owned_tmp = None

            if sha256_file(destination) != new["archive_sha256"]:
                raise FinalizerError(
                    "BYTES_MUTATED_AFTER_HASHING",
                    f"{destination} does not match the identity just written")
            # SUCCESS still has to leave the superseded archive alone. It is
            # not a rollback-only obligation: the released archive shares its
            # filename, so a successful placement is exactly when it would be
            # lost.
            for code, why in verify_superseded_archive(root, contract):
                raise FinalizerError(code, why)

            # THE LAST CHECK OF ALL. Everything verified before the archive
            # was placed was verified BEFORE the archive was placed - and
            # placement takes time, during which a tracked licence or identity
            # file can be edited from outside. Re-hash every postimage, the
            # receipt, the placed archive, the predecessor recovery state, the
            # protected records, the figures and the technical source, and
            # compare them against the identities recorded for them. Anything
            # that moved prevents success; nothing here deletes the external
            # edit, which is the rollback's problem and is preserved there.
            report.note("commit_point_reverification",
                        _reverify_before_commit(
                            root, contract, transaction, edits, receipt_edit,
                            destination, new, predecessor, displaced,
                            candidate_archive, final_docx_dir, aptos_font))

            # ================= TERMINAL COMMIT POINT =================
            # Every operation capable of triggering a rollback has now
            # completed. Past this line the release STANDS: cleanup failures
            # are reported, never rolled back into, because undoing a
            # successful release because a temporary file would not delete
            # would be the worst possible trade.
            committed = True
            report.note("commit_point", "reached")
            if displaced is not None:
                # EXPLICIT VERIFIED CLEANUP, not a pathname unlink. The
                # predecessor is moved into a run-owned slot in one rename and
                # the object that actually moved is then checked against the
                # identity recorded for it. Only bytes that ARE the predecessor
                # are dropped; anything else is retained, its path reported,
                # and the release still stands - a cleanup surprise past the
                # commit point is news for the operator, never a reason to
                # start deleting.
                try:
                    taken = _quarantine(
                        displaced, _output_slot(displaced, run_id, "superseded"),
                        code="POST_COMMIT_QUARANTINE_FAILED",
                        why="the displaced predecessor could not be "
                            "quarantined for cleanup")
                except FinalizerError as exc:
                    report.note("post_commit_cleanup_warning", exc.why)
                else:
                    want = (predecessor or {}).get("sha256")
                    if taken.state == "absent":
                        report.note("post_commit_cleanup_warning",
                                    f"{displaced} was already gone before this "
                                    f"run cleaned it up")
                    elif taken.regular and (want is None
                                            or sha256_bytes(taken.data) == want):
                        _unlink_owned(taken.slot,
                                      "the quarantined predecessor")
                        report.note("displaced_predecessor_removed",
                                    str(displaced))
                    else:
                        where = _return_to_place(taken, displaced)
                        report.note(
                            "displaced_predecessor_retained",
                            f"the move-aside path did not hold the recorded "
                            f"predecessor at cleanup time; what was there is "
                            f"preserved at {where or taken.slot} and was not "
                            f"deleted")
                displaced = None
            report.note("final_archive_written", str(destination))
            report.note("superseded_archive_preserved",
                        contract["superseded_official_archive"]["path"])
    except FinalizerError as exc:
        if committed:
            # Past the commit point the release STANDS. A cleanup failure is
            # reported; it never triggers the destruction of a successful
            # release or of its predecessor.
            report.note("post_commit_failure", f"{exc.code}: {exc.why}")
            return report
        keep_snapshot = _finalize_rollback(
            report, transaction, destination, displaced, placed, root,
            contract, predecessor, owned_tmp, placed_sha256, run_id=run_id,
            temporaries=temporaries)
        return report.fail(exc.code, exc.why)
    except BaseException as exc:                       # noqa: BLE001
        if committed:
            report.note("post_commit_failure", repr(exc))
            return report
        keep_snapshot = _finalize_rollback(
            report, transaction, destination, displaced, placed, root,
            contract, predecessor, owned_tmp, placed_sha256, run_id=run_id,
            temporaries=temporaries)
        return report.fail("TRANSACTION_ROLLED_BACK", repr(exc))
    finally:
        # The private snapshot is destroyed ONLY after a verified success or a
        # verified restoration. If the rollback could not be verified it is the
        # last intact copy of the predecessor, and its path is reported.
        if pred_dir is not None and not keep_snapshot:
            for failure in _rmtree_checked(
                    pred_dir, "the private predecessor snapshot directory"):
                report.note("cleanup_failure", failure)
        # The transaction's recovery copies go the same way, and by the same
        # rule: discard_recovery() declines to act while any journal entry is
        # holding somebody else's bytes.
        if committed or not keep_snapshot:
            transaction.discard_recovery()
        if transaction.recovery_paths:
            report.note("transaction_recovery_paths",
                        transaction.recovery_paths)
        # The locks come off last, after the commit point or after the
        # rollback has been attempted and reported - never while the tree is
        # still mid-transaction.
        for lock in locks:
            lock.release()
            if lock.release_failure:
                # A lock that could not be accounted for at release time is
                # reported. Silently walking away from it is how the next run
                # finds an unexplained lock and how a live one gets deleted.
                report.note("lock_release_failure", lock.release_failure)
        if temporaries.failures:
            report.note("temporary_cleanup_failures",
                        list(temporaries.failures))
        if temporaries.retained:
            report.note("temporary_recovery_paths",
                        dict(temporaries.retained))
        if _CLEANUP_FAILURES:
            report.note("cleanup_failures", list(_CLEANUP_FAILURES))

    return report


def _reverify_before_commit(root, contract, transaction, edits, receipt_edit,
                            destination, new, predecessor, displaced,
                            candidate_archive, final_docx_dir, aptos_font):
    """Re-hash everything the release rests on, immediately before committing.

    The invariants were all checked before the transaction and again before
    the archive was placed. Placement is not instantaneous, and a tracked
    licence or identity file edited during it would otherwise have been
    published as part of a "successful" release. Every check here raises, so
    the failure travels the ordinary rollback path - and the rollback PRESERVES
    the external edit rather than deleting it, because those bytes are not
    this run's to remove.
    """
    observed = {}

    # 1. Every edited tracked postimage, by the identity the journal recorded.
    for edit in list(edits) + [receipt_edit]:
        entry = transaction.journal.get(edit.rel)
        want = entry.expected_sha256 if entry else sha256_bytes(edit.updated)
        current = _read_regular_file(root / edit.rel)
        got = None if current is None else sha256_bytes(current)
        observed[edit.rel] = got
        if got != want:
            raise FinalizerError(
                "POSTIMAGE_MUTATED_BEFORE_COMMIT",
                f"{edit.rel} was modified after this run wrote it and before "
                f"the commit point ({got or 'absent'} != {want}); the release "
                f"is refused. The external edit is NOT deleted - the rollback "
                f"preserves bytes this run did not write and reports where the "
                f"original is")

    # 2. The durable receipt, through the SAME single fail-closed safe open the
    #    state module uses. Re-reading it with `_read_regular_file` was the
    #    same defect in a second place: on Windows its O_NOFOLLOW is zero, so
    #    the last check before the commit point would have followed a link
    #    planted at the contracted path and confirmed somebody else's bytes as
    #    "the receipt this run wrote".
    receipt_rel = contract["authorization_receipt"]["tracked_path"]
    path, receipt_issues = _artwork.resolve_receipt_path(root, contract)
    if receipt_issues:
        raise FinalizerError(receipt_issues[0][0], receipt_issues[0][1])
    if path is None:
        raise FinalizerError(
            "POSTIMAGE_MUTATED_BEFORE_COMMIT",
            f"{receipt_rel} is not the receipt this run wrote")
    try:
        on_disk = _artwork.safe_read_receipt(path, root)
    except _artwork.ReceiptOpenRefused as exc:
        raise FinalizerError("RECEIPT_PATH_INVALID", exc.why)
    if on_disk != receipt_edit.updated:
        raise FinalizerError(
            "POSTIMAGE_MUTATED_BEFORE_COMMIT",
            f"{receipt_rel} is not the receipt this run wrote")

    # 3. The final archive, at the destination, byte-for-byte.
    got = sha256_file(destination) if Path(destination).is_file() else None
    observed["_destination"] = got
    if got != new["archive_sha256"]:
        raise FinalizerError(
            "BYTES_MUTATED_AFTER_HASHING",
            f"{destination} holds {got or 'nothing'}, not the identity this "
            f"run wrote ({new['archive_sha256']})")

    # 4. Predecessor / recovery state: every copy still there and still itself.
    recovery = {}
    for key in ("path", "second_snapshot_path"):
        candidate = (predecessor or {}).get(key)
        if not candidate:
            continue
        if not Path(candidate).is_file():
            raise FinalizerError(
                "PREDECESSOR_RECOVERY_LOST",
                f"the predecessor recovery copy {candidate} disappeared before "
                f"the commit point")
        recovery[key] = sha256_file(candidate)
    if displaced is not None and Path(displaced).is_file():
        recovery["displaced"] = sha256_file(displaced)
        if (predecessor or {}).get("sha256") and \
                recovery["displaced"] != predecessor["sha256"]:
            raise FinalizerError(
                "PREDECESSOR_MUTATED",
                f"the displaced predecessor changed before the commit point "
                f"({recovery['displaced']} != {predecessor['sha256']})")
    observed["_predecessor_recovery"] = recovery

    # 5. Protected records, figures, both archives and the technical source.
    for code, why in _assert_protected_blobs_intact(root, contract):
        raise FinalizerError(code, why)
    for rel, want in sorted(contract["figures"].items()):
        got = sha256_file(root / rel) if (root / rel).is_file() else None
        if got != want:
            raise FinalizerError(
                "FIGURE_IDENTITY_MISMATCH",
                f"{rel} changed before the commit point: {got or 'absent'} != "
                f"{want}")
    for code, why in verify_superseded_archive(root, contract):
        raise FinalizerError(code, why)
    for code, why in verify_technical_source(candidate_archive, contract):
        raise FinalizerError(code, why)
    for name, want in sorted(contract["docx_fixtures"].items()):
        fixture = Path(final_docx_dir or "") / name
        if not fixture.is_file() or sha256_file(fixture) != want:
            raise FinalizerError(
                "DOCX_FIXTURE_MISMATCH",
                f"{name} is no longer the pinned FINAL fixture at the commit "
                f"point")
    font = str(aptos_font or "")
    if not font or not Path(font).is_file() or \
            sha256_file(font) != contract["aptos_font_sha256"]:
        raise FinalizerError(
            "APTOS_FONT_MISMATCH",
            "the pinned Aptos Regular face changed before the commit point")
    observed["_verified"] = True
    return observed


def _finalize_rollback(report, transaction, destination, displaced, placed,
                       root, contract, predecessor=None, owned_tmp=None,
                       placed_sha256=None, run_id="", temporaries=None):
    """Undo everything, then prove it, and report any failure to undo.

    Returns True when the private predecessor snapshot must be RETAINED
    because the rollback could not be verified.
    """
    output = _rollback_output(destination, displaced, placed, predecessor,
                              owned_tmp, placed_sha256, run_id=run_id,
                              temporaries=temporaries)
    report.note("output_rollback", output)
    if output["failures"]:
        # A failed output rollback is a ROLLBACK_FAILED, not a footnote: the
        # released archive or its predecessor may be missing or half-written.
        report.fail("ROLLBACK_FAILED",
                    f"archive placement could not be undone: "
                    f"{output['failures']}")
    # THE SINGLE ROLLBACK OWNER. Transaction.apply no longer rolls back on its
    # own, and Transaction.rollback is idempotent, so this is the one place the
    # tracked-file undo happens and it operates entirely from the journal.
    try:
        report.note("transaction_rollback", transaction.rollback())
    except RollbackError as exc:
        report.fail(exc.code, exc.why)
        report.note("rollback_failures", exc.failures)
        report.note("transaction_recovery_paths", transaction.recovery_paths)
    except BaseException as exc:                       # noqa: BLE001
        report.fail("ROLLBACK_FAILED", repr(exc))
        report.note("transaction_recovery_paths", transaction.recovery_paths)
    if any(e.preserved for e in transaction.journal.values()):
        # Bytes this run did not write were found at one or more targets and
        # left alone. Say exactly which, and where the originals are.
        report.note("preserved_concurrent_targets",
                    {rel: e.preserved
                     for rel, e in sorted(transaction.journal.items())
                     if e.preserved})
        report.note("transaction_recovery_paths", transaction.recovery_paths)

    # After a rollback the receipt must be gone and both archives correct.
    spec = contract.get("authorization_receipt") or {}
    if spec.get("tracked_path") and (root / spec["tracked_path"]).exists():
        report.fail("ROLLBACK_FAILED",
                    f"{spec['tracked_path']} survived the rollback")
    for code, why in verify_superseded_archive(root, contract):
        report.fail(code, f"after rollback: {why}")
    try:
        strays = sorted(q.name for q in Path(destination).parent.glob(
            "*finalizer-tmp*")) if Path(destination).parent.is_dir() else []
    except OSError as exc:
        strays = []
        report.fail("ROLLBACK_FAILED",
                    f"the staging directory could not be re-read: {exc}")
    if strays:
        report.fail("ROLLBACK_FAILED",
                    f"temporary archive files survived the rollback: {strays}")

    verified = "ROLLBACK_FAILED" not in report.codes
    if not verified and predecessor and Path(predecessor["path"]).is_file():
        # The last intact copy of the predecessor. Say where it is rather than
        # deleting it on the way out.
        report.note("predecessor_recovery_path", str(predecessor["path"]))
        report.note("predecessor_recovery_sha256", predecessor.get("sha256"))
    return not verified


def repo_owner(contract):
    return contract["repository"]["owner"]


def repo_name(contract):
    return contract["repository"]["name"]


def _archive_member_text(archive_path, member):
    """Read one member as text, or None if it cannot be read."""
    try:
        with zipfile.ZipFile(archive_path) as zf:
            return zf.read(member).decode("utf-8", "replace")
    except (KeyError, zipfile.BadZipFile, OSError, RuntimeError):
        return None


def new_run_id():
    """A per-run token, so temporary names cannot be predicted or collided."""
    import uuid
    return uuid.uuid4().hex[:16]


def release_temp_paths(destination, run_id=""):
    """The two temporary paths this run may create beside the destination.

    Run-unique: a predictable name can be created by another process between
    the last stale check and our own open.
    """
    destination = Path(destination)
    suffix = ("." + run_id) if run_id else ""
    return (destination.with_name(destination.name + suffix + ".finalizer-tmp"),
            destination.with_name(destination.name + suffix +
                                  ".superseded-finalizer-tmp"))


def _exclusive_copy(src, dst, journal=None):
    """Create ``dst`` EXCLUSIVELY and without following links, then fill it.

    ``O_EXCL`` makes creation fail if anything is already there - including a
    symlink planted between the stale check and this call - and ``O_NOFOLLOW``
    refuses to write through one where the platform supports it.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(str(dst), flags, 0o600)
    except FileExistsError:
        raise FinalizerError(
            "RELEASE_STAGING_STALE_TEMP",
            f"{dst} appeared between the stale-temporary check and the write; "
            f"this run refuses to write through it")
    except OSError as exc:
        raise FinalizerError("RELEASE_STAGING_UNWRITABLE",
                             f"{dst} could not be created exclusively: {exc}")
    # Hashed AS IT IS WRITTEN, from the descriptor - so even a copy that dies
    # halfway leaves an identity describing exactly the bytes that reached the
    # file. The previous version read nothing and simply unlinked the pathname
    # on error; the version after that re-read the pathname once the writer had
    # returned, which is the very thing that cannot be trusted.
    written = 0
    digest = hashlib.sha256()
    dev = ino = None
    try:
        info = os.fstat(fd)
        dev, ino = info.st_dev, info.st_ino
        with os.fdopen(fd, "wb") as out, open(src, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                out.write(chunk)
                digest.update(chunk)
                written += len(chunk)
    except BaseException:
        created = _Created(Path(dst), digest.hexdigest(), written, dev, ino)
        if journal is not None:
            # A PARTIAL copy, but a partial copy of known identity: the digest
            # covers precisely the bytes this run put there, so the cleanup can
            # still prove the object is its own.
            journal.adopt(created)
        raise
    created = _Created(Path(dst), digest.hexdigest(), written, dev, ino)
    if journal is not None:
        journal.adopt(created)
    return created


#: Anything beside the destination whose name carries this token is a
#: finalizer temporary, whoever created it.
RELEASE_TEMP_TOKEN = "finalizer-tmp"


def _temp_kind(path):
    """How a leftover presents itself, without following it."""
    try:
        if path.is_symlink():
            return "dangling symlink" if not path.exists() else "symlink"
    except OSError:
        return "unreadable entry"
    return "file"


def _assert_no_stale_release_temporaries(destination, run_id=""):
    """Refuse EVERY leftover finalizer temporary beside the destination.

    Not only the two this run would use. Run-unique names stop a concurrent
    run from colliding with ours; they do not make an INTERRUPTED EARLIER
    run's leftovers safe, and checking only our own names made the artefact
    this guard exists for invisible - an abandoned ``<archive>.finalizer-tmp``
    carries no run id, so it matched neither of the names we would create.

    Identification is by name token, so a leftover from any run is caught, and
    the directory is LISTED rather than probed: ``Path.exists()`` follows
    symlinks and answers False for a DANGLING one, which would then be
    silently clobbered - or followed on write. Listing reports the link
    itself.
    """
    destination = Path(destination)
    found = []
    for stale in release_temp_paths(destination, run_id):
        if os.path.lexists(stale):
            found.append(stale)
    parent = destination.parent
    if parent.is_dir():
        try:
            entries = sorted(parent.iterdir())
        except OSError as exc:
            raise FinalizerError(
                "RELEASE_STAGING_UNREADABLE",
                f"{parent} could not be listed, so the presence of leftover "
                f"finalizer temporaries cannot be established: {exc}")
        for entry in entries:
            if RELEASE_TEMP_TOKEN in entry.name and entry not in found:
                found.append(entry)
    if found:
        described = ", ".join(f"{p} ({_temp_kind(p)})" for p in found)
        raise FinalizerError(
            "RELEASE_STAGING_STALE_TEMP",
            f"leftover finalizer temporaries are present beside the release "
            f"destination: {described}. A temporary from an earlier or "
            f"concurrent run must be removed and accounted for before a "
            f"release is placed; this run will not overwrite it, follow it, "
            f"or silently delete it")


#: The two exclusive locks a finalization holds for its whole duration. The
#: worktree lock lives inside ``.git`` so it is never part of the tree whose
#: cleanliness this run verifies; the staging lock lives beside the release
#: destination. Neither name carries RELEASE_TEMP_TOKEN, so the stale-temporary
#: sweep does not mistake a live lock for abandoned scratch.
WORKTREE_LOCK_NAME = "scorch_finalizer.lock"
STAGING_LOCK_NAME = ".scorch_finalizer.lock"


class _Lock:
    """One exclusively created, no-follow lock file, released once.

    Two finalizations running at once would interleave their move-asides and
    their rollbacks over the same files, and each would conclude from its own
    journal that the other's bytes were concurrent damage. The whole long
    finalization - build, validation, transaction, placement - therefore runs
    under a lock on BOTH the worktree and the staging area, held through the
    commit point or through a verified rollback.
    """

    def __init__(self, path, run_id):
        self.path = Path(path)
        self.run_id = run_id
        self.held = False
        #: The exact bytes this run wrote, so the release can recognise its own
        #: lock by CONTENT rather than by the pathname it used to occupy.
        self._payload = None
        #: Set when the release could not account for what it found.
        self.release_failure = None

    def acquire(self):
        payload = json.dumps({"run_id": self.run_id, "pid": os.getpid(),
                              "finalizer_version": "runtime"},
                             sort_keys=True).encode("utf-8")
        try:
            _write_new(self.path, payload,
                       exists_code="FINALIZER_LOCK_HELD",
                       exists_why=self._held_by())
        except FinalizerError:
            raise
        self._payload = payload
        self.held = True
        return self

    def _held_by(self):
        """Describe the existing lock WITHOUT removing or reusing it.

        A lock whose owner this run cannot account for is not scratch to be
        cleaned up: it is either a live finalization or the debris of one that
        died mid-transaction, and both need a human to look before a second
        run starts moving the same files aside.
        """
        try:
            with open(self.path, "rb") as handle:
                body = handle.read(400).decode("utf-8", "replace").strip()
        except OSError as exc:
            body = f"<unreadable: {exc}>"
        return (f"{self.path} already exists: another finalization holds this "
                f"lock, or an earlier one died holding it ({body}). This run "
                f"refuses and changes nothing. The lock is NOT removed or "
                f"reused automatically - an unaccounted lock must be resolved "
                f"by an operator who has checked what the previous run left "
                f"behind")

    def release(self):
        """Remove ONLY a lock this run still owns, without racing the check.

        Reading the lock, deciding the run id is ours and THEN unlinking the
        pathname is the same defect as everywhere else in this module: an
        operator who resolved an abandoned lock and started a second
        finalization in that window had their live lock deleted by the first
        run's cleanup, and two finalizations then moved the same files aside.

        So the lock is MOVED into a run-owned slot in one rename and the object
        that actually moved is inspected. Ours - dropped. Anybody's - put back
        under its own name, or retained in the slot if the name has been taken
        again, and reported either way.
        """
        if not self.held:
            return
        self.held = False
        slot = self.path.with_name(f"{self.path.name}.release-{self.run_id}")
        try:
            taken = _quarantine(self.path, slot,
                                code="FINALIZER_LOCK_UNRELEASABLE",
                                why=f"the lock {self.path} could not be "
                                    f"released safely")
        except FinalizerError as exc:
            self.release_failure = exc.why
            return
        if taken.state == "absent":
            self.release_failure = (
                f"{self.path} was already gone when this run released it; "
                f"another process removed a lock it did not own")
            return
        if taken.matches(self._payload):
            _unlink_owned(taken.slot, "the quarantined lock")
            return
        where = _return_to_place(taken, self.path)
        self.release_failure = (
            f"{self.path} no longer held this run's lock when it was released; "
            f"the object found there is preserved at {where or taken.slot} and "
            f"was NOT deleted")


def _acquire_finalizer_locks(repo_root, staging, run_id):
    """Lock the worktree and the staging area, or acquire neither.

    If the second lock cannot be taken the first is released, so a refused run
    leaves no lock of its own behind.
    """
    root = Path(repo_root)
    worktree = _Lock(_run_owned_dir(root, WORKTREE_LOCK_NAME,
                                    "FINALIZER_LOCK_UNPLACEABLE"), run_id)
    staging_lock = _Lock(Path(staging) / STAGING_LOCK_NAME, run_id)
    worktree.acquire()
    try:
        staging_lock.acquire()
    except BaseException:
        worktree.release()
        raise
    return [worktree, staging_lock]


def _snapshot_moved_predecessor(displaced, predecessor, pred_dir, run_id):
    """Record bytes that were moved aside but are NOT the ones we snapshotted.

    The original private snapshot is NEVER overwritten. Copying the moved bytes
    over it was the defect: a copy that failed halfway left a PARTIAL private
    file, the code had already decided the moved file was untrustworthy, and
    the rollback would then have restored a truncated archive - or deleted the
    complete moved file in favour of it.

    So the moved bytes go into a SECOND snapshot, created exclusively, and the
    expected identity moves to them only after that second snapshot is verified
    complete. If it cannot be made or cannot be verified, the intact moved file
    stays exactly where it is, the original snapshot stays exactly as it was,
    and BOTH recovery paths are reported.
    """
    moved_sha = sha256_file(displaced)
    moved_bytes = displaced.stat().st_size
    predecessor["moved_path"] = displaced
    predecessor["moved_sha256"] = moved_sha
    predecessor["moved_bytes"] = moved_bytes
    predecessor["mutated_after_snapshot"] = True

    second = Path(pred_dir) / f"predecessor_moved_{run_id}.zip"
    try:
        _exclusive_copy(displaced, second)
    except (FinalizerError, OSError) as exc:
        predecessor["second_snapshot_failed"] = str(exc)
        return predecessor
    # Verify the SECOND snapshot completely before anything depends on it.
    try:
        ok = (sha256_file(second) == moved_sha
              and second.stat().st_size == moved_bytes
              and sha256_file(displaced) == moved_sha)
    except OSError as exc:
        predecessor["second_snapshot_failed"] = str(exc)
        return predecessor
    if not ok:
        predecessor["second_snapshot_failed"] = (
            "the second snapshot does not match the moved bytes")
        # A partial or mismatched copy is not a recovery source. Remove it so
        # nothing can later select it over the complete moved file.
        _unlink_owned(second, "the rejected second predecessor snapshot")
        return predecessor
    predecessor["second_snapshot_path"] = second
    #: Only NOW does the identity the rollback restores become the moved bytes.
    predecessor["sha256"] = moved_sha
    predecessor["bytes"] = moved_bytes
    return predecessor


def _output_slot(path, run_id, tag):
    """A run-owned quarantine slot beside ``path``.

    Beside it deliberately: ``os.replace`` is only atomic within one
    filesystem, and the staging directory is the one place guaranteed to be on
    the same filesystem as the destination. The name carries no
    RELEASE_TEMP_TOKEN, so a retained slot is never mistaken for abandoned
    scratch and swept away by a later run - it is evidence, and it is reported.
    """
    return Path(path).with_name(
        f"{Path(path).name}.{tag}-{run_id or 'norun'}.quarantine")


def _rollback_output(destination, displaced, placed, predecessor=None,
                     owned_tmp=None, placed_sha256=None, run_id="",
                     temporaries=None):
    """Undo archive placement BYTE-EXACTLY, and prove it.

    The predecessor is restored from the move-aside file only if that file
    still hashes to the private snapshot taken before placement; otherwise it
    is restored from the private snapshot itself. Either way the restored
    bytes are re-hashed. Every failure is collected, and the caller turns a
    non-empty list into ROLLBACK_FAILED - nothing escapes as an exception and
    nothing is assumed to have worked.
    """
    failures = []
    if not placed and displaced is None and owned_tmp is None:
        # Nothing was ever placed, moved aside, or created by THIS run, so
        # there is nothing to undo. In particular a PRE-EXISTING stale
        # temporary - the condition that refuses the run in the first place -
        # is left exactly where it is for the operator to account for, not
        # quietly deleted by the rollback.
        return {"placed": False, "displaced": "", "owned_tmp": "",
                "restored_destination_sha256": None, "failures": []}

    # Only a temporary THIS run created is removed. A partial copy2 that
    # raised before placement leaves one behind even when no predecessor
    # existed, and it must not survive.
    tmp_out = Path(owned_tmp) if owned_tmp is not None else None
    retained = {}
    if tmp_out is not None:
        # BY IDENTITY, through the run's temporaries journal - not "it is a
        # regular file, therefore it is ours". The rollback used to delete
        # whatever regular file was sitting at the temporary path, which is the
        # same defect the success path had: a replacement that arrived in the
        # window was destroyed by the cleanup that followed it.
        journal = (temporaries if temporaries is not None
                   else _RunTemporaries(run_id or "norun"))
        if not journal.discard(tmp_out,
                               what="the release output temporary"):
            failures.extend(journal.failures)
            journal.failures = []
            retained.update(journal.retained)
    # Undoing the placement means removing OUR archive - not whatever happens
    # to be at the destination now. If another process rewrote it between the
    # placement and this rollback, those bytes are somebody else's work: they
    # are neither deleted nor restored over, and the refusal is reported so
    # the operator resolves it rather than discovering it afterwards.
    concurrent_at_destination = False
    if placed:
        # QUARANTINE FIRST. Hashing the destination and then unlinking the
        # PATHNAME was a data-loss race in its own right: a process that
        # rewrote the archive in that window had its bytes deleted by a
        # rollback that had already satisfied itself the archive was ours. The
        # object is moved in one rename and then inspected, so what is judged
        # is what was taken.
        try:
            taken = _quarantine(
                destination, _output_slot(destination, run_id, "placed"),
                code="ROLLBACK_QUARANTINE_FAILED",
                why="the placed archive could not be quarantined")
        except FinalizerError as exc:
            concurrent_at_destination = True
            failures.append(
                f"the placed archive could not be moved aside before removal, "
                f"so it cannot be shown to be the archive this run wrote; it "
                f"is left in place: {exc.why}")
        else:
            if taken.state == "absent":
                pass                       # already gone; nothing to remove
            elif not taken.regular:
                concurrent_at_destination = True
                where = _return_to_place(taken, destination)
                retained["destination"] = where or str(taken.slot)
                what = taken.why or "a non-regular object"
                failures.append(
                    f"the destination held {what}, not the archive this run "
                    f"placed; it is preserved at {where or taken.slot}")
            elif placed_sha256 is not None and \
                    sha256_bytes(taken.data) != placed_sha256:
                concurrent_at_destination = True
                where = _return_to_place(taken, destination)
                retained["destination"] = where or str(taken.slot)
                failures.append(
                    f"the destination no longer holds the bytes this run "
                    f"placed ({sha256_bytes(taken.data)} != {placed_sha256}); "
                    f"another process rewrote it, this rollback did not delete "
                    f"bytes it did not write, and those bytes are at "
                    f"{where or taken.slot}")
            else:
                # OUR archive, and it is already out of the destination. The
                # slot is a run-owned name, so dropping it cannot destroy
                # anybody's work.
                _unlink_owned(taken.slot,
                              "the quarantined placed archive", failures)

    if displaced is not None and not placed and not concurrent_at_destination \
            and os.path.lexists(destination):
        # Nothing was ever placed, so the destination should be empty. Bytes
        # there came from somewhere else after the move-aside.
        concurrent_at_destination = True
        failures.append(
            "the destination was recreated after the move-aside by another "
            "process")

    if displaced is not None and concurrent_at_destination:
        # Restoring the predecessor here would overwrite the concurrent
        # writer's bytes with an older archive - a data-losing "repair".
        failures.append(
            "the predecessor was not restored: doing so would overwrite "
            "bytes written independently at the destination. The predecessor "
            "is preserved and its recovery path is reported")
    elif displaced is not None:
        want = (predecessor or {}).get("sha256")
        source = None
        # PREFERENCE ORDER, and it matters: the complete moved file first, then
        # a FULLY VERIFIED second snapshot of it, then the original private
        # snapshot. A partial copy is never a candidate, and the complete moved
        # file is never deleted in favour of one.
        if displaced.exists():
            try:
                if want is None or sha256_file(displaced) == want:
                    source = displaced
                else:
                    failures.append(
                        "the move-aside predecessor no longer hashes to the "
                        "identity recorded for it; it is retained and a "
                        "verified snapshot is used instead")
            except OSError as exc:
                failures.append(f"move-aside predecessor unreadable: {exc}")
        for key in ("second_snapshot_path", "path"):
            if source is not None:
                break
            candidate = (predecessor or {}).get(key)
            if not candidate or not Path(candidate).is_file():
                continue
            try:
                if want is None or sha256_file(candidate) == want:
                    source = Path(candidate)
            except OSError as exc:
                failures.append(f"{key} unreadable: {exc}")
        if source is None:
            failures.append("no intact predecessor copy is available")
        if source is not None:
            try:
                # NO-CLOBBER in both branches. os.replace would overwrite a
                # destination recreated during the restore itself.
                _link_no_clobber(
                    source, destination,
                    exists_code="RELEASE_DESTINATION_RECREATED",
                    exists_why=(
                        f"{destination} was recreated during the restore; the "
                        f"predecessor is retained at {source} rather than "
                        f"overwriting bytes this run did not write"))
            except FinalizerError as exc:
                failures.append(f"predecessor not restored: {exc.why}")
            except OSError as exc:
                failures.append(f"predecessor not restored: {exc}")
            else:
                # Only after the destination genuinely holds the bytes again -
                # and even then through the quarantine, never through a
                # pathname unlink. The move-aside path is a name like any
                # other and can be re-occupied between the restore and the
                # cleanup.
                if source == displaced:
                    try:
                        taken = _quarantine(
                            displaced,
                            _output_slot(displaced, run_id, "moveaside"),
                            code="ROLLBACK_QUARANTINE_FAILED",
                            why="the move-aside copy could not be quarantined")
                    except FinalizerError as exc:
                        failures.append(
                            f"the move-aside copy could not be removed after "
                            f"a verified restore: {exc.why}")
                    else:
                        if taken.state == "taken" and taken.regular and (
                                want is None
                                or sha256_bytes(taken.data) == want):
                            _unlink_owned(taken.slot,
                                      "the quarantined predecessor")
                        elif taken.state == "taken":
                            where = _return_to_place(taken, displaced)
                            retained["move_aside"] = where or str(taken.slot)
                            failures.append(
                                f"the move-aside path no longer held the "
                                f"predecessor after the restore; what was "
                                f"there is preserved at "
                                f"{where or taken.slot} rather than deleted")

        # Verify the restoration rather than assuming it.
        if source is not None and source == displaced and displaced.exists():
            failures.append("the displaced predecessor was not moved back")
        if not destination.exists():
            failures.append("the predecessor is missing from the destination")
        elif want is not None:
            try:
                got = sha256_file(destination)
            except OSError as exc:
                failures.append(f"restored output unreadable: {exc}")
            else:
                if got != want:
                    failures.append(
                        f"restored predecessor hashes {got}, expected {want}")
                else:
                    try:
                        size = destination.stat().st_size
                    except OSError as exc:
                        failures.append(f"restored output unstattable: {exc}")
                    else:
                        if size != predecessor.get("bytes"):
                            failures.append(
                                "restored predecessor byte count differs")

    if tmp_out is not None and os.path.lexists(tmp_out):
        failures.append("temporary output survived")
    try:
        strays = sorted(
            q.name for q in destination.parent.glob("*finalizer-tmp*")
        ) if destination.parent.is_dir() else []
    except OSError as exc:
        strays = []
        failures.append(f"staging directory unreadable: {exc}")
    if strays:
        failures.append(f"temporary files survived: {strays}")
    try:
        restored = sha256_file(destination) if destination.is_file() else None
    except OSError as exc:
        restored = None
        failures.append(f"restored output unreadable: {exc}")
    recovery = {}
    for key in ("path", "second_snapshot_path", "moved_path"):
        value = (predecessor or {}).get(key)
        if value and Path(value).exists():
            recovery[key] = str(value)
    if displaced is not None and displaced.exists():
        recovery["displaced"] = str(displaced)
    recovery.update(retained)
    return {"placed": placed, "displaced": str(displaced or ""),
            "owned_tmp": str(owned_tmp or ""),
            "restored_destination_sha256": restored,
            "quarantine_retained": retained,
            "predecessor_recovery_paths": recovery, "failures": failures}


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


def _git_capture(args, *, code="VALIDATION_TREE_UNBUILDABLE", why=""):
    """One git command under the sanitized environment, or a refusal."""
    proc = subprocess.run(["git", *[str(a) for a in args]],
                          capture_output=True, env=_git_env())
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()[:300]
        raise FinalizerError(
            code, f"{why or 'git ' + ' '.join(str(a) for a in args[:3])} "
                  f"failed: {detail}")
    return proc.stdout


def _mode_scan(records, where):
    """Parse ``<mode> <sha> <stage>\\t<path>`` records, refusing links/gitlinks.

    Applied to the SOURCE INDEX and to the COMMITTED TREE alike. A tracked
    symlink or gitlink in either one refuses the run: the index is what the
    operator is about to release, the tree is what the validation copy will
    actually contain, and neither may carry an object the copy cannot honestly
    reproduce.
    """
    entries = {}
    for record in records.split(b"\0"):
        if not record:
            continue
        try:
            meta, rel = record.split(b"\t", 1)
            fields = meta.split()
            mode = fields[0].decode("ascii")
            rel = rel.decode("utf-8")
        except (ValueError, UnicodeDecodeError, IndexError):
            raise FinalizerError(
                "VALIDATION_TREE_UNBUILDABLE",
                f"unparsable git record in {where}: {record[:80]!r}")
        if mode == "120000":
            raise FinalizerError(
                "VALIDATION_TREE_SYMLINK",
                f"{rel} is a tracked SYMLINK in {where}; the validation tree "
                f"is built from regular files only, so a link that resolves "
                f"outside the repository cannot be reproduced inside it")
        if mode == "160000":
            raise FinalizerError(
                "VALIDATION_TREE_SUBMODULE",
                f"{rel} is a gitlink in {where}; the validation tree has no "
                f"submodule content and would validate a hole")
        entries[rel] = mode
    return entries


def _clone_repository_at_head(src, dest, *, expected_head=None,
                              expected_branch=None, indexed=None):
    """Build ``dest`` as an INDEPENDENT clean repository at the expected head.

    The previous implementation called ``_copy_git_dir(src / ".git", ...)`` and
    walked it as a directory tree. ``.git`` is NOT a directory in a linked
    worktree - it is a file holding ``gitdir: <path>`` - and this repository is
    checked out exactly that way, so every real run refused with
    VALIDATION_TREE_UNBUILDABLE before it validated anything at all. Copying
    the administrative directory file-by-file was also copying live state:
    ``index``, ``HEAD``, reflogs and any half-written lock the source happened
    to hold at that instant.

    So the tree is not copied. It is CLONED, from committed objects, and then
    checked out at the exact head the run was invoked for:

    * ``git clone --no-hardlinks --no-checkout`` gives ``dest`` its own real
      ``.git`` DIRECTORY with its own object store, its own refs and its own
      index - independent of the source, and correct whether the source is a
      normal checkout, a linked worktree or a submodule;
    * the full history and every tag come with it, because the repository
      guards resolve explicit historical commits with ``cat-file`` and
      ``ls-tree`` and a shallow copy would make those checks vanish rather
      than fail;
    * the checkout materialises the COMMITTED bytes. Nothing the worktree
      happens to be holding - an uncommitted edit, a transient mutation of a
      test made while the copy was being prepared - can reach the validation
      tree, because the worktree is never read.

    Every git subprocess here runs under ``_git_env``, so an ambient
    ``GIT_DIR`` cannot redirect the clone at a different repository.
    """
    src = Path(src)
    dest = Path(dest)

    head = _git_capture(["-C", src, "rev-parse", "HEAD"],
                        why=f"resolving HEAD in {src}").decode().strip()
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise FinalizerError("VALIDATION_TREE_UNBUILDABLE",
                             f"{src} HEAD resolved to {head!r}")
    if expected_head and head != expected_head:
        raise FinalizerError(
            "VALIDATION_TREE_HEAD_MISMATCH",
            f"{src} is at {head}, the run was invoked for {expected_head}; "
            f"the validation tree is built from committed objects at the "
            f"expected head and will not be built from a different commit")

    # The committed tree, scanned before anything is written.
    tree_entries = _mode_scan(
        _git_capture(["-C", src, "ls-tree", "-r", "-z", head],
                     why=f"listing the tree at {head}"),
        f"the committed tree at {head}")

    if dest.exists() and any(dest.iterdir()):
        raise FinalizerError(
            "VALIDATION_TREE_UNBUILDABLE",
            f"{dest} already has content; this run will not build a validation "
            f"tree on top of somebody else's directory")

    _git_capture(["clone", "--no-hardlinks", "--no-checkout", "--quiet",
                  src, dest], why=f"cloning {src}")

    _git_capture(["-C", dest, "cat-file", "-e", f"{head}^{{commit}}"],
                 why=f"the cloned repository does not carry {head}")
    branch = expected_branch or "scorch-validation"
    _git_capture(["-C", dest, "checkout", "--quiet", "-B", branch, head],
                 why=f"checking {head} out in {dest}")

    # ---- verify the copy IS the thing it claims to be, before it is edited --
    got_head = _git_capture(["-C", dest, "rev-parse", "HEAD"]).decode().strip()
    if got_head != head:
        raise FinalizerError(
            "VALIDATION_TREE_HEAD_MISMATCH",
            f"the validation clone is at {got_head}, expected {head}")
    want_tree = _git_capture(["-C", src, "rev-parse",
                              f"{head}^{{tree}}"]).decode().strip()
    got_tree = _git_capture(["-C", dest, "rev-parse",
                             "HEAD^{tree}"]).decode().strip()
    if got_tree != want_tree:
        raise FinalizerError(
            "VALIDATION_TREE_IDENTITY_MISMATCH",
            f"the validation clone's tree is {got_tree}, the source's tree at "
            f"{head} is {want_tree}")
    copy_entries = _mode_scan(
        _git_capture(["-C", dest, "ls-files", "-s", "-z"]),
        "the validation clone index")
    if set(copy_entries) != set(tree_entries):
        missing = sorted(set(tree_entries) - set(copy_entries))[:5]
        extra = sorted(set(copy_entries) - set(tree_entries))[:5]
        raise FinalizerError(
            "VALIDATION_TREE_INCOMPLETE",
            f"the validation clone's tracked set differs from the committed "
            f"tree: missing={missing} unexpected={extra}")
    dirty = _git_capture(["-C", dest, "status", "--porcelain=v1"]).decode(
        "utf-8", "replace").strip()
    if dirty:
        raise FinalizerError(
            "VALIDATION_TREE_UNBUILDABLE",
            f"the freshly built validation tree is already dirty: "
            f"{dirty.splitlines()[:5]}")
    admin = dest / ".git"
    if admin.is_symlink() or not admin.is_dir():
        raise FinalizerError(
            "VALIDATION_TREE_UNBUILDABLE",
            f"{admin} is not a real git directory; the repository guards need "
            f"one to run against")
    return {"head": head, "branch": branch, "tree": got_tree,
            "tracked_files": len(copy_entries),
            "indexed_files": len(indexed or {}),
            "source_git_dir": str(_git_admin_dir(src) or "")}


def _copy_repository(src, dest, contract=None, expected_head=None,
                     expected_branch=None):
    """Build the disposable validation tree from COMMITTED CONTENT, explicitly.

    The previous version was ``shutil.copytree(..., symlinks=True)`` minus four
    names. That copied every ignored artifact in the worktree - editor scratch,
    stale outputs, half-written downloads, anything a previous run left - and
    it copied SYMLINKS as symlinks, so a link pointing outside the repository
    arrived in the validation tree still pointing outside it. The release is
    accepted on the strength of what this tree contains, so what it contains is
    now enumerated rather than swept up:

    * every file git tracks, by its COMMITTED bytes at the expected head,
      regular files only, materialised by a checkout of a real clone;
    * a real, independent ``.git`` DIRECTORY carrying the history and refs the
      repository guards need in order to run at all - not a copy of the
      source's administrative directory, which in a linked worktree is a file
      and in any worktree is live mutable state;
    * and nothing else, except entries on an explicit allowlist of required
      ignored artifacts, each of which must match a hash pinned in the trusted
      contract.

    A tracked symlink, a gitlink, or an allowlisted artifact whose bytes do not
    match its pin is a refusal, not a warning. So is a source whose head is not
    the head the run was invoked for.
    """
    src = Path(src)
    dest = Path(dest)

    # The SOURCE INDEX first, as a refusal surface in its own right. It is what
    # the operator is about to release, and a symlink or gitlink staged there
    # is a defect whether or not it has reached a commit yet.
    indexed = _mode_scan(
        _git_capture(["-C", src, "ls-files", "-s", "-z"],
                     why=f"listing the index in {src}"),
        f"the index of {src}")

    clone = _clone_repository_at_head(
        src, dest, expected_head=expected_head,
        expected_branch=expected_branch, indexed=indexed)
    copied = clone["tracked_files"]

    # The explicit allowlist of ignored artifacts, each hash-verified.
    allowed = ((contract or {}).get("validation_copy") or {}).get(
        "ignored_allowlist") or []
    admitted = []
    for entry in allowed:
        rel = entry.get("path")
        want = entry.get("sha256")
        if not rel or not want:
            raise FinalizerError(
                "VALIDATION_ALLOWLIST_UNPINNED",
                f"the validation-copy allowlist entry {entry!r} carries no "
                f"path/sha256 pair; an unpinned ignored artifact is exactly "
                f"the arbitrary content this allowlist exists to exclude")
        source = src / rel
        data = _read_regular_file(source)
        if data is None:
            raise FinalizerError(
                "VALIDATION_ALLOWLIST_MISSING",
                f"the allowlisted artifact {rel} is not present in {src}")
        got = sha256_bytes(data)
        if got != want:
            raise FinalizerError(
                "VALIDATION_ALLOWLIST_MISMATCH",
                f"{rel} hashes {got}, the contract pins {want}")
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_new(target, data,
                   exists_code="VALIDATION_TREE_UNBUILDABLE",
                   exists_why=f"{rel} collides with tracked content")
        admitted.append(rel)
    return {"tracked_files": copied, "allowlisted": admitted,
            "head": clone["head"], "branch": clone["branch"],
            "tree": clone["tree"], "indexed_files": clone["indexed_files"],
            "built_from": "committed objects"}


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
        # There is deliberately NO --contract option. The contract decides who
        # may authorize the release, what text counts, which assets the licence
        # reaches and what the activation may touch; an override would let an
        # operator redefine all of that from outside the repository. Production
        # reads only the tracked contract at HEAD - see load_trusted_contract.
        p.add_argument("--candidate-archive")
        p.add_argument("--final-docx-dir")
        p.add_argument("--aptos-font")
        p.add_argument("--format", choices=("text", "json", "both"),
                       default="both")

    common(sub.add_parser("preflight",
                          help="read-only verification; writes nothing"))
    fin = sub.add_parser("finalize", help="gated, transactional finalization")
    common(fin)
    # An EXPLICIT destination. The archive is never written to a path derived
    # from the repository's parent directory.
    fin.add_argument("--release-staging", required=True)
    # There is deliberately NO --python option. The release is accepted on the
    # strength of a validator verdict and a pytest summary, and both are just
    # the standard output of whatever executable was named. A wrapper that
    # prints "PASS" and a clean summary is a two-line script, so production
    # runs the interpreter that is already running - see
    # _pinned_interpreter_issues for the only alternative, a contract pin.
    fin.add_argument("--confirm", default=None)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        contract, contract_identity = load_trusted_contract(args.repo_root)
    except FinalizerError as exc:
        report = Report(args.mode)
        report.fail(exc.code, exc.why)
        if args.format in ("text", "both"):
            print(report.to_text())
        if args.format in ("json", "both"):
            print(report.to_json())
        return 1
    common = dict(contract=contract,
                  candidate_archive=args.candidate_archive,
                  final_docx_dir=args.final_docx_dir,
                  aptos_font=args.aptos_font)
    if args.mode == "preflight":
        report = preflight(args.repo_root, args.expect_branch,
                           args.expect_head, **common)
    else:
        if not args.candidate_archive:
            report = Report("finalize")
            report.fail("TECHNICAL_SOURCE_MISSING",
                        "--candidate-archive is required: the final archive is "
                        "rebuilt from the pinned pre-D6 technical source, not "
                        "from an arbitrary staging directory")
            print(report.to_text())
            return 1
        report = finalize(args.repo_root, args.expect_branch,
                          args.expect_head,
                          release_staging=args.release_staging,
                          confirm=args.confirm, **common)
    report.note("trusted_contract", contract_identity)
    if args.format in ("text", "both"):
        print(report.to_text())
    if args.format in ("json", "both"):
        print(report.to_json())
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
