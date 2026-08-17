"""Contracts on the text the publication builder GENERATES.

The builder does not just copy files: it writes the README and every
`PROVENANCE.txt` that a reader will treat as the authoritative description of
how each figure came to exist. Those sentences are claims, and they had drifted
away from the identity records they are supposed to describe:

* the reproduction-class loop hardcoded four class names and omitted
  ``deterministic_producer`` entirely, so Figures 1 and 4 were absent from a
  list that claimed to cover every figure;
* the surrounding prose said "one of four classes" as a literal, a count that
  goes stale the moment a class is added;
* it stated that Figures 1 and 4 have "no runnable producer" - untrue since the
  2026-08 correction round, which is exactly what ``deterministic_producer``
  exists to record;
* it claimed the producers regenerate their assets BYTE-IDENTICALLY, conflating
  the portable pixel guarantee with encoder-bound PNG byte identity;
* Figure S.1 was folded into the generic ERA5 rights row, silently dropping the
  NOAA/NCEI attribution its GHCN-Daily station data requires.

These tests call the builder's pure ``readme_text()`` with the REAL tracked
identity and geometry records. Nothing is materialized: no publication output
is written, read back, or modified by this module.
"""
from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
BUILDER = REPO / "scripts" / "publication" / "build_publication_outputs.py"
IDENTITY_CSV = REPO / "docs" / "MANUSCRIPT_FIGURE_IDENTITY.csv"

FIG1_4_CLASS = "deterministic_producer"


def _builder():
    spec = importlib.util.spec_from_file_location("_scorch_pubbuild", BUILDER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def builder():
    assert BUILDER.is_file(), f"required tracked builder missing: {BUILDER}"
    return _builder()


@pytest.fixture(scope="module")
def identity(builder):
    """The real tracked identity records, via the builder's own loader."""
    assert IDENTITY_CSV.is_file(), (
        f"required tracked identity record missing: {IDENTITY_CSV}")
    return builder.load_identity(REPO)


@pytest.fixture(scope="module")
def readme(builder, identity):
    """Generated README text, built in memory from the real records."""
    geom, _by_folder, _threshold = builder.load_geometry(REPO, identity)
    return builder.readme_text(identity, geom)


# ---------------------------------------------------------------------------
# 1. Every class actually used must appear in the generated text.
# ---------------------------------------------------------------------------
def test_every_used_reproduction_class_is_documented(readme, identity):
    used = sorted({r["reproduction_class"] for r in identity})
    missing = [c for c in used if f"`{c}`" not in readme]
    assert not missing, (
        f"reproduction classes present in MANUSCRIPT_FIGURE_IDENTITY.csv but "
        f"absent from the generated README: {missing}")


def test_deterministic_producer_is_documented_and_lists_figures_1_and_4(
        readme, identity):
    assert f"`{FIG1_4_CLASS}`" in readme, (
        "the deterministic_producer class is missing from the generated text")
    members = sorted(r["label"] for r in identity
                     if r["reproduction_class"] == FIG1_4_CLASS)
    assert members, "no figure carries deterministic_producer in the records"
    line = next((ln for ln in readme.splitlines()
                 if f"`{FIG1_4_CLASS}`" in ln), "")
    for label in members:
        assert label in line, (
            f"{label} carries {FIG1_4_CLASS} in the records but is not listed "
            f"on the generated class line: {line!r}")
    # The records say these are Figures 1 and 4; if that ever changes, the
    # assumption behind this whole pass changes with it.
    assert {"Fig. 1.", "Fig. 4."} <= set(members), members


def test_class_count_is_generated_not_hardcoded(readme, identity):
    used = {r["reproduction_class"] for r in identity}
    assert f"one of {len(used)} classes" in readme, (
        f"the generated text does not state the DERIVED class count "
        f"({len(used)})")
    if len(used) != 4:
        assert "one of four classes" not in readme


# ---------------------------------------------------------------------------
# 2. Stale claims must be gone.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("phrase", [
    "no runnable producer",
    "code-native vector schematic",
    "code-native vector",
])
def test_stale_producer_wording_is_absent(readme, phrase):
    assert phrase not in readme, (
        f"the generated README still contains the stale claim {phrase!r}")


def test_no_unconditional_byte_identity_claim_for_the_producers(readme):
    """Byte identity must never be asserted without naming the encoder."""
    lowered = readme.lower()
    idx = lowered.find("deterministic_producer")
    assert idx != -1
    block = lowered[idx:idx + 1400]
    assert "byte-identically" not in block, (
        "the deterministic_producer description still claims unconditional "
        "byte-identical regeneration")
    for marker in ("pixel", "canonical", "pillow", "zlib"):
        assert marker in block, (
            f"the deterministic_producer description does not mention "
            f"{marker!r}, so it cannot be distinguishing portable pixel "
            f"identity from encoder-bound byte identity")


def test_pixel_and_byte_identity_are_described_as_different_things(readme):
    lowered = readme.lower()
    assert "pixel" in lowered and "byte" in lowered
    assert "pillow" in lowered and "zlib" in lowered, (
        "the generated text never names the canonical encoder stack, so a "
        "reader cannot tell which identity claim is toolchain-bound")


# ---------------------------------------------------------------------------
# 3. Figure S.1 rights.
# ---------------------------------------------------------------------------
def _rights_rows(readme):
    return [ln for ln in readme.splitlines()
            if ln.startswith("| `") and ln.rstrip().endswith("|")]


def test_figure_s1_has_its_own_rights_row(readme):
    rows = _rights_rows(readme)
    s1_rows = [r for r in rows if "S.1" in r]
    assert len(s1_rows) == 1, (
        f"expected exactly one rights row naming Fig. S.1, found "
        f"{len(s1_rows)}: {s1_rows}")
    row = s1_rows[0]
    for marker in ("GHCN-Daily", "NOAA", "NCEI"):
        assert marker in row, (
            f"the Fig. S.1 rights row omits {marker!r}; its station data is "
            f"GHCN-Daily and owes NOAA/NCEI attribution: {row!r}")
    assert "ERA5" in row and "Copernicus" in row, (
        f"the Fig. S.1 rights row omits the applicable ERA5/Copernicus terms: "
        f"{row!r}")
    assert "authors' contribution" in row, (
        f"the Fig. S.1 rights row does not scope CC BY to the authors' "
        f"contribution: {row!r}")


