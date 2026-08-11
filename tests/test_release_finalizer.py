"""Adversarial guards for the post-D6 release finalizer.

Everything here runs against SYNTHETIC repositories built in ``tmp_path`` and
INJECTED fake GitHub responses. Nothing touches the real worktree, the real
pull request, or the real archives, and no fake approval evidence is ever
written anywhere a real run could find it.

The point of the suite is not that the happy path works. It is that each way
of getting the finalization wrong produces an ordinary nonzero failure with an
explicit code and NO partial write. A finalizer that half-applies an identity
update is worse than one that refuses.
"""
from __future__ import annotations

import csv
import io
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
_RELEASE_DIR = REPO / "scripts" / "release"

# Set before importing the finalizer. The module sets the same flag for its own
# imports, but the decision for THIS import is made here, by the importer.
sys.dont_write_bytecode = True

if str(_RELEASE_DIR) not in sys.path:
    sys.path.insert(0, str(_RELEASE_DIR))

import release_finalizer as rf  # noqa: E402  (sys.path set up just above)

AUTH_TEXT = json.loads(
    (_RELEASE_DIR / "finalizer_contract.json").read_text(encoding="utf-8")
)["authorization"]["text"]

OLD_SHA = "a" * 64
NEW_SHA = "b" * 64
OLD_ROOT = "c" * 64
NEW_ROOT = "d" * 64
ARCHIVE_NAME = "scorch_processed_data_v1.0.0.zip"

