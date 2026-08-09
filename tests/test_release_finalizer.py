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

import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
_RELEASE_DIR = REPO / "scripts" / "release"
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
# Synthetic fixtures
# ---------------------------------------------------------------------------
class FakeGitHub:
    """An injected GitHub. Tests pass an instance; production never can."""

    def __init__(self, pr=None, comments=None, live=None, missing=False):
        self._pr = pr if pr is not None else {}
        self._comments = list(comments or [])
        self._live = live
        self._missing = missing

    def pull_request(self, owner, repo, number):
        return self._pr

    def issue_comments(self, owner, repo, number):
        return self._comments

    def issue_comment(self, owner, repo, comment_id):
        if self._missing:
            raise rf.FinalizerError("GITHUB_API_UNAVAILABLE",
                                    f"comment {comment_id} is gone")
        if self._live is not None:
            return self._live
        for c in self._comments:
            if c["id"] == comment_id:
                return c
        raise rf.FinalizerError("GITHUB_API_UNAVAILABLE", "no such comment")


def comment(body=AUTH_TEXT, login="nassernajibi", cid=101,
            owner="fawazbouhamad", repo="SCORCH", number=1):
    return {"id": cid, "user": {"login": login}, "body": body,
            "html_url": f"https://github.com/{owner}/{repo}/pull/{number}"
                        f"#issuecomment-{cid}",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z"}


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
    write("assets/manuscript_final/README.md",
          f"Figure 1 artwork CC BY 4.0 PENDING. {ARCHIVE_NAME}\n")
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
                "assets/frozen_figures/README.md", ".zenodo.json"):
        write(rel, "Figure 1 and Figure 4 artwork: CC BY 4.0 PENDING - not "
                   "yet in force. GPL-3.0-only applies to the software. "
                   "Contains modified Copernicus Climate Change Service "
                   "information 2026. GHCN-Daily terms apply. ERA5 data.\n")
    for rel, blob in (("assets/frozen_figures/fig01/Figure_01.png", b"FIG1"),
                      ("assets/frozen_figures/fig04/Figure_04.png", b"FIG4")):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(blob)

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
        "authorization": {"required_login": "nassernajibi", "text": AUTH_TEXT},
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
        "figures": {
            "assets/frozen_figures/fig01/Figure_01.png":
                rf.sha256_bytes(b"FIG1"),
            "assets/frozen_figures/fig04/Figure_04.png":
                rf.sha256_bytes(b"FIG4")},
        "ccby_artwork_paths": ["assets/frozen_figures/fig01/Figure_01.png"],
        "third_party_rights_tokens": [
            "GPL-3.0-only",
            "Contains modified Copernicus Climate Change Service information",
            "GHCN-Daily", "ERA5"],
        "archive_topology": {
            "member_count": 3, "sums_entries": 2, "manifest_rows": 1,
            "relocation_rows": 21, "sums_member": "SHA256SUMS",
            "manifest_member": "FILE_MANIFEST.csv",
            "validator_member": "validate_deposit.py"},
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
        def _capture(self, rel):
            super()._capture(rel)
            if rel == protected_rel:
                (self.repo_root / protected_rel).write_text(
                    "REWRITTEN", encoding="utf-8")

    before = snapshot(synthetic["root"])
    with pytest.raises(rf.FinalizerError) as exc:
        Meddling(synthetic["root"], contract).apply(edits)
    assert exc.value.code == "PROTECTED_RECORD_MODIFIED"
    assert snapshot(synthetic["root"])[protected_rel] == before[protected_rel]


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
    synthetic["contract"]["ccby_activation_plan"] = {
        "authored": True,
        "replacements": [{"file": "docs/CANONICAL_SCIENCE.json",
                          "from": "archive", "to": "ARCHIVE", "count": 1}]}
    with pytest.raises(rf.FinalizerError) as exc:
        rf.plan_ccby_activation(synthetic["root"], synthetic["contract"])
    assert exc.value.code == "CCBY_ACTIVATION_SCOPE"


def test_activation_that_disturbs_third_party_rights_is_refused(synthetic):
    synthetic["contract"]["ccby_activation_plan"] = {
        "authored": True,
        "replacements": [{
            "file": "docs/LICENSES_AND_ATTRIBUTION.md",
            "from": "GPL-3.0-only applies to the software. ",
            "to": "", "count": 1}]}
    with pytest.raises(rf.FinalizerError) as exc:
        rf.plan_ccby_activation(synthetic["root"], synthetic["contract"])
    assert exc.value.code == "CCBY_THIRD_PARTY_LEAKAGE"


def test_activation_count_mismatch_is_refused(synthetic):
    synthetic["contract"]["ccby_activation_plan"] = {
        "authored": True,
        "replacements": [{"file": ".zenodo.json", "from": "PENDING",
                          "to": "IN FORCE", "count": 5}]}
    with pytest.raises(rf.FinalizerError) as exc:
        rf.plan_ccby_activation(synthetic["root"], synthetic["contract"])
    assert exc.value.code == "CCBY_ACTIVATION_COUNT"


def test_an_authored_in_scope_activation_is_accepted(synthetic):
    """Synthetic success, in a disposable tree, with test-only wording."""
    synthetic["contract"]["ccby_activation_plan"] = {
        "authored": True,
        "replacements": [{"file": ".zenodo.json",
                          "from": "CC BY 4.0 PENDING - not yet in force",
                          "to": "CC BY 4.0 IN FORCE (TEST-ONLY WORDING)",
                          "count": 1}]}
    edits = rf.plan_ccby_activation(synthetic["root"], synthetic["contract"])
    assert [e.rel for e in edits] == [".zenodo.json"]
    assert b"TEST-ONLY WORDING" in edits[0].updated
    assert b"GPL-3.0-only" in edits[0].updated


# ---------------------------------------------------------------------------
# 9. finalize refuses to start
# ---------------------------------------------------------------------------
def test_finalize_without_confirmation_does_nothing(synthetic):
    before = snapshot(synthetic["root"])
    report = rf.finalize(synthetic["root"], "chore/final-repository-cleanup",
                         synthetic["head"], contract=synthetic["contract"],
                         stage_dir=synthetic["tmp"],
                         github=FakeGitHub(pr=good_pr(synthetic["head"]),
                                           comments=[comment()]))
    assert report.codes == ["CONFIRMATION_REQUIRED"]
    assert snapshot(synthetic["root"]) == before


def test_finalize_stops_at_the_d6_gate_and_writes_nothing(synthetic):
    before = snapshot(synthetic["root"])
    report = rf.finalize(synthetic["root"], "chore/final-repository-cleanup",
                         synthetic["head"], contract=synthetic["contract"],
                         stage_dir=synthetic["tmp"],
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