def test_generic_reproduced_row_no_longer_absorbs_s1(readme):
    rows = _rights_rows(readme)
    generic = [r for r in rows
               if "Fig. 2, 3, 12" in r and "table sets" in r]
    assert len(generic) == 1, f"generic reproduced row not found: {rows}"
    assert "S.1" not in generic[0], (
        "the generic ERA5 reproduced row still absorbs Fig. S.1, which hides "
        f"its GHCN-Daily/NOAA obligations: {generic[0]!r}")


# ---------------------------------------------------------------------------
# 4. Figures 1 and 4 licensing stays PENDING - this pass activates nothing.
# ---------------------------------------------------------------------------
def test_figures_1_and_4_row_matches_the_licence_state(readme, builder):
    """State-aware: the row must match whichever state the repository is in.

    Asserting PENDING unconditionally would make this test - a member of the
    frozen release collection - fail the moment the licence is legitimately
    activated, which is precisely what made activation unreachable.
    """
    rows = _rights_rows(readme)
    frozen = [r for r in rows if "frozen_figures" in r]
    assert len(frozen) == 1, f"expected one frozen_figures rights row: {rows}"
    row = frozen[0]
    assert "Fig. 1, 4" in row, row
    assert row == builder.artwork_licence_row(REPO), (
        "the generated row is not the row the trusted contract serves")

    if builder.artwork_licence_state(REPO) == builder.ARTWORK_LICENCE_ACTIVE:
        assert "PENDING" not in row.upper(), row
        assert "not yet in force" not in row, row
    else:
        assert "PENDING" in row, (
            f"Figures 1 and 4 must remain CC BY PENDING: {row!r}")
        assert "not yet in force" in row, row
        # The pending row must say WHY the grant is withheld, and the reason is
        # that the artwork creator has not recorded the declaration yet. It must
        # NOT name a third party as the person whose permission is awaited: the
        # artwork is the creator's own work, and nobody is waiting on Dr. Najibi.
        assert "declaration has not been recorded" in row, row
        assert "Najibi" not in row, (
            "the pending row must not represent Dr. Najibi as a licensor whose "
            "authorization is being awaited")


def test_no_unauthored_cc_by_is_generated_for_figures_1_and_4(readme, builder):
    """PENDING must not have quietly become an in-force grant.

    In the ACTIVE state a CC BY grant is correct - but only the one the
    authors wrote into the trusted contract, never wording this builder
    invented.
    """
    rows = _rights_rows(readme)
    frozen = next(r for r in rows if "frozen_figures" in r)
    if builder.artwork_licence_state(REPO) == builder.ARTWORK_LICENCE_ACTIVE:
        contract = _als().load_trusted_contract(REPO)
        assert frozen == contract["publication_outputs_artwork_row"]["active"]
        return
    active = ("CC BY 4.0 for the authors' contribution only",
              "CC BY 4.0 for the authors' contributions")
    for phrase in active:
        assert phrase not in frozen, (
            f"the Figures 1/4 row carries an ACTIVE CC BY grant ({phrase!r}), "
            f"but D6 authorization is still outstanding: {frozen!r}")