# ---------------------------------------------------------------------------
# SYNTHETIC licence wording. This is test scaffolding, deliberately marked as
# such. The real CC BY activation prose is the authors' to write and does not
# exist yet; nothing here is a draft of it and nothing here may be copied into
# the repository.
# ---------------------------------------------------------------------------
def _guards():
    """The guard module, which owns the single TEST-ONLY synthetic clause."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_scorch_guards", REPO / "tests" / "test_public_consistency_guards.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


GUARDS = _guards()

#: The ONE synthetic active clause, imported rather than re-invented. Every
#: ACTIVE destination below emits it as a STANDALONE normalized block - its
#: own sentence, line or table cell - because classification compares whole
#: blocks, and a clause buried inside surviving pending prose is a block of
#: nothing. Three modules each inventing their own wording is exactly how the
#: registered marker stopped being a block of anything.
ACTIVE_CLAUSE = GUARDS.SYNTHETIC_ACTIVE_CLAUSE

THIRD_PARTY_TAIL = ("GPL-3.0-only applies to the software. Contains modified "
                    "Copernicus Climate Change Service information 2026. "
                    "GHCN-Daily terms apply. ERA5 data.")
PENDING_BLOCK = ("Figure 1 and Figure 4 artwork: CC BY 4.0 PENDING - not yet "
                 "in force.")
MANUSCRIPT_PENDING = ("This record states the CC BY 4.0 PENDING - not yet in "
                      "force status of the Figure 1 artwork.")
ARCHIVE_PENDING = ("Figure 1 and Figure 4 artwork: CC BY 4.0 PENDING - not "
                   "yet in force in this deposit.")
# Every destination is the clause and nothing else, so each retired pending
# block is replaced by a standalone affirmative block rather than having an
# active marker spliced into prose that still withholds the grant.
ACTIVE_BLOCK = ACTIVE_CLAUSE
MANUSCRIPT_ACTIVE = ACTIVE_CLAUSE
ARCHIVE_ACTIVE = ACTIVE_CLAUSE
PENDING_ROW = ("| `assets/frozen_figures/**` (Fig. 1, 4) | CC BY 4.0 PENDING "
               "-- not yet in force |")
ACTIVE_ROW = GUARDS.synthetic_active_row()

#: The SEVEN contracted artwork assets, mirroring the real contract's shape.
ARTWORK_PATHS = (
    "assets/frozen_figures/fig01/Figure_01.png",
    "assets/frozen_figures/fig01/Figure_01.pdf",
    "assets/frozen_figures/fig04/Figure_04.png",
    "assets/frozen_figures/fig04/Figure_04.pdf",
    "scripts/figures/fig01/original/Figure_01_original.png",
    "scripts/figures/fig04/original/Figure_04_original.png",
    "scripts/figures/fig04/donor/Figure_04_approved_horizontal.png",
)


def _artwork_bytes(rel):
    """Distinct synthetic bytes per artwork path, so hashes really differ."""
    return f"SYNTHETIC-ARTWORK::{rel}\n".encode("utf-8")


def full_activation_plan(overrides=None, drop=None):
    """A COMPLETE five-surface activation plan, in synthetic wording.

    Complete by default so that a test perturbing one entry is testing the
    thing it names, rather than tripping the completeness check first.
    """
    plan = [
        {"file": "docs/LICENSES_AND_ATTRIBUTION.md", "from": PENDING_BLOCK,
         "to": ACTIVE_BLOCK, "count": 1},
        {"file": "assets/frozen_figures/README.md", "from": PENDING_BLOCK,
         "to": ACTIVE_BLOCK, "count": 1},
        {"file": "assets/manuscript_final/README.md",
         "from": MANUSCRIPT_PENDING, "to": MANUSCRIPT_ACTIVE, "count": 1},
        {"file": ".zenodo.json", "from": PENDING_BLOCK, "to": ACTIVE_BLOCK,
         "count": 1},
        {"file": rf.ARCHIVE_FILE_PREFIX + "LICENSE.txt",
         "from": ARCHIVE_PENDING, "to": ARCHIVE_ACTIVE, "count": 1},
    ]
    if drop:
        plan = [p for p in plan if p["file"] not in set(drop)]
    for item in plan:
        if overrides and item["file"] in overrides:
            item.update(overrides[item["file"]])
    return {"authored": True, "replacements": plan}


# ---------------------------------------------------------------------------
# Synthetic fixtures
# ---------------------------------------------------------------------------
class FakeGitHub:
    """An injected GitHub. Tests pass an instance; production never can."""

    def __init__(self, pr=None, comments=None, live=None, missing=False,
                 sequence=None):
        self._pr = pr if pr is not None else {}
        self._comments = list(comments or [])
        self._live = live
        self._missing = missing
        #: successive responses for repeated issue_comment calls, so a comment
        #: edited BETWEEN the two live reads can be simulated
        self._sequence = list(sequence) if sequence else None
        self.comment_fetches = 0

    def pull_request(self, owner, repo, number):
        return self._pr

    def issue_comments(self, owner, repo, number):
        return self._comments

    def issue_comment(self, owner, repo, comment_id):
        self.comment_fetches += 1
        if self._missing:
            raise rf.FinalizerError("GITHUB_API_UNAVAILABLE",
                                    f"comment {comment_id} is gone")
        if self._sequence:
            idx = min(self.comment_fetches - 1, len(self._sequence) - 1)
            return self._sequence[idx]
        if self._live is not None:
            return self._live
        for c in self._comments:
            if c["id"] == comment_id:
                return c
        raise rf.FinalizerError("GITHUB_API_UNAVAILABLE", "no such comment")


EXPECTED_ISSUE_URL = ("https://api.github.com/repos/fawazbouhamad/SCORCH"
                      "/issues/1")


def comment(body=AUTH_TEXT, login="nassernajibi", cid=101,
            owner="fawazbouhamad", repo="SCORCH", number=1, issue_url=None,
            created="2026-01-01T00:00:00Z", updated=None):
    return {"id": cid, "user": {"login": login}, "body": body,
            "html_url": f"https://github.com/{owner}/{repo}/pull/{number}"
                        f"#issuecomment-{cid}",
            "issue_url": (issue_url if issue_url is not None
                          else f"https://api.github.com/repos/{owner}/{repo}"
                               f"/issues/{number}"),
            "created_at": created,
            "updated_at": updated if updated is not None else created}


def _run(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True,
                   capture_output=True)


def _rev(root, ref):
    return subprocess.run(["git", "-C", str(root), "rev-parse", ref],
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def synthetic(tmp_path):
    """A synthetic repository plus the contract that describes it.

    Small enough to build per test, structured exactly like the real thing:
    eight identity files carrying 56 references, two protected records, four
    licence records, pinned figures and DOCX fixtures.
    """
    root = tmp_path / "repo"
    root.mkdir()

    def write(rel, text):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")

    # 8 identity files / 56 references, mirroring the real distribution.
    write("remediation/corrected_outputs/SHA256_MANIFEST.json", json.dumps({
        "relocation": {"packages": {"PKG-DATA-V1": {
            "archive_filename": ARCHIVE_NAME, "archive_sha256": OLD_SHA,
            "archive_bytes": 1234, "content_root_hash": OLD_ROOT,
            "member_count": 3}}}}, indent=2))
    rows = ["old_repository_path,archive_member_path,member_sha256,"
            "member_bytes,archive_filename,archive_sha256"]
    for i in range(21):
        rows.append(f"old/{i}.txt,payload/{i}.txt,{'e' * 64},{i},"
                    f"{ARCHIVE_NAME},{OLD_SHA}")
    write("docs/RELOCATED_ARTIFACTS.csv", "\n".join(rows) + "\n")
    write("docs/CANONICAL_SCIENCE.json", json.dumps(
        {"archive": ARCHIVE_NAME, "sha256": OLD_SHA, "bytes": 1234}, indent=2))
    write("legacy_defective_figure09/README.md",
          f"{ARCHIVE_NAME}\n{OLD_SHA}\n{ARCHIVE_NAME}\n")
    # The collision case: this ONE file carries both the archive identity and
    # the licence wording, so the two edit plans overlap on it.
    write("assets/manuscript_final/README.md",
          f"{MANUSCRIPT_PENDING} Deposit: {ARCHIVE_NAME}\n")
    write("remediation/xlsx_equivalence/XLSX_SEMANTIC_EQUIVALENCE_REPORT.md",
          f"{ARCHIVE_NAME}\n")
    write("tests/test_public_consistency_guards.py",
          f'ARCHIVE = "{ARCHIVE_NAME}"\n')
    write("tests/test_stale_provenance.py", f'ARCHIVE = "{ARCHIVE_NAME}"\n')

    hist = "8ec500baae6a62642f5bd37799780eb70214b5ddc8f66c06c72b62a20118af6c"
    write("remediation/corrected/event_global_max_algorithm/"
          "build_manifest.json", json.dumps({"netcdf_sha256": hist}))
    write("remediation/freeze/freeze_manifest_pre.json",
          json.dumps({"netcdf_sha256": hist}))

    for rel in ("docs/LICENSES_AND_ATTRIBUTION.md",
                "assets/frozen_figures/README.md"):
        write(rel, PENDING_BLOCK + " " + THIRD_PARTY_TAIL + "\n")
    # A real JSON record, so structure preservation and duplicate-key
    # rejection are exercised rather than skipped. The artwork block sits in
    # the MIDDLE of the notes string, bounded by sentence terminators on both
    # sides: a JSON value is one physical line prefixed by its key, so a block
    # at the very start of the string would normalize to `"notes": "<block>`
    # and never be a block of its own.
    write(".zenodo.json", json.dumps(
        {"title": "SCORCH", "license": "GPL-3.0-only",
         "notes": THIRD_PARTY_TAIL + " " + PENDING_BLOCK +
                  " End of synthetic notes."}, indent=2))
    # ALL SEVEN contracted artwork assets, not one. The previous fixture
    # licensed a single file, so "the receipt covers all seven artwork paths"
    # was asserted against a one-element list and proved nothing.
    for rel in ARTWORK_PATHS:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(_artwork_bytes(rel))

    # The superseded official archive, INSIDE the repository, sharing its
    # filename with the archive that will be released. It must survive every
    # outcome byte-identical.
    old_archive = root / "release_staging" / ARCHIVE_NAME
    old_archive.parent.mkdir(parents=True, exist_ok=True)
    old_archive.write_bytes(b"SUPERSEDED OFFICIAL ARCHIVE - PRESERVE ME\n")

    docx_dir = tmp_path / "docx"
    docx_dir.mkdir()
    (docx_dir / "M.docx").write_bytes(b"MANUSCRIPT")
    font = tmp_path / "aptos.ttf"
    font.write_bytes(b"APTOS")

    _run(root, "init", "-q", "-b", "chore/final-repository-cleanup")
    _run(root, "config", "user.email", "t@example.invalid")
    _run(root, "config", "user.name", "T")
    _run(root, "add", "-A")
    _run(root, "commit", "-qm", "synthetic")
    head = _rev(root, "HEAD")
    _run(root, "update-ref",
         "refs/remotes/origin/chore/final-repository-cleanup", head)
    _run(root, "update-ref", "refs/remotes/origin/main", head)
    _run(root, "tag", "-a", "v1.0.0", "-m", "v1.0.0")

    contract = {
        "repository": {
            "owner": "fawazbouhamad", "name": "SCORCH", "pull_request": 1,
            "base_branch": "main",
            "head_branch": "chore/final-repository-cleanup",
            "expected_main_commit": head, "expected_tag": "v1.0.0",
            "expected_tag_object": _rev(root, "v1.0.0"),
            "expected_tag_commit": head},
        "authorization": {
            "required_login": "nassernajibi", "text": AUTH_TEXT,
            "live_fetches_required": 2,
            "expected_issue_url": EXPECTED_ISSUE_URL,
            "cross_read_agreement_fields": ["id", "body", "created_at",
                                            "updated_at", "html_url",
                                            "issue_url", "user"]},
        # Declared a TEST FIXTURE, which is what permits the TEST-ONLY
        # synthetic clause below. A production contract carries no such
        # declaration and the finalizer refuses TEST-ONLY wording in it.
        "synthetic_fixture": True,
        "artwork_licence_markers": {
            "pending": ["CC BY 4.0 PENDING"],
            "active": [ACTIVE_CLAUSE]},
        "authorization_receipt": {
            "schema_version": "1.0.0",
            "tracked_path": "docs/FIGURE_01_04_CC_BY_AUTHORIZATION_RECEIPT"
                            ".json",
            "must_not_exist_before_authorization": True,
            "required_fields": [
                "schema_version", "repository", "pull_request", "permalink",
                "comment_id", "login", "created_at", "updated_at", "body",
                "body_sha256", "licensed_artwork", "activated_at",
                "finalizer_version", "starting_head"]},
        "finalizer_version": "4D-r1-test",
        "identity": {
            "package_record":
                "remediation/corrected_outputs/SHA256_MANIFEST.json",
            "package_id": "PKG-DATA-V1",
            "final_archive_filename": ARCHIVE_NAME,
            "expected_file_count": 8, "expected_reference_count": 56,
            "files": {
                "remediation/corrected_outputs/SHA256_MANIFEST.json": {
                    "archive_filename": 1, "archive_sha256": 1,
                    "archive_bytes": 1, "content_root_hash": 1},
                "docs/RELOCATED_ARTIFACTS.csv": {
                    "archive_filename": 21, "archive_sha256": 21},
                "docs/CANONICAL_SCIENCE.json": {
                    "archive_filename": 1, "archive_sha256": 1,
                    "archive_bytes": 1},
                "legacy_defective_figure09/README.md": {
                    "archive_filename": 2, "archive_sha256": 1},
                "assets/manuscript_final/README.md": {"archive_filename": 1},
                "remediation/xlsx_equivalence/"
                "XLSX_SEMANTIC_EQUIVALENCE_REPORT.md": {
                    "archive_filename": 1},
                "tests/test_public_consistency_guards.py": {
                    "archive_filename": 1},
                "tests/test_stale_provenance.py": {"archive_filename": 1}}},
        "protected_historical_records": [
            "remediation/corrected/event_global_max_algorithm/"
            "build_manifest.json",
            "remediation/freeze/freeze_manifest_pre.json"],
        "historical_netcdf_sha256": hist,
        "licence_records": ["docs/LICENSES_AND_ATTRIBUTION.md",
                            "assets/frozen_figures/README.md",
                            "assets/manuscript_final/README.md",
                            ".zenodo.json"],
        "expected_pending_marker_count": 4,
        "figures": {rel: rf.sha256_bytes(_artwork_bytes(rel))
                    for rel in ARTWORK_PATHS},
        "ccby_artwork_paths": list(ARTWORK_PATHS),
        # SYNTHETIC authored row. An authored activation plan and an
        # unauthored publication row are incoherent - the tree would activate
        # and the published table would have nothing to say - so the base
        # fixture carries both. The refusal when it is absent is asserted
        # explicitly by test_an_authored_plan_without_an_active_row_is_refused.
        "publication_outputs_artwork_row": {
            "pending": PENDING_ROW, "active": ACTIVE_ROW},
        "ccby_excluded_scope": {"tokens": ["GPL-3.0-only", "ERA5",
                                           "GHCN-Daily", "Aptos", "software"]},
        "release_test_collection": {"node_id_count": None,
                                    "sorted_node_ids_sha256": None},
        "superseded_official_archive": {
            "filename": ARCHIVE_NAME,
            "path": f"release_staging/{ARCHIVE_NAME}",
            "sha256": rf.sha256_file(old_archive),
            "bytes": old_archive.stat().st_size},
        "third_party_rights_tokens": [
            "GPL-3.0-only",
            "Contains modified Copernicus Climate Change Service information",
            "GHCN-Daily", "ERA5"],
        "archive_topology": {
            "member_count": 3, "sums_entries": 2, "manifest_rows": 1,
            "relocation_rows": 21, "sums_member": "SHA256SUMS",
            "manifest_member": "FILE_MANIFEST.csv",
            "validator_member": "validate_deposit.py",
            "licence_member": "LICENSE.txt",
            "validator_verdict": {"pass_line": "PASS", "fail_line": "FAIL",
                                  "must_be_last_non_empty_line": True,
                                  "expected_verdict_lines": 1}},
        "docx_fixtures": {"M.docx": rf.sha256_bytes(b"MANUSCRIPT")},
        "aptos_font_sha256": rf.sha256_bytes(b"APTOS"),
        "ccby_activation_plan": {"authored": False, "replacements": []},
    }
    return {"root": root, "contract": contract, "head": head,
            "docx_dir": docx_dir, "font": font, "tmp": tmp_path}


def good_pr(head):
    return {"state": "open", "draft": True, "merged_at": None,
            "base": {"ref": "main"},
            "head": {"ref": "chore/final-repository-cleanup", "sha": head}}


def run_preflight(syn, github, **kw):
    return rf.preflight(syn["root"], "chore/final-repository-cleanup",
                        syn["head"], contract=syn["contract"], github=github,
                        final_docx_dir=syn["docx_dir"],
                        aptos_font=syn["font"], **kw)


def new_identity():
    return {"archive_filename": ARCHIVE_NAME, "archive_sha256": NEW_SHA,
            "archive_bytes": "999", "content_root_hash": NEW_ROOT}


def old_identity():
    return {"archive_filename": ARCHIVE_NAME, "archive_sha256": OLD_SHA,
            "archive_bytes": "1234", "content_root_hash": OLD_ROOT}


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in Path(root).rglob("*")
            if p.is_file() and ".git" not in p.parts}


# ---------------------------------------------------------------------------
# 1. Production has no bypass. This is the load-bearing test.
# ---------------------------------------------------------------------------
def test_production_source_has_no_local_approval_or_bypass():
    src = (_RELEASE_DIR / "release_finalizer.py").read_text(encoding="utf-8")
    for token in ("SCORCH_D6", "SKIP_D6", "FORCE_D6", "--force",
                  "--skip-authorization", "--assume-authorized",
                  "authorization_json", "AUTHORIZATION_FILE"):
        assert token not in src, f"bypass surface {token!r} present"
    # The authorization may be read from exactly one place: the injected
    # client's live API calls. No environment variable may reach it.
    body = src.split("def find_authorization", 1)[1].split("\ndef ", 1)[0]
    assert "environ" not in body, "find_authorization consults the environment"


def test_production_never_commits_pushes_tags_or_publishes():
    src = (_RELEASE_DIR / "release_finalizer.py").read_text(encoding="utf-8")
    for forbidden in ('"commit"', '"push"', '"merge"', '"tag"', "zenodo",
                      "gh release"):
        assert forbidden not in src, f"{forbidden} appears in production code"


def test_preflight_writes_nothing(synthetic):
    before = snapshot(synthetic["root"])
    run_preflight(synthetic, FakeGitHub(pr=good_pr(synthetic["head"])))
    assert snapshot(synthetic["root"]) == before


# ---------------------------------------------------------------------------
# 2. Authorization: every way of not having it
# ---------------------------------------------------------------------------
def test_missing_authorization_is_release_blocked_d6(synthetic):
    record, issues = rf.find_authorization(FakeGitHub(comments=[]),
                                           synthetic["contract"])
    assert record is None
    assert [c for c, _ in issues] == ["RELEASE_BLOCKED_D6"]


def test_wrong_author_is_rejected(synthetic):
    gh = FakeGitHub(comments=[comment(login="someone-else")])
    record, issues = rf.find_authorization(gh, synthetic["contract"])
    assert record is None
    assert [c for c, _ in issues] == ["RELEASE_BLOCKED_D6"]


def test_impersonated_body_from_wrong_login_is_rejected(synthetic):
    """The exact text signed by the wrong account authorizes nothing."""
    gh = FakeGitHub(comments=[comment(cid=7, login="nassernajibi")],
                    live=comment(cid=7, login="impostor"))
    record, issues = rf.find_authorization(gh, synthetic["contract"])
    assert record is None
    assert [c for c, _ in issues] == ["AUTHZ_WRONG_AUTHOR"]


def test_altered_body_is_rejected(synthetic):
    altered = AUTH_TEXT.replace("Figure 1 and Figure 4",
                                "Figure 1, Figure 4 and Figure 9")
    gh = FakeGitHub(comments=[comment(body=altered)])
    record, issues = rf.find_authorization(gh, synthetic["contract"])
    assert record is None
    assert [c for c, _ in issues] == ["AUTHZ_BODY_ALTERED"]


def test_truncated_body_is_rejected(synthetic):
    gh = FakeGitHub(comments=[comment(body=AUTH_TEXT[:len(AUTH_TEXT) // 2])])
    record, issues = rf.find_authorization(gh, synthetic["contract"])
    assert record is None
    assert [c for c, _ in issues] == ["AUTHZ_BODY_ALTERED"]


def test_comment_edited_between_listing_and_refetch_is_rejected(synthetic):
    gh = FakeGitHub(comments=[comment(cid=9)],
                    live=comment(cid=9, body="withdrawn"))
    record, issues = rf.find_authorization(gh, synthetic["contract"])
    assert record is None
    assert [c for c, _ in issues] == ["AUTHZ_BODY_ALTERED"]


def test_deleted_comment_is_unretrievable_not_authorization(synthetic):
    gh = FakeGitHub(comments=[comment()], missing=True)
    with pytest.raises(rf.FinalizerError) as exc:
        rf.find_authorization(gh, synthetic["contract"])
    assert exc.value.code == "GITHUB_API_UNAVAILABLE"


def test_comment_on_a_different_repository_or_pr_is_rejected(synthetic):
    gh = FakeGitHub(comments=[comment(owner="someone", repo="FORK")])
    record, issues = rf.find_authorization(gh, synthetic["contract"])
    assert record is None
    assert [c for c, _ in issues] == ["AUTHZ_WRONG_TARGET"]


REVOCATION = ("On reflection I withdraw the authorization above. Please do "
              "not distribute the Figure 1 or Figure 4 artwork under CC BY "
              "4.0.")


def test_an_older_grant_followed_by_a_revocation_is_refused(synthetic):
    """A grant the author later withdrew is not authorization.

    Accepting ANY historical exact match let a revoked grant stand: the
    revocation was simply never looked at. Only the author's LATEST top-level
    comment counts.
    """
    gh = FakeGitHub(comments=[
        comment(cid=101, created="2026-01-01T00:00:00Z"),
        comment(cid=102, body=REVOCATION, created="2026-02-01T00:00:00Z"),
    ])
    record, issues = rf.find_authorization(gh, synthetic["contract"])
    assert record is None
    assert [c for c, _ in issues] == ["AUTHZ_SUPERSEDED_OR_QUALIFIED"], issues
    assert "101" in issues[0][1] and "102" in issues[0][1]


def test_an_older_grant_followed_by_a_qualification_is_refused(synthetic):
    """"...but wait until X" is a qualification, and qualified is not granted."""
    gh = FakeGitHub(comments=[
        comment(cid=101, created="2026-01-01T00:00:00Z"),
        comment(cid=102, created="2026-03-01T00:00:00Z",
                body=AUTH_TEXT + " Please hold until the journal responds."),
    ])
    record, issues = rf.find_authorization(gh, synthetic["contract"])
    assert record is None
    assert [c for c, _ in issues] == ["AUTHZ_SUPERSEDED_OR_QUALIFIED"], issues


def test_a_later_comment_by_another_author_does_not_supersede_the_grant(
        synthetic):
    """Only the contracted author can withdraw the contracted author's grant.

    A stranger posting after the grant - or posting a revocation of it - has
    no bearing on whether the copyright holder authorized anything.
    """
    gh = FakeGitHub(comments=[
        comment(cid=101, created="2026-01-01T00:00:00Z"),
        comment(cid=300, login="someone-else", body=REVOCATION,
                created="2026-06-01T00:00:00Z"),
        comment(cid=301, login="fawazbouhamad", body="ping",
                created="2026-07-01T00:00:00Z"),
    ])
    record, issues = rf.find_authorization(gh, synthetic["contract"])
    assert issues == [], issues
    assert record is not None and record["comment_id"] == 101


def test_the_grant_is_found_beyond_the_first_hundred_comments(synthetic):
    """A pull request with more than one page of comments is read in full.

    Without pagination the API returns only the first 100 comments, so a grant
    posted later is invisible - and so, far worse, is a REVOCATION posted
    after it.
    """
    chatter = [comment(cid=1000 + i, login="fawazbouhamad", body=f"note {i}",
                       created="2026-01-01T00:00:00Z")
               for i in range(150)]
    grant = comment(cid=9001, created="2026-05-01T00:00:00Z")
    gh = FakeGitHub(comments=chatter + [grant])
    record, issues = rf.find_authorization(gh, synthetic["contract"])
    assert issues == [], issues
    assert record["comment_id"] == 9001

    # ...and a revocation on a still later page must reach us too.
    revoked = FakeGitHub(comments=chatter + [grant] + [
        comment(cid=9002, body=REVOCATION, created="2026-05-02T00:00:00Z")])
    record, issues = rf.find_authorization(revoked, synthetic["contract"])
    assert record is None
    assert [c for c, _ in issues] == ["AUTHZ_SUPERSEDED_OR_QUALIFIED"], issues


def test_the_comment_listing_requests_and_flattens_every_page(monkeypatch):
    """The live client really does paginate, and really does flatten.

    ``FakeGitHub`` hands the finalizer a complete list, so it cannot prove the
    REAL client asks for one. This drives ``GitHubCLI`` itself.
    """
    seen = {}

    class _Proc:
        returncode = 0
        stderr = ""

        def __init__(self, stdout):
            self.stdout = stdout

    def fake_run(argv, **kw):
        seen["argv"] = list(argv)
        seen["env"] = kw.get("env") or {}
        # --slurp yields a LIST OF PAGES, not a flat list.
        return _Proc(json.dumps([[{"id": 1}, {"id": 2}], [{"id": 3}]]))

    monkeypatch.setattr(rf.subprocess, "run", fake_run)
    out = rf.GitHubCLI().issue_comments("fawazbouhamad", "SCORCH", 1)
    assert out == [{"id": 1}, {"id": 2}, {"id": 3}], out

    argv = seen["argv"]
    assert "--paginate" in argv and "--slurp" in argv, argv
    assert any("per_page=100" in a for a in argv), argv
    assert "--hostname" in argv and rf.GITHUB_HOST in argv, argv
    # The ambient variables that could redirect the host are not inherited.
    for dropped in ("GH_HOST", "GH_ENTERPRISE_TOKEN", "GITHUB_API_URL",
                    "GH_CONFIG_DIR", "GH_REPO"):
        assert dropped not in seen["env"], dropped


def test_hard_wrapping_is_tolerated_but_alteration_is_not(synthetic):
    wrapped = AUTH_TEXT.replace(" ", "\n", 12)
    gh = FakeGitHub(comments=[comment(body=wrapped)])
    record, issues = rf.find_authorization(gh, synthetic["contract"])
    assert issues == []
    assert record["login"] == "nassernajibi"
    assert record["body_sha256"] == rf.sha256_bytes(wrapped.encode("utf-8"))
    assert record["permalink"].startswith(
        "https://github.com/fawazbouhamad/SCORCH/pull/1")


def test_screenshot_or_local_json_evidence_is_not_an_input(synthetic):
    """Local 'evidence' is inert: nothing reads it, so nothing can honour it."""
    (synthetic["root"] / "APPROVAL.json").write_text(
        json.dumps({"approved": True, "login": "nassernajibi",
                    "body": AUTH_TEXT}), encoding="utf-8")
    (synthetic["root"] / "approval_screenshot.png").write_bytes(b"PNG")
    record, issues = rf.find_authorization(FakeGitHub(comments=[]),
                                           synthetic["contract"])
    assert record is None
    assert [c for c, _ in issues] == ["RELEASE_BLOCKED_D6"]


# ---------------------------------------------------------------------------
# 3. Repository state
# ---------------------------------------------------------------------------
def test_dirty_tree_is_rejected(synthetic):
    (synthetic["root"] / "stray.txt").write_text("x", encoding="utf-8")
    report = run_preflight(synthetic, FakeGitHub(pr=good_pr(synthetic["head"])))
    assert "GIT_TREE_DIRTY" in report.codes


def test_wrong_branch_is_rejected(synthetic):
    report = rf.preflight(synthetic["root"], "some-other-branch",
                          synthetic["head"], contract=synthetic["contract"],
                          github=FakeGitHub(pr=good_pr(synthetic["head"])),
                          final_docx_dir=synthetic["docx_dir"],
                          aptos_font=synthetic["font"])
    assert "GIT_BRANCH_MISMATCH" in report.codes


def test_wrong_head_is_rejected(synthetic):
    report = rf.preflight(synthetic["root"], "chore/final-repository-cleanup",
                          "f" * 40, contract=synthetic["contract"],
                          github=FakeGitHub(pr=good_pr(synthetic["head"])),
                          final_docx_dir=synthetic["docx_dir"],
                          aptos_font=synthetic["font"])
    assert "GIT_HEAD_MISMATCH" in report.codes


def test_moved_main_is_rejected(synthetic):
    synthetic["contract"]["repository"]["expected_main_commit"] = "0" * 40
    report = run_preflight(synthetic, FakeGitHub(pr=good_pr(synthetic["head"])))
    assert "GIT_MAIN_MOVED" in report.codes


def test_moved_tag_is_rejected(synthetic):
    synthetic["contract"]["repository"]["expected_tag_object"] = "0" * 40
    report = run_preflight(synthetic, FakeGitHub(pr=good_pr(synthetic["head"])))
    assert "GIT_TAG_MOVED" in report.codes


def test_remote_branch_drift_is_rejected(synthetic):
    """A local commit the remote has not seen must block finalization."""
    _run(synthetic["root"], "commit", "-q", "--allow-empty", "-m", "drift")
    moved = _rev(synthetic["root"], "HEAD")
    report = rf.preflight(synthetic["root"], "chore/final-repository-cleanup",
                          moved, contract=synthetic["contract"],
                          github=FakeGitHub(pr=good_pr(moved)),
                          final_docx_dir=synthetic["docx_dir"],
                          aptos_font=synthetic["font"])
    assert "GIT_REMOTE_BRANCH_MISMATCH" in report.codes


@pytest.mark.parametrize("mutation", [
    {"state": "closed"},
    {"draft": False},
    {"merged_at": "2026-01-01T00:00:00Z"},
    {"base": {"ref": "release"}},
])
def test_changed_pr_state_is_rejected(synthetic, mutation):
    pr = good_pr(synthetic["head"])
    pr.update(mutation)
    report = run_preflight(synthetic, FakeGitHub(pr=pr))
    assert "PR_STATE_UNEXPECTED" in report.codes


# ---------------------------------------------------------------------------
# 4. Figures, markers, fixtures, font
# ---------------------------------------------------------------------------
def test_changed_figure_is_rejected(synthetic):
    (synthetic["root"] / "assets/frozen_figures/fig04/Figure_04.png"
     ).write_bytes(b"TAMPERED")
    report = run_preflight(synthetic, FakeGitHub(pr=good_pr(synthetic["head"])))
    assert "FIGURE_IDENTITY_MISMATCH" in report.codes


def test_pending_marker_count_other_than_four_is_rejected(synthetic):
    (synthetic["root"] / ".zenodo.json").write_text(
        "no artwork wording here at all\n", encoding="utf-8")
    report = run_preflight(synthetic, FakeGitHub(pr=good_pr(synthetic["head"])))
    assert "PENDING_MARKER_COUNT" in report.codes


def test_wrong_docx_fixture_pair_is_rejected(synthetic):
    (synthetic["docx_dir"] / "M.docx").write_bytes(b"SUPERSEDED-PRE-R5")
    report = run_preflight(synthetic, FakeGitHub(pr=good_pr(synthetic["head"])))
    assert "DOCX_FIXTURE_MISMATCH" in report.codes


def test_missing_font_is_reported_independently_of_d6(synthetic):
    report = rf.preflight(synthetic["root"], "chore/final-repository-cleanup",
                          synthetic["head"], contract=synthetic["contract"],
                          github=FakeGitHub(pr=good_pr(synthetic["head"]),
                                            comments=[comment()]),
                          final_docx_dir=synthetic["docx_dir"],
                          aptos_font=None)
    assert "APTOS_FONT_MISSING" in report.codes
    assert "RELEASE_BLOCKED_D6" not in report.codes


def test_substituted_font_is_rejected_not_accepted(synthetic, tmp_path):
    other = tmp_path / "calibri.ttf"
    other.write_bytes(b"NOT-APTOS")
    report = rf.preflight(synthetic["root"], "chore/final-repository-cleanup",
                          synthetic["head"], contract=synthetic["contract"],
                          github=FakeGitHub(pr=good_pr(synthetic["head"])),
                          final_docx_dir=synthetic["docx_dir"],
                          aptos_font=other)
    assert "APTOS_FONT_MISMATCH" in report.codes


# ---------------------------------------------------------------------------
# 5. The identity update arithmetic
# ---------------------------------------------------------------------------
def test_eight_files_and_fifty_six_references_are_planned(synthetic):
    edits = rf.plan_identity_edits(synthetic["root"], synthetic["contract"],
                                   old_identity(), new_identity())
    assert len(edits) == 8
    assert sum(e.references for e in edits) == 56
    # the filename is unchanged, so exactly the 27 value references change
    assert sum(e.changed for e in edits) == 27


def test_seven_file_mapping_is_rejected(synthetic):
    synthetic["contract"]["identity"]["files"].pop(
        "tests/test_stale_provenance.py")
    with pytest.raises(rf.FinalizerError) as exc:
        rf.plan_identity_edits(synthetic["root"], synthetic["contract"],
                               old_identity(), new_identity())
    assert exc.value.code in {"EDIT_FILE_COUNT", "EDIT_REFERENCE_COUNT"}


def test_fifty_five_reference_mapping_is_rejected(synthetic):
    synthetic["contract"]["identity"]["files"][
        "docs/RELOCATED_ARTIFACTS.csv"]["archive_sha256"] = 20
    with pytest.raises(rf.FinalizerError) as exc:
        rf.plan_identity_edits(synthetic["root"], synthetic["contract"],
                               old_identity(), new_identity())
    assert exc.value.code == "EDIT_REFERENCE_COUNT"


def test_extra_occurrence_makes_the_count_ambiguous_and_fails(synthetic):
    path = synthetic["root"] / "docs/CANONICAL_SCIENCE.json"
    path.write_text(path.read_text(encoding="utf-8").replace(
        f'"sha256": "{OLD_SHA}"',
        f'"sha256": "{OLD_SHA}", "copy": "{OLD_SHA}"'), encoding="utf-8")
    with pytest.raises(rf.FinalizerError) as exc:
        rf.plan_identity_edits(synthetic["root"], synthetic["contract"],
                               old_identity(), new_identity())
    assert exc.value.code == "EDIT_REFERENCE_COUNT"


def test_protected_historical_record_can_never_be_planned(synthetic):
    synthetic["contract"]["identity"]["files"][
        "remediation/freeze/freeze_manifest_pre.json"] = {"archive_sha256": 1}
    with pytest.raises(rf.FinalizerError) as exc:
        rf.plan_identity_edits(synthetic["root"], synthetic["contract"],
                               old_identity(), new_identity())
    assert exc.value.code == "EDIT_PROTECTED_RECORD"


def test_provisional_identity_is_never_copied(synthetic):
    """Current values come from the tracked record, never from a constant."""
    assert rf.current_identity(synthetic["root"],
                               synthetic["contract"]) == old_identity()
    src = (_RELEASE_DIR / "release_finalizer.py").read_text(encoding="utf-8")
    for provisional in ("7a2ab7568b5ec84ebf11907d2f71bae334ba855cfd2ae795",
                        "28e10268d3efbcc5ecacb168f43a805ac85eba70b36ce7f9",
                        "pre_D6_local_candidate"):
        assert provisional not in src, "a provisional identity is hardcoded"


def test_structure_breakage_is_caught_even_when_counts_look_right():
    with pytest.raises(rf.FinalizerError) as exc:
        rf._assert_structure_preserved("x.json", b'{"a": 1}',
                                       b'{"a": 1, "b": 2}')
    assert exc.value.code == "EDIT_STRUCTURE_BROKEN"


# ---------------------------------------------------------------------------
# 6. Transactions: no partial writes, at any boundary
# ---------------------------------------------------------------------------
def test_transaction_restores_exact_bytes_when_a_later_write_fails(synthetic):
    before = snapshot(synthetic["root"])
    edits = rf.plan_identity_edits(synthetic["root"], synthetic["contract"],
                                   old_identity(), new_identity())
    doomed = rf.Edit("does/not/exist.txt", b"", b"x", {"archive_sha256": 1}, 1)
    txn = rf.Transaction(synthetic["root"], synthetic["contract"])
    with pytest.raises(Exception):
        txn.apply(edits + [doomed])
    assert snapshot(synthetic["root"]) == before, "a partial write survived"
    assert txn.applied is False


@pytest.mark.parametrize("boundary", range(1, 9))
def test_failure_at_every_write_boundary_leaves_no_trace(synthetic, boundary):
    """Fail after N successful writes, for every N. Nothing may remain."""
    before = snapshot(synthetic["root"])
    edits = rf.plan_identity_edits(synthetic["root"], synthetic["contract"],
                                   old_identity(), new_identity())
    poisoned = list(edits[:boundary]) + [
        rf.Edit("nope/missing.md", b"", b"x", {"archive_filename": 1}, 1)]
    txn = rf.Transaction(synthetic["root"], synthetic["contract"])
    with pytest.raises(Exception):
        txn.apply(poisoned)
    assert snapshot(synthetic["root"]) == before


def test_transaction_detects_a_protected_record_changed_underneath(synthetic):
    contract = synthetic["contract"]
    protected_rel = contract["protected_historical_records"][0]
    edits = rf.plan_identity_edits(synthetic["root"], contract,
                                   old_identity(), new_identity())

    class Meddling(rf.Transaction):
        """Rewrites a protected record while the transaction is writing."""

        def _write_target(self, entry):
            result = super()._write_target(entry)
            (self.repo_root / protected_rel).write_text(
                "REWRITTEN", encoding="utf-8")
            return result

    txn = Meddling(synthetic["root"], contract)
    with pytest.raises(rf.FinalizerError) as exc:
        txn.apply(edits)
    assert exc.value.code == "PROTECTED_RECORD_MODIFIED"

    # VERIFICATION-ONLY. The rollback REPORTS that the historical record moved;
    # it does not write to it. Rewriting a record that exists to document a
    # superseded artifact as historical fact - in order to tidy up after a
    # failed run - is precisely what the protection exists to prevent.
    with pytest.raises(rf.RollbackError) as rb:
        txn.rollback()
    assert any("verification-only" in f for f in rb.value.failures), \
        rb.value.failures
    assert (synthetic["root"] / protected_rel).read_text(
        encoding="utf-8") == "REWRITTEN", \
        "the rollback rewrote a protected historical record"


# ---------------------------------------------------------------------------
# 7. Archive building and topology
# ---------------------------------------------------------------------------
def _stage(tmp_path):
    stage = tmp_path / "stage"
    (stage / "gridded").mkdir(parents=True)
    (stage / "payload.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (stage / "validate_deposit.py").write_text("print('ok')\n",
                                               encoding="utf-8")
    return stage


def test_double_build_from_identical_inputs_is_byte_identical(tmp_path):
    stage = _stage(tmp_path)
    a = rf.build_deterministic_zip(stage, tmp_path / "a.zip")
    b = rf.build_deterministic_zip(stage, tmp_path / "b.zip")
    assert rf.sha256_file(a) == rf.sha256_file(b)
    assert a.read_bytes() == b.read_bytes()


def test_changed_input_changes_the_recomputed_identity(tmp_path):
    stage = _stage(tmp_path)
    first = rf.archive_identity(
        rf.build_deterministic_zip(stage, tmp_path / "a.zip"))
    (stage / "payload.csv").write_text("a,b\n9,9\n", encoding="utf-8")
    second = rf.archive_identity(
        rf.build_deterministic_zip(stage, tmp_path / "b.zip"))
    assert first["archive_sha256"] != second["archive_sha256"]
    assert first["content_root_hash"] != second["content_root_hash"]


def test_duplicate_members_are_detected(tmp_path, synthetic):
    dupe = tmp_path / "dupe.zip"
    with zipfile.ZipFile(dupe, "w") as zf:
        zf.writestr("a.txt", "1")
        zf.writestr("a.txt", "2")
        zf.writestr("SHA256SUMS", "")
        zf.writestr("FILE_MANIFEST.csv",
                    "file,bytes,sha256,n_rows,description\n")
    codes = [c for c, _ in rf.archive_topology_issues(dupe,
                                                      synthetic["contract"])]
    assert "ARCHIVE_DUPLICATE_RAW_MEMBER" in codes


def test_wrong_member_count_is_detected(tmp_path, synthetic):
    thin = tmp_path / "thin.zip"
    with zipfile.ZipFile(thin, "w") as zf:
        zf.writestr("only.txt", "1")
        zf.writestr("SHA256SUMS", "")
        zf.writestr("FILE_MANIFEST.csv",
                    "file,bytes,sha256,n_rows,description\n")
        zf.writestr("extra.txt", "2")
    codes = [c for c, _ in rf.archive_topology_issues(thin,
                                                      synthetic["contract"])]
    assert "ARCHIVE_MEMBER_COUNT" in codes


def test_absent_deposit_validator_is_detected(tmp_path, synthetic):
    novalidator = tmp_path / "nv.zip"
    with zipfile.ZipFile(novalidator, "w") as zf:
        zf.writestr("a.txt", "1")
        zf.writestr("SHA256SUMS", "")
        zf.writestr("FILE_MANIFEST.csv",
                    "file,bytes,sha256,n_rows,description\n")
    codes = [c for c, _ in rf.archive_topology_issues(novalidator,
                                                      synthetic["contract"])]
    assert "DEPOSIT_VALIDATOR_ABSENT" in codes


def test_circular_identity_is_refused(tmp_path, synthetic):
    """An identity-bearing file inside the archive it names is circular."""
    circ = tmp_path / "circ.zip"
    with zipfile.ZipFile(circ, "w") as zf:
        zf.writestr("docs/CANONICAL_SCIENCE.json", "{}")
    codes = [c for c, _ in rf.circular_identity_issues(
        circ, synthetic["contract"], {"archive_sha256": NEW_SHA})]
    assert "CIRCULAR_IDENTITY" in codes


def test_member_carrying_the_archives_own_hash_is_refused(tmp_path, synthetic):
    circ = tmp_path / "selfref.zip"
    with zipfile.ZipFile(circ, "w") as zf:
        zf.writestr("PROVENANCE.md", f"this archive is {NEW_SHA}\n")
    codes = [c for c, _ in rf.circular_identity_issues(
        circ, synthetic["contract"], {"archive_sha256": NEW_SHA})]
    assert "CIRCULAR_IDENTITY" in codes


def test_sidecar_member_drift_is_refused(synthetic):
    new = dict(new_identity())
    new["member_hashes"] = {f"payload/{i}.txt": "f" * 64 for i in range(21)}
    with pytest.raises(rf.FinalizerError) as exc:
        rf._assert_sidecar_members_unchanged(synthetic["root"],
                                             synthetic["contract"], new)
    assert exc.value.code == "SIDECAR_MEMBER_DRIFT"


# ---------------------------------------------------------------------------
# 8. CC BY activation: scope, leakage, and the deliberate authorship gate
# ---------------------------------------------------------------------------
def test_unauthored_activation_plan_blocks_activation(synthetic):
    with pytest.raises(rf.FinalizerError) as exc:
        rf.plan_ccby_activation(synthetic["root"], synthetic["contract"])
    assert exc.value.code == "CCBY_ACTIVATION_PLAN_UNAUTHORED"


def test_shipped_contract_ships_with_activation_unauthored():
    """The real contract must never arrive with activation pre-authorized."""
    real = json.loads((_RELEASE_DIR / "finalizer_contract.json")
                      .read_text(encoding="utf-8"))
    assert real["ccby_activation_plan"]["authored"] is False
    assert real["ccby_activation_plan"]["replacements"] == []


def test_activation_outside_the_licence_records_is_refused(synthetic):
    plan = full_activation_plan()
    plan["replacements"].append({"file": "docs/CANONICAL_SCIENCE.json",
                                 "from": PENDING_BLOCK, "to": ACTIVE_BLOCK,
                                 "count": 1})
    synthetic["contract"]["ccby_activation_plan"] = plan
    with pytest.raises(rf.FinalizerError) as exc:
        rf.plan_ccby_activation(synthetic["root"], synthetic["contract"])
    assert exc.value.code == "CCBY_ACTIVATION_SCOPE"


def test_activation_that_disturbs_third_party_rights_is_refused(synthetic):
    synthetic["contract"]["ccby_activation_plan"] = full_activation_plan({
        "docs/LICENSES_AND_ATTRIBUTION.md": {
            "from": PENDING_BLOCK + " GPL-3.0-only applies to the software.",
            "to": ACTIVE_BLOCK}})
    with pytest.raises(rf.FinalizerError) as exc:
        rf.plan_ccby_activation(synthetic["root"], synthetic["contract"])
    assert exc.value.code == "CCBY_THIRD_PARTY_LEAKAGE"


def test_activation_count_mismatch_is_refused(synthetic):
    synthetic["contract"]["ccby_activation_plan"] = full_activation_plan({
        ".zenodo.json": {"count": 5}})
    with pytest.raises(rf.FinalizerError) as exc:
        rf.plan_ccby_activation(synthetic["root"], synthetic["contract"])
    assert exc.value.code == "CCBY_ACTIVATION_COUNT"


def test_a_bare_marker_is_not_a_valid_activation_block(synthetic):
    """Activation must not become a global replacement of the word PENDING."""
    synthetic["contract"]["ccby_activation_plan"] = full_activation_plan({
        ".zenodo.json": {"from": "PENDING", "to": "IN FORCE"}})
    with pytest.raises(rf.FinalizerError) as exc:
        rf.plan_ccby_activation(synthetic["root"], synthetic["contract"])
    assert exc.value.code == "CCBY_ACTIVATION_BLOCK_TOO_BROAD"


@pytest.mark.parametrize("dropped", [
    "docs/LICENSES_AND_ATTRIBUTION.md",
    "assets/frozen_figures/README.md",
    "assets/manuscript_final/README.md",
    ".zenodo.json",
    "archive:LICENSE.txt",
])
def test_a_partial_activation_is_refused(synthetic, dropped):
    """All four tracked records and the archive licence transition together."""
    synthetic["contract"]["ccby_activation_plan"] = full_activation_plan(
        drop=[dropped])
    with pytest.raises(rf.FinalizerError) as exc:
        rf.plan_ccby_activation(synthetic["root"], synthetic["contract"])
    assert exc.value.code == "CCBY_ACTIVATION_PARTIAL"


def test_an_empty_authored_plan_is_refused(synthetic):
    synthetic["contract"]["ccby_activation_plan"] = {"authored": True,
                                                     "replacements": []}
    with pytest.raises(rf.FinalizerError) as exc:
        rf.plan_ccby_activation(synthetic["root"], synthetic["contract"])
    assert exc.value.code == "CCBY_ACTIVATION_PLAN_EMPTY"


def test_an_authored_in_scope_activation_is_accepted(synthetic):
    """Synthetic success, in a disposable tree, with test-only wording."""
    synthetic["contract"]["ccby_activation_plan"] = full_activation_plan()
    edits, archive = rf.plan_ccby_activation(synthetic["root"],
                                             synthetic["contract"])
    assert sorted(e.rel for e in edits) == sorted(
        synthetic["contract"]["licence_records"])
    assert archive["from"] == ARCHIVE_PENDING
    for edit in edits:
        assert b"TEST-ONLY SYNTHETIC WORDING" in edit.updated
        # Where a third-party token was present it must survive untouched.
        if b"GPL-3.0-only" in edit.original:
            assert edit.updated.count(b"GPL-3.0-only") == \
                edit.original.count(b"GPL-3.0-only")


SHARED_FILE = "assets/manuscript_final/README.md"


def test_a_shared_file_is_written_exactly_once(synthetic):
    """One file carries BOTH the archive identity and the licence wording."""
    synthetic["contract"]["ccby_activation_plan"] = full_activation_plan()
    identity = rf.plan_identity_edits(synthetic["root"], synthetic["contract"],
                                      old_identity(), new_identity())
    base = {e.rel: e.updated for e in identity}
    ccby, _ = rf.plan_ccby_activation(synthetic["root"], synthetic["contract"],
                                      base=base)
    composed = rf.compose_edits(identity, ccby)

    assert [e.rel for e in composed].count(SHARED_FILE) == 1
    assert len(composed) == len({e.rel for e in composed})
    merged = next(e for e in composed if e.rel == SHARED_FILE)
    assert b"TEST-ONLY SYNTHETIC WORDING" in merged.updated
    assert ARCHIVE_NAME.encode() in merged.updated
    assert MANUSCRIPT_PENDING.encode() not in merged.updated


def test_uncomposed_edits_lose_the_identity_change_on_a_shared_file(synthetic):
    """The latent hazard composition exists to remove, demonstrated.

    Today the two plans happen to be compatible on this file because its only
    identity field is the archive FILENAME and the filename does not change -
    so the identity edit is a checked no-op and nothing is actually lost. The
    moment the filename does change, planning both from the same original and
    applying them in sequence discards whichever landed first. That is what is
    exercised here, with a renamed archive.
    """
    synthetic["contract"]["ccby_activation_plan"] = full_activation_plan()
    renamed = dict(new_identity(),
                   archive_filename="scorch_processed_data_v1.0.1.zip")

    identity = rf.plan_identity_edits(synthetic["root"], synthetic["contract"],
                                      old_identity(), renamed)
    base = {e.rel: e.updated for e in identity}
    composed = rf.compose_edits(
        identity,
        rf.plan_ccby_activation(synthetic["root"], synthetic["contract"],
                                base=base)[0])
    merged = next(e for e in composed if e.rel == SHARED_FILE)
    assert b"v1.0.1" in merged.updated, "composition lost the rename"
    assert b"TEST-ONLY SYNTHETIC WORDING" in merged.updated

    # Planned from the original instead, the licence edit would be written
    # last and would silently revert the rename.
    naive, _ = rf.plan_ccby_activation(synthetic["root"],
                                       synthetic["contract"])
    naive_edit = next(e for e in naive if e.rel == SHARED_FILE)
    assert b"v1.0.1" not in naive_edit.updated, (
        "fixture no longer demonstrates the hazard")
    assert naive_edit.updated != merged.updated


# ---------------------------------------------------------------------------
# 9. finalize refuses to start
# ---------------------------------------------------------------------------
def test_finalize_without_confirmation_does_nothing(synthetic):
    before = snapshot(synthetic["root"])
    report = rf.finalize(synthetic["root"], "chore/final-repository-cleanup",
                         synthetic["head"], contract=synthetic["contract"],
                         candidate_archive=None,
                         release_staging=synthetic["tmp"],
                         github=FakeGitHub(pr=good_pr(synthetic["head"]),
                                           comments=[comment()]))
    assert report.codes == ["CONFIRMATION_REQUIRED"]
    assert snapshot(synthetic["root"]) == before


def test_finalize_stops_at_the_d6_gate_and_writes_nothing(synthetic):
    before = snapshot(synthetic["root"])
    report = rf.finalize(synthetic["root"], "chore/final-repository-cleanup",
                         synthetic["head"], contract=synthetic["contract"],
                         candidate_archive=None,
                         release_staging=synthetic["tmp"],
                         github=FakeGitHub(pr=good_pr(synthetic["head"])),
                         final_docx_dir=synthetic["docx_dir"],
                         aptos_font=synthetic["font"],
                         confirm=rf.CONFIRM_PHRASE)
    assert "RELEASE_BLOCKED_D6" in report.codes
    assert not report.ok
    assert snapshot(synthetic["root"]) == before


def test_isolation_diagnostics_record_the_resolved_tree(synthetic):
    """The residual path anomaly is answered with evidence, not belief."""
    info = rf.isolation_diagnostics(synthetic["root"], sys.executable)
    assert info["cwd"] == str(synthetic["root"])
    assert info["repository_root"] == str(synthetic["root"])
    assert info["dont_write_bytecode"] is True
    assert info["pythonpath"] == "src"
    assert info["test_stale_provenance__file__"].startswith(
        str(synthetic["root"])), "collection resolved outside the copy"


# ---------------------------------------------------------------------------
# 10. EXACT EQUALITY. Containment is the defect this section exists to kill.
# ---------------------------------------------------------------------------
#: Each of these CONTAINS the authorization paragraph verbatim. Under a
#: containment rule every one of them authorizes the release; the first is an
#: explicit refusal that would have licensed the artwork anyway.
NOT_AUTHORIZATION = {
    "appended_revocation":
        AUTH_TEXT + " However, I revoke this authorization.",
    "appended_unrelated_prose":
        AUTH_TEXT + " Note: this is a draft for discussion only, please do "
                    "not treat it as final.",
    "prefixed_qualification":
        "DO NOT ACT ON THIS YET, I am still checking with legal. " + AUTH_TEXT,
    "quoted_rejection":
        'Someone asked me to post the following: "' + AUTH_TEXT +
        '" I decline to give this authorization.',
    "conditional":
        "If and only if the journal requires it, I would say: " + AUTH_TEXT,
}


@pytest.mark.parametrize("label", sorted(NOT_AUTHORIZATION))
def test_paragraph_plus_anything_else_is_not_authorization(synthetic, label):
    body = NOT_AUTHORIZATION[label]
    assert AUTH_TEXT in body, "fixture must genuinely contain the paragraph"
    gh = FakeGitHub(comments=[comment(body=body)])
    record, issues = rf.find_authorization(gh, synthetic["contract"])
    assert record is None, f"{label} was accepted as authorization"
    assert [c for c, _ in issues] == ["AUTHZ_BODY_ALTERED"]


def test_the_matching_rule_is_equality_not_containment(synthetic):
    """The regression this whole section guards, stated once, directly."""
    want = rf.normalize_prose(AUTH_TEXT)
    revoked = rf.normalize_prose(NOT_AUTHORIZATION["appended_revocation"])
    assert want in revoked, "containment would have accepted the revocation"
    assert want != revoked, "equality must reject it"


def test_comment_edited_between_the_two_live_reads_is_refused(synthetic):
    """The listing and the first re-read agree; the second does not."""
    gh = FakeGitHub(comments=[comment(cid=11)],
                    sequence=[comment(cid=11),
                              comment(cid=11, body=AUTH_TEXT + " Revoked.")])
    record, issues = rf.find_authorization(gh, synthetic["contract"])
    assert record is None
    assert [c for c, _ in issues] == ["AUTHZ_BODY_ALTERED"]


def test_metadata_mutated_between_the_two_live_reads_is_refused(synthetic):
    """Same exact body, but the comment was edited between the reads."""
    first = comment(cid=12)
    second = dict(comment(cid=12), updated_at="2026-06-06T00:00:00Z")
    gh = FakeGitHub(comments=[first], sequence=[first, second])
    record, issues = rf.find_authorization(gh, synthetic["contract"])
    assert record is None
    assert [c for c, _ in issues] == ["AUTHZ_MUTATED_DURING_READ"]


def test_the_comment_is_fetched_live_twice(synthetic):
    gh = FakeGitHub(comments=[comment()])
    record, issues = rf.find_authorization(gh, synthetic["contract"])
    assert issues == [] and record is not None
    assert gh.comment_fetches == 2, "exactly two live re-fetches are required"


def test_a_review_comment_is_not_a_top_level_comment(synthetic):
    review = dict(comment(cid=13), pull_request_review_id=999)
    gh = FakeGitHub(comments=[review])
    record, issues = rf.find_authorization(gh, synthetic["contract"])
    assert record is None
    assert [c for c, _ in issues] == ["AUTHZ_WRONG_TARGET"]


def test_a_comment_on_another_pull_request_is_refused(synthetic):
    gh = FakeGitHub(comments=[comment(number=2)])
    record, issues = rf.find_authorization(gh, synthetic["contract"])
    assert record is None
    assert [c for c, _ in issues] == ["AUTHZ_WRONG_TARGET"]


def test_a_comment_whose_issue_url_is_elsewhere_is_refused(synthetic):
    stray = dict(comment(cid=14),
                 issue_url="https://api.github.com/repos/other/REPO/issues/1")
    gh = FakeGitHub(comments=[stray])
    record, issues = rf.find_authorization(gh, synthetic["contract"])
    assert record is None
    assert [c for c, _ in issues] == ["AUTHZ_WRONG_TARGET"]


# ---------------------------------------------------------------------------
# 11. The contract production is allowed to trust
# ---------------------------------------------------------------------------
def _contract_repo(tmp_path, contract, *, commit=True):
    """A git repo carrying the contract at its tracked path."""
    root = tmp_path / "crepo"
    (root / "scripts" / "release").mkdir(parents=True)
    (root / "scripts" / "release" / "finalizer_contract.json").write_text(
        json.dumps(contract, indent=2), encoding="utf-8", newline="\n")
    _run(root, "init", "-q", "-b", "chore/final-repository-cleanup")
    _run(root, "config", "user.email", "t@example.invalid")
    _run(root, "config", "user.name", "T")
    # Keep the blob byte-identical to the LF file written above, whatever the
    # ambient global core.autocrlf happens to be.
    _run(root, "config", "core.autocrlf", "false")
    if commit:
        _run(root, "add", "-A")
        _run(root, "commit", "-qm", "contract")
    return root


def test_production_cli_has_no_contract_override():
    """The load-bearing anti-injection test for the contract itself."""
    parser = rf.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["preflight", "--repo-root", ".",
                           "--expect-branch", "b", "--expect-head", "h",
                           "--contract", "/tmp/attacker.json"])
    src = (_RELEASE_DIR / "release_finalizer.py").read_text(encoding="utf-8")
    assert '"--contract"' not in src, "a --contract option was reintroduced"


def test_trusted_contract_is_accepted_when_it_equals_the_head_blob(tmp_path,
                                                                   synthetic):
    root = _contract_repo(tmp_path, synthetic["contract"])
    contract, identity = rf.load_trusted_contract(root)
    assert contract["authorization"]["required_login"] == "nassernajibi"
    assert identity["disk_sha256"] == identity["head_blob_sha256"]
    assert identity["path"] == rf.TRACKED_CONTRACT_REL


def test_modified_tracked_contract_is_refused(tmp_path, synthetic):
    """Editing the contract without committing it does not make it trusted."""
    root = _contract_repo(tmp_path, synthetic["contract"])
    tampered = json.loads(json.dumps(synthetic["contract"]))
    tampered["authorization"]["required_login"] = "attacker"
    (root / rf.TRACKED_CONTRACT_REL).write_text(
        json.dumps(tampered, indent=2), encoding="utf-8", newline="\n")
    with pytest.raises(rf.FinalizerError) as exc:
        rf.load_trusted_contract(root)
    assert exc.value.code == "CONTRACT_NOT_AT_HEAD"


def test_untracked_contract_is_refused(tmp_path, synthetic):
    root = _contract_repo(tmp_path, synthetic["contract"], commit=False)
    with pytest.raises(rf.FinalizerError) as exc:
        rf.load_trusted_contract(root)
    assert exc.value.code in {"CONTRACT_UNTRACKED", "CONTRACT_NOT_AT_HEAD"}


@pytest.mark.parametrize("mutation", [
    ("authorization", "required_login", "attacker"),
    ("authorization", "text", "I approve. -- not the contracted paragraph"),
])
def test_an_external_contract_cannot_redefine_who_or_what_authorizes(
        tmp_path, synthetic, mutation):
    """An attacker-supplied contract is not reachable from production.

    There is no flag that accepts one, and a locally modified tracked contract
    is refused, so changing the login, the text, the licensed assets or the
    activation scope from outside is not a supported operation.
    """
    section, key, value = mutation
    root = _contract_repo(tmp_path, synthetic["contract"])
    external = tmp_path / "attacker.json"
    hostile = json.loads(json.dumps(synthetic["contract"]))
    hostile[section][key] = value
    external.write_text(json.dumps(hostile, indent=2), encoding="utf-8")

    parser = rf.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["preflight", "--repo-root", str(root),
                           "--expect-branch", "b", "--expect-head", "h",
                           "--contract", str(external)])
    contract, _ = rf.load_trusted_contract(root)
    assert contract[section][key] == synthetic["contract"][section][key]


@pytest.mark.parametrize("scope_key", ["ccby_artwork_paths", "licence_records",
                                       "figures"])
def test_an_external_contract_cannot_redefine_the_licensed_scope(
        tmp_path, synthetic, scope_key):
    root = _contract_repo(tmp_path, synthetic["contract"])
    contract, _ = rf.load_trusted_contract(root)
    assert contract[scope_key] == synthetic["contract"][scope_key]


def test_duplicate_json_keys_are_rejected():
    with pytest.raises(ValueError):
        rf.loads_strict('{"license": "CC BY", "license": "PENDING"}')
    assert rf.loads_strict('{"a": 1, "b": 2}') == {"a": 1, "b": 2}


def test_the_shipped_contract_parses_without_duplicate_keys():
    text = (_RELEASE_DIR / "finalizer_contract.json").read_text(
        encoding="utf-8")
    contract = rf.loads_strict(text)
    assert contract["trusted_contract"]["tracked_path"] == \
        rf.TRACKED_CONTRACT_REL
    assert contract["technical_source_candidate"][
        "is_released_archive_identity"] is False
    assert contract["technical_source_candidate"][
        "is_evidence_of_publication_or_deposit"] is False


def test_protected_record_identities_distinguish_blob_from_worktree():
    """A Windows checkout hash is not a portable git-blob identity."""
    contract = rf.load_contract()
    pins = contract["protected_historical_record_identities"]
    for rel in contract["protected_historical_records"]:
        pin = pins[rel]
        assert pin["git_blob_sha256"] != pin["worktree_sha256"], (
            f"{rel}: blob and worktree hashes must not be conflated")
        assert pin["git_blob_bytes"] < pin["worktree_bytes"], (
            f"{rel}: the CRLF checkout must be the larger rendering")
        assert pin["eol_relationship"] == "crlf_worktree_of_lf_blob"


# ---------------------------------------------------------------------------
# 12. The durable authorization receipt
# ---------------------------------------------------------------------------
ACTIVATED_AT = "2026-01-02T03:04:05Z"


def _record(synthetic):
    record, issues = rf.find_authorization(FakeGitHub(comments=[comment()]),
                                           synthetic["contract"])
    assert issues == []
    return record


def test_receipt_carries_every_required_field(synthetic):
    record = _record(synthetic)
    receipt = rf.build_authorization_receipt(
        synthetic["root"], synthetic["contract"], record,
        starting_head=synthetic["head"], activated_at=ACTIVATED_AT)
    for field in synthetic["contract"]["authorization_receipt"][
            "required_fields"]:
        assert field in receipt, f"receipt omits {field}"
    assert receipt["login"] == "nassernajibi"
    assert receipt["body"] == AUTH_TEXT
    assert receipt["body_sha256"] == rf.sha256_bytes(AUTH_TEXT.encode())
    assert receipt["starting_head"] == synthetic["head"]
    assert sorted(receipt["licensed_artwork"]) == sorted(
        synthetic["contract"]["ccby_artwork_paths"])
    assert rf.validate_authorization_receipt(
        receipt, synthetic["contract"], record,
        starting_head=synthetic["head"], repo_root=synthetic["root"]) == []


@pytest.mark.parametrize("field,value,code", [
    ("login", "impostor", "RECEIPT_LOGIN"),
    ("body", "I approve.", "RECEIPT_BODY"),
    ("starting_head", "0" * 40, "RECEIPT_STARTING_HEAD"),
    ("comment_id", 999999, "RECEIPT_DISAGREES_WITH_LIVE_COMMENT"),
    ("activated_at", "", "RECEIPT_ACTIVATED_AT"),
])
def test_a_receipt_that_misstates_the_authorization_is_refused(
        synthetic, field, value, code):
    record = _record(synthetic)
    receipt = rf.build_authorization_receipt(
        synthetic["root"], synthetic["contract"], record,
        starting_head=synthetic["head"], activated_at=ACTIVATED_AT)
    receipt[field] = value
    codes = [c for c, _ in rf.validate_authorization_receipt(
        receipt, synthetic["contract"], record,
        starting_head=synthetic["head"], repo_root=synthetic["root"])]
    assert code in codes


def test_a_receipt_may_not_widen_the_licensed_scope(synthetic):
    record = _record(synthetic)
    receipt = rf.build_authorization_receipt(
        synthetic["root"], synthetic["contract"], record,
        starting_head=synthetic["head"], activated_at=ACTIVATED_AT)
    receipt["licensed_artwork"]["assets/frozen_figures/fig09/Figure_09.png"] \
        = "f" * 64
    codes = [c for c, _ in rf.validate_authorization_receipt(
        receipt, synthetic["contract"], record,
        starting_head=synthetic["head"], repo_root=synthetic["root"])]
    assert "RECEIPT_ARTWORK_SCOPE" in codes


def test_a_receipt_missing_a_required_field_is_refused(synthetic):
    record = _record(synthetic)
    receipt = rf.build_authorization_receipt(
        synthetic["root"], synthetic["contract"], record,
        starting_head=synthetic["head"], activated_at=ACTIVATED_AT)
    del receipt["permalink"]
    codes = [c for c, _ in rf.validate_authorization_receipt(
        receipt, synthetic["contract"], record,
        starting_head=synthetic["head"], repo_root=synthetic["root"])]
    assert codes == ["RECEIPT_FIELD_MISSING"]


def test_the_receipt_is_created_transactionally_and_undone_on_rollback(
        synthetic):
    """A new file is a real transactional state: rollback deletes it."""
    record = _record(synthetic)
    rel = synthetic["contract"]["authorization_receipt"]["tracked_path"]
    target = synthetic["root"] / rel
    assert not target.exists()

    receipt = rf.build_authorization_receipt(
        synthetic["root"], synthetic["contract"], record,
        starting_head=synthetic["head"], activated_at=ACTIVATED_AT)
    receipt_edit = rf.Edit(rel, None, rf.receipt_bytes(receipt),
                           {"receipt": 1}, 1, creates=True)
    edits = rf.plan_identity_edits(synthetic["root"], synthetic["contract"],
                                   old_identity(), new_identity())

    before = snapshot(synthetic["root"])
    doomed = rf.Edit("nope/missing/deeper.md", b"", b"x",
                     {"archive_filename": 1}, 1)
    txn = rf.Transaction(synthetic["root"], synthetic["contract"])
    with pytest.raises(Exception):
        txn.apply(edits + [receipt_edit, doomed])
    assert not target.exists(), "the receipt survived a failed transaction"
    assert snapshot(synthetic["root"]) == before

    txn2 = rf.Transaction(synthetic["root"], synthetic["contract"])
    txn2.apply(edits + [receipt_edit])
    assert target.is_file()
    assert rf.loads_strict(target.read_text(encoding="utf-8")) == receipt
    txn2.rollback()
    assert not target.exists(), "rollback must remove a created receipt"
    assert snapshot(synthetic["root"]) == before


def test_no_receipt_exists_in_the_real_repository():
    """This pass defines the receipt. It does not create one."""
    contract = rf.load_contract()
    rel = contract["authorization_receipt"]["tracked_path"]
    assert not (REPO / rel).exists(), (
        f"{rel} must not exist until a real D6 authorization is fetched")


def test_a_premature_receipt_is_refused_by_preflight(synthetic):
    rel = synthetic["contract"]["authorization_receipt"]["tracked_path"]
    target = synthetic["root"] / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('{"forged": true}', encoding="utf-8")
    report = run_preflight(synthetic, FakeGitHub(pr=good_pr(synthetic["head"])))
    assert "RECEIPT_PREMATURE" in report.codes


# ---------------------------------------------------------------------------
# 13. preflight really does write nothing - including bytecode
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 14. A COMPLETE successful synthetic finalization.
#
# The old suite proved every refusal path and never once proved the happy path
# worked. A finalizer that only ever refuses is not demonstrably a finalizer.
# Everything here is synthetic: a throwaway repository, a throwaway origin, a
# throwaway archive and TEST-ONLY licence wording.
# ---------------------------------------------------------------------------
MANIFEST_FIELDS = ["file", "bytes", "sha256", "n_rows", "description"]

#: A validator that actually VALIDATES. The previous fixture shipped one that
#: printed "PASS" and exited 0 unconditionally, so the finalizer's "the
#: archive's own validator passed" assurance was worth nothing. This one
#: re-hashes every manifest row and every checksum line against the extracted
#: tree, checks coverage both ways, and prints exactly one unambiguous verdict.
VALIDATOR_SRC = '''\
import csv, hashlib, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST, SUMS = "FILE_MANIFEST.csv", "SHA256SUMS"


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


problems = []
on_disk = sorted(p.relative_to(ROOT).as_posix()
                 for p in ROOT.rglob("*") if p.is_file())

with open(ROOT / MANIFEST, encoding="utf-8", newline="") as handle:
    rows = list(csv.DictReader(handle))
declared = [r["file"] for r in rows]
for row in rows:
    target = ROOT / row["file"]
    if not target.is_file():
        problems.append("manifest row missing on disk: " + row["file"])
        continue
    if int(row["bytes"]) != target.stat().st_size:
        problems.append("byte count mismatch: " + row["file"])
    if row["sha256"] != sha256(target):
        problems.append("sha256 mismatch: " + row["file"])
uncovered = sorted(set(on_disk) - set(declared) - {MANIFEST, SUMS})
if uncovered:
    problems.append("files absent from the manifest: %s" % uncovered[:5])

sums_paths = []
for line in (ROOT / SUMS).read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    digest, rel = line.split("  ", 1)
    sums_paths.append(rel)
    target = ROOT / rel
    if not target.is_file():
        problems.append("checksum entry missing on disk: " + rel)
    elif sha256(target) != digest:
        problems.append("checksum mismatch: " + rel)
missing_sums = sorted(set(on_disk) - set(sums_paths) - {SUMS})
if missing_sums:
    problems.append("files absent from SHA256SUMS: %s" % missing_sums[:5])

if problems:
    for problem in problems:
        print("  - " + problem)
    print("FAIL")
    sys.exit(1)
print("[ok] manifest, checksums and coverage verified")
print("PASS")
sys.exit(0)
'''

#: Global attributes matching the shape the deposit contract requires. Taken
#: from the project's own canonical field so the synthetic member exercises the
#: SAME metadata contract, not a weakened one.
NETCDF_MEMBER = "gridded/scorch_processed_daily_tmax_field_v1.0.0.nc"
NETCDF_ATTRS = {
    "Conventions": "CF-1.10",
    "title": ("SCORCH processed daily 1-degree maximum temperature field with "
              "95th-percentile thresholds, exceedance indicator, and "
              "grid-level heatwave episode identifiers (1940-2025 warm "
              "seasons)"),
    "institution": "University of Florida",
    "comment": ("Synthetic fixture field. No missing data; _FillValue "
                "conventions declared for completeness."),
    "history": ("Built by scripts/deposit/build_processed_field_netcdf.py "
                "from the canonical long-table CSV."),
    "references": ("Bouhamad and Najibi, Understanding the Spatiotemporal "
                   "Organization of Regionally Extensive Heatwaves Using the "
                   "SCORCH Framework (manuscript in preparation). SCORCH: "
                   "Spatiotemporal Classification of Regional Compound "
                   "Heatwaves."),
    "source": ("ERA5 hourly 2-m temperature (Hersbach et al., 2020), "
               "retrieved from the ARCO-ERA5 analysis-ready public mirror "
               "(gs://gcp-public-data-arco-era5); dataset of record: "
               "Copernicus Climate Data Store, DOI 10.24381/cds.adbb2d47. "
               "ERA5 coverage used: 1940-2025 (warm seasons, "
               "April-September). Required Copernicus attribution: see the "
               "`license` attribute."),
    "license": ("CC BY 4.0 for the value added by the authors "
                "(https://creativecommons.org/licenses/by/4.0/), which covers "
                "only the authors' contribution; the underlying ERA5 "
                "information is provided under the licence to use Copernicus "
                "products, "
                "https://ecds.ecmwf.int/licences/licence-to-use-copernicus-"
                "products, and is not CC BY licensed by this deposit. ERA5 "
                "coverage used: 1940-2025 (warm seasons, April-September). "
                "Required attribution: Contains modified Copernicus Climate "
                "Change Service information 2026. Neither the European "
                "Commission nor ECMWF is responsible for any use that may be "
                "made of the Copernicus information or data it contains."),
}


#: Tests that run INSIDE the disposable validation copy, against the REAL
#: shared state module and the REAL publication builder, in the ACTIVE state.
#: This is what makes the synthetic finalization representative: the release
#: is accepted on the strength of this run, so it has to execute production
#: code rather than a placeholder assert.
ACTIVE_STATE_TESTS = '''\
"""Active-state guards, executed inside the disposable validation copy."""
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts" / "release"))

import artwork_licence_state as als


def _contract():
    return als.load_trusted_contract(REPO)


def _receipt(contract):
    path = REPO / contract["authorization_receipt"]["tracked_path"]
    return als.loads_strict(path.read_text(encoding="utf-8"))


def test_state_is_active():
    state, issues, detail = als.artwork_licence_state(REPO)
    assert state == als.ACTIVE, (state, issues)
    assert detail["_receipt_valid"] is True, issues


def test_receipt_covers_all_seven_artwork_paths():
    contract = _contract()
    receipt = _receipt(contract)
    licensed = receipt["licensed_artwork"]
    assert len(licensed) == 7, sorted(licensed)
    assert sorted(licensed) == sorted(contract["ccby_artwork_paths"])
    for rel, digest in licensed.items():
        assert als.sha256_file(REPO / rel) == digest, rel
    assert als.validate_receipt(receipt, contract, REPO) == []


def test_zero_pending_claims():
    contract = _contract()
    for rel in contract["licence_records"]:
        text = (REPO / rel).read_text(encoding="utf-8")
        assert "PENDING" not in text.upper(), rel
        assert als.classify_claim(text) == als.ACTIVE, rel


def test_real_publication_builder_emits_the_active_row():
    path = REPO / "scripts" / "publication" / "build_publication_outputs.py"
    spec = importlib.util.spec_from_file_location("_scorch_pubbuild", path)
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    assert builder.artwork_licence_state(REPO) == builder.ARTWORK_LICENCE_ACTIVE
    row = builder.artwork_licence_row(REPO)
    assert "PENDING" not in row.upper()
    assert "TEST-ONLY SYNTHETIC WORDING" in row
'''


def _write_netcdf(path):
    """A tiny but real canonical NetCDF member carrying the contract attrs."""
    netCDF4 = pytest.importorskip("netCDF4")
    path.parent.mkdir(parents=True, exist_ok=True)
    with netCDF4.Dataset(path, "w", format="NETCDF4") as ds:
        ds.createDimension("time", 2)
        var = ds.createVariable("tmax", "f4", ("time",), zlib=False)
        var[:] = [300.0, 301.0]
        var.units = "K"
        for key, value in NETCDF_ATTRS.items():
            ds.setncattr(key, value)


def _write_deposit(stage):
    """A small but structurally real deposit tree."""
    stage.mkdir(parents=True, exist_ok=True)
    (stage / "LICENSE.txt").write_text(
        ARCHIVE_PENDING + " " + THIRD_PARTY_TAIL + "\n",
        encoding="utf-8", newline="\n")
    (stage / "validate_deposit.py").write_text(VALIDATOR_SRC,
                                               encoding="utf-8", newline="\n")
    _write_netcdf(stage / NETCDF_MEMBER)
    payload = stage / "payload"
    payload.mkdir(exist_ok=True)
    for i in range(21):
        (payload / f"{i}.txt").write_text(f"row {i}\n", encoding="utf-8",
                                          newline="\n")

    files = ["LICENSE.txt", "validate_deposit.py", NETCDF_MEMBER] + \
            [f"payload/{i}.txt" for i in range(21)]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=MANIFEST_FIELDS,
                            lineterminator="\r\n")
    writer.writeheader()
    for rel in files:
        path = stage / rel
        writer.writerow({"file": rel, "bytes": str(path.stat().st_size),
                         "sha256": rf.sha256_file(path), "n_rows": "",
                         "description": "synthetic deposit member"})
    (stage / "FILE_MANIFEST.csv").write_bytes(buf.getvalue().encode("utf-8"))
    sums = [f"{rf.sha256_file(stage / r)}  {r}\n"
            for r in files + ["FILE_MANIFEST.csv"]]
    (stage / "SHA256SUMS").write_bytes("".join(sums).encode("utf-8"))
    return stage


@pytest.fixture
def e2e(synthetic, tmp_path):
    """A synthetic repo with a real origin and a pinned candidate archive."""
    root = synthetic["root"]
    contract = json.loads(json.dumps(synthetic["contract"]))

    stage = _write_deposit(tmp_path / "deposit")
    candidate = tmp_path / "scorch_processed_data_pre_D6_local_candidate.zip"
    rf.build_deterministic_zip(stage, candidate)
    ident = rf.archive_identity(candidate)

    contract["archive_topology"].update(
        {"member_count": 26, "sums_entries": 25, "manifest_rows": 24,
         "expected_netcdf_members": 1})
    # Synthetic authored wording, so the REAL publication builder can render
    # the active row in the disposable run. Test-only; the real contract keeps
    # "active": null.
    contract["publication_outputs_artwork_row"]["active"] = ACTIVE_ROW
    contract["artwork_licence_markers"] = {
        "pending": ["CC BY 4.0 PENDING"],
        "active": [ACTIVE_CLAUSE]}
    # This synthetic tree has its own modules; the real three do not exist here.
    contract["isolation_probe_modules"] = ["test_synthetic_active_state"]
    contract["technical_source_candidate"] = {
        "filename": candidate.name,
        "status": "LOCAL, UNPUBLISHED, PRE-D6 TECHNICAL SOURCE (SYNTHETIC)",
        "is_released_archive_identity": False,
        "is_evidence_of_publication_or_deposit": False,
        "sha256": ident["archive_sha256"],
        "bytes": int(ident["archive_bytes"]),
        "content_root_hash": ident["content_root_hash"],
        "topology": dict(contract["archive_topology"]),
    }
    contract["ccby_activation_plan"] = full_activation_plan()

    # The sidecar must name members that really exist, at their real hashes.
    rows = ["old_repository_path,archive_member_path,member_sha256,"
            "member_bytes,archive_filename,archive_sha256"]
    for i in range(21):
        member = f"payload/{i}.txt"
        rows.append(f"old/{i}.txt,{member},{ident['member_hashes'][member]},"
                    f"{len(f'row {i}' + chr(10))},{ARCHIVE_NAME},{OLD_SHA}")
    (root / "docs/RELOCATED_ARTIFACTS.csv").write_text(
        "\n".join(rows) + "\n", encoding="utf-8", newline="\n")
    contract["identity"]["files"]["docs/RELOCATED_ARTIFACTS.csv"] = {
        "archive_filename": 21, "archive_sha256": 21}

    # The REAL shared state module and the REAL publication builder, so the
    # disposable run exercises production code in the ACTIVE state rather than
    # a stub. The previous fixture collected one trivial assert-True node.
    for rel in ("scripts/release/artwork_licence_state.py",
                "scripts/publication/build_publication_outputs.py"):
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / rel, dest)

    (root / "tests" / "test_synthetic_ok.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8", newline="\n")
    (root / "tests" / "test_synthetic_active_state.py").write_text(
        ACTIVE_STATE_TESTS, encoding="utf-8", newline="\n")

    # Freeze the collection this run must reproduce EXACTLY.
    node_ids = sorted([
        "tests/test_synthetic_active_state.py::test_state_is_active",
        "tests/test_synthetic_active_state.py::"
        "test_receipt_covers_all_seven_artwork_paths",
        "tests/test_synthetic_active_state.py::test_zero_pending_claims",
        "tests/test_synthetic_active_state.py::"
        "test_real_publication_builder_emits_the_active_row",
        "tests/test_synthetic_ok.py::test_ok",
    ])
    contract["release_test_collection"] = {
        "node_id_count": len(node_ids),
        "sorted_node_ids_sha256": rf.sha256_bytes(
            ("\n".join(node_ids) + "\n").encode("utf-8")),
    }

    # The contract the copy will load as its own trusted contract.
    (root / "scripts" / "release" / "finalizer_contract.json").write_text(
        json.dumps(contract, indent=2), encoding="utf-8", newline="\n")

    # A real origin, so live ls-remote checks resolve. The URL is pinned in the
    # CONTRACT rather than left to be resolved through the remote name: r3f
    # stopped `live_remote_state` reading `origin` at all, because a name is
    # resolved through configuration and a global `url.*.insteadOf` could
    # rewrite where it pointed. The remote is still added so the fixture can
    # push to it.
    origin = tmp_path / "origin.git"
    _run(origin.parent, "init", "-q", "--bare", str(origin))
    _run(root, "remote", "add", "origin", str(origin))
    contract["repository"]["remote_url"] = str(origin).replace("\\", "/")
    _run(root, "add", "-A")
    _run(root, "commit", "-qm", "e2e fixture")
    head = _rev(root, "HEAD")
    _run(root, "push", "-q", "origin",
         f"HEAD:refs/heads/{contract['repository']['head_branch']}")
    _run(root, "push", "-q", "origin", "HEAD:refs/heads/main")
    _run(root, "tag", "-f", "-a", "v1.0.0", "-m", "v1.0.0")
    _run(root, "push", "-q", "-f", "origin", "refs/tags/v1.0.0")
    _run(root, "update-ref",
         f"refs/remotes/origin/{contract['repository']['head_branch']}", head)
    _run(root, "update-ref", "refs/remotes/origin/main", head)

    contract["repository"]["expected_main_commit"] = head
    contract["repository"]["expected_tag_object"] = _rev(root, "v1.0.0")
    contract["repository"]["expected_tag_commit"] = head
    staging = tmp_path / "release_staging"
    staging.mkdir()
    return {"root": root, "contract": contract, "head": head,
            "candidate": candidate, "staging": staging,
            "docx_dir": synthetic["docx_dir"], "font": synthetic["font"],
            "tmp": tmp_path}


def run_finalize(e2e, github=None, **kw):
    return rf.finalize(
        e2e["root"], "chore/final-repository-cleanup", e2e["head"],
        contract=e2e["contract"], candidate_archive=e2e["candidate"],
        release_staging=e2e["staging"],
        github=github or FakeGitHub(pr=good_pr(e2e["head"]),
                                    comments=[comment()]),
        final_docx_dir=e2e["docx_dir"], aptos_font=e2e["font"],
        confirm=rf.CONFIRM_PHRASE, activated_at=ACTIVATED_AT, **kw)


def test_synthetic_end_to_end_finalization_succeeds(e2e):
    """The complete happy path, proved rather than assumed."""
    report = run_finalize(e2e)
    assert report.ok, f"finalize failed: {report.codes} {report.detail}"
    root, contract = e2e["root"], e2e["contract"]

    # the archive was placed in the EXPLICIT staging destination
    out = e2e["staging"] / contract["identity"]["final_archive_filename"]
    assert out.is_file(), "the final archive was not placed"
    assert not (Path(root).parent /
                contract["identity"]["final_archive_filename"]).exists(), \
        "an archive was written next to the repository"

    # identity was recomputed from the final bytes and written to the tree
    final = report.data["final_identity"]
    assert final["archive_sha256"] == rf.sha256_file(out)
    assert final["archive_bytes"] == str(out.stat().st_size)
    assert final["archive_sha256"] != OLD_SHA
    pkg = json.loads((root / contract["identity"]["package_record"])
                     .read_text(encoding="utf-8"))
    stored = pkg["relocation"]["packages"][contract["identity"]["package_id"]]
    assert stored["archive_sha256"] == final["archive_sha256"]
    assert stored["content_root_hash"] == final["content_root_hash"]

    # the durable receipt exists, validates, and names the right comment
    receipt_rel = contract["authorization_receipt"]["tracked_path"]
    receipt = rf.loads_strict((root / receipt_rel).read_text(encoding="utf-8"))
    assert receipt["login"] == "nassernajibi"
    assert receipt["body"] == AUTH_TEXT
    assert receipt["starting_head"] == e2e["head"]
    assert sorted(receipt["licensed_artwork"]) == sorted(
        contract["ccby_artwork_paths"])

    # zero pending claims survive, in the tree AND in the shipped archive
    for rel in contract["licence_records"]:
        text = (root / rel).read_text(encoding="utf-8")
        assert "TEST-ONLY SYNTHETIC WORDING" in text, rel
        assert "PENDING" not in text.upper(), f"{rel} still claims PENDING"
    with zipfile.ZipFile(out) as zf:
        licence = zf.read("LICENSE.txt").decode("utf-8")
    assert ARCHIVE_ACTIVE in licence
    assert "PENDING" not in licence.upper()

    # third-party rights are untouched
    for token in contract["third_party_rights_tokens"]:
        assert token in licence or token in (
            root / "docs/LICENSES_AND_ATTRIBUTION.md").read_text("utf-8")

    # both manifest systems were regenerated and agree with the archive
    build = report.data["archive_build"]
    assert build["topology"] == {"manifest_rows": 24, "sums_entries": 25,
                                 "member_count": 26}
    # the archive's own validator really validated, and said so exactly once
    assert build["validator"]["exit_code"] == 0
    assert build["validator"]["verdict"] == "PASS"
    assert build["validator"]["verdict_lines"] == 1
    assert build["validator"]["terminal_line"] == "PASS"
    # the verified source snapshot was unchanged across both builds
    snap = build["verified_source_snapshot"]
    assert snap["sha256"] == snap["sha256_after"]
    # nothing but the three authorized members differed from the source
    assert sorted(build["member_drift"]["authorized_changes"]) == sorted(
        rf.AUTHORIZED_MEMBER_CHANGES)
    assert build["member_drift"]["members_compared"] == 26
    # the canonical NetCDF member survived the rebuild and the contract
    with zipfile.ZipFile(out) as zf:
        assert NETCDF_MEMBER in zf.namelist()
    assert rf.canonical_netcdf_members(out) == [NETCDF_MEMBER]
    assert [c for c, _ in rf.archive_topology_issues(out, contract)] == []

    # the receipt licenses EXACTLY the seven contracted artwork paths
    assert len(receipt["licensed_artwork"]) == 7
    for rel, digest in receipt["licensed_artwork"].items():
        assert rf.sha256_file(root / rel) == digest, rel
    assert rf.validate_authorization_receipt(
        receipt, contract, None, starting_head=e2e["head"],
        repo_root=root) == []

    # the superseded official archive is present and byte-identical
    old = root / contract["superseded_official_archive"]["path"]
    assert old.is_file()
    assert rf.sha256_file(old) == \
        contract["superseded_official_archive"]["sha256"]

    # the state machine reports ACTIVE, and the run was complete
    assert report.data["licence_state"]["state"] == rf.ACTIVE
    validation = report.data["validation"]
    assert validation["failed"] == validation["errors"] == 0
    assert validation["skipped"] == validation["xfailed"] == 0
    assert validation["not_executed"] == []
    assert validation["collected_nodeids"], "nothing was collected"

    # protected historical records untouched, byte for byte
    for rel in contract["protected_historical_records"]:
        assert contract["historical_netcdf_sha256"] in \
            (root / rel).read_text(encoding="utf-8")


def test_synthetic_finalization_is_deterministic(e2e):
    """Two independent fresh extractions must build byte-identical archives."""
    report = run_finalize(e2e)
    assert report.ok, report.codes
    build = report.data["archive_build"]["double_build"]
    assert build["first"] == build["second"]
    assert build["first"] == report.data["final_identity"]["archive_sha256"]


def test_a_nondeterministic_source_is_refused(e2e, monkeypatch):
    """If two extractions disagree, the build is refused, not averaged."""
    calls = {"n": 0}
    real = rf.build_deterministic_zip

    def flaky(stage_dir, dest_path):
        calls["n"] += 1
        if calls["n"] == 2:
            (Path(stage_dir) / "payload" / "0.txt").write_text(
                "DIVERGENT\n", encoding="utf-8", newline="\n")
        return real(stage_dir, dest_path)

    monkeypatch.setattr(rf, "build_deterministic_zip", flaky)
    report = run_finalize(e2e)
    assert "BUILD_NONDETERMINISTIC" in report.codes


# ---------------------------------------------------------------------------
# 15. Concurrency: the world may move between validation and the write.
#
# Every check below happens IMMEDIATELY before the transaction, because a
# check performed ten minutes and one archive build earlier is a check of the
# past. In each case nothing may be left behind.
# ---------------------------------------------------------------------------
def _assert_nothing_written(e2e, report):
    root, contract = e2e["root"], e2e["contract"]
    assert not report.ok
    assert not (e2e["staging"] /
                contract["identity"]["final_archive_filename"]).exists(), \
        "an archive was placed despite the failure"
    assert not (root /
                contract["authorization_receipt"]["tracked_path"]).exists(), \
        "a receipt survived a failed finalization"
    pkg = json.loads((root / contract["identity"]["package_record"])
                     .read_text(encoding="utf-8"))
    stored = pkg["relocation"]["packages"][contract["identity"]["package_id"]]
    assert stored["archive_sha256"] == OLD_SHA, "the identity was updated"
    for rel in contract["licence_records"]:
        assert "PENDING" in (root / rel).read_text(encoding="utf-8").upper(), \
            f"{rel} was activated despite the failure"


def test_a_tracked_file_changed_before_the_write_is_refused(e2e, monkeypatch):
    """Someone edits a licence record while the archive is being built."""
    calls = {"n": 0}
    real = rf._assert_live_refs_unmoved

    def meddling(root, contract, head, report=None):
        calls["n"] += 1
        if calls["n"] == 2:          # the pre-write recheck
            path = Path(root) / "docs/LICENSES_AND_ATTRIBUTION.md"
            path.write_text(path.read_text(encoding="utf-8") + "\nedited\n",
                            encoding="utf-8", newline="\n")
        return real(root, contract, head, report)

    monkeypatch.setattr(rf, "_assert_live_refs_unmoved", meddling)
    report = run_finalize(e2e)
    # Either refusal is correct: the pre-write recheck notices the dirty tree
    # first, and the transaction would refuse the stale plan regardless.
    assert {"GIT_TREE_DIRTY", "CONCURRENT_MODIFICATION"} & set(report.codes), \
        report.codes
    _assert_nothing_written(e2e, report)


def test_the_transaction_refuses_a_plan_made_against_stale_bytes(synthetic):
    """The last-line check: bytes changed after planning, before writing.

    The outer rechecks run before an archive build; this one runs with nothing
    left to happen afterwards. Without it, a change landing in that window is
    silently overwritten by a plan computed from the file's older contents.
    """
    root = synthetic["root"]
    edits = rf.plan_identity_edits(root, synthetic["contract"],
                                   old_identity(), new_identity())
    target = root / "docs/CANONICAL_SCIENCE.json"
    before = snapshot(root)

    # Someone else writes the file after the plan was computed.
    target.write_text(target.read_text(encoding="utf-8") + "\n",
                      encoding="utf-8", newline="\n")
    after_meddling = snapshot(root)

    txn = rf.Transaction(root, synthetic["contract"])
    with pytest.raises(rf.FinalizerError) as exc:
        txn.apply(edits)
    assert exc.value.code == "CONCURRENT_MODIFICATION"
    assert txn.applied is False
    # The meddler's change is left exactly as it was - not reverted to the
    # pre-plan bytes, and certainly not overwritten by the stale plan.
    assert snapshot(root) == after_meddling
    assert snapshot(root) != before


def test_the_authorization_withdrawn_before_the_write_is_refused(e2e):
    """The comment is edited after validation and before the transaction."""
    class Withdrawing(FakeGitHub):
        def __init__(self, **kw):
            super().__init__(**kw)
            self.listings = 0

        def issue_comments(self, owner, repo, number):
            self.listings += 1
            if self.listings >= 3:      # preflight, finalize, then pre-write
                return [comment(body=AUTH_TEXT + " I revoke this.")]
            return super().issue_comments(owner, repo, number)

    gh = Withdrawing(pr=good_pr(e2e["head"]), comments=[comment()])
    report = run_finalize(e2e, github=gh)
    assert "AUTHZ_WITHDRAWN_BEFORE_WRITE" in report.codes
    _assert_nothing_written(e2e, report)


@pytest.mark.parametrize("replacement,field", [
    (dict(cid=101, created="2026-01-01T00:00:00Z",
          updated="2026-09-09T00:00:00Z"), "updated_at"),
    (dict(cid=777, created="2026-01-01T00:00:00Z"), "comment_id"),
])
def test_an_authorization_identity_change_before_the_write_is_refused(
        e2e, replacement, field):
    """Same TEXT is not the same AUTHORIZATION.

    The pre-write re-read used to compare four fields, so a comment deleted
    and reposted with identical text, or edited so only its `updated_at`
    moved, passed as "unchanged" - and the receipt then recorded a comment
    that is not the one validation approved. Every identity field the receipt
    carries is compared.
    """
    class Edited(FakeGitHub):
        def __init__(self, later, **kw):
            super().__init__(**kw)
            self.later = later
            self.listings = 0

        def issue_comments(self, owner, repo, number):
            self.listings += 1
            if self.listings >= 3:      # preflight, finalize, then pre-write
                self._comments = [comment(**self.later)]
            return list(self._comments)

    gh = Edited(replacement, pr=good_pr(e2e["head"]), comments=[comment()])
    report = run_finalize(e2e, github=gh)
    assert "AUTHZ_CHANGED_BEFORE_WRITE" in report.codes, report.codes
    assert field in report.detail["AUTHZ_CHANGED_BEFORE_WRITE"], \
        report.detail["AUTHZ_CHANGED_BEFORE_WRITE"]
    _assert_nothing_written(e2e, report)


def test_the_remote_moving_before_the_write_is_refused(e2e, monkeypatch):
    """main moves on the server between validation and the write."""
    calls = {"n": 0}
    real = rf.live_remote_state

    def moved(root, contract):
        calls["n"] += 1
        refs = dict(real(root, contract))
        if calls["n"] >= 2:
            refs["refs/heads/main"] = "0" * 40
        return refs

    monkeypatch.setattr(rf, "live_remote_state", moved)
    report = run_finalize(e2e)
    assert "GIT_MAIN_MOVED" in report.codes
    _assert_nothing_written(e2e, report)


def test_the_live_remote_is_read_from_the_server_not_the_local_cache(e2e):
    """A stale refs/remotes/* entry cannot stand in for the live answer."""
    # Poison the LOCAL cache. The live check must ignore it entirely.
    _run(e2e["root"], "update-ref", "refs/remotes/origin/main", "HEAD")
    live = rf.live_remote_state(e2e["root"], e2e["contract"])
    assert live["refs/heads/main"] == e2e["head"], \
        "live_remote_state did not read the server"

    # And the live value is what gates the run.
    e2e["contract"]["repository"]["expected_main_commit"] = "0" * 40
    report = run_finalize(e2e)
    assert "GIT_MAIN_MOVED" in report.codes
    _assert_nothing_written(e2e, report)


def _fail_only_at_placement(monkeypatch, staging):
    """Break the OUTPUT PLACEMENT write, and only that.

    Placement no longer goes through ``shutil.copy2``: it goes through
    ``_exclusive_copy``, which opens the temporary with ``O_EXCL |
    O_NOFOLLOW`` so a file or symlink planted between the stale check and the
    write cannot be clobbered or followed. An adversary still aimed at
    ``copy2`` therefore never reached placement at all, and these tests
    quietly stopped proving anything about it.

    Still selective: the predecessor snapshot and the rollback restore have to
    keep working, or the test would be measuring the wrong failure.
    """
    real = rf._exclusive_copy
    staging = Path(staging).resolve()

    def selective(src, dst, *a, **kw):
        try:
            Path(dst).resolve().parent.relative_to(staging)
        except ValueError:
            return real(src, dst, *a, **kw)
        raise OSError("disk full")

    monkeypatch.setattr(rf, "_exclusive_copy", selective)


def _partial_placement(monkeypatch, staging):
    """Placement leaves BYTES ON DISK and then raises.

    The temporary is created exactly the way the real writer creates it -
    exclusively, without following links - so what survives into the rollback
    is a genuine half-written output owned by this run.
    """
    real = rf._exclusive_copy
    staging = Path(staging).resolve()

    def partial(src, dst, journal=None, *a, **kw):
        try:
            Path(dst).resolve().parent.relative_to(staging)
        except ValueError:
            return real(src, dst, journal, *a, **kw)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_NOFOLLOW", 0)
        flags |= getattr(os, "O_BINARY", 0)
        payload = b"partially written bytes"
        fd = os.open(str(dst), flags, 0o600)
        info = os.fstat(fd)
        with os.fdopen(fd, "wb") as out:
            out.write(payload)
        # r3g: the real writer hands the journal the identity of what it
        # actually wrote, PARTIAL WRITES INCLUDED, taken from its own
        # descriptor. A stand-in that skipped that would be testing a
        # writer the finalizer does not have.
        if journal is not None:
            journal.adopt(rf._Created(Path(dst), rf.sha256_bytes(payload),
                                      len(payload), info.st_dev,
                                      info.st_ino))
        raise OSError("disk full mid-copy")

    monkeypatch.setattr(rf, "_exclusive_copy", partial)


def test_archive_placement_failure_rolls_everything_back(e2e, monkeypatch):
    """The last write can still fail; nothing may survive it."""
    _fail_only_at_placement(monkeypatch, e2e["staging"])
    report = run_finalize(e2e)
    assert not report.ok
    # It really did reach placement: the build completed first.
    assert "archive_build" in report.data, report.codes
    _assert_nothing_written(e2e, report)


def test_a_preexisting_output_archive_is_preserved_on_failure(e2e,
                                                              monkeypatch):
    """A predecessor at the destination is never lost to a failure."""
    dest = e2e["staging"] / e2e["contract"]["identity"][
        "final_archive_filename"]
    dest.write_bytes(b"PRE-EXISTING PREDECESSOR ARCHIVE")
    before = dest.read_bytes()

    _fail_only_at_placement(monkeypatch, e2e["staging"])
    report = run_finalize(e2e)
    assert not report.ok
    assert "archive_build" in report.data, report.codes
    assert dest.is_file() and dest.read_bytes() == before, \
        "the predecessor was destroyed"
    assert not list(e2e["staging"].glob("*.finalizer-tmp")), \
        "a temporary archive was left behind"
    assert not list(e2e["staging"].glob("*.superseded-finalizer-tmp")), \
        "the displaced predecessor was left behind"


def test_a_late_failure_after_placement_restores_the_predecessor(e2e,
                                                                 monkeypatch):
    """The predecessor must survive a failure occurring AFTER placement.

    It used to be unlinked as soon as the new archive landed, so any later
    refusal rolled back into an empty space.
    """
    dest = e2e["staging"] / e2e["contract"]["identity"][
        "final_archive_filename"]
    dest.write_bytes(b"PRE-EXISTING PREDECESSOR ARCHIVE")
    before = dest.read_bytes()

    # Fail at the very last fallible step, after the archive is in place.
    real = rf.verify_superseded_archive
    calls = {"n": 0}

    def late(root, contract):
        calls["n"] += 1
        if calls["n"] >= 3:            # preflight, pre-write, post-placement
            return [("SUPERSEDED_ARCHIVE_MODIFIED", "synthetic late failure")]
        return real(root, contract)

    monkeypatch.setattr(rf, "verify_superseded_archive", late)
    report = run_finalize(e2e)
    assert "SUPERSEDED_ARCHIVE_MODIFIED" in report.codes
    assert dest.is_file(), "the predecessor was not restored"
    assert dest.read_bytes() == before, \
        "the predecessor was not restored byte-for-byte"
    assert not list(e2e["staging"].glob("*finalizer-tmp*"))
    # Tree-side invariants (the destination legitimately holds the restored
    # predecessor here, so the blanket _assert_nothing_written does not apply).
    root, contract = e2e["root"], e2e["contract"]
    assert not (root /
                contract["authorization_receipt"]["tracked_path"]).exists()
    pkg = json.loads((root / contract["identity"]["package_record"])
                     .read_text(encoding="utf-8"))
    assert pkg["relocation"]["packages"][
        contract["identity"]["package_id"]]["archive_sha256"] == OLD_SHA


def test_a_failing_output_rollback_reports_rollback_failed(e2e, monkeypatch):
    """A failed output rollback is ROLLBACK_FAILED, not a footnote.

    The temporary this run half-wrote cannot be removed, so a temporary output
    survives the rollback. That is a broken cleanup of THIS run's own artefact
    and must be reported as such - it is not a pre-existing leftover, which is
    refused before placement instead.
    """
    _partial_placement(monkeypatch, e2e["staging"])
    real_unlink = Path.unlink
    real_os_unlink = rf.os.unlink

    staging = Path(e2e["staging"]).resolve()

    def _is_the_output_temporary(path):
        # The removal no longer happens on the temporary's own pathname: it is
        # moved into a short run-owned quarantine slot first and the SLOT is
        # what gets unlinked. Blocking only `finalizer-tmp` would no longer
        # block anything.
        #
        # It is scoped to the STAGING DIRECTORY on purpose. The transaction
        # stages its own temporaries under `.q...` names too, inside the git
        # admin directory, and blocking those makes the run fail before the
        # archive is ever placed - so there would be no output rollback left
        # to fail, which is the thing this test is about.
        path = Path(path)
        try:
            parent = path.resolve().parent
        except OSError:                                     # pragma: no cover
            return False
        if parent != staging:
            return False
        return rf.RELEASE_TEMP_TOKEN in path.name or path.name.startswith(".q")

    def stubborn(self, *a, **kw):
        if _is_the_output_temporary(self):
            raise OSError("cannot remove temporary output")
        return real_unlink(self, *a, **kw)

    def stubborn_os(path, *a, **kw):
        if _is_the_output_temporary(path):
            raise OSError("cannot remove temporary output")
        return real_os_unlink(path, *a, **kw)

    monkeypatch.setattr(Path, "unlink", stubborn)
    monkeypatch.setattr(rf.os, "unlink", stubborn_os)
    report = run_finalize(e2e)
    assert "ROLLBACK_FAILED" in report.codes, report.codes


def test_receipt_creation_failure_rolls_everything_back(e2e, monkeypatch):
    def exploding(*a, **kw):
        raise rf.FinalizerError("RECEIPT_ARTWORK_MISSING", "synthetic failure")

    monkeypatch.setattr(rf, "build_authorization_receipt", exploding)
    report = run_finalize(e2e)
    assert "RECEIPT_ARTWORK_MISSING" in report.codes
    _assert_nothing_written(e2e, report)


def test_a_validation_run_that_skips_is_not_acceptance(e2e, monkeypatch):
    real = rf.run_validation

    def skipping(*a, **kw):
        summary = dict(real(*a, **kw))
        summary["skipped"] = 1
        return summary

    monkeypatch.setattr(rf, "run_validation", skipping)
    report = run_finalize(e2e)
    assert "VALIDATION_RUN_FAILED" in report.codes
    _assert_nothing_written(e2e, report)


def test_a_deselected_test_is_not_a_complete_run(e2e, monkeypatch):
    """Counts alone cannot tell a clean run from a filtered one."""
    real = rf.run_validation

    def filtered(*a, **kw):
        summary = dict(real(*a, **kw))
        summary["not_executed"] = ["tests/test_synthetic_ok.py::test_ok"]
        return summary

    monkeypatch.setattr(rf, "run_validation", filtered)
    report = run_finalize(e2e)
    assert "VALIDATION_INCOMPLETE" in report.codes
    _assert_nothing_written(e2e, report)


# ---------------------------------------------------------------------------
# 16. Archive construction: the source, the extraction and the validator
# ---------------------------------------------------------------------------
def test_the_source_replaced_after_verification_is_refused(e2e, monkeypatch):
    """Time-of-check / time-of-use: verify the path, then swap the file."""
    real = rf.verify_technical_source

    def swap_after_verifying(path, contract):
        issues = real(path, contract)
        if not issues:                       # verified - now replace it
            Path(path).write_bytes(b"SUBSTITUTED ARCHIVE\n")
        return issues

    monkeypatch.setattr(rf, "verify_technical_source", swap_after_verifying)
    report = run_finalize(e2e)
    assert "TECHNICAL_SOURCE_MISMATCH" in report.codes
    _assert_nothing_written(e2e, report)


def test_a_sibling_prefix_member_cannot_escape_the_extraction_root(tmp_path):
    """`/tmp/extract-evil` is NOT inside `/tmp/extract`, prefixes notwithstanding."""
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../extract-evil/pwned.txt", "escaped")
    with pytest.raises(rf.FinalizerError) as exc:
        rf.extract_archive(archive, tmp_path / "extract")
    assert exc.value.code == "ARCHIVE_MEMBER_PATH_ESCAPE"
    assert not (tmp_path / "extract-evil").exists()


def test_an_absolute_member_path_is_refused(tmp_path):
    archive = tmp_path / "abs.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("/etc/pwned", "escaped")
    with pytest.raises(rf.FinalizerError) as exc:
        rf.extract_archive(archive, tmp_path / "extract")
    assert exc.value.code == "ARCHIVE_MEMBER_PATH_ESCAPE"


def test_unrelated_payload_drift_is_refused(tmp_path, synthetic):
    """Only LICENSE.txt, FILE_MANIFEST.csv and SHA256SUMS may differ."""
    source = _write_deposit(tmp_path / "src")
    src_zip = rf.build_deterministic_zip(source, tmp_path / "src.zip")
    (source / "payload" / "3.txt").write_text("TAMPERED\n", encoding="utf-8",
                                              newline="\n")
    drifted = rf.build_deterministic_zip(source, tmp_path / "drift.zip")
    with pytest.raises(rf.FinalizerError) as exc:
        rf._assert_no_unauthorized_member_drift(drifted, src_zip,
                                                synthetic["contract"])
    assert exc.value.code == "ARCHIVE_MEMBER_DRIFT"
    assert "payload/3.txt" in exc.value.why


def test_an_added_or_removed_member_is_refused(tmp_path, synthetic):
    source = _write_deposit(tmp_path / "src")
    src_zip = rf.build_deterministic_zip(source, tmp_path / "src.zip")
    (source / "payload" / "extra.txt").write_text("x\n", encoding="utf-8",
                                                  newline="\n")
    added = rf.build_deterministic_zip(source, tmp_path / "added.zip")
    with pytest.raises(rf.FinalizerError) as exc:
        rf._assert_no_unauthorized_member_drift(added, src_zip,
                                                synthetic["contract"])
    assert exc.value.code == "ARCHIVE_MEMBER_DRIFT"
    assert "added" in exc.value.why


@pytest.mark.parametrize("script,code", [
    # silence
    ("import sys\nsys.exit(0)\n", "DEPOSIT_VALIDATOR_AMBIGUOUS"),
    # an anchored FAIL verdict
    ("print('FAIL')\n", "DEPOSIT_VALIDATOR_FAILED"),
    # mixed verdicts
    ("print('PASS')\nprint('FAIL')\n", "DEPOSIT_VALIDATOR_FAILED"),
    ("print('FAIL')\nprint('PASS')\n", "DEPOSIT_VALIDATOR_FAILED"),
    # duplicate PASS
    ("print('PASS')\nprint('PASS')\n", "DEPOSIT_VALIDATOR_AMBIGUOUS"),
    # SUBSTRING IMPOSTORS - both contain "PASS"
    ("print('BYPASS')\n", "DEPOSIT_VALIDATOR_AMBIGUOUS"),
    ("print('COMPASS')\n", "DEPOSIT_VALIDATOR_AMBIGUOUS"),
    ("print('PASSED')\n", "DEPOSIT_VALIDATOR_AMBIGUOUS"),
    ("print('deposit validation: PASS')\n", "DEPOSIT_VALIDATOR_AMBIGUOUS"),
    # a verdict that is not the terminal line
    ("print('PASS')\nprint('[ok] trailing chatter')\n",
     "DEPOSIT_VALIDATOR_AMBIGUOUS"),
    # nonzero exit
    ("print('PASS')\nimport sys\nsys.exit(3)\n", "DEPOSIT_VALIDATOR_FAILED"),
])
def test_validator_output_must_be_one_unambiguous_pass(tmp_path, synthetic,
                                                       script, code):
    """Exit zero is necessary and nowhere near sufficient.

    Substring counting accepted BYPASS and COMPASS as passes; the verdict is
    an anchored whole line and must be the last non-empty one.
    """
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "validate_deposit.py").write_text(script, encoding="utf-8",
                                               newline="\n")
    with pytest.raises(rf.FinalizerError) as exc:
        rf.run_deposit_validator(stage, synthetic["contract"], sys.executable)
    assert exc.value.code == code


def test_a_genuine_validator_pass_is_accepted(tmp_path, synthetic):
    stage = _write_deposit(tmp_path / "stage")
    result = rf.run_deposit_validator(stage, synthetic["contract"],
                                      sys.executable)
    assert result["exit_code"] == 0
    assert result["verdict"] == "PASS"
    assert result["verdict_lines"] == 1
    assert result["terminal_line"] == "PASS"


def test_the_substantive_validator_detects_a_tampered_payload(tmp_path,
                                                              synthetic):
    """Proof the fixture validator is not a rubber stamp."""
    stage = _write_deposit(tmp_path / "stage")
    (stage / "payload" / "5.txt").write_text("TAMPERED\n", encoding="utf-8",
                                             newline="\n")
    with pytest.raises(rf.FinalizerError) as exc:
        rf.run_deposit_validator(stage, synthetic["contract"], sys.executable)
    assert exc.value.code == "DEPOSIT_VALIDATOR_FAILED"


# ---------------------------------------------------------------------------
# 17. The superseded official archive, which shares the released filename
# ---------------------------------------------------------------------------
def test_a_destination_colliding_with_the_superseded_archive_is_refused(e2e):
    """The released archive has the SAME NAME. Placing it there destroys it."""
    contract = e2e["contract"]
    old = e2e["root"] / contract["superseded_official_archive"]["path"]
    before = old.read_bytes()
    report = rf.finalize(
        e2e["root"], "chore/final-repository-cleanup", e2e["head"],
        contract=contract, candidate_archive=e2e["candidate"],
        release_staging=old.parent,
        github=FakeGitHub(pr=good_pr(e2e["head"]), comments=[comment()]),
        final_docx_dir=e2e["docx_dir"], aptos_font=e2e["font"],
        confirm=rf.CONFIRM_PHRASE, activated_at=ACTIVATED_AT)
    assert "RELEASE_DESTINATION_COLLIDES_WITH_SUPERSEDED" in report.codes
    assert old.read_bytes() == before, "the superseded archive was touched"


def test_a_modified_superseded_archive_blocks_finalization(e2e):
    old = e2e["root"] / e2e["contract"]["superseded_official_archive"]["path"]
    old.write_bytes(b"SOMEONE REPLACED THE OLD ARCHIVE\n")
    report = run_finalize(e2e)
    assert "SUPERSEDED_ARCHIVE_MODIFIED" in report.codes


def test_successful_finalization_preserves_the_superseded_archive(e2e):
    """Not only rollback: SUCCESS is when it would be lost."""
    old = e2e["root"] / e2e["contract"]["superseded_official_archive"]["path"]
    before = old.read_bytes()
    report = run_finalize(e2e)
    assert report.ok, report.codes
    assert old.is_file(), "the superseded archive vanished on success"
    assert old.read_bytes() == before, "the superseded archive changed"
    assert report.data["superseded_archive_preserved"] == \
        e2e["contract"]["superseded_official_archive"]["path"]


# ---------------------------------------------------------------------------
# 18. Authorization is pinned to github.com
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("url", [
    "https://evil.example/fawazbouhamad/SCORCH/pull/1#issuecomment-101",
    "https://github.com.evil.example/fawazbouhamad/SCORCH/pull/1"
    "#issuecomment-101",
    "http://github.com/fawazbouhamad/SCORCH/pull/1#issuecomment-101",
    "https://github.example.com/fawazbouhamad/SCORCH/pull/1#issuecomment-101",
])
def test_a_foreign_host_permalink_is_refused(synthetic, url):
    """The path may say anything; only the HOST decides whose comment it is."""
    hostile = dict(comment(cid=77), html_url=url)
    record, issues = rf.find_authorization(FakeGitHub(comments=[hostile]),
                                           synthetic["contract"])
    assert record is None
    assert [c for c, _ in issues] == ["AUTHZ_WRONG_TARGET"]


def test_a_foreign_api_issue_url_is_refused(synthetic):
    hostile = dict(comment(cid=78),
                   issue_url="https://evil.example/repos/fawazbouhamad/"
                             "SCORCH/issues/1")
    record, issues = rf.find_authorization(FakeGitHub(comments=[hostile]),
                                           synthetic["contract"])
    assert record is None
    assert [c for c, _ in issues] == ["AUTHZ_WRONG_TARGET"]


@pytest.mark.parametrize("issue_url", [
    None,                                              # missing entirely
    "",                                                # empty
    "https://evil.example/repos/fawazbouhamad/SCORCH/issues/1",
    "https://api.github.com/x/repos/fawazbouhamad/SCORCH/issues/1",
    "https://api.github.com/repos/fawazbouhamad/SCORCH/issues/2",
    "https://api.github.com/repos/someone/FORK/issues/1",
    "http://api.github.com/repos/fawazbouhamad/SCORCH/issues/1",
])
def test_a_wrong_or_missing_api_issue_url_is_refused(synthetic, issue_url):
    """Exact, not endswith: a prefixed foreign path ends the same way."""
    bad = comment(cid=91)
    if issue_url is None:
        bad.pop("issue_url")
    else:
        bad["issue_url"] = issue_url
    record, issues = rf.find_authorization(FakeGitHub(comments=[bad]),
                                           synthetic["contract"])
    assert record is None
    assert [c for c, _ in issues] == ["AUTHZ_WRONG_TARGET"]


def test_a_permalink_naming_another_comment_is_refused(synthetic):
    """The fragment must name the comment being read, not a neighbour."""
    bad = dict(comment(cid=92),
               html_url="https://github.com/fawazbouhamad/SCORCH/pull/1"
                        "#issuecomment-999")
    record, issues = rf.find_authorization(FakeGitHub(comments=[bad]),
                                           synthetic["contract"])
    assert record is None
    assert [c for c, _ in issues] == ["AUTHZ_WRONG_TARGET"]


@pytest.mark.parametrize("field,value", [
    ("created_at", "2026-06-06T00:00:00Z"),
    ("issue_url", "https://api.github.com/repos/someone/FORK/issues/1"),
    ("user", {"login": "nassernajibi", "id": 999}),
])
def test_identity_fields_must_agree_across_both_live_reads(synthetic, field,
                                                           value):
    first = comment(cid=93)
    second = dict(comment(cid=93))
    second[field] = value
    gh = FakeGitHub(comments=[first], sequence=[first, second])
    record, issues = rf.find_authorization(gh, synthetic["contract"])
    assert record is None
    assert [c for c, _ in issues] in (["AUTHZ_MUTATED_DURING_READ"],
                                      ["AUTHZ_WRONG_TARGET"])


def test_the_authorization_record_carries_the_api_issue_url(synthetic):
    record, issues = rf.find_authorization(FakeGitHub(comments=[comment()]),
                                           synthetic["contract"])
    assert issues == []
    assert record["issue_url"] == EXPECTED_ISSUE_URL


def test_the_github_cli_pins_the_host_and_drops_ambient_redirection():
    src = (_RELEASE_DIR / "release_finalizer.py").read_text(encoding="utf-8")
    body = src.split("class GitHubCLI", 1)[1].split("\ndef ", 1)[0]
    assert '"--hostname", GITHUB_HOST' in body
    for ambient in ("GH_HOST", "GH_ENTERPRISE_TOKEN", "GITHUB_API_URL"):
        assert ambient in body, f"{ambient} is not cleared for the gh child"
    assert rf.GITHUB_HOST == "github.com"


# ---------------------------------------------------------------------------
# 19. Rollback can fail too, and must say so
# ---------------------------------------------------------------------------
def test_a_failing_rollback_is_reported_not_swallowed(synthetic,
                                                      monkeypatch):
    """A silent rollback failure is worse than no rollback at all."""
    root = synthetic["root"]
    edits = rf.plan_identity_edits(root, synthetic["contract"],
                                   old_identity(), new_identity())
    txn = rf.Transaction(root, synthetic["contract"])
    txn.apply(edits)
    assert txn.applied is True

    real_link = rf._link_no_clobber

    def broken(source, destination, **kw):
        if str(destination).endswith("CANONICAL_SCIENCE.json"):
            raise OSError("read-only filesystem")
        return real_link(source, destination, **kw)

    monkeypatch.setattr(rf, "_link_no_clobber", broken)
    with pytest.raises(rf.RollbackError) as exc:
        txn.rollback()
    assert exc.value.code == "ROLLBACK_FAILED"
    assert any("CANONICAL_SCIENCE.json" in f for f in exc.value.failures)
    assert txn.rollback_failures
    # The recovery copy of the file that could not be put back is RETAINED and
    # its path reported: it is now the only intact original.
    assert txn.recovery_paths.get("docs/CANONICAL_SCIENCE.json")
    txn.discard_recovery()
    assert Path(txn.recovery_paths["docs/CANONICAL_SCIENCE.json"]).is_file(), \
        "the last intact original was discarded after an unverified rollback"


def test_the_rollback_is_idempotent_and_the_only_owner(synthetic):
    """apply() must not roll back; rollback() must be safe to call twice."""
    root = synthetic["root"]
    edits = rf.plan_identity_edits(root, synthetic["contract"],
                                   old_identity(), new_identity())
    txn = rf.Transaction(root, synthetic["contract"])
    before = snapshot(root)
    txn.apply(edits)
    assert snapshot(root) != before, "apply wrote nothing"

    first = txn.rollback()
    assert snapshot(root) == before
    second = txn.rollback()
    assert second is first, "the second rollback re-derived state"
    assert snapshot(root) == before

    # apply() itself never rolls back: the source carries no self-restore.
    body = (_RELEASE_DIR / "release_finalizer.py").read_text(
        encoding="utf-8").split("    def apply(self, edits)", 1)[1]
    body = body.split("    def _write_target", 1)[0]
    assert "self.rollback()" not in body, \
        "apply() still rolls back; that is the inner half of the double undo"


def test_a_rollback_that_restores_wrong_bytes_is_detected(synthetic):
    """Even the immutable recovery copy is re-verified after the restore."""
    root = synthetic["root"]
    rel = "docs/CANONICAL_SCIENCE.json"
    edits = rf.plan_identity_edits(root, synthetic["contract"],
                                   old_identity(), new_identity())
    txn = rf.Transaction(root, synthetic["contract"])
    txn.apply(edits)

    # Corrupt the recovery copy itself - the one source the restore trusts.
    recovery = Path(txn.recovery_paths[rel])
    assert recovery.is_file(), txn.recovery_paths
    recovery.write_bytes(b'{"corrupted": true}\n')

    with pytest.raises(rf.RollbackError) as exc:
        txn.rollback()
    assert any("restored bytes differ from the recorded original" in f
               for f in exc.value.failures), exc.value.failures


MOD = "test_synthetic_active_state"


def _good_probe(tmp_path):
    return {"probe_exit": 0, "cwd": str(tmp_path), "dont_write_bytecode": True,
            f"{MOD}__file__": str(tmp_path / "tests" / f"{MOD}.py"),
            f"{MOD}__REPO": str(tmp_path)}


def test_isolation_diagnostics_are_an_acceptance_gate(tmp_path):
    """Recording that the run resolved the wrong tree is not enough."""
    good = _good_probe(tmp_path)
    assert rf.isolation_acceptance_issues(good, tmp_path, [MOD]) == []

    codes = lambda info: [c for c, _ in rf.isolation_acceptance_issues(  # noqa: E731
        info, tmp_path, [MOD])]
    assert "ISOLATION_UNVERIFIED" in codes({})
    assert "ISOLATION_WRONG_TREE" in codes(
        dict(good, cwd=str(tmp_path.parent)))
    assert "ISOLATION_BYTECODE_ENABLED" in codes(
        dict(good, dont_write_bytecode=False))
    assert "ISOLATION_WRONG_TREE" in codes(
        dict(good, **{f"{MOD}__file__": "/elsewhere/mod.py"}))
    # every probe error is a gate failure, not an observation
    assert "ISOLATION_PROBE_FAILED" in codes(
        dict(good, **{f"{MOD}__error": "ModuleNotFoundError"}))
    assert "ISOLATION_PROBE_FAILED" in codes(
        dict(good, pytest_import_error="no pytest"))
    # a missing answer is a failure: the run cannot show what it executed
    missing = dict(good)
    missing.pop(f"{MOD}__REPO")
    assert "ISOLATION_MODULE_UNRESOLVED" in codes(missing)
    # a module resolving a DIFFERENT repository root
    assert "ISOLATION_WRONG_TREE" in codes(
        dict(good, **{f"{MOD}__REPO": str(tmp_path.parent)}))


def test_sibling_prefix_paths_are_not_inside_the_copy(tmp_path):
    """`/x/copy-evil` is not inside `/x/copy`, however the strings line up."""
    copy = tmp_path / "copy"
    copy.mkdir()
    evil = tmp_path / "copy-evil"
    evil.mkdir()
    info = dict(_good_probe(copy), cwd=str(evil),
                **{f"{MOD}__file__": str(evil / "tests" / f"{MOD}.py"),
                   f"{MOD}__REPO": str(evil)})
    codes = [c for c, _ in rf.isolation_acceptance_issues(info, copy, [MOD])]
    assert "ISOLATION_WRONG_TREE" in codes


def test_the_validation_environment_strips_inherited_controls():
    """PYTHONOPTIMIZE strips assertions - and the suite IS assertions."""
    src = (_RELEASE_DIR / "release_finalizer.py").read_text(encoding="utf-8")
    body = src.split("def run_validation", 1)[1].split("\ndef ", 1)[0]
    # The child environment is now built by ALLOWING variables through, not by
    # naming bad ones: a deny-list is only as complete as the last person to
    # think about it, and every entry that mattered was found after the fact.
    assert "_hermetic_env(home)" in body, (
        "the validation run no longer builds a minimal child environment")
    assert 'env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"' in body

    hermetic = src.split("def _hermetic_env", 1)[1].split("\ndef ", 1)[0]
    assert "_isolated_home_vars(home)" in hermetic
    assert 'env["PYTHONNOUSERSITE"] = "1"' in hermetic
    assert 'env["PYTHONDONTWRITEBYTECODE"] = "1"' in hermetic
    # r3f: every per-user root is redirected, not just HOME. On Windows APPDATA
    # and LOCALAPPDATA are separate roots that git, `gh` and pip all read, and
    # the operator's were being passed straight through the allow-list.
    home_vars = src.split("def _isolated_home_vars", 1)[1].split(
        "\n#: Variables the finalizer", 1)[0]
    for name in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
                 "XDG_CONFIG_HOME", "MPLCONFIGDIR", "GIT_CONFIG_GLOBAL",
                 "GIT_CONFIG_SYSTEM"):
        assert f'"{name}"' in home_vars, f"{name} is not redirected into home"
    assert "APPDATA" not in str(rf._ENV_ALLOWLIST), \
        "the operator's APPDATA is still inherited"
    for family in ("SCORCH", "PYTEST", "PYTHON", "GIT_", "GH_", "COVERAGE",
                   "XDG_", "MPL"):
        assert family in str(rf._CLEAR_PREFIXES), \
            f"{family} is not a cleared family"


@pytest.mark.parametrize("hostile", [
    "GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE", "GH_TOKEN", "GITHUB_TOKEN",
    "COVERAGE_PROCESS_START", "XDG_CONFIG_HOME", "MPLCONFIGDIR",
    "PYTHONOPTIMIZE", "SCORCH_DATA_DIR", "PYTEST_ADDOPTS"])
def test_hostile_ambient_variables_never_reach_the_child(monkeypatch, tmp_path,
                                                         hostile):
    """GIT_DIR alone points the repository guards at another repository."""
    monkeypatch.setenv(hostile, str(tmp_path / "ambient"))
    home = tmp_path / "home"
    home.mkdir()
    env = rf._hermetic_env(home)
    assert env.get(hostile) != str(tmp_path / "ambient"), (
        f"{hostile} was inherited by the hermetic child environment")
    assert env["HOME"] == str(home)
    assert env["USERPROFILE"] == str(home)
    assert Path(env["XDG_CONFIG_HOME"]) == home / ".config"
    assert Path(env["MPLCONFIGDIR"]) == home / ".matplotlib"


def test_pythonoptimize_is_not_inherited_by_the_validation_run(monkeypatch,
                                                              tmp_path):
    """An ambient PYTHONOPTIMIZE=2 must not reach the disposable run."""
    monkeypatch.setenv("PYTHONOPTIMIZE", "2")
    monkeypatch.setenv("PYTHONHOME", str(tmp_path / "bogus-home"))
    monkeypatch.setenv("SCORCH_DATA_DIR", str(tmp_path / "ambient"))
    monkeypatch.setenv("PYTEST_ADDOPTS", "-k nothing_matches_this")
    captured = {}
    real = rf.subprocess.run

    def capture(cmd, **kw):
        if "pytest" in " ".join(str(c) for c in cmd):
            captured.update(kw.get("env") or {})
            class R:
                returncode, stdout, stderr = 0, "", ""
            return R()
        return real(cmd, **kw)

    monkeypatch.setattr(rf.subprocess, "run", capture)
    copy_root = tmp_path / "copy"
    (copy_root / "tests").mkdir(parents=True)
    rf.run_validation(copy_root, sys.executable, tmp_path / "a.zip",
                      tmp_path / "extract",
                      summary_path=tmp_path / "summary.json")
    assert "PYTHONOPTIMIZE" not in captured, "PYTHONOPTIMIZE was inherited"
    assert "PYTHONHOME" not in captured, "PYTHONHOME was inherited"
    assert "PYTEST_ADDOPTS" not in captured, "PYTEST_ADDOPTS was inherited"
    assert captured.get("SCORCH_DATA_DIR") == str(tmp_path / "extract")
    assert captured.get("PYTHONNOUSERSITE") == "1"
    assert captured.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD") == "1"


def test_an_unfrozen_release_collection_is_not_acceptance():
    """A release cannot be accepted against an unknown denominator."""
    summary = {"failed": 0, "errors": 0, "xfailed": 0, "xpassed": 0,
               "skipped": 0, "exit_code": 0, "not_executed": [],
               "executed_not_collected": [], "collected_nodeids": ["a::b"]}
    contract = {"release_test_collection": {"node_id_count": None,
                                            "sorted_node_ids_sha256": None}}
    codes = [c for c, _ in rf.validation_acceptance_issues(summary, contract)]
    assert "RELEASE_COLLECTION_UNFROZEN" in codes

    frozen = {"release_test_collection": {
        "node_id_count": 1,
        "sorted_node_ids_sha256": rf.sha256_bytes(b"a::b\n")}}
    assert rf.validation_acceptance_issues(summary, frozen) == []

    drifted = {"release_test_collection": {
        "node_id_count": 2,
        "sorted_node_ids_sha256": rf.sha256_bytes(b"a::b\nc::d\n")}}
    codes = [c for c, _ in rf.validation_acceptance_issues(summary, drifted)]
    assert "RELEASE_COLLECTION_DRIFT" in codes


# ---------------------------------------------------------------------------
# 20. Phase 4D-r3a: audited defects
# ---------------------------------------------------------------------------
DENIALS = [
    "Figure 1 is NOT licensed under CC BY 4.0.",
    "Figure 4 artwork is excluded from the CC BY 4.0 grant.",
    "No CC BY 4.0 licence applies to the Figure 1 schematic.",
    "Figure 1 and Figure 4 require written authorization before any "
    "CC BY 4.0 grant can exist.",
    "Nothing in this file grants CC BY 4.0 over Figure 1 or Figure 4.",
]


@pytest.mark.parametrize("text", DENIALS)
def test_a_denial_of_the_grant_is_not_an_active_claim(synthetic, text):
    """"Figure 1 is NOT licensed under CC BY 4.0" is a DENIAL, not a grant.

    A fallback that treated any artwork sentence mentioning CC BY as ACTIVE
    read every one of these as an assertion of the licence.
    """
    contract = synthetic["contract"]
    assert rf._artwork.classify_claim(text, contract) is None


def test_classification_uses_registered_markers_only(synthetic):
    contract = synthetic["contract"]
    assert rf._artwork.classify_claim(
        "wording nobody registered: CC BY 4.0 over Figure 1", contract) is None
    assert rf._artwork.classify_claim(PENDING_BLOCK, contract) == rf.PENDING
    assert rf._artwork.classify_claim(ACTIVE_BLOCK, contract) == rf.ACTIVE


def test_an_authored_plan_without_active_markers_is_refused(synthetic):
    """Activation the classifier could never recognise is not activation."""
    synthetic["contract"]["ccby_activation_plan"] = full_activation_plan()
    synthetic["contract"]["artwork_licence_markers"]["active"] = []
    with pytest.raises(rf.FinalizerError) as exc:
        rf.plan_ccby_activation(synthetic["root"], synthetic["contract"])
    assert exc.value.code == "CCBY_ACTIVE_MARKERS_MISSING"


GENERIC_MARKERS = [
    "CC BY 4.0",
    "Creative Commons Attribution 4.0",
    "in force",
    "Figure 1",
    "licensed",
]


@pytest.mark.parametrize("marker", GENERIC_MARKERS)
def test_a_generic_active_marker_is_refused(synthetic, marker):
    """A token is not a claim.

    "CC BY 4.0" appears in a dozen sentences of these records, several of
    which say the licence does NOT apply to this artwork. Registering it as
    the marker that means "the grant is in force" would make every one of
    them read as an activation.
    """
    synthetic["contract"]["ccby_activation_plan"] = full_activation_plan()
    synthetic["contract"]["artwork_licence_markers"]["active"] = [marker]
    with pytest.raises(rf.FinalizerError) as exc:
        rf.plan_ccby_activation(synthetic["root"], synthetic["contract"])
    assert exc.value.code.startswith("CCBY_ACTIVE_MARKER_"), exc.value.code


DENIAL_MARKERS = [
    "Figure 1 and Figure 4 artwork is NOT licensed under CC BY 4.0 anywhere.",
    "Figure 1 and Figure 4 artwork is excluded from the CC BY 4.0 grant.",
    "No CC BY 4.0 licence is in force over the Figure 1 and Figure 4 art.",
    "Figure 1 and Figure 4 artwork CC BY 4.0 licensing remains PENDING here.",
    "Figure 1 and Figure 4 artwork requires separate written authorization "
    "before any CC BY 4.0 grant exists.",
]


@pytest.mark.parametrize("marker", DENIAL_MARKERS)
def test_a_denial_may_not_be_registered_as_the_active_marker(synthetic,
                                                             marker):
    """Long, scoped, mentions CC BY 4.0 - and DENIES the grant.

    Every one of these passes a length check, names the artwork and names the
    licence. Only reading them as affirmative-or-not tells them apart from a
    grant, and registering one would make the withheld state indistinguishable
    from the granted one.
    """
    synthetic["contract"]["ccby_activation_plan"] = full_activation_plan()
    synthetic["contract"]["artwork_licence_markers"]["active"] = [marker]
    with pytest.raises(rf.FinalizerError) as exc:
        rf.plan_ccby_activation(synthetic["root"], synthetic["contract"])
    assert exc.value.code == "CCBY_ACTIVE_MARKER_NOT_AFFIRMATIVE", exc.value


@pytest.mark.parametrize("rel", ["docs/LICENSES_AND_ATTRIBUTION.md",
                                 "assets/frozen_figures/README.md",
                                 "assets/manuscript_final/README.md",
                                 ".zenodo.json"])
def test_a_marker_already_present_before_activation_is_refused(synthetic, rel):
    """A marker already in the tree cannot signal that anything changed.

    If the pre-activation records already classify ACTIVE, "the activation
    took effect" and "the activation did nothing" produce identical evidence.
    """
    synthetic["contract"]["ccby_activation_plan"] = full_activation_plan()
    target = synthetic["root"] / rel
    target.write_text(target.read_text(encoding="utf-8") + "\n"
                      + ACTIVE_CLAUSE + "\n", encoding="utf-8", newline="\n")
    with pytest.raises(rf.FinalizerError) as exc:
        rf.plan_ccby_activation(synthetic["root"], synthetic["contract"])
    assert exc.value.code == "CCBY_ACTIVE_MARKER_PRE_EXISTING", exc.value
    assert rel in exc.value.why


UNMARKED_DESTINATION = ("Figure 1 and Figure 4 artwork: CC BY 4.0 is now in "
                        "force for these assets.")


@pytest.mark.parametrize("surface", [
    "docs/LICENSES_AND_ATTRIBUTION.md",
    "assets/frozen_figures/README.md",
    "assets/manuscript_final/README.md",
    ".zenodo.json",
    "archive:LICENSE.txt",
])
def test_a_missing_marker_on_any_destination_surface_is_refused(synthetic,
                                                                surface):
    """ALL FIVE surfaces, not just the convenient one.

    An unregistered destination on any single surface leaves that record
    unclassifiable after the activation, and the state machine reports
    LICENCE_STATE_UNREADABLE rather than a completed activation.
    """
    synthetic["contract"]["ccby_activation_plan"] = full_activation_plan(
        {surface: {"to": UNMARKED_DESTINATION}})
    with pytest.raises(rf.FinalizerError) as exc:
        rf.plan_ccby_activation(synthetic["root"], synthetic["contract"])
    assert exc.value.code == "CCBY_ACTIVE_MARKER_ABSENT", exc.value
    assert surface in exc.value.why


def test_an_authored_plan_without_an_active_row_is_refused(synthetic):
    """An activation nobody can publish is not a complete activation.

    The five licence surfaces are not the whole story: `publication_outputs/`
    republishes the licence table, and a plan that activates the records while
    leaving the published row unauthored produces a deposit whose own licence
    table cannot state the grant that is now in force.
    """
    synthetic["contract"]["ccby_activation_plan"] = full_activation_plan()
    synthetic["contract"]["publication_outputs_artwork_row"]["active"] = None
    with pytest.raises(rf.FinalizerError) as exc:
        rf.plan_ccby_activation(synthetic["root"], synthetic["contract"])
    assert exc.value.code == "CCBY_ACTIVE_MARKER_ABSENT"


def test_a_destination_block_without_an_active_marker_is_refused(synthetic):
    synthetic["contract"]["ccby_activation_plan"] = full_activation_plan({
        ".zenodo.json": {"to": "Figure 1 and Figure 4 artwork: CC BY 4.0 is "
                               "now in force for these assets."}})
    with pytest.raises(rf.FinalizerError) as exc:
        rf.plan_ccby_activation(synthetic["root"], synthetic["contract"])
    assert exc.value.code == "CCBY_ACTIVE_MARKER_ABSENT"


@pytest.mark.parametrize("blob", [
    b"not a zip at all",
    b"PK\x03\x04 truncated garbage",
    b"",
])
def test_a_corrupt_candidate_is_a_code_not_a_traceback(synthetic, tmp_path,
                                                       blob):
    """Corrupt candidate bytes through the REAL preflight()."""
    cand = tmp_path / "corrupt.zip"
    cand.write_bytes(blob)
    report = run_preflight(synthetic,
                           FakeGitHub(pr=good_pr(synthetic["head"])),
                           candidate_archive=cand)
    assert "ARCHIVE_CANDIDATE_CORRUPT" in report.codes, report.codes
    assert not report.ok
    # and it is a REPORT, not an exception: other invariants were still checked
    assert report.data.get("figures_verified") == len(
        synthetic["contract"]["figures"])


def test_a_directory_supplied_as_the_candidate_is_a_code(synthetic, tmp_path):
    report = run_preflight(synthetic,
                           FakeGitHub(pr=good_pr(synthetic["head"])),
                           candidate_archive=tmp_path)
    assert {"ARCHIVE_CANDIDATE_MISSING", "ARCHIVE_CANDIDATE_CORRUPT"} & set(
        report.codes), report.codes


def test_pythonoptimize_cannot_bypass_the_shipped_validator(tmp_path,
                                                            synthetic,
                                                            monkeypatch):
    """`assert False` must still fail under an ambient PYTHONOPTIMIZE=2.

    `python -O` removes assert statements. A validator whose checks are
    assertions would then print its pass verdict having verified nothing.
    """
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "validate_deposit.py").write_text(
        'assert False, "the deposit is broken"\nprint("PASS")\n',
        encoding="utf-8", newline="\n")
    monkeypatch.setenv("PYTHONOPTIMIZE", "2")
    monkeypatch.setenv("PYTEST_ADDOPTS", "-k nothing")
    monkeypatch.setenv("SCORCH_DATA_DIR", str(tmp_path / "ambient"))
    with pytest.raises(rf.FinalizerError) as exc:
        rf.run_deposit_validator(stage, synthetic["contract"], sys.executable)
    assert exc.value.code == "DEPOSIT_VALIDATOR_FAILED"


def test_the_validator_environment_is_stripped_like_the_pytest_one():
    src = (_RELEASE_DIR / "release_finalizer.py").read_text(encoding="utf-8")
    body = src.split("def run_deposit_validator", 1)[1].split("\ndef ", 1)[0]
    # r3e: the three-prefix DENY-list is gone. It removed SCORCH*, PYTEST* and
    # PYTHON* and inherited everything else - GH_TOKEN, GIT_DIR, coverage, XDG
    # and matplotlib control among them. The validator now runs under the same
    # isolated-home ALLOW-LIST the pytest validation uses.
    assert 'startswith(("SCORCH", "PYTEST", "PYTHON"))' not in body, \
        "the deposit validator is back on a three-prefix deny-list"
    assert "_hermetic_env(_isolated_home())" in body, \
        "the deposit validator does not use the isolated-home allow-list"
    assert "_CLEAR_ALWAYS" in body
    assert 'env["PYTHONNOUSERSITE"] = "1"' in body


@pytest.mark.parametrize("stale", [".finalizer-tmp",
                                   ".superseded-finalizer-tmp"])
def test_a_stale_finalizer_temp_at_the_destination_is_refused(e2e, stale):
    """A leftover temporary from an interrupted run must not be overwritten."""
    name = e2e["contract"]["identity"]["final_archive_filename"] + stale
    (e2e["staging"] / name).write_bytes(b"leftover from an earlier run")
    report = run_finalize(e2e)
    assert "RELEASE_STAGING_STALE_TEMP" in report.codes, report.codes
    assert (e2e["staging"] / name).read_bytes() == \
        b"leftover from an earlier run"
    _assert_nothing_written(e2e, report)


def test_a_tampered_move_aside_predecessor_is_restored_from_the_snapshot(
        e2e, monkeypatch):
    """The move-aside file lives where anything can reach it."""
    dest = e2e["staging"] / e2e["contract"]["identity"][
        "final_archive_filename"]
    dest.write_bytes(b"PRE-EXISTING PREDECESSOR ARCHIVE")
    before = dest.read_bytes()

    real = rf.verify_superseded_archive
    calls = {"n": 0}

    def late(root, contract):
        calls["n"] += 1
        if calls["n"] >= 3:
            # Tamper with the move-aside copy, then force a late failure.
            aside = dest.with_name(dest.name + ".superseded-finalizer-tmp")
            if aside.exists():
                aside.write_bytes(b"TAMPERED MOVE-ASIDE")
            return [("SUPERSEDED_ARCHIVE_MODIFIED", "synthetic late failure")]
        return real(root, contract)

    monkeypatch.setattr(rf, "verify_superseded_archive", late)
    report = run_finalize(e2e)
    assert not report.ok
    assert dest.is_file()
    assert dest.read_bytes() == before, (
        "the predecessor was not restored byte-exactly from the private "
        "snapshot")
    assert not list(e2e["staging"].glob("*finalizer-tmp*"))


def _destination_unreadable_after(monkeypatch, dest, after=2):
    """Make `dest` unhashable from read `after`+1 onwards.

    r3f moved the two PRE-PLACEMENT reads of the destination off `sha256_file`
    and onto `sha256_regular_no_follow`, which classifies the object before it
    reads it. Both have to be counted, or the failure lands somewhere other
    than the restore verification these tests are about.
    """
    real_sha = rf.sha256_file
    real_checked = rf.sha256_regular_no_follow
    reads = {"n": 0}

    def _hit(path):
        if Path(path) == Path(dest):
            reads["n"] += 1
            return reads["n"] > after
        return False

    def unreadable(path):
        if _hit(path):
            raise OSError("device error")
        return real_sha(path)

    def unreadable_checked(path, **kw):
        if _hit(path):
            raise OSError("device error")
        return real_checked(path, **kw)

    monkeypatch.setattr(rf, "sha256_file", unreadable)
    monkeypatch.setattr(rf, "sha256_regular_no_follow", unreadable_checked)
    return reads


def test_an_unreadable_restored_output_reports_rollback_failed(e2e,
                                                               monkeypatch):
    """A restore that cannot be verified is ROLLBACK_FAILED, not silence."""
    dest = e2e["staging"] / e2e["contract"]["identity"][
        "final_archive_filename"]
    dest.write_bytes(b"PRE-EXISTING PREDECESSOR ARCHIVE")

    # Reads 1 and 2 are the private predecessor snapshot and the identity
    # recheck immediately before the move-aside, both of which happen BEFORE
    # placement. Failing from read 3 makes the RESTORE unverifiable rather
    # than aborting before anything was placed.
    reads = _destination_unreadable_after(monkeypatch, dest, after=2)
    report = run_finalize(e2e)
    assert "ROLLBACK_FAILED" in report.codes, report.codes
    assert reads["n"] > 1, "the run never reached the post-placement reads"


@pytest.mark.parametrize("stamps,expect", [
    ({"created_at": "2026-01-02T00:00:00Z",
      "updated_at": "2026-01-01T00:00:00Z"}, True),
    ({"updated_at": "2026-01-03T00:00:00Z",
      "activated_at": "2026-01-02T00:00:00Z"}, True),
    ({"created_at": "2026-01-01T00:00:00Z",
      "updated_at": "2026-01-02T00:00:00Z",
      "activated_at": "2026-01-03T00:00:00Z"}, False),
])
def test_receipt_timestamp_ordering_is_enforced(synthetic, stamps, expect):
    """created_at <= updated_at <= activated_at."""
    record = _record(synthetic)
    receipt = rf.build_authorization_receipt(
        synthetic["root"], synthetic["contract"], record,
        starting_head=synthetic["head"], activated_at=ACTIVATED_AT)
    receipt.update(stamps)
    codes = [c for c, _ in rf.validate_authorization_receipt(
        receipt, synthetic["contract"], None,
        starting_head=synthetic["head"], repo_root=synthetic["root"])]
    assert ("RECEIPT_TIMESTAMP_ORDER" in codes) is expect, codes


# ---------------------------------------------------------------------------
# 21. Phase 4D-r3b: final narrow safety repair
# ---------------------------------------------------------------------------
def test_fractional_seconds_are_not_collapsed():
    """.001Z and .999Z are not the same instant."""
    early = rf._artwork.parse_timestamp("2026-01-01T00:00:00.001Z")
    late = rf._artwork.parse_timestamp("2026-01-01T00:00:00.999Z")
    assert early is not None and late is not None
    assert early < late, "fractional seconds were truncated away"
    assert rf._artwork.parse_timestamp("2026-13-45T99:99:99.000Z") is None


def test_fractional_ordering_is_enforced_in_the_receipt(synthetic):
    record = _record(synthetic)
    receipt = rf.build_authorization_receipt(
        synthetic["root"], synthetic["contract"], record,
        starting_head=synthetic["head"], activated_at=ACTIVATED_AT)
    receipt.update({"created_at": "2026-01-01T00:00:00.500Z",
                    "updated_at": "2026-01-01T00:00:00.100Z"})
    codes = [c for c, _ in rf.validate_authorization_receipt(
        receipt, synthetic["contract"], None,
        starting_head=synthetic["head"], repo_root=synthetic["root"])]
    assert "RECEIPT_TIMESTAMP_ORDER" in codes


@pytest.mark.parametrize("value", [True, False, 1.0, "1", None, [1]])
def test_a_non_integer_pull_request_is_refused(synthetic, value):
    """JSON true and 1.0 both compare equal to 1."""
    record = _record(synthetic)
    receipt = rf.build_authorization_receipt(
        synthetic["root"], synthetic["contract"], record,
        starting_head=synthetic["head"], activated_at=ACTIVATED_AT)
    receipt["pull_request"] = value
    codes = [c for c, _ in rf.validate_authorization_receipt(
        receipt, synthetic["contract"], None,
        starting_head=synthetic["head"], repo_root=synthetic["root"])]
    assert "RECEIPT_PULL_REQUEST" in codes, (value, codes)


def test_an_edited_authorization_activates_at_its_updated_time(synthetic):
    """activated_at defaults to updated_at, so an edit cannot invert order."""
    edited = dict(comment(cid=55), updated_at="2026-03-03T00:00:00Z")
    gh = FakeGitHub(comments=[edited], sequence=[edited, edited])
    record, issues = rf.find_authorization(gh, synthetic["contract"])
    assert issues == []
    receipt = rf.build_authorization_receipt(
        synthetic["root"], synthetic["contract"], record,
        starting_head=synthetic["head"], activated_at=record["updated_at"])
    assert receipt["activated_at"] == "2026-03-03T00:00:00Z"
    assert rf.validate_authorization_receipt(
        receipt, synthetic["contract"], record,
        starting_head=synthetic["head"], repo_root=synthetic["root"]) == []
    receipt["activated_at"] = record["created_at"]
    codes = [c for c, _ in rf.validate_authorization_receipt(
        receipt, synthetic["contract"], None,
        starting_head=synthetic["head"], repo_root=synthetic["root"])]
    assert "RECEIPT_TIMESTAMP_ORDER" in codes


def _active_tree_with_row(tmp_path, row):
    """A minimal ACTIVE tree whose contract carries `row` as the active row."""
    als = rf._artwork
    contract = rf.load_contract()
    contract["synthetic_fixture"] = True
    root = tmp_path / "tree"
    (root / "scripts" / "release").mkdir(parents=True)
    contract["artwork_licence_markers"]["active"] = [ACTIVE_CLAUSE]
    contract["publication_outputs_artwork_row"]["active"] = row
    (root / "scripts/release/finalizer_contract.json").write_text(
        json.dumps(contract, indent=2), encoding="utf-8", newline="\n")
    for rel in contract["licence_records"]:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(ACTIVE_CLAUSE + "\n",
                          encoding="utf-8", newline="\n")
    artwork = {}
    for rel in contract["ccby_artwork_paths"]:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(("S::" + rel + "\n").encode("utf-8"))
        artwork[rel] = als.sha256_file(target)
    repo = contract["repository"]
    body = contract["authorization"]["text"]
    receipt_path = root / contract["authorization_receipt"]["tracked_path"]
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps({
        "schema_version": contract["authorization_receipt"]["schema_version"],
        "repository": repo["owner"] + "/" + repo["name"],
        "pull_request": repo["pull_request"],
        "permalink": "https://github.com/" + repo["owner"] + "/"
                     + repo["name"] + "/pull/" + str(repo["pull_request"])
                     + "#issuecomment-101",
        "issue_url": contract["authorization"]["expected_issue_url"],
        "comment_id": 101,
        "login": contract["authorization"]["required_login"],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z", "body": body,
        "body_sha256": als.sha256_hex(body), "licensed_artwork": artwork,
        "activated_at": "2026-01-01T00:00:00Z",
        "finalizer_version": contract["finalizer_version"],
        "starting_head": "a" * 40}, indent=2),
        encoding="utf-8", newline="\n")
    return root


@pytest.mark.parametrize("row,expect", [
    ("", "ARTWORK_ROW_ACTIVE_UNAUTHORED"),
    # A row carrying NO registrable marker is refused before it is classified:
    # whatever it would be published as, it does not assert the grant.
    ("| frozen_figures | wording nobody registered |",
     "ARTWORK_ROW_ACTIVE_MARKER_ABSENT"),
    ("| frozen_figures (Fig. 1, 4) | Figures 1 and 4 are NOT licensed under "
     "CC BY 4.0 |", "ARTWORK_ROW_ACTIVE_MARKER_ABSENT"),
    ("| frozen_figures | CC BY 4.0 PENDING |",
     "ARTWORK_ROW_ACTIVE_MARKER_ABSENT"),
    # This one DOES carry the registrable marker, so it clears the shape gate -
    # and is then caught by the classifier, because a row that also carries a
    # PENDING marker classifies as pending whatever else it says.
    ("| art | " + ACTIVE_CLAUSE + " | CC BY 4.0 PENDING |",
     "ARTWORK_ROW_STATE_MISMATCH"),
])
def test_an_active_row_must_classify_as_active(tmp_path, row, expect):
    """A denial must never be emitted as the ACTIVE row."""
    als = rf._artwork
    root = _active_tree_with_row(tmp_path, row)
    assert als.artwork_licence_state(root)[0] == als.ACTIVE
    with pytest.raises(RuntimeError) as exc:
        als.publication_artwork_row(root)
    assert expect in str(exc.value), str(exc.value)


def _unsupported_compression_zip(path):
    """A structurally valid ZIP whose compression method is unsupported."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("payload.txt", "data")
    raw = bytearray(path.read_bytes())
    i = raw.find(b"PK\x03\x04")
    raw[i + 8:i + 10] = (99).to_bytes(2, "little")
    j = raw.find(b"PK\x01\x02")
    raw[j + 10:j + 12] = (99).to_bytes(2, "little")
    path.write_bytes(bytes(raw))
    return path


def test_an_unsupported_compression_method_is_a_code_not_a_traceback(
        synthetic, tmp_path):
    """A VALID ZIP using an unsupported method raises NotImplementedError."""
    cand = _unsupported_compression_zip(tmp_path / "method99.zip")
    with pytest.raises(NotImplementedError):
        rf.archive_identity(cand)
    report = run_preflight(synthetic,
                           FakeGitHub(pr=good_pr(synthetic["head"])),
                           candidate_archive=cand)
    assert "ARCHIVE_CANDIDATE_CORRUPT" in report.codes, report.codes


def test_the_candidate_catch_is_exception_not_baseexception():
    src = (_RELEASE_DIR / "release_finalizer.py").read_text(encoding="utf-8")
    before = src.split("ARCHIVE_CANDIDATE_CORRUPT", 1)[0][-900:]
    assert "except Exception as exc" in before
    assert "except BaseException" not in before


def _plant_dangling_temp(staging, link, monkeypatch):
    """Put an entry at ``link`` for which ``exists()`` is False.

    Prefers a real dangling symlink. Where the host forbids creating one -
    Windows without Developer Mode or SeCreateSymbolicLinkPrivilege - the
    SAME OBSERVABLE CONDITION is simulated: a real directory entry that
    ``lexists`` reports and ``exists()`` denies, presenting as a symlink.

    Simulating is not a weaker test here. The defect being guarded is that
    ``Path.exists()`` answers False for something that is really there, so the
    entry gets clobbered or followed; the property under test is precisely
    "listed but exists() says no", and that is what is reproduced. Skipping
    instead would mean the guard is unproven on the machine the release is
    actually cut on - and a release run is required to report zero skips, so
    an environmental skip here is not a neutral omission.

    Returns the string describing which mechanism was used.
    """
    try:
        link.symlink_to(staging / "does-not-exist.zip")
        if os.path.lexists(link) and not link.exists():
            return "real dangling symlink"
        # Some filesystems resolve it anyway; fall through to simulation.
    except (OSError, NotImplementedError, AttributeError):
        pass
    if not os.path.lexists(link):
        link.write_bytes(b"stale temporary from an interrupted run")
    real_exists = Path.exists
    real_is_symlink = Path.is_symlink

    def exists(self, *a, **kw):
        if Path(self) == link:
            return False
        return real_exists(self, *a, **kw)

    def is_symlink(self, *a, **kw):
        if Path(self) == link:
            return True
        return real_is_symlink(self, *a, **kw)

    monkeypatch.setattr(Path, "exists", exists)
    monkeypatch.setattr(Path, "is_symlink", is_symlink)
    return "simulated dangling entry"


def test_a_dangling_temp_symlink_is_refused(e2e, monkeypatch):
    """Path.exists() is False for a dangling symlink; lexists is not.

    No environmental skip: where a real symlink cannot be created the
    condition is simulated, so this guard is proved on every host.
    """
    dest = e2e["staging"] / e2e["contract"]["identity"][
        "final_archive_filename"]
    link = dest.with_name(dest.name + ".finalizer-tmp")
    mechanism = _plant_dangling_temp(e2e["staging"], link, monkeypatch)

    # The discriminating property, asserted before the run relies on it.
    assert os.path.lexists(link), mechanism
    assert not link.exists(), (
        f"{mechanism}: exists() must be False, or this proves nothing")

    report = run_finalize(e2e)
    assert "RELEASE_STAGING_STALE_TEMP" in report.codes, (mechanism,
                                                          report.codes)
    assert os.path.lexists(link), f"{mechanism}: the entry was consumed"
    _assert_nothing_written(e2e, report)


def test_a_partial_copy_leaves_no_temporary_even_without_a_predecessor(
        e2e, monkeypatch):
    """The placement write leaves bytes, then raises. Nothing may survive.

    There is no predecessor here, so the rollback has nothing to restore -
    which is exactly the case in which a half-written temporary used to be
    left sitting beside the destination with nothing to notice it.
    """
    dest = e2e["staging"] / e2e["contract"]["identity"][
        "final_archive_filename"]
    assert not dest.exists(), "this case has NO predecessor"
    _partial_placement(monkeypatch, e2e["staging"])
    report = run_finalize(e2e)
    assert not report.ok
    assert not list(e2e["staging"].glob("*finalizer-tmp*")), \
        "a partial temporary survived with no predecessor to restore"
    assert not dest.exists()
    _assert_nothing_written(e2e, report)


def test_a_destination_recreated_after_the_move_aside_is_refused(e2e,
                                                                 monkeypatch):
    """Between the move-aside and the placement, someone recreates the file.

    ``os.replace`` would have silently overwritten it. The no-clobber
    ``os.link`` refuses instead - and the rollback then refuses to restore the
    predecessor OVER those bytes, reports that it could not complete, and says
    where the intact predecessor is.
    """
    dest = e2e["staging"] / e2e["contract"]["identity"][
        "final_archive_filename"]
    dest.write_bytes(b"PREDECESSOR ARCHIVE")
    real = rf._exclusive_copy

    def recreate(src, dst, *a, **kw):
        result = real(src, dst, *a, **kw)
        if not os.path.lexists(dest):
            dest.write_bytes(b"ANOTHER PROCESS RECREATED THIS")
        return result

    monkeypatch.setattr(rf, "_exclusive_copy", recreate)
    report = run_finalize(e2e)
    assert "RELEASE_DESTINATION_RECREATED" in report.codes, report.codes
    assert dest.read_bytes() == b"ANOTHER PROCESS RECREATED THIS", \
        "the recreated destination was overwritten or deleted"
    assert "ROLLBACK_FAILED" in report.codes, report.codes
    assert report.data.get("predecessor_recovery_path"), report.data
    recovered = Path(report.data["predecessor_recovery_path"])
    assert recovered.is_file()
    assert recovered.read_bytes() == b"PREDECESSOR ARCHIVE"


def _fire_once_after_placement(monkeypatch, dest, predecessor_bytes, action):
    """Run ``action`` on the first superseded-archive check AFTER placement.

    Keyed on the destination holding something other than the predecessor,
    which is true only once the new archive has landed. Every other call -
    preflight, and the rollback's own re-verification - delegates to the real
    function, so the adversary perturbs exactly one moment.
    """
    real = rf.verify_superseded_archive
    fired = {"n": 0}

    def hooked(root, contract):
        if (not fired["n"] and dest.is_file()
                and dest.read_bytes() != predecessor_bytes):
            fired["n"] = 1
            return action()
        return real(root, contract)

    monkeypatch.setattr(rf, "verify_superseded_archive", hooked)
    return fired


def test_a_destination_rewritten_before_the_rollback_is_not_deleted(
        e2e, monkeypatch):
    """A concurrent writer's bytes survive a rollback that wanted to undo ours.

    The rollback used to unlink the destination unconditionally, so a process
    that replaced the archive between our placement and our failure had its
    work deleted by our cleanup.
    """
    dest = e2e["staging"] / e2e["contract"]["identity"][
        "final_archive_filename"]
    predecessor_bytes = b"PREDECESSOR ARCHIVE"
    dest.write_bytes(predecessor_bytes)

    def rewrite_and_fail():
        dest.write_bytes(b"CONCURRENT WRITER BYTES")
        return [("SUPERSEDED_ARCHIVE_MODIFIED",
                 "synthetic post-placement failure")]

    fired = _fire_once_after_placement(monkeypatch, dest, predecessor_bytes,
                                       rewrite_and_fail)
    report = run_finalize(e2e)
    assert fired["n"], "the adversary never reached the post-placement check"
    assert not report.ok
    assert dest.read_bytes() == b"CONCURRENT WRITER BYTES", \
        "the concurrent writer's bytes were deleted or overwritten"
    assert "ROLLBACK_FAILED" in report.codes, report.codes
    assert report.data.get("predecessor_recovery_path"), report.data
    assert Path(report.data["predecessor_recovery_path"]).read_bytes() == \
        predecessor_bytes


def test_a_superseded_verification_that_raises_rolls_everything_back(
        e2e, monkeypatch):
    """An EXCEPTION from the post-placement check is a rollback, not a crash."""
    dest = e2e["staging"] / e2e["contract"]["identity"][
        "final_archive_filename"]
    predecessor_bytes = b"PREDECESSOR ARCHIVE"
    dest.write_bytes(predecessor_bytes)

    def explode():
        raise RuntimeError("synthetic verification explosion")

    fired = _fire_once_after_placement(monkeypatch, dest, predecessor_bytes,
                                       explode)
    report = run_finalize(e2e)
    assert fired["n"], "the adversary never reached the post-placement check"
    assert "TRANSACTION_ROLLED_BACK" in report.codes, report.codes
    # The predecessor IS back at the destination - that is what a correct
    # rollback leaves behind - so the generic "nothing was written" helper,
    # which requires an EMPTY destination, does not apply here.
    assert dest.read_bytes() == predecessor_bytes, \
        "the predecessor was not restored"
    assert not list(e2e["staging"].glob("*finalizer-tmp*"))
    assert "ROLLBACK_FAILED" not in report.codes, report.codes
    receipt = e2e["root"] / e2e["contract"]["authorization_receipt"][
        "tracked_path"]
    assert not receipt.exists(), "the receipt survived the rollback"
    for rel in e2e["contract"]["licence_records"]:
        assert PENDING_BLOCK in (e2e["root"] / rel).read_text("utf-8") or \
            MANUSCRIPT_PENDING in (e2e["root"] / rel).read_text("utf-8"), rel


def test_a_cleanup_failure_after_the_commit_point_leaves_the_release_standing(
        e2e, monkeypatch):
    """Past the terminal commit point a cleanup failure is reported, not undone.

    Destroying a completed, verified release because a displaced predecessor
    would not delete is the worst available trade.
    """
    dest = e2e["staging"] / e2e["contract"]["identity"][
        "final_archive_filename"]
    dest.write_bytes(b"PREDECESSOR ARCHIVE")
    # r3e: the post-commit cleanup no longer unlinks a pathname it verified
    # earlier - it quarantines the object and inspects what actually moved - so
    # the failure is injected at the quarantine, which is where the cleanup now
    # happens. The point of the test is unchanged: past the terminal commit
    # point a cleanup failure is REPORTED and the release stands.
    real_quarantine = rf._quarantine

    def stubborn(path, slot, **kw):
        # ONLY the displaced predecessor. r3f routes the release output
        # temporary through a quarantine as well, and that one happens BEFORE
        # the commit point - failing it there would abort the run instead of
        # exercising what this test is about, which is a cleanup failure after
        # the release already stands.
        if "superseded-finalizer-tmp" in Path(path).name:
            raise rf.FinalizerError("POST_COMMIT_QUARANTINE_FAILED",
                                    "cannot remove the displaced predecessor")
        return real_quarantine(path, slot, **kw)

    monkeypatch.setattr(rf, "_quarantine", stubborn)
    report = run_finalize(e2e)
    assert report.ok, report.codes
    assert report.data.get("commit_point") == "reached", report.data
    assert "post_commit_cleanup_warning" in report.data, report.data
    # The release itself stands, and the receipt was not rolled back.
    contract = e2e["contract"]
    assert dest.is_file() and dest.stat().st_size > len(b"PREDECESSOR ARCHIVE")
    assert (e2e["root"]
            / contract["authorization_receipt"]["tracked_path"]).is_file()


@pytest.mark.parametrize("planter", ["file", "symlink"])
def test_a_temporary_appearing_after_the_stale_check_is_refused(
        e2e, monkeypatch, planter):
    """The exact race the exclusive open closes.

    The stale-temporary check passes, and only THEN does another process
    create the very path this run is about to write. A plain open would
    clobber the file or write through the link; ``O_EXCL`` refuses.
    """
    real_check = rf._assert_no_stale_release_temporaries
    planted = {}

    def check_then_plant(destination, run_id=""):
        real_check(destination, run_id)
        if planted:
            return
        tmp_out, _displaced = rf.release_temp_paths(destination, run_id)
        if planter == "symlink":
            try:
                tmp_out.symlink_to(Path(destination).parent / "nowhere.zip")
            except (OSError, NotImplementedError, AttributeError):
                tmp_out.write_bytes(b"squatter planted after the check")
        else:
            tmp_out.write_bytes(b"squatter planted after the check")
        planted["path"] = tmp_out

    monkeypatch.setattr(rf, "_assert_no_stale_release_temporaries",
                        check_then_plant)
    report = run_finalize(e2e)
    assert planted, "the adversary never ran"
    assert "RELEASE_STAGING_STALE_TEMP" in report.codes, report.codes
    assert os.path.lexists(planted["path"]), \
        "the squatter planted after the check was consumed"
    _assert_nothing_written(e2e, report)


def test_exclusive_copy_retains_and_journals_its_partial_output(tmp_path):
    """r3g: the writer no longer unlinks a pathname on its error path.

    It used to delete the half-written file itself, which is a
    check-then-delete with the check missing. It now hands the journal the
    identity of exactly the bytes it managed to write, and the cleanup - which
    CAN prove ownership from that identity - is what removes it.
    """
    journal = rf._RunTemporaries("rid")
    src = tmp_path / "src.bin"
    src.write_bytes(b"payload")
    dst = tmp_path / ("out" + rf.RELEASE_TEMP_TOKEN)

    class Halfway(io.BytesIO):
        def read(self, *a):
            raise OSError("disk full mid-copy")

    import builtins
    real_open = builtins.open

    def fake_open(path, *a, **kw):
        try:
            same = Path(path) == src
        except TypeError:
            same = False
        return Halfway() if same else real_open(path, *a, **kw)

    builtins.open = fake_open
    try:
        with pytest.raises(OSError):
            rf._exclusive_copy(src, dst, journal=journal)
    finally:
        builtins.open = real_open

    assert os.path.lexists(dst),         "the writer deleted a pathname on its error path"
    assert journal.unresolved[str(dst)]["confirmed"] is True
    # ...and the cleanup, which knows the identity, may remove it.
    assert journal.discard(dst, what="the partial output") is True
    assert not os.path.lexists(dst)


def test_exclusive_copy_refuses_a_target_that_already_exists(tmp_path):
    """O_EXCL: something planted after the stale check is refused, not written.

    This is the race the run-unique name narrows and the exclusive open
    closes: between the last stale-temporary check and this open, another
    process may create the very path we are about to write.
    """
    src = tmp_path / "src.bin"
    src.write_bytes(b"payload")
    dst = tmp_path / ("out." + rf.RELEASE_TEMP_TOKEN)
    dst.write_bytes(b"squatter")
    with pytest.raises(rf.FinalizerError) as exc:
        rf._exclusive_copy(src, dst)
    assert exc.value.code == "RELEASE_STAGING_STALE_TEMP"
    assert dst.read_bytes() == b"squatter", "the squatter was overwritten"


def test_bytes_written_after_the_private_snapshot_are_preserved(e2e,
                                                                monkeypatch):
    """A concurrent writer's bytes must be preserved, not an older snapshot."""
    dest = e2e["staging"] / e2e["contract"]["identity"][
        "final_archive_filename"]
    dest.write_bytes(b"ORIGINAL PREDECESSOR")
    real_copy = rf.shutil.copy2
    fired = {"n": 0}

    def mutate_after_snapshot(src, dst, *a, **kw):
        result = real_copy(src, dst, *a, **kw)
        if Path(dst).name == "predecessor.zip" and not fired["n"]:
            fired["n"] = 1
            dest.write_bytes(b"CONCURRENT WRITER BYTES")
        return result

    monkeypatch.setattr(rf.shutil, "copy2", mutate_after_snapshot)
    report = run_finalize(e2e)
    assert "PREDECESSOR_MUTATED" in report.codes, report.codes
    assert dest.read_bytes() == b"CONCURRENT WRITER BYTES", \
        "the concurrent writer's bytes were discarded"


def test_a_failed_rollback_reports_the_snapshot_recovery_path(e2e,
                                                              monkeypatch):
    """When rollback cannot be verified, say where the last copy is."""
    dest = e2e["staging"] / e2e["contract"]["identity"][
        "final_archive_filename"]
    dest.write_bytes(b"PRE-EXISTING PREDECESSOR ARCHIVE")

    _fail_only_at_placement(monkeypatch, e2e["staging"])
    # Fail only once the archive is actually in place (see above).
    _destination_unreadable_after(monkeypatch, dest, after=2)
    report = run_finalize(e2e)
    assert "ROLLBACK_FAILED" in report.codes
    recovery = report.data.get("predecessor_recovery_path")
    assert recovery, "no recovery path was reported"
    assert Path(recovery).is_file(), (
        "the private snapshot was deleted despite an unverified rollback")
    assert Path(recovery).read_bytes() == b"PRE-EXISTING PREDECESSOR ARCHIVE"


def test_running_the_cli_creates_no_pycache(tmp_path):
    """The residual write preflight used to make without admitting it."""
    import shutil as _shutil
    scripts = tmp_path / "scripts"
    _shutil.copytree(REPO / "scripts", scripts,
                     ignore=_shutil.ignore_patterns("__pycache__"))
    assert not list(scripts.rglob("__pycache__"))

    env = dict(os.environ)
    env.pop("PYTHONDONTWRITEBYTECODE", None)   # the module must not need it
    subprocess.run(
        [sys.executable, str(scripts / "release" / "release_finalizer.py"),
         "preflight", "--repo-root", str(tmp_path / "absent"),
         "--expect-branch", "b", "--expect-head", "h"],
        cwd=str(tmp_path), env=env, capture_output=True, text=True)

    stray = sorted(p.relative_to(tmp_path).as_posix()
                   for p in scripts.rglob("__pycache__"))
    assert stray == [], f"preflight created bytecode caches: {stray}"


# ---------------------------------------------------------------------------
# 24. r3d: the tracked-file transaction is no longer a predictable sibling
#
# `_atomic_write` wrote every target through `<target>.finalizer-tmp` with an
# ordinary open(). Every test below reaches the branch it names and asserts
# that it did, so a refusal that happened for some other reason cannot pass as
# this one.
# ---------------------------------------------------------------------------
def _can_symlink(tmp_path):
    """Whether this process may create symlinks at all.

    Windows gates ``os.symlink`` behind SeCreateSymbolicLinkPrivilege, which an
    ordinary account does not hold. A release run requires ZERO skipped tests,
    so nothing below is allowed to skip on that account: each adversary reaches
    the branch it is about by whatever means the platform allows - a real link
    where one can be made, and an equivalent non-regular object or a stubbed
    ``lstat`` where one cannot.
    """
    probe = Path(tmp_path) / "_symlink_probe"
    try:
        os.symlink(str(tmp_path), str(probe))
    except (OSError, NotImplementedError, AttributeError):
        return False
    ok = probe.is_symlink()
    try:
        probe.unlink()
    except OSError:
        pass
    return ok


def _plant_non_regular(path, tmp_path, victim=None):
    """Put a NON-REGULAR object at ``path`` and say which kind it is.

    Returns ``("symlink", victim)`` when a real link could be planted, and
    ``("directory", None)`` otherwise. Both reach the same branch: the target
    is not a regular file, so it is neither read through nor written through.
    """
    path = Path(path)
    if victim is not None and _can_symlink(tmp_path):
        os.symlink(str(victim), str(path))
        if path.is_symlink():
            return "symlink", victim
    path.mkdir(parents=True)
    return "directory", None


def test_no_predictable_sibling_temporary_survives_in_the_source():
    """The whole class of defect: a guessable name beside a real target."""
    src = (_RELEASE_DIR / "release_finalizer.py").read_text(encoding="utf-8")
    assert "def _atomic_write" not in src, \
        "_atomic_write is back; its sibling name is guessable and followed"
    body = src.split("class Transaction", 1)[1].split(
        "\n#: The two exclusive locks", 1)[0]
    assert 'with_name(target.name + ".finalizer-tmp")' not in body
    assert "_write_new(" in body and "_link_no_clobber(" in body, \
        "the transaction no longer stages exclusively and places no-clobber"


def test_a_symlink_planted_at_a_tracked_target_is_never_written_through(
        synthetic, tmp_path):
    """A link at a TRACKED path must not carry the write to its target."""
    root = synthetic["root"]
    rel = "docs/CANONICAL_SCIENCE.json"
    edits = [e for e in rf.plan_identity_edits(
        root, synthetic["contract"], old_identity(), new_identity())
        if e.rel == rel]
    assert edits, "the fixture no longer edits this file"

    bystander = tmp_path / "unrelated_file.txt"
    bystander.write_bytes(b"UNRELATED CONTENT")
    (root / rel).unlink()
    kind, _ = _plant_non_regular(root / rel, tmp_path, victim=bystander)

    txn = rf.Transaction(root, synthetic["contract"])
    with pytest.raises(rf.FinalizerError) as exc:
        txn.apply(edits)
    assert exc.value.code in ("TRANSACTION_TARGET_NOT_REGULAR",
                              "CONCURRENT_MODIFICATION"), \
        f"{exc.value.code} for a planted {kind}"
    assert bystander.read_bytes() == b"UNRELATED CONTENT", \
        "the write followed the planted object and destroyed another file"


def test_a_non_regular_object_at_the_staging_slot_is_refused(tmp_path):
    """The run-owned staging slot is created exclusively and no-follow."""
    bystander = tmp_path / "victim.txt"
    bystander.write_bytes(b"VICTIM")
    slot = tmp_path / "slot"
    kind, _ = _plant_non_regular(slot, tmp_path, victim=bystander)
    with pytest.raises(rf.FinalizerError) as exc:
        rf._write_new(slot, b"OVERWRITTEN", exists_code="STAGE_OCCUPIED",
                      exists_why="occupied")
    assert exc.value.code == "STAGE_OCCUPIED", f"planted {kind}"
    assert bystander.read_bytes() == b"VICTIM", \
        "the exclusive create followed a planted object"


def test_the_exclusive_open_asks_for_no_follow_where_the_platform_has_it():
    """O_NOFOLLOW is requested when the platform provides it."""
    if hasattr(os, "O_NOFOLLOW"):
        assert rf._EXCL_FLAGS & os.O_NOFOLLOW
    assert rf._EXCL_FLAGS & os.O_EXCL and rf._EXCL_FLAGS & os.O_CREAT
    src = (_RELEASE_DIR / "release_finalizer.py").read_text(encoding="utf-8")
    body = src.split("def _read_regular_file", 1)[1].split("\ndef ", 1)[0]
    assert 'getattr(os, "O_NOFOLLOW", 0)' in body
    assert "S_ISREG" in body, "a non-regular target is not refused on read"


def test_a_regular_stale_temporary_is_refused_not_reused(tmp_path):
    """An interrupted run's leftover is evidence, not scratch to truncate."""
    stale = tmp_path / "leftover"
    stale.write_bytes(b"BYTES FROM AN INTERRUPTED RUN")
    with pytest.raises(rf.FinalizerError) as exc:
        rf._write_new(stale, b"NEW",
                      exists_code="TRANSACTION_STAGING_OCCUPIED",
                      exists_why="a stale temporary is present")
    assert exc.value.code == "TRANSACTION_STAGING_OCCUPIED"
    assert stale.read_bytes() == b"BYTES FROM AN INTERRUPTED RUN", \
        "the stale temporary was truncated and reused"


def test_a_receipt_appearing_concurrently_is_preserved_and_refuses(synthetic):
    """A receipt that shows up mid-transaction is somebody's evidence."""
    root = synthetic["root"]
    rel = synthetic["contract"]["authorization_receipt"]["tracked_path"]
    payload = b'{"mine": true}\n'
    txn = rf.Transaction(root, synthetic["contract"])
    txn._capture(rel, payload, True)                  # snapshot: absent
    assert txn.journal[rel].original is None

    # ...and NOW it appears, after the snapshot and before the write.
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_bytes(b'{"someone_elses": true}\n')

    with pytest.raises(rf.FinalizerError) as exc:
        txn._write_target(txn.journal[rel])
    assert exc.value.code in ("RECEIPT_APPEARED_CONCURRENTLY",
                              "CONCURRENT_MODIFICATION"), exc.value.code
    assert (root / rel).read_bytes() == b'{"someone_elses": true}\n', \
        "the concurrent receipt was overwritten"


def test_a_target_recreated_after_move_aside_is_refused(synthetic,
                                                        monkeypatch):
    """os.replace would have silently overwritten the recreated file."""
    root = synthetic["root"]
    rel = "docs/CANONICAL_SCIENCE.json"
    edits = [e for e in rf.plan_identity_edits(
        root, synthetic["contract"], old_identity(), new_identity())
        if e.rel == rel]
    txn = rf.Transaction(root, synthetic["contract"])
    real_write_new = rf._write_new
    fired = {"n": 0}

    def recreate(path, data, **kw):
        result = real_write_new(path, data, **kw)
        if Path(path).name.startswith("stage."):
            # Somebody puts a file back at the destination while we stage.
            Path(root / rel).write_bytes(b"RECREATED BY ANOTHER PROCESS")
            fired["n"] += 1
        return result

    monkeypatch.setattr(rf, "_write_new", recreate)
    with pytest.raises(rf.FinalizerError) as exc:
        txn.apply(edits)
    assert fired["n"] == 1, "the adversary never recreated the destination"
    assert exc.value.code == "TRANSACTION_TARGET_RECREATED", exc.value.code
    assert (root / rel).read_bytes() == b"RECREATED BY ANOTHER PROCESS", \
        "the recreated file was overwritten"

    # The rollback must not delete those bytes either, and must say where the
    # original went.
    monkeypatch.setattr(rf, "_write_new", real_write_new)
    with pytest.raises(rf.RollbackError):
        txn.rollback()
    assert (root / rel).read_bytes() == b"RECREATED BY ANOTHER PROCESS"
    assert Path(txn.recovery_paths[rel]).is_file(), \
        "the original was not preserved"
    assert txn.journal[rel].preserved


def test_a_concurrent_edit_after_a_write_is_preserved_by_the_rollback(
        synthetic):
    """The rollback removes OUR bytes, never somebody else's."""
    root = synthetic["root"]
    rel = "docs/CANONICAL_SCIENCE.json"
    edits = rf.plan_identity_edits(root, synthetic["contract"],
                                   old_identity(), new_identity())
    txn = rf.Transaction(root, synthetic["contract"])
    txn.apply(edits)

    # An external editor rewrites one file AFTER the transaction wrote it.
    hostile = b'{"edited": "by a human, after the write"}\n'
    (root / rel).write_bytes(hostile)

    with pytest.raises(rf.RollbackError) as exc:
        txn.rollback()
    assert any("preserved" in f and rel in f for f in exc.value.failures), \
        exc.value.failures
    assert (root / rel).read_bytes() == hostile, \
        "the rollback destroyed an edit it did not make"
    assert txn.journal[rel].preserved
    assert Path(txn.recovery_paths[rel]).is_file()
    # Every OTHER file still went back.
    other = [e.rel for e in edits if e.rel != rel][0]
    assert (root / other).read_bytes() == txn.journal[other].original


def test_two_transactions_interleaving_cannot_share_a_recovery_slot(synthetic):
    """Run-unique staging: neither run can see or reuse the other's slots."""
    root, contract = synthetic["root"], synthetic["contract"]
    first = rf.Transaction(root, contract, run_id="aaaaaaaaaaaaaaaa")
    second = rf.Transaction(root, contract, run_id="bbbbbbbbbbbbbbbb")
    assert first._recovery_root() != second._recovery_root()
    assert first._slot("x/y.json", "orig") != second._slot("x/y.json", "orig")

    edits = rf.plan_identity_edits(root, contract, old_identity(),
                                   new_identity())
    first.apply(edits)
    # The second run's plan was made against the ORIGINAL bytes, which are no
    # longer there. It must refuse rather than write over the first run.
    with pytest.raises(rf.FinalizerError) as exc:
        second.apply(edits)
    assert exc.value.code == "CONCURRENT_MODIFICATION", exc.value.code
    first.rollback()
    assert first.journal[edits[0].rel].preserved is None


# ---------------------------------------------------------------------------
# 25. r3d: the two exclusive locks
# ---------------------------------------------------------------------------
def test_a_second_finalizer_fails_normally_and_touches_nothing(e2e):
    """The whole long finalization runs under a lock on both areas."""
    root, staging = Path(e2e["root"]), Path(e2e["staging"])
    final_name = e2e["contract"]["identity"]["final_archive_filename"]
    held = rf._acquire_finalizer_locks(root, staging, "held-by-run-one")
    before = snapshot(root)
    try:
        report = run_finalize(e2e)
        assert "FINALIZER_LOCK_HELD" in report.codes, report.codes
        assert not report.ok
        assert snapshot(root) == before, \
            "the second finalizer wrote to the tree"
        assert not (staging / final_name).exists(), \
            "the second finalizer placed an archive"
    finally:
        for lock in held:
            lock.release()

    # ...and with the lock gone the same run succeeds, so the refusal above
    # really was the lock and not some other unmet precondition.
    assert run_finalize(e2e).ok


def test_an_unknown_stale_lock_is_never_removed_or_reused(tmp_path):
    """A lock nobody can account for needs a human, not an automatic sweep."""
    lock_path = tmp_path / "scorch_finalizer.lock"
    foreign = b'{"run_id": "someone-else", "pid": 4242}'
    lock_path.write_bytes(foreign)
    lock = rf._Lock(lock_path, "my-run")
    with pytest.raises(rf.FinalizerError) as exc:
        lock.acquire()
    assert exc.value.code == "FINALIZER_LOCK_HELD"
    assert "NOT removed or reused" in exc.value.why
    assert lock_path.read_bytes() == foreign

    # Releasing a lock we never took, and never owned, removes nothing.
    lock.release()
    assert lock_path.is_file(), "another run's lock was deleted"


def test_a_failed_second_lock_releases_the_first(tmp_path):
    """A refused run leaves no lock of its own behind."""
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / rf.STAGING_LOCK_NAME).write_bytes(b'{"run_id": "other"}')
    with pytest.raises(rf.FinalizerError) as exc:
        rf._acquire_finalizer_locks(root, staging, "mine")
    assert exc.value.code == "FINALIZER_LOCK_HELD"
    assert not (root / ".git" / rf.WORKTREE_LOCK_NAME).exists(), \
        "the worktree lock survived a refused acquisition"


def test_a_successful_run_releases_both_locks(e2e):
    root, staging = Path(e2e["root"]), Path(e2e["staging"])
    assert run_finalize(e2e).ok
    assert not (root / ".git" / rf.WORKTREE_LOCK_NAME).exists()
    assert not (staging / rf.STAGING_LOCK_NAME).exists()


# ---------------------------------------------------------------------------
# 26. r3d: moved predecessor bytes are preserved, never re-snapshotted over
# ---------------------------------------------------------------------------
ORIGINAL_SNAP = b"THE ORIGINAL SNAPSHOT"
CONCURRENT = b"WRITTEN BY A CONCURRENT PROCESS"


def _predecessor(tmp_path, moved=CONCURRENT):
    pred_dir = tmp_path / "private"
    pred_dir.mkdir()
    displaced = tmp_path / "displaced.zip"
    displaced.write_bytes(moved)
    original = pred_dir / "predecessor.zip"
    original.write_bytes(ORIGINAL_SNAP)
    return pred_dir, displaced, {
        "path": original, "sha256": rf.sha256_bytes(ORIGINAL_SNAP),
        "bytes": len(ORIGINAL_SNAP)}


def test_moved_bytes_go_to_a_second_snapshot_not_over_the_first(tmp_path):
    """Mutation INSIDE the destination -> displaced replace window."""
    pred_dir, displaced, pred = _predecessor(tmp_path)
    out = rf._snapshot_moved_predecessor(displaced, dict(pred), pred_dir, "rid")

    assert Path(pred["path"]).read_bytes() == ORIGINAL_SNAP, \
        "the original private snapshot was overwritten"
    second = Path(out["second_snapshot_path"])
    assert second != Path(pred["path"])
    assert second.read_bytes() == CONCURRENT
    assert displaced.read_bytes() == CONCURRENT, \
        "the intact moved file was disturbed"
    # Only after a COMPLETE verified second snapshot does the identity move.
    assert out["sha256"] == rf.sha256_bytes(CONCURRENT)
    assert out["mutated_after_snapshot"] is True


def test_a_partial_resnapshot_retains_the_moved_file_and_both_paths(
        tmp_path, monkeypatch):
    """A copy that fails halfway must never become the recovery source."""
    pred_dir, displaced, pred = _predecessor(tmp_path)
    fired = {"n": 0}

    def half_written(src, dst):
        Path(dst).write_bytes(CONCURRENT[:6])          # a TRUNCATED copy
        fired["n"] += 1
        raise OSError("device full")

    monkeypatch.setattr(rf, "_exclusive_copy", half_written)
    out = rf._snapshot_moved_predecessor(displaced, dict(pred), pred_dir, "rid")

    assert fired["n"] == 1, "the adversary never ran"
    assert "second_snapshot_failed" in out
    assert "second_snapshot_path" not in out, \
        "a partial copy was offered as a recovery source"
    assert displaced.read_bytes() == CONCURRENT, \
        "the complete moved file was deleted in favour of a partial copy"
    assert Path(pred["path"]).read_bytes() == ORIGINAL_SNAP
    # The identity must NOT move to bytes we cannot prove we captured.
    assert out["sha256"] == pred["sha256"]
    assert out["moved_sha256"] == rf.sha256_bytes(CONCURRENT)


def test_a_mismatched_second_snapshot_is_discarded(tmp_path, monkeypatch):
    """A snapshot that does not equal the moved bytes is not a snapshot."""
    pred_dir, displaced, pred = _predecessor(tmp_path)

    def wrong(src, dst):
        Path(dst).write_bytes(b"SOMETHING ELSE ENTIRELY")
        return Path(dst)

    monkeypatch.setattr(rf, "_exclusive_copy", wrong)
    out = rf._snapshot_moved_predecessor(displaced, dict(pred), pred_dir, "rid")
    assert "second_snapshot_path" not in out
    assert out["second_snapshot_failed"]
    assert not (pred_dir / "predecessor_moved_rid.zip").exists(), \
        "a mismatched snapshot was left where it could later be selected"
    assert displaced.read_bytes() == CONCURRENT
    assert out["sha256"] == pred["sha256"]


@pytest.mark.parametrize("kind", ["file", "non_regular"])
def test_a_planted_displaced_path_is_refused(e2e, tmp_path, kind, monkeypatch):
    """The displaced name is RESERVED exclusively before the rename."""
    staging = Path(e2e["staging"])
    final_name = e2e["contract"]["identity"]["final_archive_filename"]
    destination = staging / final_name
    predecessor_bytes = b"PRE-EXISTING PREDECESSOR ARCHIVE"
    destination.write_bytes(predecessor_bytes)

    victim = tmp_path / "planted_victim.txt"
    victim.write_bytes(b"PLANTED VICTIM")
    planted = {"seen": False, "kind": None}
    real_sweep = rf._assert_no_stale_release_temporaries

    def sweep_then_plant(dest, run_id=""):
        real_sweep(dest, run_id)
        # Plant AFTER a sweep has passed: that is exactly the window the
        # exclusive reservation of the displaced name closes.
        if run_id and not planted["seen"]:
            _tmp_out, displaced_path = rf.release_temp_paths(dest, run_id)
            planted["seen"] = True
            if kind == "file":
                Path(displaced_path).write_bytes(b"PLANTED")
                planted["kind"] = "file"
            else:
                planted["kind"], _ = _plant_non_regular(
                    displaced_path, tmp_path, victim=victim)

    monkeypatch.setattr(rf, "_assert_no_stale_release_temporaries",
                        sweep_then_plant)
    report = run_finalize(e2e)

    assert planted["seen"], "the adversary never planted anything"
    assert "RELEASE_STAGING_STALE_TEMP" in report.codes, \
        f"{report.codes} for a planted {planted['kind']}"
    assert destination.read_bytes() == predecessor_bytes, \
        "the predecessor was lost"
    assert victim.read_bytes() == b"PLANTED VICTIM", \
        "the move-aside followed a planted object"


def test_a_destination_recreated_during_restore_is_not_overwritten(tmp_path):
    """The restore is no-clobber: recreated bytes survive it."""
    staging = tmp_path / "staging"
    staging.mkdir()
    destination = staging / "archive.zip"
    displaced = staging / "archive.zip.rid.superseded-finalizer-tmp"
    displaced.write_bytes(b"THE PREDECESSOR")
    destination.write_bytes(b"RECREATED BY SOMEONE ELSE")

    out = rf._rollback_output(
        destination, displaced, placed=False,
        predecessor={"path": tmp_path / "absent.zip",
                     "sha256": rf.sha256_bytes(b"THE PREDECESSOR"),
                     "bytes": len(b"THE PREDECESSOR")})
    assert out["failures"], "a recreated destination was silently overwritten"
    assert any("recreated" in f for f in out["failures"]), out["failures"]
    assert destination.read_bytes() == b"RECREATED BY SOMEONE ELSE"
    assert displaced.read_bytes() == b"THE PREDECESSOR"
    assert out["predecessor_recovery_paths"], "no recovery path was reported"


def test_a_concurrently_replaced_destination_is_not_deleted(tmp_path):
    """Rollback deletes the archive it placed, not whatever is there now."""
    staging = tmp_path / "staging"
    staging.mkdir()
    destination = staging / "archive.zip"
    destination.write_bytes(b"WRITTEN BY ANOTHER PROCESS")
    out = rf._rollback_output(destination, None, placed=True,
                              placed_sha256=rf.sha256_bytes(b"OUR BYTES"))
    assert any("did not write" in f for f in out["failures"]), out["failures"]
    assert destination.read_bytes() == b"WRITTEN BY ANOTHER PROCESS"


# ---------------------------------------------------------------------------
# 27. r3d: the reverification immediately before the commit point
# ---------------------------------------------------------------------------
def test_a_tracked_edit_after_placement_prevents_success(e2e, monkeypatch):
    """Placement takes time. A licence file edited during it must not ship."""
    root = Path(e2e["root"])
    rel = e2e["contract"]["licence_records"][0]
    hostile = b"EDITED FROM OUTSIDE DURING ARCHIVE PLACEMENT\n"
    fired = {"n": 0}
    real_link = rf._link_no_clobber

    def edit_during_placement(source, destination, **kw):
        result = real_link(source, destination, **kw)
        # Only for the ARCHIVE placement, which is the last link of the run.
        if str(destination).endswith(".zip"):
            fired["n"] += 1
            (root / rel).write_bytes(hostile)
        return result

    monkeypatch.setattr(rf, "_link_no_clobber", edit_during_placement)
    report = run_finalize(e2e)
    assert fired["n"] == 1, "the adversary never ran during placement"
    assert "POSTIMAGE_MUTATED_BEFORE_COMMIT" in report.codes, report.codes
    assert report.data.get("commit_point") != "reached", \
        "the run committed despite a postimage that had moved"
    # The external edit is REPORTED, never deleted.
    assert (root / rel).read_bytes() == hostile, \
        "the run deleted an edit made from outside"
    assert "ROLLBACK_FAILED" in report.codes
    assert report.data.get("transaction_recovery_paths", {}).get(rel), \
        "the original was not preserved with a reported recovery path"


def test_the_commit_point_reverification_covers_every_contracted_surface():
    """Named explicitly, so a surface cannot be dropped without noticing."""
    src = (_RELEASE_DIR / "release_finalizer.py").read_text(encoding="utf-8")
    body = src.split("def _reverify_before_commit", 1)[1].split("\ndef ", 1)[0]
    for needle in ("expected_sha256", "resolve_receipt_path",
                   "archive_sha256", "PREDECESSOR_RECOVERY_LOST",
                   "_assert_protected_blobs_intact", 'contract["figures"]',
                   "verify_superseded_archive", "verify_technical_source",
                   "docx_fixtures", "aptos_font_sha256"):
        assert needle in body, f"the commit-point recheck omits {needle}"
    # ...and it is the LAST thing that happens before the terminal commit.
    tail = src.split("_reverify_before_commit(\n", 1)[1]
    between = tail.split("committed = True", 1)[0]
    assert "raise " not in between and "os.replace" not in between, \
        "something else happens between the recheck and the commit point"


# ---------------------------------------------------------------------------
# 28. r3d: the receipt path is contained, regular, and read no-follow
# ---------------------------------------------------------------------------
def test_a_symlinked_receipt_outside_the_repository_is_never_active(
        tmp_path, monkeypatch):
    """A perfectly valid receipt somewhere else licenses nothing here.

    Runs on every platform. Where symlinks can be created, a real one is
    planted; where the privilege is unavailable, ``lstat`` and ``readlink`` are
    stubbed for that one path so the decision under test - "the contracted path
    is a link, therefore RECEIPT_PATH_INVALID" - is exercised either way. It
    never skips: a release run requires zero skipped tests, and this is one of
    the checks a release most needs to have actually run.
    """
    als = rf._artwork
    root = _active_tree_with_row(tmp_path, ACTIVE_ROW)
    assert als.artwork_licence_state(root)[0] == als.ACTIVE, \
        "the fixture is not ACTIVE to begin with, so this proves nothing"

    contract = rf.loads_strict(
        (root / "scripts/release/finalizer_contract.json")
        .read_text(encoding="utf-8"))
    rel = contract["authorization_receipt"]["tracked_path"]
    target = root / rel
    outside = tmp_path / "elsewhere" / "receipt.json"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_bytes(target.read_bytes())          # a VALID receipt

    if _can_symlink(tmp_path):
        target.unlink()
        os.symlink(str(outside), str(target))
        assert target.is_symlink()
    else:
        import stat as _stat
        real_lstat = os.lstat

        class _LinkStat:
            def __init__(self, base):
                self.st_mode = (base.st_mode & ~_stat.S_IFMT(base.st_mode)) \
                    | _stat.S_IFLNK

            def __getattr__(self, name):
                return 0

        def fake_lstat(path, *a, **kw):
            info = real_lstat(path, *a, **kw)
            if Path(str(path)) == target:
                return _LinkStat(info)
            return info

        monkeypatch.setattr(os, "lstat", fake_lstat)
        monkeypatch.setattr(os, "readlink",
                            lambda p, *a, **kw: str(outside))

    path, issues = als.resolve_receipt_path(root)
    assert path is None, "a link at the contracted path was accepted"
    assert [c for c, _ in issues] == ["RECEIPT_PATH_INVALID"], issues
    assert "SYMLINK" in issues[0][1], issues[0][1]

    state, state_issues, _detail = als.artwork_licence_state(root)
    assert state != als.ACTIVE, \
        "a receipt outside the repository carried the artwork to ACTIVE"
    assert "RECEIPT_PATH_INVALID" in [c for c, _ in state_issues]


def _special_object_kinds():
    kinds = ["directory"]
    if hasattr(os, "mkfifo"):
        kinds.append("fifo")
    return kinds


@pytest.mark.parametrize("kind", _special_object_kinds())
def test_a_special_object_at_the_receipt_path_is_refused(tmp_path, kind):
    als = rf._artwork
    root = _active_tree_with_row(tmp_path, ACTIVE_ROW)
    contract = rf.loads_strict(
        (root / "scripts/release/finalizer_contract.json")
        .read_text(encoding="utf-8"))
    target = root / contract["authorization_receipt"]["tracked_path"]
    target.unlink()
    if kind == "directory":
        target.mkdir()
    else:
        os.mkfifo(str(target))
    path, issues = als.resolve_receipt_path(root)
    assert path is None
    assert [c for c, _ in issues] == ["RECEIPT_PATH_INVALID"], issues
    assert "not a regular file" in issues[0][1]
    assert als.artwork_licence_state(root)[0] != als.ACTIVE


def test_a_receipt_resolving_outside_the_repository_is_refused(tmp_path,
                                                               monkeypatch):
    """Containment is checked by REALPATH, not only by object type."""
    als = rf._artwork
    root = _active_tree_with_row(tmp_path, ACTIVE_ROW)
    contract = rf.loads_strict(
        (root / "scripts/release/finalizer_contract.json")
        .read_text(encoding="utf-8"))
    rel = contract["authorization_receipt"]["tracked_path"]
    target = root / rel
    outside = tmp_path / "outside" / "receipt.json"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_bytes(target.read_bytes())

    real_realpath = os.path.realpath

    def fake_realpath(path, *a, **kw):
        if Path(str(path)) == target:
            return str(outside)
        return real_realpath(path, *a, **kw)

    monkeypatch.setattr(os.path, "realpath", fake_realpath)
    path, issues = als.resolve_receipt_path(root)
    assert path is None
    assert [c for c, _ in issues] == ["RECEIPT_PATH_INVALID"], issues
    assert "outside the repository" in issues[0][1]


def test_every_receipt_surface_uses_the_same_containment_rule():
    """The helper, the builder, the guards and the finalizer, not just one."""
    helper = (_RELEASE_DIR / "artwork_licence_state.py").read_text(
        encoding="utf-8")
    assert "def resolve_receipt_path" in helper
    assert "def safe_read_receipt" in helper
    state_body = helper.split("def artwork_licence_state", 1)[1].split(
        "\n#: An ACTIVE marker", 1)[0]
    assert "resolve_receipt_path(root, contract)" in state_body
    # r3e: the bytes come from the SINGLE fail-closed safe open, not from a
    # second, plain open of a pathname a previous call happened to approve.
    assert "safe_read_receipt(path, root)" in state_body, \
        "the state reads the receipt through something other than the one " \
        "fail-closed safe-open operation"
    assert "read_receipt_bytes(" not in state_body, \
        "the inspect-then-reopen split is back"

    fin = (_RELEASE_DIR / "release_finalizer.py").read_text(encoding="utf-8")
    assert fin.count("_artwork.resolve_receipt_path") >= 3, \
        "the finalizer does not apply the containment rule at every surface"


# ---------------------------------------------------------------------------
# 29. r3d: supersession by the author's LATEST ACTIVITY, not creation order
# ---------------------------------------------------------------------------
def _find(comments):
    return rf.find_authorization(
        FakeGitHub(pr=good_pr("h" * 40), comments=list(comments)),
        rf.load_contract())


@pytest.mark.parametrize("later_body,what", [
    ("I revoke the authorization given above. Do not distribute the artwork.",
     "revocation"),
    ("The authorization above applies only to Figure 1, and not to Figure 4.",
     "qualification"),
])
def test_an_older_comment_edited_after_the_grant_invalidates_it(later_body,
                                                                what):
    """created_at ordering read an edited-in revocation as ancient history."""
    grant = comment(cid=200, created="2026-02-01T00:00:00Z",
                    updated="2026-02-01T00:00:00Z")
    # POSTED BEFORE the grant, EDITED AFTER it into a revocation/qualification.
    edited = comment(body=later_body, cid=100,
                     created="2026-01-01T00:00:00Z",
                     updated="2026-03-01T00:00:00Z")
    record, issues = _find([edited, grant])
    assert record is None, f"an edited-in {what} was ignored"
    assert [c for c, _ in issues] == ["AUTHZ_SUPERSEDED_OR_QUALIFIED"], issues
    assert "last edited 2026-03-01T00:00:00Z" in issues[0][1], issues[0][1]


def test_an_older_unedited_comment_does_not_supersede_the_grant():
    """The control: without the edit the same pair MUST authorize."""
    grant = comment(cid=200, created="2026-02-01T00:00:00Z")
    earlier = comment(body="Looks good, reviewing now.", cid=100,
                      created="2026-01-01T00:00:00Z")
    record, issues = _find([earlier, grant])
    assert issues == [], issues
    assert record is not None and record["comment_id"] == 200


def test_equal_activity_timestamps_break_deterministically_on_id():
    """A tie must not depend on the order the API returned the page in."""
    stamp = "2026-02-01T00:00:00Z"
    for order in ([comment(cid=100, created=stamp),
                   comment(body="Actually, hold off for now.", cid=101,
                           created=stamp)],
                  [comment(body="Actually, hold off for now.", cid=101,
                           created=stamp),
                   comment(cid=100, created=stamp)]):
        record, issues = _find(order)
        assert record is None, "the tie resolved in favour of the grant"
        assert [c for c, _ in issues] == ["AUTHZ_SUPERSEDED_OR_QUALIFIED"]

    # The mirror image: the GRANT carries the higher id and wins both orders.
    for order in ([comment(cid=101, created=stamp),
                   comment(body="Reviewing.", cid=100, created=stamp)],
                  [comment(body="Reviewing.", cid=100, created=stamp),
                   comment(cid=101, created=stamp)]):
        record, issues = _find(order)
        assert issues == [], issues
        assert record["comment_id"] == 101


def test_an_unparsable_timestamp_refuses_rather_than_guessing():
    """An unorderable timeline cannot show that nothing came after."""
    grant = comment(cid=200, created="2026-02-01T00:00:00Z")
    broken = comment(body="hm", cid=100, created="2026-13-45T99:99:99Z",
                     updated="not a date at all")
    record, issues = _find([broken, grant])
    assert record is None
    assert [c for c, _ in issues] == ["AUTHZ_TIMESTAMP_UNPARSABLE"], issues


def test_pagination_and_the_two_live_refetches_are_retained():
    """The r3c improvements survive the r3d ordering change."""
    src = (_RELEASE_DIR / "release_finalizer.py").read_text(encoding="utf-8")
    assert '"--paginate", "--slurp"' in src
    body = src.split("def find_authorization", 1)[1].split("\ndef ", 1)[0]
    assert "live_fetches_required" in body
    assert "github.issue_comment(owner, name, chosen" in body


# ---------------------------------------------------------------------------
# 30. r3d: ACTIVE wording is enforced centrally
# ---------------------------------------------------------------------------
GOOD_CLAUSE = ("Figures 1 and 4 are licensed under the Creative Commons "
               "Attribution 4.0 International licence (CC BY 4.0).")


@pytest.mark.parametrize("marker,code", [
    ("Figure 1 is licensed under the Creative Commons Attribution 4.0 "
     "International licence (CC BY 4.0).", "CCBY_ACTIVE_MARKER_UNSCOPED"),
    ("Figure 4 is licensed under the Creative Commons Attribution 4.0 "
     "International licence (CC BY 4.0).", "CCBY_ACTIVE_MARKER_UNSCOPED"),
    ("Figures 1 and 4 and CC BY 4.0 are discussed in the licensing section "
     "of this document.", "CCBY_ACTIVE_MARKER_NOT_AFFIRMATIVE"),
    ("Figures 1 and 4 may be licensed under CC BY 4.0 after approval by the "
     "coauthor.", "CCBY_ACTIVE_MARKER_CONDITIONAL"),
    ("Figures 1 and 4 are licensed under CC BY 4.0 if approved by the "
     "copyright holder.", "CCBY_ACTIVE_MARKER_CONDITIONAL"),
    ("Figures 1 and 4 are licensed under CC BY 4.0 subject to written "
     "authorization from the coauthor.", "CCBY_ACTIVE_MARKER_CONDITIONAL"),
    ("Figures 1 and 4 are NOT licensed under CC BY 4.0 and are excluded from "
     "the entry.", "CCBY_ACTIVE_MARKER_NOT_AFFIRMATIVE"),
    ("CC BY 4.0", "CCBY_ACTIVE_MARKER_GENERIC"),
    # r3e. Four clauses the keyword-search shape rule accepted. Each names both
    # figures, names CC BY 4.0, trips no negation and trips no conditional -
    # and none of them is a grant in force over the Figure 1 / Figure 4
    # artwork.
    #   1. a bare `and 4` alternative let a sentence about how many COPIES
    #      exist stand in for naming Figure 4;
    ("Figure 1 artwork is licensed under CC BY 4.0, and 4 copies exist.",
     "CCBY_ACTIVE_MARKER_UNSCOPED"),
    #   2. two sentences: the first licenses Figure 1, the second merely
    #      MENTIONS Figure 4, and together they read as a grant over both;
    ("Figure 1 is licensed under CC BY 4.0. Figure 4 is discussed elsewhere.",
     "CCBY_ACTIVE_MARKER_COMPOUND"),
    #   3. an unrelated granting verb: the subject is the project and the
    #      object is data, while the artwork is only "discussed";
    ("The project licenses data; Figure 1 and Figure 4 artwork and CC BY 4.0 "
     "are discussed.", "CCBY_ACTIVE_MARKER_NOT_AFFIRMATIVE"),
    #   4. the grant stated and withdrawn in the same clause.
    ("Figures 1 and 4 artwork is licensed under CC BY 4.0, although approval "
     "is required.", "CCBY_ACTIVE_MARKER_QUALIFIED"),
    # r3f. The anchored grammar accepted ANY trailing parenthetical, so the
    # qualification simply moved inside the brackets and every one of these
    # registered as a grant in force.
    ("Figures 1 and 4 are licensed under CC BY 4.0 (without authorization).",
     "CCBY_ACTIVE_MARKER_PARENTHETICAL"),
    ("Figures 1 and 4 are licensed under CC BY 4.0 (authorization absent).",
     "CCBY_ACTIVE_MARKER_PARENTHETICAL"),
    ("Figures 1 and 4 are licensed under CC BY 4.0 (approval denied).",
     "CCBY_ACTIVE_MARKER_PARENTHETICAL"),
    ("Figures 1 and 4 are licensed under CC BY 4.0 (authorization revoked).",
     "CCBY_ACTIVE_MARKER_PARENTHETICAL"),
    ("Figures 1 and 4 are licensed under CC BY 4.0 (only after consent).",
     "CCBY_ACTIVE_MARKER_PARENTHETICAL"),
    ("Figures 1 and 4 are licensed under CC BY 4.0 (expires tomorrow).",
     "CCBY_ACTIVE_MARKER_PARENTHETICAL"),
])
def test_unregistrable_active_markers_are_rejected(marker, code):
    als = rf._artwork
    codes = [c for c, _ in als.active_marker_shape_issues(marker)]
    assert code in codes, codes
    # ...and such a marker can NEVER classify a document as ACTIVE.
    contract = {"artwork_licence_markers": {"pending": [], "active": [marker]}}
    assert als.registrable_active_markers(contract) == []
    assert als.classify_claim(marker, contract) is None, \
        "an unregistrable marker classified a document as ACTIVE"


def test_the_real_contract_carries_no_test_only_wording():
    """TEST-ONLY wording is the fixtures' and may never ship.

    The synthetic clause exists so the tests can drive the ACTIVE state without
    anybody drafting licence prose. That is worth nothing if the same wording
    can reach the production contract - the repository would then be asserting
    a copyright licence over a coauthor's artwork in words that say, in
    themselves, that they are not real.
    """
    als = rf._artwork
    contract = rf.load_contract()
    assert not als.is_synthetic_contract(contract),         "the REAL contract declares itself a test fixture"
    assert als.synthetic_wording_issues(contract) == [],         als.synthetic_wording_issues(contract)
    # ...and not anywhere else in the tracked file either.
    raw = (_RELEASE_DIR / "finalizer_contract.json").read_text(
        encoding="utf-8")
    assert als.SYNTHETIC_MARKER_TOKEN not in raw,         "the tracked contract mentions TEST-ONLY"


@pytest.mark.parametrize("where,mutate", [
    ("marker", lambda c: c["artwork_licence_markers"]["active"]
     .append(GUARDS.SYNTHETIC_ACTIVE_CLAUSE)),
    ("publication row", lambda c: c["publication_outputs_artwork_row"]
     .__setitem__("active", GUARDS.synthetic_active_row())),
    ("activation plan", lambda c: c["ccby_activation_plan"]
     .__setitem__("replacements",
                  [{"file": c["licence_records"][0], "from": "x" * 80,
                    "to": GUARDS.SYNTHETIC_ACTIVE_CLAUSE, "count": 1}])),
])
def test_test_only_wording_is_refused_in_a_production_contract(where, mutate):
    """Every surface the review named: contract, plan, row, replacement."""
    als = rf._artwork
    contract = json.loads(json.dumps(rf.load_contract()))
    mutate(contract)
    codes = [c for c, _ in als.synthetic_wording_issues(contract)]
    assert codes == ["CCBY_TESTONLY_WORDING_IN_PRODUCTION"], (where, codes)

    # The activation planner refuses it outright.
    with pytest.raises(rf.FinalizerError) as exc:
        rf.plan_ccby_activation(".", contract)
    assert exc.value.code == "CCBY_TESTONLY_WORDING_IN_PRODUCTION"

    # ...and a contract that DECLARES itself synthetic may use it.
    contract["synthetic_fixture"] = True
    assert als.synthetic_wording_issues(contract) == []


def test_the_production_contract_loader_refuses_test_only_wording(tmp_path):
    """The choke point: a contract tracked and committed IS the production one."""
    root = tmp_path / "repo"
    (root / "scripts" / "release").mkdir(parents=True)
    contract = json.loads(json.dumps(rf.load_contract()))
    contract["artwork_licence_markers"]["active"] = [
        GUARDS.SYNTHETIC_ACTIVE_CLAUSE]
    (root / rf.TRACKED_CONTRACT_REL).write_text(
        json.dumps(contract, indent=2), encoding="utf-8", newline="\n")
    _init_repo(root)

    with pytest.raises(rf.FinalizerError) as exc:
        rf.load_trusted_contract(root)
    assert exc.value.code == "CCBY_TESTONLY_WORDING_IN_PRODUCTION",         exc.value.code


def test_the_registrable_clause_is_accepted():
    """The control: the rule must not reject every possible grant."""
    als = rf._artwork
    assert als.active_marker_shape_issues(GOOD_CLAUSE) == []
    contract = {"artwork_licence_markers": {"pending": [],
                                            "active": [GOOD_CLAUSE]}}
    assert als.classify_claim(GOOD_CLAUSE, contract) == als.ACTIVE


@pytest.mark.parametrize("clause", [
    GUARDS.SYNTHETIC_ACTIVE_CLAUSE,
    GUARDS.SYNTHETIC_ACTIVE_CLAUSE_ALPHA,
    GOOD_CLAUSE,
])
def test_the_anchored_grammar_still_accepts_every_authored_shape(clause):
    """A tightened rule that rejects everything is not a tightened rule.

    All three authored shapes - "Figure 1 and Figure 4 artwork is licensed
    under ...", "Figures 1 and 4 are licensed under ...", with and without a
    trailing parenthetical - must still register, or the ACTIVE state becomes
    unreachable and the activation path stops being testable at all.
    """
    als = rf._artwork
    assert als.active_marker_shape_issues(clause) == [], \
        als.active_marker_shape_issues(clause)
    assert als.ACTIVE_CLAUSE_RX.match(als.normalize_prose(clause))


def test_the_shape_rule_lives_in_the_classifier_not_only_the_planner():
    helper = (_RELEASE_DIR / "artwork_licence_state.py").read_text(
        encoding="utf-8")
    classify = helper.split("def classify_claim", 1)[1].split("\ndef ", 1)[0]
    assert "registrable_active_markers(contract)" in classify, \
        "classify_claim registers markers the planner would have refused"
    checked = helper.split("def _checked_row", 1)[1]
    assert "registrable_active_markers(contract)" in checked, \
        "_checked_row emits rows the classifier would have refused"


def test_an_unregistrable_marker_cannot_emit_an_active_row(tmp_path):
    """The shape rule reaches what is PUBLISHED, not only what is read."""
    als = rf._artwork
    root = _active_tree_with_row(tmp_path, ACTIVE_ROW)
    path = root / "scripts/release/finalizer_contract.json"
    contract = rf.loads_strict(path.read_text(encoding="utf-8"))
    contract["artwork_licence_markers"]["active"] = [
        "Figures 1 and 4 may be licensed under CC BY 4.0 after approval."]
    path.write_text(json.dumps(contract, indent=2), encoding="utf-8",
                    newline="\n")
    with pytest.raises(RuntimeError) as exc:
        als.publication_artwork_row(root)
    # Either refusal is correct and both are conservative: with no registrable
    # marker the records become UNCLASSIFIABLE, so the state machine reports
    # the surfaces as unreadable rather than resolving them in either
    # direction, and nothing is rendered. What must NEVER happen is a rendered
    # active row.
    assert "ARTWORK_ROW" in str(exc.value) or \
        "ARTWORK_LICENCE_STATE_INCONSISTENT" in str(exc.value), str(exc.value)
    assert als.artwork_licence_state(root)[0] != als.ACTIVE


def test_an_active_marker_must_be_absent_before_activation(tmp_path):
    """Otherwise activation cannot be distinguished from doing nothing."""
    contract = json.loads(json.dumps(rf.load_contract()))
    contract["synthetic_fixture"] = True     # licenses the TEST-ONLY clause
    contract["artwork_licence_markers"]["active"] = [ACTIVE_CLAUSE]
    contract["ccby_activation_plan"] = {
        "authored": True,
        "replacements": [{"file": contract["licence_records"][0],
                          "from": "x" * 80, "to": "y" * 80, "count": 1}]}
    root = tmp_path / "tree"
    for rel in contract["licence_records"]:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(ACTIVE_CLAUSE + "\n", encoding="utf-8",
                                newline="\n")
    with pytest.raises(rf.FinalizerError) as exc:
        rf.plan_ccby_activation(root, contract)
    assert exc.value.code == "CCBY_ACTIVE_MARKER_PRE_EXISTING", exc.value.code


# ---------------------------------------------------------------------------
# 31. r3d: hermetic validation
# ---------------------------------------------------------------------------
def _init_repo(root, *add):
    _run(root, "init", "-q")
    _run(root, "config", "user.email", "t@example.invalid")
    _run(root, "config", "user.name", "T")
    _run(root, "add", *(add or ("-A",)))
    _run(root, "commit", "-qm", "x")


def test_the_validation_tree_is_built_from_tracked_content_only(tmp_path):
    """Not copytree-minus-four-names: ignored files stay out."""
    src = tmp_path / "src"
    (src / "sub").mkdir(parents=True)
    (src / "tracked.txt").write_text("tracked", encoding="utf-8")
    (src / "sub" / "also_tracked.md").write_text("also", encoding="utf-8")
    _init_repo(src)

    # ...and now the kind of debris a real worktree accumulates.
    (src / "editor_scratch.tmp").write_text("junk", encoding="utf-8")
    (src / "sub" / "stale_output.csv").write_text("stale", encoding="utf-8")

    dest = tmp_path / "copy"
    info = rf._copy_repository(src, dest,
                               {"validation_copy": {"ignored_allowlist": []}})
    assert info["tracked_files"] == 2, info
    assert (dest / "tracked.txt").read_text(encoding="utf-8") == "tracked"
    assert (dest / "sub" / "also_tracked.md").is_file()
    assert not (dest / "editor_scratch.tmp").exists(), \
        "an arbitrary ignored file was copied into the validation tree"
    assert not (dest / "sub" / "stale_output.csv").exists()
    assert (dest / ".git").is_dir(), "the guards have no repository to run in"


def test_an_allowlisted_artifact_must_match_its_pin(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "keep.txt").write_text("tracked", encoding="utf-8")
    (src / "needed.json").write_text('{"generated": true}', encoding="utf-8")
    _init_repo(src, "keep.txt")

    want = rf.sha256_bytes((src / "needed.json").read_bytes())
    good = {"validation_copy": {"ignored_allowlist":
                                [{"path": "needed.json", "sha256": want}]}}
    info = rf._copy_repository(src, tmp_path / "ok", good)
    assert info["allowlisted"] == ["needed.json"]
    assert (tmp_path / "ok" / "needed.json").is_file()

    bad = {"validation_copy": {"ignored_allowlist":
                               [{"path": "needed.json", "sha256": "0" * 64}]}}
    with pytest.raises(rf.FinalizerError) as exc:
        rf._copy_repository(src, tmp_path / "bad", bad)
    assert exc.value.code == "VALIDATION_ALLOWLIST_MISMATCH", exc.value.code

    unpinned = {"validation_copy": {"ignored_allowlist":
                                    [{"path": "needed.json"}]}}
    with pytest.raises(rf.FinalizerError) as exc:
        rf._copy_repository(src, tmp_path / "unpinned", unpinned)
    assert exc.value.code == "VALIDATION_ALLOWLIST_UNPINNED", exc.value.code


def test_a_tracked_symlink_refuses_the_validation_tree(tmp_path):
    """A link that resolves outside cannot be reproduced inside.

    The index entry is written DIRECTLY with ``update-index --cacheinfo``, so
    this runs on a Windows account that holds no symlink privilege: what
    ``_copy_repository`` inspects is the recorded mode, and mode 120000 is what
    a tracked symlink is.
    """
    src = tmp_path / "src"
    src.mkdir()
    (src / "real.txt").write_text("real", encoding="utf-8")
    _init_repo(src)
    blob = subprocess.run(
        ["git", "-C", str(src), "hash-object", "-w", "--stdin"],
        input="../../etc/passwd", capture_output=True, text=True).stdout.strip()
    _run(src, "update-index", "--add", "--cacheinfo",
         f"120000,{blob},link.txt")
    modes = subprocess.run(["git", "-C", str(src), "ls-files", "-s"],
                           capture_output=True, text=True).stdout
    assert "120000" in modes, modes

    with pytest.raises(rf.FinalizerError) as exc:
        rf._copy_repository(src, tmp_path / "copy", None)
    assert exc.value.code == "VALIDATION_TREE_SYMLINK", exc.value.code
    assert not (tmp_path / "copy" / "link.txt").exists()


def test_a_tracked_gitlink_refuses_the_validation_tree(tmp_path):
    """A submodule hole would validate content that is not there."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "real.txt").write_text("real", encoding="utf-8")
    _init_repo(src)
    # A REAL commit object: git refuses a cacheinfo entry naming nothing.
    commit = _rev(src, "HEAD")
    assert len(commit) == 40, commit
    _run(src, "update-index", "--add", "--cacheinfo",
         f"160000,{commit},vendor")
    with pytest.raises(rf.FinalizerError) as exc:
        rf._copy_repository(src, tmp_path / "copy", None)
    assert exc.value.code == "VALIDATION_TREE_SUBMODULE", exc.value.code


def test_the_real_contract_admits_no_unpinned_validation_artifacts():
    spec = (rf.load_contract().get("validation_copy") or {})
    for entry in spec.get("ignored_allowlist") or []:
        assert entry.get("sha256"), f"{entry} is not pinned"


def test_production_has_no_python_trust_bypass():
    """--python let an operator supply the executable that says PASS."""
    src = (_RELEASE_DIR / "release_finalizer.py").read_text(encoding="utf-8")
    parser = src.split("def build_parser", 1)[1].split("\ndef ", 1)[0]
    assert '"--python"' not in parser, "--python is back on the production CLI"
    main_body = src.split("def main(", 1)[1]
    assert "python_exe=args.python_exe" not in main_body

    with pytest.raises(SystemExit):
        rf.build_parser().parse_args(
            ["finalize", "--repo-root", ".", "--expect-branch", "b",
             "--expect-head", "h", "--release-staging", ".",
             "--python", sys.executable])


def test_an_unpinned_foreign_interpreter_is_refused():
    contract = rf.load_contract()
    assert rf._pinned_interpreter_issues(sys.executable, contract) == []
    codes = [c for c, _ in
             rf._pinned_interpreter_issues("/somewhere/else/python", contract)]
    assert codes == ["INTERPRETER_UNTRUSTED"], codes
    # ...and a contract that DOES pin one accepts exactly that one.
    pinned = dict(contract, trusted_interpreter={"realpath": sys.executable})
    assert rf._pinned_interpreter_issues(sys.executable, pinned) == []


def test_run_owned_files_never_land_inside_a_linked_worktree(tmp_path):
    """`.git` is a FILE in a linked worktree - and this repository is one.

    Testing `(root / ".git").is_dir()` and falling back to the worktree root
    would put the lock and the recovery directory INSIDE the tree, which is an
    untracked change in the very tree the run verifies is clean: the
    finalization would abort itself.
    """
    main = tmp_path / "main"
    main.mkdir()
    (main / "f.txt").write_text("x", encoding="utf-8")
    _run(main, "init", "-q")
    _run(main, "config", "user.email", "t@example.invalid")
    _run(main, "config", "user.name", "T")
    _run(main, "add", "-A")
    _run(main, "commit", "-qm", "x")
    linked = tmp_path / "linked"
    _run(main, "worktree", "add", "-q", "-b", "wt", str(linked))
    assert (linked / ".git").is_file(), "git did not create a linked worktree"

    admin = rf._git_admin_dir(linked)
    assert admin is not None and admin.is_dir()
    assert linked.resolve() not in admin.resolve().parents, \
        "the admin directory resolved inside the working tree"

    lock = rf._run_owned_dir(linked, rf.WORKTREE_LOCK_NAME, "X")
    assert linked.resolve() not in Path(lock).resolve().parents
    txn = rf.Transaction(linked, {"protected_historical_records": []})
    recovery = txn._recovery_root()
    assert linked.resolve() not in recovery.resolve().parents, \
        "the recovery directory was created inside the working tree"
    assert subprocess.run(["git", "-C", str(linked), "status",
                           "--porcelain=v1"], capture_output=True,
                          text=True).stdout.strip() == "", \
        "this run made the working tree dirty"
    txn.discard_recovery()


def test_an_unresolvable_git_directory_refuses_rather_than_using_the_tree():
    """No guessing a location inside the tree when git cannot answer."""
    import tempfile as _tf
    with _tf.TemporaryDirectory() as plain:
        assert rf._git_admin_dir(plain) is None
        with pytest.raises(rf.FinalizerError) as exc:
            rf._run_owned_dir(plain, "x.lock", "FINALIZER_LOCK_UNPLACEABLE")
        assert exc.value.code == "FINALIZER_LOCK_UNPLACEABLE"
        assert "inside the tree" in exc.value.why


# ---------------------------------------------------------------------------
# 32. r3e: the validation tree is an INDEPENDENT CLONE at the expected head
#
# `_copy_repository` used to call `_copy_git_dir(src / ".git", ...)`, which
# refuses anything that is not a directory. `.git` is a FILE in a linked
# worktree and this repository is checked out as one, so every real run died
# with VALIDATION_TREE_UNBUILDABLE before validating anything.
# ---------------------------------------------------------------------------
def _linked_worktree(tmp_path):
    """A real main repository plus a real linked worktree of it."""
    main = tmp_path / "main"
    (main / "tests").mkdir(parents=True)
    (main / "tests" / "test_guard.py").write_bytes(
        b"def test_ok():\n    assert True\n")
    (main / "kept.txt").write_bytes(b"committed bytes\n")
    _run(main, "init", "-q")
    _run(main, "config", "user.email", "t@example.invalid")
    _run(main, "config", "user.name", "T")
    # Pin the line-ending policy so the source checkout and a fresh clone
    # agree byte-for-byte; this test is about content provenance, not EOLs.
    _run(main, "config", "core.autocrlf", "false")
    _run(main, "add", "-A")
    _run(main, "commit", "-qm", "x")
    linked = tmp_path / "linked"
    _run(main, "worktree", "add", "-q", "-b", "wt", str(linked))
    assert (linked / ".git").is_file(), \
        "git did not produce a linked worktree, so this proves nothing"
    return main, linked


def test_the_validation_tree_builds_from_a_real_linked_worktree(tmp_path):
    """The end-to-end regression for the r3d blocker, on the real shape."""
    _main, linked = _linked_worktree(tmp_path)
    head = _rev(linked, "HEAD")
    dest = tmp_path / "copy"
    info = rf._copy_repository(
        linked, dest, {"validation_copy": {"ignored_allowlist": []}},
        expected_head=head, expected_branch="wt")

    assert info["head"] == head, info
    assert info["built_from"] == "committed objects"
    assert (dest / ".git").is_dir() and not (dest / ".git").is_symlink(), \
        "the validation tree has no real git directory to run guards in"
    assert _rev(dest, "HEAD") == head
    assert _rev(dest, "HEAD^{tree}") == _rev(linked, "HEAD^{tree}"), \
        "the clone is not the same tree as the source head"
    assert (dest / "kept.txt").read_bytes() == b"committed bytes\n"
    assert subprocess.run(["git", "-C", str(dest), "status", "--porcelain=v1"],
                          capture_output=True, text=True).stdout.strip() == "", \
        "the freshly built validation tree is dirty"
    # The history the repository guards resolve explicit commits against.
    assert subprocess.run(["git", "-C", str(dest), "cat-file", "-e",
                           head + "^{commit}"], capture_output=True
                          ).returncode == 0


def test_a_transient_mutation_of_a_source_test_cannot_enter_the_copy(tmp_path):
    """A test neutered while the copy is being prepared, then put back.

    This is the attack the old worktree-byte copy could not see. The suite is
    what the release is accepted on; a mutation that is present while the copy
    is taken and absent by the time anything checks the tree for dirt would
    have been validated and would have left no trace. Building from committed
    objects removes the window rather than narrowing it.
    """
    _main, linked = _linked_worktree(tmp_path)
    head = _rev(linked, "HEAD")
    guard = linked / "tests" / "test_guard.py"
    committed = guard.read_bytes()
    neutered = b"def test_ok():\n    assert True  # NEUTERED\n"

    guard.write_bytes(neutered)                       # during preparation
    assert guard.read_bytes() == neutered
    dest = tmp_path / "copy"
    rf._copy_repository(linked, dest, None, expected_head=head,
                        expected_branch="wt")
    assert (dest / "tests" / "test_guard.py").read_bytes() == committed, \
        "a worktree mutation reached the validation copy"

    guard.write_bytes(committed)                      # ...and it disappears
    assert subprocess.run(["git", "-C", str(linked), "status",
                           "--porcelain=v1"], capture_output=True,
                          text=True).stdout.strip() == "", \
        "the mutation left a trace, so the dirty-tree check would have caught it"
    assert (dest / "tests" / "test_guard.py").read_bytes() == committed


def test_the_validation_tree_refuses_a_source_at_a_different_head(tmp_path):
    """The copy is built for ONE commit, and it says so."""
    _main, linked = _linked_worktree(tmp_path)
    with pytest.raises(rf.FinalizerError) as exc:
        rf._copy_repository(linked, tmp_path / "copy", None,
                            expected_head="0" * 40, expected_branch="wt")
    assert exc.value.code == "VALIDATION_TREE_HEAD_MISMATCH", exc.value.code
    assert not (tmp_path / "copy" / ".git").exists()


def test_the_finalizer_builds_the_validation_tree_for_the_expected_head():
    """Wired through, not merely available."""
    src = (_RELEASE_DIR / "release_finalizer.py").read_text(encoding="utf-8")
    assert "def _copy_git_dir" not in src, \
        "the .git directory copy is back"
    assert "expected_head=expect_head" in src, \
        "finalize does not build the validation tree for the expected head"


# ---------------------------------------------------------------------------
# 33. r3e: no check-then-delete anywhere. Each adversary replaces its target
#     at exactly the instant the old code sat between verifying a pathname and
#     unlinking it.
# ---------------------------------------------------------------------------
def _replace_at(target, hostile):
    """A concurrent REPLACEMENT of ``target`` - unlink, then create anew.

    Not an in-place write: a replacement is what a rename or a fresh create
    does, and it is the case that breaks reasoning based on a pathname.
    """
    def adversary(path, slot, _real=None, **kw):
        if Path(path) == Path(target):
            if os.path.lexists(str(target)):
                os.unlink(str(target))
            Path(target).write_bytes(hostile)
        return _real(path, slot, **kw)
    return adversary


def test_a_replacement_during_the_transaction_rollback_is_never_deleted(
        tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "a.md").write_bytes(b"ORIGINAL")
    _init_repo(root)

    txn = rf.Transaction(root, {"protected_historical_records": []})
    txn.apply([rf.Edit("docs/a.md", b"ORIGINAL", b"REWRITTEN", {}, 1)])
    assert (root / "docs" / "a.md").read_bytes() == b"REWRITTEN"

    hostile = b"WRITTEN INDEPENDENTLY WHILE THE ROLLBACK RAN"
    real = rf._quarantine
    monkeypatch.setattr(
        rf, "_quarantine",
        lambda p, s, **kw: _replace_at(root / "docs" / "a.md", hostile)(
            p, s, _real=real, **kw))

    with pytest.raises(rf.RollbackError):
        txn.rollback()
    result = txn._rollback_result
    assert result["failures"], "the rollback reported success over a race"

    candidates = [root / "docs" / "a.md"]
    candidates += [Path(p) for p in result["preserved"].values() if p]
    candidates += [Path(p) for p in result["quarantined"].values()]
    assert any(p.is_file() and p.read_bytes() == hostile for p in candidates), \
        "the concurrent bytes were destroyed by the rollback"
    txn.discard_recovery()


def test_a_replacement_at_the_destination_during_rollback_is_never_deleted(
        tmp_path, monkeypatch):
    staging = tmp_path / "staging"
    staging.mkdir()
    dest = staging / "archive.zip"
    ours = b"THE ARCHIVE THIS RUN PLACED"
    dest.write_bytes(ours)
    hostile = b"AN ARCHIVE WRITTEN INDEPENDENTLY"

    real = rf._quarantine
    monkeypatch.setattr(rf, "_quarantine",
                        lambda p, s, **kw: _replace_at(dest, hostile)(
                            p, s, _real=real, **kw))
    out = rf._rollback_output(dest, None, True, None, None,
                              rf.sha256_bytes(ours), run_id="rid")
    assert out["failures"], "the rollback claimed to have undone a race"
    where = out["quarantine_retained"].get("destination")
    holder = Path(where) if where else dest
    assert holder.is_file() and holder.read_bytes() == hostile, \
        "the concurrently written archive was deleted by the rollback"


def test_a_replacement_of_the_move_aside_copy_is_never_deleted(tmp_path,
                                                               monkeypatch):
    staging = tmp_path / "staging"
    staging.mkdir()
    dest = staging / "archive.zip"
    displaced = staging / "archive.zip.rid.superseded-finalizer-tmp"
    pred = b"THE PREDECESSOR ARCHIVE"
    displaced.write_bytes(pred)
    predecessor = {"sha256": rf.sha256_bytes(pred), "bytes": len(pred)}
    hostile = b"SOMETHING ELSE ENTIRELY"

    real = rf._quarantine
    monkeypatch.setattr(rf, "_quarantine",
                        lambda p, s, **kw: _replace_at(displaced, hostile)(
                            p, s, _real=real, **kw))
    out = rf._rollback_output(dest, displaced, False, predecessor, None, None,
                              run_id="rid")
    assert out["failures"], "the move-aside cleanup reported success over a race"
    where = out["quarantine_retained"].get("move_aside")
    holder = Path(where) if where else displaced
    assert holder.is_file() and holder.read_bytes() == hostile, \
        "the bytes that replaced the move-aside copy were deleted"


def test_a_lock_replaced_before_release_is_never_deleted(tmp_path):
    """Releasing a lock must not delete the lock of the run that took over."""
    path = tmp_path / "scorch_finalizer.lock"
    lock = rf._Lock(path, "run-A").acquire()
    hostile = b'{"pid": 2, "run_id": "run-B"}'
    os.unlink(str(path))
    path.write_bytes(hostile)                 # a second run took the name

    lock.release()
    assert lock.release_failure, "the release reported success over a race"
    assert path.read_bytes() == hostile, "a live lock was deleted"


def test_a_replaced_temporary_is_preserved_rather_than_deleted(tmp_path):
    """r3f: a temporary is removed by IDENTITY, not by pathname.

    The release temporary lives beside the destination, where anything can
    reach it. Deleting whatever happens to be sitting at that name at cleanup
    time is the same defect as everywhere else in this module.
    """
    temps = rf._RunTemporaries("rid")
    tmp = tmp_path / "archive.zip.rid.finalizer-tmp"
    payload = b"THE TEMPORARY THIS RUN WROTE"
    tmp.write_bytes(payload)
    temps.adopt(rf._Created(tmp, rf.sha256_bytes(payload), len(payload)))

    tmp.unlink()
    tmp.write_bytes(b"SOMEBODY ELSE'S FILE")          # a replacement
    assert temps.discard(tmp, what="the release output temporary") is False
    assert temps.failures, "the cleanup reported success over a replacement"
    where = temps.retained.get(str(tmp))
    assert where, temps.retained
    assert Path(where).read_bytes() == b"SOMEBODY ELSE'S FILE", \
        "the concurrently written file was deleted by the cleanup"


def test_a_release_temporary_replaced_before_cleanup_survives(e2e,
                                                              monkeypatch):
    """The same rule, in situ, on the SUCCESS path's own cleanup.

    The window is between the placement and the removal of the output
    temporary. The adversary lets the placement happen and then replaces the
    temporary - precisely what an unconditional `os.unlink(tmp_out)` destroyed.
    """
    hostile = b"WRITTEN INDEPENDENTLY AT THE TEMPORARY PATH"
    real_link = rf._link_no_clobber
    fired = {"n": 0}

    def swap_after_placement(source, destination, **kw):
        result = real_link(source, destination, **kw)
        if rf.RELEASE_TEMP_TOKEN in Path(source).name and not fired["n"]:
            fired["n"] += 1
            os.unlink(str(source))
            Path(source).write_bytes(hostile)
        return result

    monkeypatch.setattr(rf, "_link_no_clobber", swap_after_placement)
    report = run_finalize(e2e)
    assert fired["n"] == 1, "the adversary never ran"
    assert not report.ok, report.codes
    assert "RELEASE_TEMPORARY_NOT_OURS" in report.codes, report.codes

    retained = report.data.get("temporary_recovery_paths") or {}
    candidates = [Path(p) for p in retained.values()]
    candidates += [Path(p) for p in retained]
    assert any(p.is_file() and p.read_bytes() == hostile
               for p in candidates),         f"the concurrently written bytes were deleted; retained={retained}"


def test_an_unjournalled_object_is_never_removed_as_a_temporary(tmp_path):
    temps = rf._RunTemporaries("rid")
    stray = tmp_path / "never-journalled.finalizer-tmp"
    stray.write_bytes(b"NOT THIS RUN'S")
    assert temps.discard(stray, what="the release output temporary") is False
    assert any("never journalled" in f for f in temps.failures), temps.failures
    where = temps.retained.get(str(stray))
    assert Path(where or stray).read_bytes() == b"NOT THIS RUN'S"


def test_a_quarantine_deletion_failure_is_not_reported_clean(tmp_path,
                                                             monkeypatch):
    """Checked deletion: `unlink` returning without removing is a failure."""
    temps = rf._RunTemporaries("rid")
    tmp = tmp_path / "t.finalizer-tmp"
    tmp.write_bytes(b"OURS")
    temps.adopt(rf._Created(tmp, rf.sha256_bytes(b"OURS"), 4))

    real_unlink = os.unlink

    def stubborn(path, *a, **kw):
        # The quarantine slot is a short digest-named sibling, because a
        # suffix on the original name overflows the Windows path limit.
        if Path(path).name.startswith(".q"):
            raise OSError("the quarantined temporary is locked")
        return real_unlink(path, *a, **kw)

    monkeypatch.setattr(os, "unlink", stubborn)
    assert temps.discard(tmp, what="the release output temporary") is False
    assert any("could not be removed" in f for f in temps.failures), \
        temps.failures


def test_a_release_destination_that_is_not_a_regular_file_is_refused(tmp_path):
    """r3f: classify before hashing. `sha256_file` follows links."""
    staging = tmp_path / "staging"
    staging.mkdir()
    victim = staging / "archive.zip"
    victim.mkdir()                       # a directory, not an archive
    with pytest.raises(rf.FinalizerError) as exc:
        rf.sha256_regular_no_follow(
            victim, code="RELEASE_DESTINATION_NOT_REGULAR",
            what="the existing release destination")
    assert exc.value.code == "RELEASE_DESTINATION_NOT_REGULAR", exc.value.code
    assert "not a regular file" in exc.value.why

    real = staging / "real.zip"
    real.write_bytes(b"archive bytes")
    got, size = rf.sha256_regular_no_follow(
        real, code="X", what="a regular archive")
    assert got == rf.sha256_bytes(b"archive bytes") and size == 13


def test_cleanup_state_does_not_leak_between_finalizer_runs(e2e):
    """`_CLEANUP_FAILURES` is module-level; a run must start from empty."""
    rf._CLEANUP_FAILURES.append("a stale warning from an earlier run")
    report = run_finalize(e2e)
    assert report.ok, report.codes
    assert "a stale warning from an earlier run" not in \
        (report.data.get("cleanup_failures") or []), \
        "an earlier run's cleanup state was attached to this run's report"
    assert rf._CLEANUP_FAILURES == [] or all(
        "stale warning" not in f for f in rf._CLEANUP_FAILURES)


# ---------------------------------------------------------------------------
# 36. r3g: temporary ownership is decided from the WRITER, at creation.
#
# One test per point at which the filesystem can change under the mechanism.
# ---------------------------------------------------------------------------
def test_write_new_interrupted_mid_write_retains_and_reports(tmp_path):
    """State changes DURING `_write_new`: the object is kept, never guessed at.

    The writer cannot say what reached the file, so the identity is journalled
    as UNCONFIRMED and the cleanup refuses to remove it. The old code unlinked
    the pathname on the way out of the error - a check-then-delete with the
    check missing altogether.
    """
    journal = rf._RunTemporaries("rid")
    target = tmp_path / "t.finalizer-tmp"

    class Exploding(bytes):
        def __len__(self):                              # raised during write
            raise OSError("device error mid-write")

    with pytest.raises(OSError):
        rf._write_new(target, Exploding(b"partial"), exists_code="X",
                      exists_why="x", journal=journal)

    assert target.exists(), "the writer deleted a pathname on the error path"
    entry = journal.unresolved[str(target)]
    assert entry["confirmed"] is False and entry["sha256"] is None, entry
    assert journal.discard(target, what="the interrupted temporary") is False
    assert any("interrupted" in f for f in journal.failures), journal.failures
    where = journal.retained.get(str(target))
    assert Path(where or target).exists(), "the retained object vanished"


def test_exclusive_copy_interrupted_mid_copy_journals_what_it_wrote(
        tmp_path, monkeypatch):
    """State changes DURING `_exclusive_copy`: a partial copy is still known.

    It hashes as it writes, so a copy that dies halfway still leaves an
    identity describing exactly the bytes that reached the file - and the
    cleanup can therefore prove the object is its own and remove it.
    """
    journal = rf._RunTemporaries("rid")
    src = tmp_path / "src.bin"
    src.write_bytes(b"A" * 4096)
    dst = tmp_path / "dst.finalizer-tmp"

    import builtins
    real_open = builtins.open
    state = {"n": 0}

    class Halfway(io.BytesIO):
        def read(self, *a):
            state["n"] += 1
            if state["n"] > 1:
                raise OSError("source went away mid-copy")
            return b"A" * 512

    def fake_open(path, *a, **kw):
        try:
            same = Path(path) == src
        except TypeError:
            same = False
        return Halfway() if same else real_open(path, *a, **kw)

    monkeypatch.setattr(builtins, "open", fake_open)
    with pytest.raises(OSError):
        rf._exclusive_copy(src, dst, journal=journal)
    monkeypatch.undo()

    assert dst.exists(), "the writer deleted a pathname on the error path"
    entry = journal.unresolved[str(dst)]
    assert entry["confirmed"] is True
    assert entry["sha256"] == rf.sha256_bytes(b"A" * 512), entry
    assert entry["bytes"] == 512, entry
    # ...and BECAUSE the identity is known, the cleanup may remove it.
    assert journal.discard(dst, what="the partial output") is True
    assert not dst.exists()
    assert journal.failures == [], journal.failures


def test_state_changing_between_writer_return_and_journal_is_caught(tmp_path):
    """The window after the writer returns. Identity came from the writer.

    Nothing re-reads the pathname, so a replacement here is detected by
    comparison rather than adopted as though it were this run's own.
    """
    journal = rf._RunTemporaries("rid")
    target = tmp_path / "t.finalizer-tmp"
    rf._write_new(target, b"OURS", exists_code="X", exists_why="x",
                  journal=journal)
    assert journal.unresolved[str(target)]["sha256"] == \
        rf.sha256_bytes(b"OURS")

    intruder = b"WRITTEN BY SOMETHING ELSE"
    os.unlink(str(target))
    target.write_bytes(intruder)                  # after the writer returned
    assert journal.discard(target, what="the temporary") is False
    where = journal.retained.get(str(target))
    assert Path(where or target).read_bytes() == intruder


def test_state_changing_between_quarantine_reservation_and_move(tmp_path,
                                                                monkeypatch):
    """The window between reserving the slot and the rename that fills it."""
    journal = rf._RunTemporaries("rid")
    target = tmp_path / "t.finalizer-tmp"
    rf._write_new(target, b"OURS", exists_code="X", exists_why="x",
                  journal=journal)

    intruder = b"ARRIVED IN THE RESERVATION WINDOW"
    real_replace = os.replace
    real_unlink = os.unlink
    fired = {"n": 0}

    def swap_then_replace(src, dst, *a, **kw):
        if Path(src) == target and not fired["n"]:
            fired["n"] += 1
            real_unlink(str(target))
            Path(target).write_bytes(intruder)
        return real_replace(src, dst, *a, **kw)

    monkeypatch.setattr(os, "replace", swap_then_replace)
    assert journal.discard(target, what="the temporary") is False
    assert fired["n"] == 1
    monkeypatch.undo()
    where = journal.retained.get(str(target))
    assert Path(where or target).read_bytes() == intruder, \
        "bytes that arrived in the reservation window were destroyed"


def test_a_quarantine_deletion_that_does_not_delete_is_reported(tmp_path,
                                                                monkeypatch):
    """The window between verifying the moved object and dropping the slot.

    The slot is a run-owned name, so it IS unlinked - but the unlink is
    CHECKED. An `unlink` that returns while the object is still there must not
    be reported as a clean cleanup.
    """
    journal = rf._RunTemporaries("rid")
    target = tmp_path / "t.finalizer-tmp"
    rf._write_new(target, b"OURS", exists_code="X", exists_why="x",
                  journal=journal)

    real_unlink = os.unlink

    def pretend(path, *a, **kw):
        if Path(path).name.startswith(".q"):
            return None                     # "succeeds", removes nothing
        return real_unlink(path, *a, **kw)

    monkeypatch.setattr(os, "unlink", pretend)
    assert journal.discard(target, what="the temporary") is False
    assert any("still exists after removal" in f
               for f in journal.failures), journal.failures


def test_a_transaction_stage_cleanup_failure_stops_the_transaction(
        tmp_path, monkeypatch):
    """A temporary the transaction cannot account for is not a footnote."""
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "a.md").write_bytes(b"ORIGINAL")
    _init_repo(root)

    txn = rf.Transaction(root, {"protected_historical_records": []})
    real_unlink = os.unlink

    def pretend(path, *a, **kw):
        if Path(path).name.startswith(".q"):
            return None                     # the slot survives its removal
        return real_unlink(path, *a, **kw)

    monkeypatch.setattr(os, "unlink", pretend)
    with pytest.raises(rf.FinalizerError) as exc:
        txn.apply([rf.Edit("docs/a.md", b"ORIGINAL", b"REWRITTEN", {}, 1)])
    assert exc.value.code == "TEMPORARY_CLEANUP_FAILED", exc.value.code

    # ...and the recovery directory is RETAINED while anything is unresolved.
    monkeypatch.undo()
    txn.discard_recovery()
    assert txn._recovery_dir is not None, \
        "the recovery directory was discarded with temporaries outstanding"
    assert any("retained" in f for f in txn.rollback_failures), \
        txn.rollback_failures


def test_no_verified_pathname_is_ever_unlinked():
    """Structural: the four sites named in review all go through quarantine."""
    src = (_RELEASE_DIR / "release_finalizer.py").read_text(encoding="utf-8")
    for name, needle in (
            ("Transaction.rollback", "self._slot(rel, \"quarantine\")"),
            ("_rollback_output/placed", '_output_slot(destination, run_id, "placed")'),
            ("_rollback_output/move-aside", '"moveaside"'),
            ("post-commit predecessor", '_output_slot(displaced, run_id, "superseded")'),
            ("_Lock.release", 'f"{self.path.name}.release-{self.run_id}"')):
        assert needle in src, f"{name} does not quarantine before removing"
    # ...and no cleanup failure is hidden. `shutil.rmtree` is gone from the
    # module entirely: its only failure channel is a callback whose spelling
    # is itself deprecated, and a run's report of where somebody's last intact
    # bytes are should not rest on that.
    import re as _re
    assert not _re.search(r"shutil\.rmtree\(", src), \
        "shutil.rmtree is back; its failures are reported only by callback"
    # r3f: and there is no silent unlink left anywhere.
    assert "_unlink_quietly(" not in src, \
        "the error-swallowing unlink is back"
    # r3g: journalled BY THE WRITER, from its own descriptor - never by
    # re-reading the pathname after the writer returned. And neither writer
    # unlinks a pathname on its error path any more.
    assert "_RunTemporaries" in src, "the temporaries journal is gone"
    assert "_exclusive_copy(final_path, tmp_out, journal=temporaries)" in src, \
        "the release output temporary is not journalled by its writer"
    assert ".record(" not in src, \
        "a temporary is journalled by re-reading a pathname again"
    for writer in ("def _write_new", "def _exclusive_copy"):
        body = src.split(writer, 1)[1].split("\ndef ", 1)[0]
        assert "os.unlink(" not in body, \
            f"{writer} unlinks a pathname on its error path"
    assert "temporaries.discard(tmp_out" in src, \
        "the release output temporary is removed by pathname again"
    assert "sha256_regular_no_follow(" in src, \
        "the release destination is hashed without being classified"
    assert "del _CLEANUP_FAILURES[:]" in src, \
        "cleanup state is not reset per run"
    assert "_rmtree_checked" in src
    body = src.split("def _rmtree_checked", 1)[1].split("\n\n\n", 1)[0]
    assert "_CLEANUP_FAILURES.append" in body, \
        "a cleanup failure is discarded instead of recorded"
    for site in ("the transaction recovery directory",
                 "the private predecessor snapshot directory"):
        assert site in src, f"{site} is no longer removed through the report"


# ---------------------------------------------------------------------------
# 34. r3e: the receipt is opened by ONE fail-closed operation
# ---------------------------------------------------------------------------
def _link_dir(link, target):
    """A directory link, by whatever means the platform allows. True if made.

    Windows junctions need no privilege, so the parent-component swap is
    reachable on an ordinary account even where ``os.symlink`` is not.
    """
    try:
        if os.name == "nt":
            return subprocess.run(["cmd", "/c", "mklink", "/J", str(link),
                                   str(target)], capture_output=True
                                  ).returncode == 0 and Path(link).exists()
        os.symlink(str(target), str(link), target_is_directory=True)
        return True
    except OSError:
        return False


def test_the_receipt_open_refuses_an_object_swapped_after_inspection(tmp_path):
    """The inspect-then-open window. There is nothing to swap any more.

    ``resolve_receipt_path`` approves the path; the object at it is then
    replaced; the read must refuse rather than return the replacement's bytes.
    Where a symlink cannot be created the object is replaced by a directory -
    a different object under the same name, which is the same decision.
    """
    als = rf._artwork
    root = _active_tree_with_row(tmp_path, ACTIVE_ROW)
    contract = rf.loads_strict(
        (root / "scripts/release/finalizer_contract.json")
        .read_text(encoding="utf-8"))
    target = root / contract["authorization_receipt"]["tracked_path"]

    path, issues = als.resolve_receipt_path(root, contract)
    assert path is not None and not issues, issues      # inspection approves

    outside = tmp_path / "elsewhere" / "receipt.json"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_bytes(target.read_bytes())            # a VALID receipt
    external = outside.read_bytes()
    target.unlink()
    if _can_symlink(tmp_path):
        os.symlink(str(outside), str(target))
    else:
        target.mkdir()

    with pytest.raises(als.ReceiptOpenRefused) as exc:
        als.safe_read_receipt(path, root)
    assert exc.value.why
    # And whatever happened, the external bytes were NOT what got read.
    try:
        got = als.safe_read_receipt(path, root)
    except als.ReceiptOpenRefused:
        got = None
    assert got != external, "the external receipt was read through the swap"
    assert als.artwork_licence_state(root)[0] != als.ACTIVE


def test_the_receipt_open_protects_every_path_component(tmp_path):
    """A junction on a PARENT directory redirects just as effectively.

    Nothing about the final filename is wrong in this case: ``docs`` is what
    was replaced. The check that catches it is the final resolved path of the
    handle actually opened, which is why that is the check.
    """
    als = rf._artwork
    root = _active_tree_with_row(tmp_path, ACTIVE_ROW)
    contract = rf.loads_strict(
        (root / "scripts/release/finalizer_contract.json")
        .read_text(encoding="utf-8"))
    rel = contract["authorization_receipt"]["tracked_path"]
    parent = (root / rel).parent
    receipt = (root / rel).read_bytes()

    external = tmp_path / "external_docs"
    shutil.copytree(parent, external)
    swapped = False
    try:
        shutil.rmtree(parent)
        swapped = _link_dir(parent, external)
    finally:
        if not swapped and not parent.exists():
            shutil.copytree(external, parent)

    if swapped:
        assert (root / rel).is_file(), "the junction did not resolve"
        assert (root / rel).read_bytes() == receipt
        with pytest.raises(als.ReceiptOpenRefused) as exc:
            als.safe_read_receipt(root / rel, root)
        # EITHER refusal is correct, and both are the same decision. The
        # component walk refuses a linked parent AT THE COMPONENT ("is a
        # symlink or is not a directory"); the handle-path comparison
        # refuses it as "outside the repository". Requiring the second
        # wording made a POSIX run fail for giving the better answer.
        why = exc.value.why
        assert ("component" in why or "outside the repository" in why), why
    else:
        # No directory link is creatable here. The SAME rule is exercised
        # directly: the handle's final path must be inside the root it is
        # judged against. This never skips.
        with pytest.raises(als.ReceiptOpenRefused) as exc:
            als.safe_read_receipt(root / rel, tmp_path / "some_other_root")
        assert "outside the repository" in exc.value.why, exc.value.why


def test_a_linked_parent_component_is_refused_at_the_component(tmp_path):
    """r3f: every component is opened, not just the last one.

    `O_NOFOLLOW` on the final path says nothing about `docs`. Where a directory
    link can be made, the walk must refuse at the component that is a link;
    where it cannot, the same rule is exercised by pointing the read at a root
    the receipt is not under, which is the other half of the same check.
    """
    als = rf._artwork
    root = tmp_path / "root"
    (root / "docs").mkdir(parents=True)
    receipt = root / "docs" / "receipt.json"
    receipt.write_bytes(b'{"ok": true}')
    assert als.safe_read_receipt(receipt, root) == b'{"ok": true}'

    outside = tmp_path / "outside_docs"
    outside.mkdir()
    (outside / "receipt.json").write_bytes(b'{"forged": true}')
    shutil.rmtree(root / "docs")
    if _link_dir(root / "docs", outside):
        assert (root / "docs" / "receipt.json").is_file()
        with pytest.raises(als.ReceiptOpenRefused) as exc:
            als.safe_read_receipt(root / "docs" / "receipt.json", root)
        why = exc.value.why
        assert ("component" in why or "outside the repository" in why), why
        # And the forged bytes were never returned.
        try:
            got = als.safe_read_receipt(root / "docs" / "receipt.json", root)
        except als.ReceiptOpenRefused:
            got = None
        assert got != b'{"forged": true}'
    else:
        (root / "docs").mkdir()
        (root / "docs" / "receipt.json").write_bytes(b'{"ok": true}')
        with pytest.raises(als.ReceiptOpenRefused):
            als.safe_read_receipt(root / "docs" / "receipt.json",
                                  tmp_path / "not_the_root")


def test_the_receipt_open_resolves_no_pathname_after_opening():
    """A realpath after the open is a second question about a NAME."""
    helper = (_RELEASE_DIR / "artwork_licence_state.py").read_text(
        encoding="utf-8")
    body = helper.split("def safe_read_receipt", 1)[1].split("\ndef ", 1)[0]
    # The CALL, not the word: the docstring explains why the call is absent.
    assert "realpath(" not in body, \
        "safe_read_receipt re-resolves a pathname after opening the handle"
    posix = helper.split("def _posix_safe_open", 1)[1].split("\ndef ", 1)[0]
    assert "realpath(" not in posix, "the POSIX walk re-resolves a pathname"
    assert "O_DIRECTORY" in posix and "dir_fd=" in posix, \
        "the POSIX open does not walk the components with openat"
    # r3g: the Windows side walks every component and hands back the ROOT's
    # handle-derived path alongside the receipt's, so both sides of the
    # comparison still come from open handles - and the root handle is opened
    # FIRST and held for the whole operation.
    assert "fd, final, root_final = _windows_safe_open(root, rel)" in body, \
        "the Windows containment check does not compare two handle paths"
    win = helper.split("def _windows_safe_open", 1)[1].split("\ndef ", 1)[0]
    assert "realpath(" not in win, "the Windows walk re-resolves a pathname"
    assert "FILE_FLAG_OPEN_REPARSE_POINT" in helper
    assert "for name in parts[:-1]" in win, \
        "the Windows open does not inspect every path component"
    assert win.index("root_handle = _windows_component_handle") < \
        win.index("for name in parts[:-1]"), \
        "the root handle is not opened before the components below it"


def test_the_receipt_open_never_falls_back_to_a_following_open():
    helper = (_RELEASE_DIR / "artwork_licence_state.py").read_text(
        encoding="utf-8")
    assert 'getattr(os, "O_NOFOLLOW", 0)' not in helper, \
        "O_NOFOLLOW-or-zero is back; on Windows that is a following open"
    assert "FILE_FLAG_OPEN_REPARSE_POINT" in helper
    assert "GetFinalPathNameByHandleW" in helper
    assert "GetFileInformationByHandle" in helper
    body = helper.split("def _windows_safe_open", 1)[1].split(
        "\ndef _posix_safe_open", 1)[0]
    assert "ReceiptOpenRefused" in body and "unavailable" in body, \
        "an unavailable platform primitive does not refuse"


def test_a_special_object_is_refused_by_the_handle_not_only_the_name(tmp_path):
    """The refusal survives even when the name-based pre-check is defeated."""
    als = rf._artwork
    root = tmp_path / "root"
    root.mkdir()
    victim = root / "receipt.json"
    victim.mkdir()
    with pytest.raises(als.ReceiptOpenRefused):
        als.safe_read_receipt(victim, root)


# ---------------------------------------------------------------------------
# 35. r3e: environment capture. No ambient control reaches a validation child.
# ---------------------------------------------------------------------------
_POISON = {
    "SCORCH_DATA_DIR": "AMBIENT-SENTINEL-scorch",
    "PYTEST_ADDOPTS": "AMBIENT-SENTINEL-pytest",
    "PYTHONOPTIMIZE": "AMBIENT-SENTINEL-pythonopt",
    "PYTHONPATH": "AMBIENT-SENTINEL-pythonpath",
    # r3f. This one is the point of the fix. PYTHONDONTWRITEBYTECODE is a
    # variable the FINALIZER SETS ITSELF, to "1". The first version of this
    # check called it an inherited leak whenever the operator's shell happened
    # to set the same name to the same value - so the verdict depended on the
    # environment it exists to be independent of, and any operator who exports
    # it would have seen a false failure. Poisoning it with a value that is
    # NOT "1" makes the real question askable: the child must receive exactly
    # "1", the finalizer's own value, and never the sentinel.
    "PYTHONDONTWRITEBYTECODE": "AMBIENT-SENTINEL-dontwritebytecode",
    "PYTHONNOUSERSITE": "AMBIENT-SENTINEL-nousersite",
    # The child's OWN pytest sets PYTEST_VERSION in its own process, and when
    # both run the same pytest the two values are identical - which a
    # value-equality leak check reads as inheritance. Poisoning it settles the
    # question by observation instead of by exemption: the sentinel means it
    # was inherited, "9.0.3" means the child's pytest set it itself.
    "PYTEST_VERSION": "AMBIENT-SENTINEL-pytestversion",
    "GIT_DIR": "AMBIENT-SENTINEL-gitdir",
    "GIT_INDEX_FILE": "AMBIENT-SENTINEL-gitindex",
    "GIT_CONFIG_GLOBAL": "AMBIENT-SENTINEL-gitconfig",
    "GH_TOKEN": "AMBIENT-SENTINEL-ghtoken",
    "GITHUB_TOKEN": "AMBIENT-SENTINEL-githubtoken",
    "COVERAGE_PROCESS_START": "AMBIENT-SENTINEL-coverage",
    "XDG_CONFIG_HOME": "AMBIENT-SENTINEL-xdg",
    "MPLCONFIGDIR": "AMBIENT-SENTINEL-mpl",
    "MPLBACKEND": "AMBIENT-SENTINEL-mplbackend",
}
_SENTINEL = "AMBIENT-SENTINEL-"

_ENV_CAPTURE_VALIDATOR = """\
import json, os, sys
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "captured_env.json"), "w", encoding="utf-8") as fh:
    json.dump(dict(os.environ), fh)
print("[ok] deposit inspected")
print("PASS")
"""


def _poison(monkeypatch):
    for key, value in _POISON.items():
        monkeypatch.setenv(key, value)


def _assert_child_environment_is_clean(captured):
    """What a validation child actually received must carry nothing ambient.

    Three separate questions, because passing two of them is not enough:

    1. no sentinel value arrived, under ANY name;
    2. `ambient_control_leaks` agrees - and it now excludes the variables the
       finalizer sets to a fixed value, so this is a real check rather than a
       tautology in either direction;
    3. the variables the finalizer OWNS arrived holding the finalizer's value.
       Without this a child that simply dropped `PYTHONDONTWRITEBYTECODE`
       would pass (1) and (2) while quietly writing bytecode into the tree
       under validation.
    """
    leaked = {k: v for k, v in captured.items() if _SENTINEL in str(v)}
    assert leaked == {}, f"ambient control reached the child: {leaked}"
    assert rf.ambient_control_leaks(captured, dict(os.environ)) == {}, \
        rf.ambient_control_leaks(captured, dict(os.environ))
    assert captured.get("PYTHONDONTWRITEBYTECODE") == "1", \
        (f"the child did not receive the finalizer's own value: "
         f"{captured.get('PYTHONDONTWRITEBYTECODE')!r}")
    assert captured.get("PYTHONNOUSERSITE") == "1", \
        captured.get("PYTHONNOUSERSITE")
    home = captured.get("HOME") or captured.get("USERPROFILE") or ""
    assert "scorch_finalizer_home_" in home or "hermetic_home_" in home, home
    assert home != os.environ.get("HOME", "\0")
    # Every per-user root, not only HOME.
    for name in ("APPDATA", "LOCALAPPDATA"):
        got = captured.get(name)
        if got is None:
            continue
        assert got != os.environ.get(name, "\0"), \
            f"the operator's {name} reached the child: {got}"
        assert str(Path(home)) in str(Path(got).parents[1]) or \
            str(home) in got, f"{name} was not redirected into the home: {got}"


def test_the_deposit_validator_inherits_no_ambient_control(tmp_path,
                                                           monkeypatch):
    """The environment-capture validator: it reports what it actually got."""
    _poison(monkeypatch)
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "validate_deposit.py").write_text(_ENV_CAPTURE_VALIDATOR,
                                               encoding="utf-8", newline="\n")
    contract = {"archive_topology": {
        "validator_member": "validate_deposit.py",
        "validator_verdict": {"pass_line": "PASS", "fail_line": "FAIL",
                              "expected_verdict_lines": 1,
                              "must_be_last_non_empty_line": True}}}
    result = rf.run_deposit_validator(stage, contract)
    assert result["verdict"] == "PASS", result

    captured = json.loads((stage / "captured_env.json")
                          .read_text(encoding="utf-8"))
    _assert_child_environment_is_clean(captured)


def test_every_git_subprocess_runs_under_the_sanitized_environment(monkeypatch):
    _poison(monkeypatch)
    env = rf._git_env()
    leaked = {k: v for k, v in env.items() if _SENTINEL in str(v)}
    assert leaked == {}, leaked
    assert rf.ambient_control_leaks(env) == {}, rf.ambient_control_leaks(env)
    assert "scorch_finalizer_home_" in env["HOME"]
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"
    # r3f: there is no network exception left to ask for.
    for key in ("GIT_DIR", "GIT_INDEX_FILE", "GH_TOKEN", "GITHUB_TOKEN"):
        assert key not in env, key
    for key in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM"):
        assert env["HOME"] in env[key], \
            f"{key} does not point inside the isolated home: {env[key]}"
        assert Path(env[key]).is_file() and \
            Path(env[key]).read_text(encoding="utf-8") == "", \
            f"{key} does not name an empty run-owned file"
    for name in ("APPDATA", "LOCALAPPDATA"):
        assert env["HOME"] in env[name], env[name]
        assert env[name] != os.environ.get(name, "\0")

    src = (_RELEASE_DIR / "release_finalizer.py").read_text(encoding="utf-8")
    assert "env=_git_env()" in src
    assert "network=True" not in src, \
        "the real-HOME network exception is back"


def test_the_live_ref_check_cannot_be_redirected_by_git_configuration(
        tmp_path, monkeypatch):
    """A global `url.<base>.insteadOf` used to rewrite the live-ref check.

    The finalization gates itself on what the SERVER says about main, the head
    branch and the tag. Resolving that through the remote NAME `origin`, with
    the operator's real HOME retained so credential helpers worked, meant one
    line of global configuration could serve those refs from anywhere:

        [url "file:///tmp/attacker"]
            insteadOf = https://github.com/

    The check now names its URL from the trusted contract and runs with global
    and system configuration neutralised, so there is nothing to rewrite.
    """
    truth = tmp_path / "truth.git"
    _run(tmp_path, "init", "-q", "--bare", str(truth))
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "f.txt").write_bytes(b"real\n")
    _init_repo(seed)
    _run(seed, "remote", "add", "origin", str(truth))
    _run(seed, "push", "-q", "origin", "HEAD:refs/heads/main")
    _run(seed, "push", "-q", "origin", "HEAD:refs/heads/wt")
    _run(seed, "tag", "-f", "-a", "v1.0.0", "-m", "v")
    _run(seed, "push", "-q", "-f", "origin", "refs/tags/v1.0.0")
    real_head = _rev(seed, "HEAD")

    # The attacker's repository, serving DIFFERENT commits under the same refs.
    lie = tmp_path / "lie.git"
    _run(tmp_path, "init", "-q", "--bare", str(lie))
    other = tmp_path / "other"
    other.mkdir()
    (other / "g.txt").write_bytes(b"forged\n")
    _init_repo(other)
    _run(other, "push", "-q", str(lie), "HEAD:refs/heads/main")

    contract = {"repository": {
        "owner": "fawazbouhamad", "name": "SCORCH", "base_branch": "main",
        "head_branch": "wt", "expected_tag": "v1.0.0",
        "remote_url": str(truth).replace("\\", "/")}}

    # A hostile global configuration that rewrites the truth URL to the lie.
    # GIT_CONFIG_GLOBAL is poisoned DIRECTLY, not only HOME: when this suite is
    # itself run under the finalizer's hermetic environment, HOME is already
    # redirected and GIT_CONFIG_GLOBAL already names an empty file, so a
    # hostile `~/.gitconfig` would never be read and the probe below would
    # prove nothing. Poisoning the variable that actually decides keeps the
    # test valid in both environments - and it is the stronger attack.
    fake_home = tmp_path / "hostile_home"
    fake_home.mkdir()
    hostile_config = fake_home / ".gitconfig"
    hostile_config.write_text(
        '[url "{lie}"]\n\tinsteadOf = {truth}\n'.format(
            lie=str(lie).replace("\\", "/"),
            truth=str(truth).replace("\\", "/")),
        encoding="utf-8", newline="\n")
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(hostile_config))

    # The redirection is REAL: a plain git honours it. Without this the test
    # would pass just as well against a finalizer that had not been fixed.
    plain = subprocess.run(
        ["git", "ls-remote", str(truth).replace("\\", "/"),
         "refs/heads/main"], capture_output=True, text=True,
        env=dict(os.environ)).stdout
    assert plain.strip(), "the probe produced nothing at all"
    assert real_head not in plain, \
        "the hostile insteadOf did not actually redirect, so this proves nothing"

    refs = rf.live_remote_state(seed, contract)
    assert refs.get("refs/heads/main") == real_head, \
        f"the live-ref check was redirected by git configuration: {refs}"


def test_the_live_ref_url_comes_from_the_contract_not_a_remote_name():
    contract = rf.load_contract()
    assert "remote_url" not in contract["repository"], \
        "the REAL contract pins an override; production must use github.com"
    assert rf.live_remote_url(contract) == \
        "https://github.com/fawazbouhamad/SCORCH.git", \
        rf.live_remote_url(contract)
    src = (_RELEASE_DIR / "release_finalizer.py").read_text(encoding="utf-8")
    body = src.split("def live_remote_state", 1)[1].split("\ndef ", 1)[0]
    assert '"ls-remote", url' in body, \
        "the live-ref check still resolves a remote NAME"
    assert '"origin"' not in body, "the live-ref check still names `origin`"
    assert '"-C"' not in body, \
        "the live-ref check still runs inside a repository, so .git/config " \
        "is read and can carry an insteadOf of its own"


_RUN_VALIDATION_ENV_DUMP = '''\
import json, os
from pathlib import Path


def test_capture_environment():
    out = Path(__file__).resolve().parents[1] / "captured_env.json"
    out.write_text(json.dumps(dict(os.environ)), encoding="utf-8")
'''


def test_the_pytest_validation_run_inherits_no_ambient_control(tmp_path,
                                                               monkeypatch):
    """The capture, executed under the ACTUAL run_validation environment.

    Checking `run_deposit_validator` and asserting on the `_git_env` dict
    leaves the biggest child of all - the pytest run the release is accepted
    on - proved only by reading the source. This runs it.
    """
    _poison(monkeypatch)
    copy_root = tmp_path / "validation_copy"
    (copy_root / "tests").mkdir(parents=True)
    (copy_root / "tests" / "test_env_dump.py").write_text(
        _RUN_VALIDATION_ENV_DUMP, encoding="utf-8", newline="\n")

    summary = tmp_path / "summary.json"
    result = rf.run_validation(copy_root, sys.executable,
                               tmp_path / "final.zip", tmp_path / "extract",
                               summary_path=summary)
    assert result["exit_code"] == 0, result["tail"][-2000:]

    captured = json.loads((copy_root / "captured_env.json")
                          .read_text(encoding="utf-8"))
    _assert_child_environment_is_clean(captured)
    # ...and the pins the validation run depends on really are the run's own.
    assert captured.get("SCORCH_DATA_ARCHIVE") == str(tmp_path / "final.zip")
    assert captured.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD") == "1"


def test_git_reads_the_named_repository_despite_a_hostile_git_dir(tmp_path,
                                                                  monkeypatch):
    """GIT_DIR alone used to redirect every guard to another repository."""
    wanted = tmp_path / "wanted"
    wanted.mkdir()
    (wanted / "f.txt").write_bytes(b"wanted\n")
    _init_repo(wanted)
    other = tmp_path / "other"
    other.mkdir()
    (other / "g.txt").write_bytes(b"other\n")
    _init_repo(other)

    # Recorded BEFORE the poison, because `_rev` is a plain subprocess that
    # inherits the ambient environment - which is exactly the point.
    wanted_head = _rev(wanted, "HEAD")
    other_head = _rev(other, "HEAD")
    assert wanted_head and wanted_head != other_head

    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))
    assert _rev(wanted, "HEAD") == other_head, \
        "the ambient GIT_DIR is not actually redirecting anything, so this " \
        "test would pass even with the sanitization removed"
    assert rf.git(wanted, "rev-parse", "HEAD") == wanted_head, \
        "an ambient GIT_DIR redirected the finalizer to another repository"
    assert "f.txt" in rf.git(wanted, "ls-files")
    assert "g.txt" not in rf.git(wanted, "ls-files")