# ---------------------------------------------------------------------------
# 5. Nothing was materialized by this module.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 5. The artwork licence is a STATE, and BOTH states must be exercised.
#
# Hard-coding the pending wording made activation unreachable: release
# acceptance requires a fully clean validation run, so a guard that asserts
# PENDING unconditionally fails the instant the licence is correctly
# activated. The wording below is TEST-ONLY SYNTHETIC scaffolding - the real
# active prose is the authors' to write and does not exist.
# ---------------------------------------------------------------------------
def _guards():
    """The guard module, which owns the single TEST-ONLY synthetic clause."""
    spec = importlib.util.spec_from_file_location(
        "_scorch_guards", REPO / "tests" / "test_public_consistency_guards.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


GUARDS = _guards()

#: ONE definition, imported. Every ACTIVE fixture in this module uses it.
SYNTHETIC_ACTIVE_CLAUSE = GUARDS.SYNTHETIC_ACTIVE_CLAUSE
SYNTHETIC_ACTIVE_ROW = GUARDS.synthetic_active_row()

# A synthetic record carries the claim inside real surrounding sentences, so
# the fixture exercises a document with context rather than a file whose whole
# content is the marker. The clause is a LINE of its own in the text form and
# a SENTENCE of its own in the JSON form; in both it normalizes to exactly the
# registered marker, which is what classification compares.
_ACTIVE_SENTENCES = ("TEST-ONLY SYNTHETIC LICENCE RECORD.",
                     SYNTHETIC_ACTIVE_CLAUSE,
                     "End of TEST-ONLY SYNTHETIC LICENCE RECORD.")
_PENDING_SENTENCES = (
    "TEST-ONLY SYNTHETIC LICENCE RECORD.",
    "Figure 1 and Figure 4 artwork: CC BY 4.0 PENDING - not yet in force.",
    "End of TEST-ONLY SYNTHETIC LICENCE RECORD.")

ACTIVE_RECORD_TEXT = "\n".join(_ACTIVE_SENTENCES) + "\n"
ACTIVE_RECORD_NOTES = " ".join(_ACTIVE_SENTENCES)
PENDING_RECORD_TEXT = "\n".join(_PENDING_SENTENCES) + "\n"
PENDING_RECORD_NOTES = " ".join(_PENDING_SENTENCES)


def _als():
    import sys
    release_dir = REPO / "scripts" / "release"
    if str(release_dir) not in sys.path:
        sys.path.insert(0, str(release_dir))
    import artwork_licence_state
    return artwork_licence_state


def _commit_declaration(root, contract, als, artwork):
    """Write and COMMIT the creator declaration, returning receipt fields.

    A real git repository, because a valid receipt must rest on a declaration
    that is tracked at HEAD and byte-equal to its blob.
    """
    import hashlib
    import json as _json
    import subprocess as _sp

    def _git(*args):
        _sp.run(["git", "-C", str(root), *args], check=True,
                capture_output=True)

    spec = contract["declaration_source"]
    rel = spec["tracked_record_path"]
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    declaration = {
        "schema_version": spec["schema_version"],
        "declaration_date": "2026-01-01T00:00:00Z",
        "declared_text": contract["licence_declaration"]["text"],
        "licensed_artwork": artwork,
        "creator_attestation": {
            "creator": spec["creator"],
            "declared_at": "2026-01-02T00:00:00Z",
            "statement": spec["attestation_statement"]},
        "scientific_guidance_credit": spec["guidance_credit"],
    }
    blob_bytes = (_json.dumps(declaration, indent=2, sort_keys=True)
                  + "\n").encode("utf-8")
    path.write_bytes(blob_bytes)
    # A COPIED tree can carry an inherited `.git`. In a linked worktree that is
    # a FILE holding `gitdir: <the real repository>`, so `git -C <copy>` would
    # resolve to - and commit into - the REAL repository. Neutralise it before
    # anything runs, and always work in a self-contained repository of our own.
    dotgit = root / ".git"
    if dotgit.is_file():
        dotgit.unlink()
    if not dotgit.exists():
        _git("init", "-q", "-b", "chore/final-repository-cleanup")
        _git("config", "user.email", "t@example.invalid")
        _git("config", "user.name", "T")
        _git("config", "core.autocrlf", "false")
    _git("add", "-A")
    _git("commit", "-qm", "declaration")
    blob = _sp.run(["git", "-C", str(root), "rev-parse", "HEAD:" + rel],
                   capture_output=True, text=True).stdout.strip()
    text = contract["licence_declaration"]["text"]
    return {
        "licence_source": "creator_declaration",
        "declaration_date": "2026-01-01T00:00:00Z",
        "declared_text": text,
        "declared_text_sha256": als.sha256_hex(text),
        "declaration_record_path": rel,
        "declaration_record_sha256": hashlib.sha256(blob_bytes).hexdigest(),
        "declaration_record_blob_sha1": blob,
        "creator": spec["creator"],
        "declared_at": "2026-01-02T00:00:00Z",
        "scientific_guidance_credit": spec["guidance_credit"],
    }


def _synthetic_tree(tmp_path, *, valid_receipt, active_row, active_records):
    """A throwaway tree whose licence state is whatever the test needs."""
    import json
    import shutil
    als = _als()
    contract = json.loads(
        (REPO / "scripts/release/finalizer_contract.json").read_text("utf-8"))
    contract["publication_outputs_artwork_row"]["active"] = active_row
    # With the "any Figure 1/4 + CC BY sentence is ACTIVE" fallback removed,
    # activated wording is recognised ONLY through a registered exact marker,
    # and the marker must be a COMPLETE affirmative scoped clause - the shared
    # one, so this fixture cannot drift away from the others.
    # A TEST FIXTURE, declared as such: that is what licenses the
    # TEST-ONLY synthetic clause. Production contracts refuse it.
    contract["synthetic_fixture"] = True
    contract["artwork_licence_markers"]["active"] = [SYNTHETIC_ACTIVE_CLAUSE]

    root = tmp_path / "tree"
    (root / "scripts" / "release").mkdir(parents=True)
    shutil.copy2(REPO / "scripts/release/artwork_licence_state.py",
                 root / "scripts/release/artwork_licence_state.py")
    (root / "scripts/release/finalizer_contract.json").write_text(
        json.dumps(contract, indent=2), encoding="utf-8", newline="\n")

    text = ACTIVE_RECORD_TEXT if active_records else PENDING_RECORD_TEXT
    # A JSON record holds its prose in a STRING, so the clause cannot be a
    # line of its own there. Embedded newlines would be escaped as literal
    # "\n" inside one physical line and the clause would be a block of
    # nothing; the one-line sentence form makes it a sentence of its own.
    notes = ACTIVE_RECORD_NOTES if active_records else PENDING_RECORD_NOTES
    for rel in contract["licence_records"]:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if rel.endswith(".json"):
            target.write_text(json.dumps({"notes": notes}, indent=2),
                              encoding="utf-8", newline="\n")
        else:
            target.write_text(text, encoding="utf-8", newline="\n")

    artwork = {}
    for rel in contract["ccby_artwork_paths"]:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f"SYNTHETIC::{rel}\n".encode("utf-8"))
        artwork[rel] = als.sha256_file(target)

    receipt_path = root / contract["licence_receipt"]["tracked_path"]
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    if valid_receipt == "stub":
        receipt_path.write_text('{"schema_version": "1.0.0"}',
                                encoding="utf-8", newline="\n")
    elif valid_receipt:
        repo = contract["repository"]
        fields = _commit_declaration(root, contract, als, artwork)
        receipt_path.write_text(json.dumps(dict(fields, **{
            "schema_version":
                contract["licence_receipt"]["schema_version"],
            "repository": f"{repo['owner']}/{repo['name']}",
            "licensed_artwork": artwork,
            "activated_at": "2026-01-03T00:00:00Z",
            "finalizer_version": contract["finalizer_version"],
            "starting_head": "a" * 40,
        }), indent=2, sort_keys=True), encoding="utf-8", newline="\n")
    return root


def test_pending_state_emits_the_withholding_row(builder, tmp_path):
    root = _synthetic_tree(tmp_path, valid_receipt=None, active_row=None,
                           active_records=False)
    assert builder.artwork_licence_state(root) == \
        builder.ARTWORK_LICENCE_PENDING
    row = builder.artwork_licence_row(root)
    assert "PENDING" in row and "not yet in force" in row


def test_a_stub_receipt_does_not_activate_anything(builder, tmp_path):
    """`{"schema_version": "1.0.0"}` used to be enough. It is not.

    And it is not PENDING either: a receipt that is present but does not
    validate is REFUSED. Answering PENDING published a licence table that
    described a coherent repository while a stub, forged or half-written
    receipt sat in it - the builder's own output covering for the defect. The
    core claim still holds first: nothing is activated.
    """
    als = _als()
    root = _synthetic_tree(tmp_path, valid_receipt="stub", active_row=None,
                           active_records=False)
    assert (root / builder.ARTWORK_RECEIPT_REL).is_file()
    state, issues, detail = als.artwork_licence_state(root)
    assert state == als.PENDING and detail["_receipt_valid"] is False
    assert [c for c, _ in issues if c.startswith("RECEIPT_")], issues

    for call in (builder.artwork_licence_state, builder.artwork_licence_row):
        with pytest.raises(RuntimeError) as exc:
            call(root)
        assert "ARTWORK_RECEIPT_INVALID" in str(exc.value)


@pytest.mark.parametrize("blob", [
    "{ not json at all",
    '{"schema_version": "1.0.0", "schema_version": "1.0.0"}',
    "[]",
    "",
])
def test_a_malformed_receipt_is_refused_not_reported_as_pending(
        builder, tmp_path, blob):
    """Unparseable, duplicate-keyed, wrong-typed and empty receipts all refuse."""
    root = _synthetic_tree(tmp_path, valid_receipt="stub", active_row=None,
                           active_records=False)
    (root / builder.ARTWORK_RECEIPT_REL).write_text(
        blob, encoding="utf-8", newline="\n")
    with pytest.raises(RuntimeError) as exc:
        builder.artwork_licence_state(root)
    assert "ARTWORK_RECEIPT_INVALID" in str(exc.value)


def test_active_state_refuses_to_invent_the_licence_wording(builder, tmp_path):
    """The builder will not author someone else's copyright grant."""
    root = _synthetic_tree(tmp_path, valid_receipt=True, active_row=None,
                           active_records=True)
    assert builder.artwork_licence_state(root) == \
        builder.ARTWORK_LICENCE_ACTIVE
    with pytest.raises(RuntimeError) as exc:
        builder.artwork_licence_row(root)
    assert "UNAUTHORED" in str(exc.value)


def test_active_state_emits_authored_wording_with_no_pending_claim(
        builder, tmp_path):
    root = _synthetic_tree(tmp_path, valid_receipt=True,
                           active_row=SYNTHETIC_ACTIVE_ROW,
                           active_records=True)
    assert builder.artwork_licence_state(root) == \
        builder.ARTWORK_LICENCE_ACTIVE
    row = builder.artwork_licence_row(root)
    assert row == SYNTHETIC_ACTIVE_ROW
    assert "PENDING" not in row and "not yet in force" not in row
    assert "frozen_figures" in row


def test_readme_follows_the_contract_row_and_takes_no_injected_prose(
        builder, identity):
    """No parameter exists for passing licence text into published output."""
    import inspect
    params = inspect.signature(builder.readme_text).parameters
    assert "artwork_row" not in params, (
        "a prose-injection parameter was reintroduced")
    geom, _by_folder, _threshold = builder.load_geometry(REPO, identity)
    text = builder.readme_text(identity, geom)
    rows = [r for r in text.splitlines() if "frozen_figures" in r]
    assert len(rows) == 1, f"expected exactly one frozen_figures row: {rows}"
    assert rows[0] == builder.artwork_licence_row(REPO)


def test_the_real_repository_state_is_coherent(builder):
    """Never INCONSISTENT. Today PENDING, with no receipt to explain otherwise.

    State-aware rather than PENDING-only: this test is in the frozen release
    collection, so hard-coding PENDING would fail a legitimate activation.
    """
    als = _als()
    state, issues, detail = als.artwork_licence_state(REPO)
    assert state != als.INCONSISTENT, issues
    if state == als.ACTIVE:
        assert detail["_receipt_valid"] is True
        assert not issues
    else:
        assert state == als.PENDING
        assert detail["_receipt_valid"] is False
        assert not (REPO / builder.ARTWORK_RECEIPT_REL).exists(), (
            "this pass activates nothing: the real tree has no D6 receipt")


def test_real_builder_and_guard_modules_agree_in_a_disposable_active_tree(
        tmp_path, builder):
    """The REAL modules, in a disposable ACTIVE tree, with TEST-ONLY wording.

    Exercising activation only through the five custom synthetic nodes inside
    the finalizer's own fixture would leave the production builder and the
    repository's own guards unproven in the state that matters.
    """
    import importlib.util
    als = _als()
    root = _synthetic_tree(tmp_path, valid_receipt=True,
                           active_row=SYNTHETIC_ACTIVE_ROW,
                           active_records=True)

    # the shared strict helper
    state, issues, detail = als.artwork_licence_state(root)
    assert state == als.ACTIVE, (state, issues)
    assert detail["_receipt_valid"] is True and not issues

    # the REAL publication builder
    assert builder.artwork_licence_state(root) == builder.ARTWORK_LICENCE_ACTIVE
    row = builder.artwork_licence_row(root)
    assert row == SYNTHETIC_ACTIVE_ROW
    assert "PENDING" not in row.upper()

    # the REAL public-consistency guard module, against the same tree
    spec = importlib.util.spec_from_file_location(
        "_scorch_guards", REPO / "tests" / "test_public_consistency_guards.py")
    guards = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guards)
    assert guards.artwork_licence_is_active(root) is True
    guard_state, guard_issues = guards.artwork_licence_state(root)
    assert guard_state == als.ACTIVE and not guard_issues

    # zero pending claims survive anywhere in that tree
    contract = als.load_trusted_contract(root)
    for rel in contract["licence_records"]:
        text = (root / rel).read_text(encoding="utf-8")
        assert als.classify_claim(text, contract) == als.ACTIVE, rel
        assert "CC BY 4.0 PENDING" not in text, rel


ACTIVE_MARKER = SYNTHETIC_ACTIVE_CLAUSE

#: Files an activation is allowed to rewrite. Everything else in the copied
#: tree must come out byte-identical.
ACTIVATION_WRITABLE = ("scripts/release/finalizer_contract.json",
                       "docs/LICENSES_AND_ATTRIBUTION.md",
                       "assets/frozen_figures/README.md",
                       "assets/manuscript_final/README.md",
                       ".zenodo.json")


def _activated_copy(source, root, marker):
    """Copy ``source`` and normalize it into the ACTIVE state under ``marker``.

    EXACT, RECORD-SPECIFIC BLOCK TRANSFORMATIONS - never a whole-file
    replacement. The previous helper ran ``text.replace(old_marker, marker)``
    over each record, which rewrote every occurrence of a marker wherever it
    appeared - including inside sentences that DENY the grant - and left the
    surrounding pending prose standing. A record could come out of it carrying
    an active marker inside a paragraph still saying the licence is not in
    force, which is precisely the contradiction the classifier exists to catch.

    Each transformation names ONE complete source block that must occur
    EXACTLY ONCE in the record it belongs to. Zero matches and two matches are
    both errors and neither is repaired by guessing. Every destination emits
    the clause as a standalone normalized block and carries the third-party
    rights sentences across verbatim, so ERA5, GHCN-Daily, Natural Earth, GPL
    and Aptos wording and counts are unchanged.

    Works whether the SOURCE is PENDING or ALREADY ACTIVE under a different
    authored marker: during a real finalization the full suite runs from an
    already-ACTIVE validation copy, so the candidate source blocks are the
    pending block PLUS the destination block of every marker the SOURCE
    contract registers. Exactly one of them may be present.
    """
    import json
    import shutil
    als = _als()
    guards = _guards()
    shutil.copytree(
        source, root, symlinks=True,
        ignore=shutil.ignore_patterns(
            # `.git` FIRST, and for a reason: in a linked worktree it is a
            # FILE holding `gitdir: <the real repository>`. Copying it makes
            # every `git -C <copy>` in this module resolve to the REAL
            # repository, so a helper that commits into "its own" tree commits
            # into the operator's branch instead.
            ".git",
            "release_staging", "manuscript_revision_output",
            "manuscript_revision_inputs", "__pycache__", ".pytest_cache"))

    contract_path = root / "scripts/release/finalizer_contract.json"
    contract = als.loads_strict(contract_path.read_text(encoding="utf-8"))
    prior = [m for m in contract["artwork_licence_markers"]["active"] if m]

    # The transformation tables are index-aligned across clauses, so entry i
    # of the table for a PRIOR marker is the block that entry i of the new
    # table replaces when the source is already ACTIVE.
    wanted = guards.synthetic_activation_transforms(marker)
    variants = [guards.synthetic_activation_transforms(p) for p in prior]

    protected_before = {
        rel: (root / rel).read_bytes()
        for rel in contract["protected_historical_records"]}
    before = {rel: (root / rel).read_text(encoding="utf-8")
              for rel in contract["licence_records"]}
    staged = dict(before)
    applied = []

    for index, (rel, pending_source, destination) in enumerate(wanted):
        text = staged[rel]
        candidates = [pending_source] + [v[index][2] for v in variants]
        # Deduplicate: re-activating under the SAME marker makes the pending
        # variant and a prior variant identical, and that is one candidate.
        seen, sources = set(), []
        for candidate in candidates:
            if candidate not in seen:
                seen.add(candidate)
                sources.append(candidate)
        counts = {candidate: text.count(candidate) for candidate in sources}
        multiple = {c: n for c, n in counts.items() if n > 1}
        assert not multiple, (
            f"{rel}: activation source block occurs more than once "
            f"({ {c[:60]: n for c, n in multiple.items()} }); a block that is "
            f"not unique cannot identify the claim being retired")
        present = [c for c, n in counts.items() if n == 1]
        assert len(present) == 1, (
            f"{rel}: expected EXACTLY ONE of {len(sources)} candidate source "
            f"block(s) to be present, found {len(present)}. The record is "
            f"neither cleanly PENDING nor cleanly ACTIVE under a registered "
            f"marker, and this helper will not guess which claim to retire. "
            f"Candidates: {[c[:70] for c in sources]}")
        source_block = present[0]
        staged[rel] = text.replace(source_block, destination)
        applied.append((rel, source_block, destination))

    # Nothing but the intended blocks may have moved. Reversing every applied
    # transformation must reproduce the ORIGINAL bytes exactly; if any other
    # byte had changed, the reversal would not.
    reversed_text = dict(staged)
    for rel, source_block, destination in reversed(applied):
        assert reversed_text[rel].count(destination) == 1, rel
        reversed_text[rel] = reversed_text[rel].replace(
            destination, source_block)
    for rel in before:
        assert reversed_text[rel] == before[rel], (
            f"{rel}: the activation changed bytes outside its authored blocks")

    # Third-party rights wording is not the artwork's to touch.
    for rel in before:
        for token in guards.PRESERVED_RIGHTS_TOKENS:
            assert staged[rel].count(token) == before[rel].count(token), (
                f"{rel}: activation changed the number of {token!r} "
                f"occurrences ({before[rel].count(token)} -> "
                f"{staged[rel].count(token)})")

    contract["artwork_licence_markers"]["active"] = [marker]
    contract["publication_outputs_artwork_row"]["active"] = \
        guards.synthetic_active_row(marker)
    contract_path.write_text(json.dumps(contract, indent=2),
                             encoding="utf-8", newline="\n")
    for rel, text in staged.items():
        (root / rel).write_text(text, encoding="utf-8", newline="\n")

    # Prove the outcome rather than assuming it.
    for rel in contract["licence_records"]:
        text = (root / rel).read_text(encoding="utf-8")
        stale = [m for m in contract["artwork_licence_markers"]["pending"]
                 if m and m in text]
        assert not stale, f"{rel} still carries pending markers {stale}"
        assert als.classify_claim(text, contract) == als.ACTIVE, (
            f"{rel} does not classify as ACTIVE after activation")
    for rel, original in protected_before.items():
        assert (root / rel).read_bytes() == original, (
            f"{rel} is a protected historical record and must be "
            f"byte-identical after an activation")
    return contract


def _disposable_active_repository(tmp_path, source=None, marker=None):
    """A full copy of a repository, switched into the ACTIVE state.

    TEST-ONLY wording throughout. Nothing here is a draft of the real
    activation prose, and none of it touches the real tree.
    """
    import json
    als = _als()
    root = tmp_path / "active_repo"
    contract = _activated_copy(source or REPO, root, marker or ACTIVE_MARKER)

    # A receipt that VALIDATES against this tree.
    repo = contract["repository"]
    artwork = {rel: als.sha256_file(root / rel)
               for rel in contract["ccby_artwork_paths"]}
    receipt = dict(_commit_declaration(root, contract, als, artwork), **{
        "schema_version": contract["licence_receipt"]["schema_version"],
        "repository": f"{repo['owner']}/{repo['name']}",
        "licensed_artwork": artwork,
        "activated_at": "2026-01-03T00:00:00Z",
        "finalizer_version": contract["finalizer_version"],
        "starting_head": "a" * 40,
    })
    receipt_path = root / contract["licence_receipt"]["tracked_path"]
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True),
                            encoding="utf-8", newline="\n")
    assert als.validate_receipt(receipt, contract, root) == []
    state, issues, _detail = als.artwork_licence_state(root, contract)
    assert state == als.ACTIVE, (state, issues)
    return root


def _minimal_activation_source(dest):
    """The smallest tree ``_activated_copy`` can operate on, from real files.

    Only the contract, the four licence records and the two protected
    historical records are copied, so a transformation-policy test costs a
    handful of files instead of a whole repository.
    """
    import shutil
    als = _als()
    contract = als.load_trusted_contract(REPO)
    rels = ["scripts/release/finalizer_contract.json"] + \
        list(contract["licence_records"]) + \
        list(contract["protected_historical_records"])
    for rel in rels:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / rel, target)
    return dest


def _incoming_marker(root):
    """A marker that is NOT the one ``root`` already registers.

    These tests run twice: once against the tracked PENDING tree, and once -
    by subprocess - inside a disposable copy that is already ACTIVE. Activating
    to the marker a tree already carries is a no-op, so a test written for the
    PENDING case silently stops exercising anything in the ACTIVE one.
    """
    als = _als()
    registered = als.load_trusted_contract(
        root)["artwork_licence_markers"]["active"]
    return ALPHA_MARKER if ACTIVE_MARKER in registered else ACTIVE_MARKER


def _real_activation_applied(root=REPO):
    """True when the REAL authored activation has already been applied.

    The synthetic machinery below rewrites the PENDING prose into a TEST-ONLY
    clause. A real finalization replaces that SAME prose with the AUTHORED
    destination, which neither transform table knows - so once that has
    happened there is no block left for a synthetic activation to retire.

    These tests belong to the frozen release collection, so they also run
    inside the disposable validation copy of an activated release. There they
    have nothing to transform, and they say so and return rather than failing
    on a premise that no longer holds or skipping (acceptance requires zero
    skips). The activated state is proved instead by the state-aware guards in
    tests/test_release_finalizer.py section 8a.
    """
    als = _als()
    contract = als.load_trusted_contract(root)
    for item in contract["ccby_activation_plan"]["replacements"]:
        rel = item["file"]
        if rel.startswith("archive:"):
            continue
        path = Path(root) / rel
        if path.is_file() and item["to"] in path.read_text(encoding="utf-8"):
            return True
    return False


def _current_source_block(root, index, marker):
    """``(rel, block)``: the block a fresh activation would retire right now.

    The record may be PENDING or already ACTIVE under another authored marker.
    Both are legitimate starting states, so the block is DERIVED from what is
    actually in the record rather than assumed to be the pending one.
    """
    als = _als()
    guards = _guards()
    contract = als.load_trusted_contract(root)
    rel, pending, _dst = guards.synthetic_activation_transforms(marker)[index]
    text = (Path(root) / rel).read_text(encoding="utf-8")
    candidates = [pending] + [
        guards.synthetic_activation_transforms(prior)[index][2]
        for prior in contract["artwork_licence_markers"]["active"] if prior]
    present = [c for c in candidates if text.count(c) == 1]
    assert len(present) == 1, (rel, index, len(present))
    return rel, present[0]


def test_activation_changes_only_the_artwork_blocks(tmp_path):
    """Whole-tree proof: the authored blocks change and NOTHING else does.

    A whole-file marker replacement passes every state assertion while
    silently rewriting unrelated prose that happens to contain the marker.
    The only way to see that is to compare the entire tree.
    """
    if _real_activation_applied():
        return
    als = _als()
    guards = _guards()
    marker = _incoming_marker(REPO)
    transforms = guards.synthetic_activation_transforms(marker)
    applied = [(rel, _current_source_block(REPO, i, marker)[1], dst)
               for i, (rel, _src, dst) in enumerate(transforms)]

    root = tmp_path / "active"
    contract = _activated_copy(REPO, root, marker)

    changed = []
    for path in root.rglob("*"):
        # .git is copied verbatim and is not an activation surface; the guards
        # that recompute repository scope from git need it present.
        if ".git" in path.parts or not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        origin = REPO / rel
        if not origin.is_file() or path.read_bytes() != origin.read_bytes():
            changed.append(rel)
    assert sorted(changed) == sorted(ACTIVATION_WRITABLE), (
        f"activation changed files outside the licence surfaces: "
        f"{sorted(set(changed) - set(ACTIVATION_WRITABLE))}; and failed to "
        f"change {sorted(set(ACTIVATION_WRITABLE) - set(changed))}")

    # Inside the four records, the ONLY difference is the authored blocks:
    # reversing every transformation reproduces the tracked bytes exactly.
    rebuilt = {}
    for rel, source_block, destination in reversed(applied):
        text = rebuilt.get(rel)
        if text is None:
            text = (root / rel).read_text(encoding="utf-8")
        assert text.count(destination) == 1, (
            f"{rel}: the authored destination block is not present exactly "
            f"once after activation")
        assert source_block not in text, (
            f"{rel}: the retired pending block survived the activation")
        rebuilt[rel] = text.replace(destination, source_block)
    for rel, text in rebuilt.items():
        assert text == (REPO / rel).read_text(encoding="utf-8"), (
            f"{rel} differs from the tracked record outside its blocks")

    # Rights that are not the artwork's: unchanged, token for token.
    for rel in contract["licence_records"]:
        activated = (root / rel).read_text(encoding="utf-8")
        tracked = (REPO / rel).read_text(encoding="utf-8")
        for token in guards.PRESERVED_RIGHTS_TOKENS:
            assert activated.count(token) == tracked.count(token), (
                f"{rel}: {token!r} count changed")
        assert als.classify_claim(activated, contract) == als.ACTIVE, rel
    for rel in contract["protected_historical_records"]:
        assert (root / rel).read_bytes() == (REPO / rel).read_bytes(), (
            f"{rel} is a protected historical record")


def test_activation_refuses_a_record_whose_source_block_is_absent(tmp_path):
    """Zero matches is an error, not a silent no-op."""
    source = _minimal_activation_source(tmp_path / "src")
    marker = _incoming_marker(source)
    rel, block = _current_source_block(source, 0, marker)
    target = source / rel
    target.write_text(
        target.read_text(encoding="utf-8").replace(block, " REWRITTEN "),
        encoding="utf-8", newline="\n")
    with pytest.raises(AssertionError) as exc:
        _activated_copy(source, tmp_path / "out", marker)
    assert "EXACTLY ONE" in str(exc.value)


def test_activation_refuses_a_duplicated_source_block(tmp_path):
    """Two matches is an error: the block no longer identifies one claim."""
    source = _minimal_activation_source(tmp_path / "src")
    marker = _incoming_marker(source)
    rel, block = _current_source_block(source, 0, marker)
    target = source / rel
    text = target.read_text(encoding="utf-8")
    target.write_text(text.replace(block, block + block, 1),
                      encoding="utf-8", newline="\n")
    with pytest.raises(AssertionError) as exc:
        _activated_copy(source, tmp_path / "out", marker)
    assert "more than once" in str(exc.value)


def test_the_real_modules_pass_by_subprocess_in_an_active_repository(
        tmp_path):
    """The COMPLETE real modules, run by pytest, in an ACTIVE repository.

    Imported helper calls exercise the helpers. This runs the two modules the
    way CI runs them, in a tree where the artwork licence is genuinely
    activated - which is the state a real finalization produces and the one
    that used to be unreachable.
    """
    import json
    import os
    import subprocess
    import sys

    if os.environ.get("SCORCH_NESTED_ACTIVE_RUN") or \
            _real_activation_applied():
        # Already inside a disposable ACTIVE repository - either because this
        # run forked one (recursing would fork a copy of a copy forever), or
        # because a real finalization built this tree and the synthetic
        # activation has no PENDING block left to retire. Returns rather than
        # skipping, because the ACTIVE run must report zero skips.
        return

    root = _disposable_active_repository(tmp_path)
    summary = tmp_path / "summary.json"
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    (plugin_dir / "scorch_tally.py").write_text(
        "import json, os\n"
        "def pytest_terminal_summary(terminalreporter, exitstatus, config):\n"
        "    s = terminalreporter.stats\n"
        "    json.dump({k: len(s.get(k, [])) for k in\n"
        "               ('passed','failed','error','skipped','xfailed',\n"
        "                'xpassed')},\n"
        "              open(os.environ['SCORCH_TALLY'], 'w'))\n",
        encoding="utf-8", newline="\n")

    env = {k: v for k, v in os.environ.items()
           if not k.upper().startswith(("SCORCH", "PYTEST", "PYTHON"))}
    env.update({
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTHONPATH": os.pathsep.join(["src", str(plugin_dir)]),
        "SCORCH_TALLY": str(summary),
        "SCORCH_NESTED_ACTIVE_RUN": "1",
    })
    proc = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/test_publication_builder_contracts.py",
         "tests/test_public_consistency_guards.py",
         "-p", "no:cacheprovider", "-p", "scorch_tally", "-q", "--no-header",
         "-rsxX"],
        cwd=str(root), env=env, capture_output=True, text=True)

    tally = json.loads(summary.read_text(encoding="utf-8")) \
        if summary.is_file() else {}
    detail = (proc.stdout[-4000:] + proc.stderr[-2000:])
    assert tally, f"the run produced no tally:\n{detail}"
    _assert_clean_nested_tally(tally, detail, "ACTIVE-state")
    assert tally["passed"] > 100, tally
    assert proc.returncode == 0, detail


#: The ONE skip a history-less copy may legitimately report.
#:
#: `_disposable_active_repository` builds its tree with `shutil.copytree`, which
#: deliberately does NOT copy `.git` - in a linked worktree that is a pointer
#: FILE, and copying it made every `git` call in the copy resolve to, and
#: commit into, the REAL repository. The price of that isolation is that one
#: guard, which recomputes tracked-file totals from two historical commits,
#: has no history to recompute from and skips.
#:
#: This does NOT relax the release rule. A real finalization validates in
#: `_clone_repository_at_head`, which is a genuine clone WITH history, so that
#: guard runs there and the accepted run still reports zero skips. Only this
#: test's own copy is affected, the allowance is exactly one skip, and its
#: REASON must match - any other skip still fails.
EXPECTED_COPY_SKIP = "cannot recompute baseline_before_scope_cleanup"


def _assert_clean_nested_tally(tally, detail, label):
    """Zero failures/errors/xfails/xpasses, and no unexplained skip."""
    for key in ("failed", "error", "xfailed", "xpassed"):
        assert tally.get(key, 1) == 0, (
            f"{label} run reported {tally.get(key)} {key}:\n{detail}")
    skipped = tally.get("skipped", 1)
    if skipped:
        assert skipped == 1, (
            f"{label} run reported {skipped} skips; only the history-less "
            f"baseline recompute may skip in a copied tree:\n{detail}")
        assert EXPECTED_COPY_SKIP in detail, (
            f"{label} run skipped something other than the history-less "
            f"baseline recompute:\n{detail}")


#: A second VALID authored clause: complete, scoped, affirmative, and
#: distinct from the shared one, so re-activating an already-ACTIVE tree is a
#: real transition between two registrable markers rather than a no-op.
ALPHA_MARKER = GUARDS.SYNTHETIC_ACTIVE_CLAUSE_ALPHA


def _run_modules(root, tmp_path):
    """Run the two real modules by pytest subprocess inside ``root``."""
    import json
    import os
    import subprocess
    import sys

    summary = tmp_path / "tally.json"
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir(exist_ok=True)
    (plugin_dir / "scorch_tally.py").write_text(
        "import json, os\n"
        "def pytest_terminal_summary(terminalreporter, exitstatus, config):\n"
        "    s = terminalreporter.stats\n"
        "    json.dump({k: len(s.get(k, [])) for k in\n"
        "               ('passed','failed','error','skipped','xfailed',\n"
        "                'xpassed')},\n"
        "              open(os.environ['SCORCH_TALLY'], 'w'))\n",
        encoding="utf-8", newline="\n")

    env = {k: v for k, v in os.environ.items()
           if not k.upper().startswith(("SCORCH", "PYTEST", "PYTHON"))}
    env.update({
        "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTHONPATH": os.pathsep.join(["src", str(plugin_dir)]),
        "SCORCH_TALLY": str(summary), "SCORCH_NESTED_ACTIVE_RUN": "1",
    })
    proc = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/test_publication_builder_contracts.py",
         "tests/test_public_consistency_guards.py",
         "-p", "no:cacheprovider", "-p", "scorch_tally", "-q", "--no-header",
         "-rsxX"],
        cwd=str(root), env=env, capture_output=True, text=True)
    tally = json.loads(summary.read_text(encoding="utf-8")) \
        if summary.is_file() else {}
    return tally, proc


def test_the_real_modules_pass_from_an_ALREADY_ACTIVE_source(tmp_path):
    """The source repository is already ACTIVE, under a DIFFERENT marker.

    A real finalization runs the whole suite from an already-ACTIVE validation
    copy. The helper used to retire only the PENDING markers, so the source's
    own authored active marker survived unregistered in the new contract and
    every record became unclassifiable.
    """
    import os
    if os.environ.get("SCORCH_NESTED_ACTIVE_RUN") or \
            _real_activation_applied():
        # Same two reasons as above: a nested copy would recurse forever, and a
        # really-activated tree has no PENDING block for the synthetic
        # transform to retire. Returns rather than skipping.
        return

    als = _als()
    # 1. An ACTIVE source with its own authored marker and a valid receipt.
    source = _disposable_active_repository(tmp_path / "alpha",
                                           marker=ALPHA_MARKER)
    state, issues, detail = als.artwork_licence_state(source)
    assert state == als.ACTIVE, (state, issues)
    assert detail["_receipt_valid"] is True
    receipt = als.loads_strict(
        (source / als.load_trusted_contract(source)["licence_receipt"]
         ["tracked_path"]).read_text(encoding="utf-8"))
    assert len(receipt["licensed_artwork"]) == 7

    # 2. Re-activate FROM that already-ACTIVE source under a different marker.
    root = _disposable_active_repository(tmp_path / "beta", source=source)
    state, issues, detail = als.artwork_licence_state(root)
    assert state == als.ACTIVE, (state, issues)
    assert detail["_receipt_valid"] is True and not issues
    contract = als.load_trusted_contract(root)
    assert contract["artwork_licence_markers"]["active"] == [ACTIVE_MARKER]
    for rel in contract["licence_records"]:
        text = (root / rel).read_text(encoding="utf-8")
        assert ALPHA_MARKER not in text, f"{rel} kept the source's marker"
        assert als.classify_claim(text, contract) == als.ACTIVE, rel

    # 3. The complete real modules, by subprocess, from that copy.
    tally, proc = _run_modules(root, tmp_path)
    detail_text = proc.stdout[-4000:] + proc.stderr[-2000:]
    assert tally, f"no tally:\n{detail_text}"
    _assert_clean_nested_tally(tally, detail_text, "already-ACTIVE-source")
    assert tally["passed"] > 100, tally
    assert proc.returncode == 0, detail_text


def test_the_builder_threads_the_selected_root(tmp_path, builder):
    """`--root` must reach the licence-state and contract lookup.

    A build against an alternate root must read THAT root's contract and
    receipt, not the repository this file happens to live in.
    """
    active = _synthetic_tree(tmp_path / "a", valid_receipt=True,
                             active_row=SYNTHETIC_ACTIVE_ROW,
                             active_records=True)
    pending = _synthetic_tree(tmp_path / "b", valid_receipt=None,
                              active_row=None, active_records=False)
    assert builder.artwork_licence_state(active) == \
        builder.ARTWORK_LICENCE_ACTIVE
    assert builder.artwork_licence_state(pending) == \
        builder.ARTWORK_LICENCE_PENDING
    assert builder.artwork_licence_row(active) == SYNTHETIC_ACTIVE_ROW
    assert "PENDING" in builder.artwork_licence_row(pending)
    # and the two answers really are different, i.e. the root was used
    assert builder.artwork_licence_row(active) != \
        builder.artwork_licence_row(pending)


def test_readme_generation_is_pure_text(readme):
    """Guards the guard: readme_text must be pure text generation."""
    assert isinstance(readme, str) and readme.strip()


def test_an_invalid_receipt_path_refuses_the_builder(builder, tmp_path):
    """r3d: the containment rule reaches the BUILDER, not only the helper.

    `Path.is_file()` follows links, so a symlink at the contracted path aimed
    at a valid receipt outside the repository was read and validated. The
    receipt that licences a coauthor's copyright has to be in the repository
    that claims the licence, and the builder must refuse rather than publish a
    row derived from a document this tree does not contain.
    """
    root = _synthetic_tree(tmp_path, valid_receipt=True,
                           active_row=SYNTHETIC_ACTIVE_ROW,
                           active_records=True)
    assert builder.artwork_licence_state(root) == \
        builder.ARTWORK_LICENCE_ACTIVE, "the fixture proves nothing otherwise"

    contract = builder._artwork.load_trusted_contract(root)
    target = root / contract["licence_receipt"]["tracked_path"]
    target.unlink()
    target.mkdir()                      # a non-regular object, portably

    path, issues = builder._artwork.resolve_receipt_path(root, contract)
    assert path is None
    assert [c for c, _ in issues] == ["RECEIPT_PATH_INVALID"], issues

    with pytest.raises(RuntimeError) as exc:
        builder.artwork_licence_state(root)
    assert "ARTWORK_RECEIPT_INVALID" in str(exc.value), str(exc.value)
    with pytest.raises(RuntimeError):
        builder.artwork_licence_row(root)


def test_the_builder_never_reaches_active_through_an_invalid_receipt_path(
        builder, tmp_path):
    """Whatever else happens, the answer is never ACTIVE."""
    root = _synthetic_tree(tmp_path, valid_receipt=True,
                           active_row=SYNTHETIC_ACTIVE_ROW,
                           active_records=True)
    contract = builder._artwork.load_trusted_contract(root)
    target = root / contract["licence_receipt"]["tracked_path"]
    target.unlink()
    target.mkdir()
    state, issues, _detail = builder._artwork.artwork_licence_state(root)
    assert state != builder.ARTWORK_LICENCE_ACTIVE
    assert "RECEIPT_PATH_INVALID" in [c for c, _ in issues]
