#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Release-alignment stale-provenance guards (v1.0.0 final remediation).

These tests fail the build if superseded pre-release provenance re-enters
the ACTIVE release documentation or routing. They deliberately distinguish
quarantined historical provenance (lines explicitly labelled superseded /
historical / pre-release) from active release fields: erasing valuable
history is not required to stay green, but presenting it as current is a
failure.

Guarded invariants (docs/CANONICAL_SCIENCE.json is the contract):

* the Figure A producer documents the exact combined-score account
  204.5440673062212 and never the false pre-release "33+100+76 = 209";
* the superseded Table 1 checksum (778e08ab...) never appears outside an
  explicitly labelled historical context, and the active Table 1 checksum
  is the canonical f12ee1ab...;
* the defective Figure 9 is never described as "published" (the project
  was never publicly released);
* no active path routes through the retired ALIGNMENT_V1_0_1_20260804
  staging tree;
* "V12" appears only as an explicitly historical pre-release label;
* every machine-readable version field is exactly 1.0.0;
* repo-relative paths claimed by the science contract exist in the tree
  (unless explicitly labelled as external / research-repository paths);
* no frequency Mann-Kendall / Sen inference reappears in the two producers
  it was removed from;
* the corrected Figure 9 embed and Figure S.1 hashes are pinned;
* the two frozen FINAL DOCX hashes are pinned (verified when the documents
  are present; skipped with a clear message otherwise).
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent

# --- canonical constants (docs/CANONICAL_SCIENCE.json) ----------------------
TABLE1_CANONICAL_SHA = (
    "f12ee1ab937956e4bcaeb1c2baad7b0aa05ed939c498310ba91882a58baa0c2e")
TABLE1_SUPERSEDED_SHA_PREFIX = "778e08ab"
FIG9_EMBED_SHA = (
    "7859acbd9ea69047d5a85bda65c4eed25d3592d52c4b0bfaad0a3068226a1431")
FIGS1_CANONICAL_SHA = (
    "d125a87d0f3a875a737a9175c43f133f9d353adf95bc307e4c3885731d38e634")
FINAL_MANUSCRIPT_SHA = (
    "9e140b9ea8927ae3b69c4e50afb8301006e8802dcf3e601f1c80c511ca3ca2e3")
FINAL_SUPPLEMENT_SHA = (
    "fdd41f686e082f83c14816da21b121345259e1baea700275db8fab04b122f1ec")
COMBINED_EXACT = "204.5440673062212"
COMBINED_MIN = "29.20696324951644"
COMBINED_AVG = "75.33710405670476"

RETIRED_STAGING_TOKEN = "ALIGNMENT_V1_0_1_2026" + "0804"  # split so this
# guard module never matches its own source when scanning the tree.

HISTORICAL_MARKERS = (
    "superseded", "historical", "historically", "pre-release",
    "never published", "never-public", "never public",
)

ACTIVE_DOC_GLOBS = (
    "README.md", "CHANGELOG.md", "CONTRIBUTING.md", "CITATION.cff",
    ".zenodo.json", "docs/*.md", "docs/*.csv", "docs/*.json",
    "assets/frozen_figures/README.md", "assets/manuscript_final/README.md",
    "provenance/legacy/figure09/README.md",
)


def _active_docs():
    files = []
    for pattern in ACTIVE_DOC_GLOBS:
        files.extend(sorted(ROOT.glob(pattern)))
    assert files, "active documentation set resolved to nothing"
    return files


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _csv_rows(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _line_is_historical(line: str) -> bool:
    low = line.lower()
    return any(marker in low for marker in HISTORICAL_MARKERS)


# --- Figure A producer -------------------------------------------------------

def test_figureA_producer_carries_exact_combined_account():
    src = _read(ROOT / "scripts" / "figures" / "figA1" /
                "make_figA1_sigma_matrices.py")
    assert COMBINED_EXACT in src, (
        "Figure A producer must document the exact combined score "
        f"{COMBINED_EXACT}")
    assert COMBINED_MIN in src and COMBINED_AVG in src, (
        "Figure A producer must document the exact Min/Average components "
        "of the combined score")


def test_figureA_producer_has_no_false_209_claim():
    src = _read(ROOT / "scripts" / "figures" / "figA1" /
                "make_figA1_sigma_matrices.py")
    assert "33+100+76" not in src.replace(" ", ""), (
        "the false pre-release account '33+100+76 = 209' must not reappear")
    assert re.search(r"=\s*209\b", src) is None, (
        "the false combined-score value 209 must not reappear")


# --- Table 1 checksums -------------------------------------------------------

def test_superseded_table1_hash_only_in_labelled_history():
    for doc in _active_docs():
        for lineno, line in enumerate(_read(doc).splitlines(), start=1):
            if TABLE1_SUPERSEDED_SHA_PREFIX in line:
                assert _line_is_historical(line), (
                    f"{doc.relative_to(ROOT)}:{lineno}: superseded Table 1 "
                    "checksum appears without an explicit superseded/"
                    "historical label")


def test_active_table1_checksum_is_canonical():
    matrix = _read(ROOT / "docs" / "REPRODUCIBILITY_MATRIX.csv")
    table1_rows = [ln for ln in matrix.splitlines()
                   if "Table_Compound_Heatwave_Typologies_global_max.csv"
                   in ln and "EXECUTED-PASS" in ln]
    assert table1_rows, "no active Table 1 row found in the matrix"
    assert any(TABLE1_CANONICAL_SHA in ln for ln in table1_rows), (
        "the active Table 1 row must carry the canonical checksum "
        f"{TABLE1_CANONICAL_SHA}")
    prov = _read(ROOT / "docs" / "TABLE_PROVENANCE.csv")
    assert TABLE1_CANONICAL_SHA in prov


def _find_deposit_table01():
    candidates = []
    env = os.environ.get("SCORCH_DATA_DIR")
    if env:
        candidates.append(Path(env))
    for parent in Path(__file__).resolve().parents:
        candidates.append(parent / "scorch_data")
    for root in candidates:
        if not root.exists():
            continue
        for cand in [root] + [p for p in sorted(root.glob("*"))
                              if p.is_dir()]:
            t = (cand / "figure_table_source_data" / "table01" /
                 "Table_Compound_Heatwave_Typologies_global_max.csv")
            if t.exists():
                return t
    return None


def test_deposit_table1_file_hashes_to_canonical():
    t = _find_deposit_table01()
    if t is None:
        pytest.skip("processed-data deposit not available "
                    "(set SCORCH_DATA_DIR to enable)")
    assert _sha256(t) == TABLE1_CANONICAL_SHA, (
        "the deposit staging Table 1 file no longer hashes to the "
        "canonical checksum - the deposit copy is stale or modified")


# --- defective Figure 9 lifecycle wording ------------------------------------

def test_defective_figure9_never_described_as_published():
    forbidden = (
        re.compile(r"published\s+figure\s*9", re.IGNORECASE),
        re.compile(r"figure\s*9[^.\n]{0,80}\bas\s+published\b",
                   re.IGNORECASE),
        re.compile(r"\bwas\s+published\s+at\s+-?21\.10", re.IGNORECASE),
    )
    for doc in _active_docs():
        text = _read(doc)
        for pat in forbidden:
            m = pat.search(text)
            assert m is None, (
                f"{doc.relative_to(ROOT)}: defective Figure 9 described as "
                f"published: {m.group(0)!r}")


# --- retired staging paths ---------------------------------------------------

def test_no_retired_alignment_staging_paths():
    this_file = Path(__file__).resolve()
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        if "__pycache__" in path.parts or ".pytest_cache" in path.parts:
            continue
        if path.resolve() == this_file:
            continue
        if path.suffix.lower() in (".png", ".pdf", ".nc", ".npz", ".xlsx",
                                   ".pyc"):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert RETIRED_STAGING_TOKEN not in text, (
            f"{path.relative_to(ROOT)}: references the retired "
            "ALIGNMENT_V1_0_1 staging tree")


# --- V12 only as history -----------------------------------------------------

def test_v12_appears_only_as_historical_label():
    for doc in _active_docs():
        for lineno, line in enumerate(_read(doc).splitlines(), start=1):
            # "V12-as-current" names the PROHIBITION itself (guard/changelog
            # descriptions), not a claim that V12 is current.
            scrubbed = line.replace("V12-as-current", "")
            if re.search(r"\bV12\b", scrubbed):
                assert _line_is_historical(scrubbed), (
                    f"{doc.relative_to(ROOT)}:{lineno}: 'V12' appears "
                    "without an explicit historical/pre-release label; the "
                    "current public identity is SCORCH v1.0.0")


# --- version fields ----------------------------------------------------------

def test_all_version_fields_are_1_0_0():
    pyproject = _read(ROOT / "pyproject.toml")
    m = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    assert m and m.group(1) == "1.0.0", "pyproject.toml version != 1.0.0"

    zen = json.loads(_read(ROOT / ".zenodo.json"))
    assert zen["version"] == "1.0.0", ".zenodo.json version != 1.0.0"

    cff = _read(ROOT / "CITATION.cff")
    m = re.search(r"^version:\s*(\S+)", cff, re.MULTILINE)
    assert m and m.group(1) == "1.0.0", "CITATION.cff version != 1.0.0"

    init = _read(ROOT / "src" / "scorch" / "__init__.py")
    m = re.search(r'^__version__\s*=\s*"([^"]+)"', init, re.MULTILINE)
    assert m and m.group(1) == "1.0.0", "scorch.__version__ != 1.0.0"


# --- contract paths must exist ----------------------------------------------

_EXTERNAL_LABELS = ("research repository", "research tree", "external",
                    "not shipped", "research working tree")
_PATH_PREFIXES = ("scripts/", "docs/", "assets/", "src/", "tests/",
                  "configs/", "environment/", "provenance/")
# "provenance" is matched with a lookbehind-free alternation; the archive
# member prefix "provenance_evidence/..." matches only its leading
# "provenance" token, which resolves to the real provenance/ directory.
_PATH_RE = re.compile(
    r"(?:scripts|docs|assets|src|tests|configs|environment|"
    r"provenance)(?:/[\w.\-]+)*")


def _iter_json_strings(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _iter_json_strings(key)
            yield from _iter_json_strings(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_json_strings(item)
    elif isinstance(node, str):
        yield node


def test_science_contract_paths_exist():
    contract = json.loads(_read(ROOT / "docs" / "CANONICAL_SCIENCE.json"))
    missing = []
    for text in _iter_json_strings(contract):
        if not any(p in text for p in _PATH_PREFIXES):
            continue
        low = text.lower()
        if any(label in low for label in _EXTERNAL_LABELS):
            continue
        for match in _PATH_RE.finditer(text):
            token = match.group(0).rstrip(" .,;:*").rstrip("/")
            if not (ROOT / token).exists():
                missing.append(token)
    assert not missing, (
        "docs/CANONICAL_SCIENCE.json references paths that do not exist in "
        f"the release tree (label external paths explicitly): {missing}")


def test_key_active_paths_exist():
    # The two legacy Figure 9 rasters are deliberately absent: they were
    # relocated into the LOCAL, UNPUBLISHED processed-data archive candidate
    # (not a deposit - nothing has been uploaded or published; saying
    # "deposit" here is the very claim FORBIDDEN_DEPOSIT_CLAIM rejects in
    # tests/test_public_consistency_guards.py). Their identities are verified
    # against the relocation manifest and the archive crosswalk by
    # test_relocated_legacy_figure9_rasters_are_accounted_for below, not by an
    # existence assertion here.
    for rel in (
        "provenance/legacy/figure09/README.md",
        "scripts/figures/common/scorch_axial.py",
        "scripts/figures/common/ellipse_pca.py",
        "scripts/figures/figA1/make_figA1_sigma_matrices.py",
        "scripts/figures/figA1/make_figA1_sigma_sensitivity.py",
        "scripts/figures/figS1/make_figS1_station_panels.py",
        "scripts/figures/figS1/make_figS1_station_strip.py",
        "docs/CANONICAL_SCIENCE.json",
        "docs/ALIGNMENT_DECISIONS.md",
    ):
        assert (ROOT / rel).exists(), f"active release path missing: {rel}"


# Keys are the rasters' HISTORICAL pre-relocation repository paths, exactly as
# the crosswalk's old_repository_path column records them; values name
# immutable archive members. Neither may be rewritten to the current
# provenance/legacy/figure09/ layout: the rasters never lived there.
LEGACY_FIG9_RASTERS = {
    "legacy_defective_figure09/"
    "Figure9_assembled_LEGACY_ARITHMETIC_DEFECTIVE.png": (
        "provenance_evidence/legacy_defective_figure09/"
        "Figure9_assembled_LEGACY_ARITHMETIC_DEFECTIVE.png",
        "4cb3b38a5d80db8b2a936ed9ddf8246e2007609cd9c6ae1e6984256f1d1ffa04",
        944684),
    "legacy_defective_figure09/Figure_09_LEGACY_ARITHMETIC_DEFECTIVE.png": (
        "provenance_evidence/legacy_defective_figure09/"
        "Figure_09_LEGACY_ARITHMETIC_DEFECTIVE.png",
        "b023c6e55359b69d74dd1b93f7199c2f82f12d782cd76f3de5170a8f36460ad1",
        274118),
}


def test_relocated_legacy_figure9_rasters_are_accounted_for():
    """The defective rasters left the tree; they must still be pinned.

    Replaces the former existence assertions. Absence is only legal when the
    relocation crosswalk names the exact archive member and pins its hash and
    byte count, and the surviving pointer README carries both the reserved DOI
    and the exact member paths.
    """
    rows = {r["old_repository_path"]: r
            for r in _csv_rows(ROOT / "docs" / "RELOCATED_ARTIFACTS.csv")}
    readme = _read(ROOT / "provenance" / "legacy" / "figure09" / "README.md")
    assert "10.5281/zenodo.21717752" in readme, (
        "the pointer README must carry the reserved data DOI")
    assert "scorch_processed_data_v1.0.0.zip" in readme

    for rel, (member, sha, nbytes) in LEGACY_FIG9_RASTERS.items():
        assert not (ROOT / rel).exists(), (
            f"{rel} is relocated; it must not be back in the tree")
        row = rows.get(rel)
        assert row is not None, f"{rel} missing from the relocation crosswalk"
        assert row["state"] == "relocated"
        assert row["archive_member_path"] == member, (
            f"{rel}: crosswalk names member {row['archive_member_path']!r}")
        assert row["member_sha256"] == sha, f"{rel}: member hash changed"
        assert int(row["member_bytes"]) == nbytes, f"{rel}: member size changed"
        # binary PNG: both byte identities are the same bytes
        assert row["repository_sha256"] == sha
        assert row["historical_byte_identity_sha256"] == sha
        assert len(row["archive_sha256"]) == 64
        assert sha in readme, f"{rel}: hash absent from the pointer README"
        assert member in readme, f"{rel}: member path absent from the README"


# --- frequency inference must stay removed -----------------------------------

def test_no_frequency_trend_inference_reappears():
    producers = (
        ROOT / "scripts" / "pipeline" / "make_global_max_tables.py",
        ROOT / "scripts" / "figures" / "fig10" /
        "Figure_9_Trend_Analysis_With_Table_statistics.py",
    )
    forbidden = re.compile(
        r"\bsen_f\b|\bp_f\b|\bsen_freq\b|\bmk_p_freq\b|"
        r"frequency_sen|frequency_mk", re.IGNORECASE)
    for producer in producers:
        src = _read(producer)
        m = forbidden.search(src)
        assert m is None, (
            f"{producer.relative_to(ROOT)}: frequency trend-inference "
            f"token {m.group(0)!r} reappeared; annual event counts are "
            "descriptive only")


# --- pinned corrected assets -------------------------------------------------

def test_corrected_figure9_embed_hash_pinned():
    asset = ROOT / "assets" / "manuscript_final" / "Figure_09.png"
    assert _sha256(asset) == FIG9_EMBED_SHA, (
        "assets/manuscript_final/Figure_09.png no longer matches the "
        "corrected Figure 9 manuscript embed hash")
    sums = _read(ROOT / "assets" / "manuscript_final" / "SHA256SUMS")
    assert FIG9_EMBED_SHA in sums


def test_canonical_figure_s1_hash_pinned_in_provenance():
    for doc in ("docs/FIGURE_PROVENANCE.csv", "docs/CANONICAL_SCIENCE.json",
                "docs/REPRODUCIBILITY_MATRIX.csv"):
        assert FIGS1_CANONICAL_SHA in _read(ROOT / doc), (
            f"{doc}: canonical Figure S.1 hash missing")


def _find_final_docx(name):
    env = os.environ.get("SCORCH_FINAL_DOCX_DIR")
    if env and (Path(env) / name).exists():
        return Path(env) / name
    for parent in Path(__file__).resolve().parents:
        cand = parent / name
        if cand.exists():
            return cand
    return None


@pytest.mark.parametrize("name,expected", [
    ("SCORCH_Manuscript_FINAL_v1.0.0.docx", FINAL_MANUSCRIPT_SHA),
    ("SCORCH_Supplementary_Material_FINAL_v1.0.0.docx",
     FINAL_SUPPLEMENT_SHA),
])
def test_final_docx_hash_unchanged(name, expected):
    path = _find_final_docx(name)
    if path is None:
        pytest.skip(f"{name} not present in this checkout "
                    "(set SCORCH_FINAL_DOCX_DIR to enable)")
    assert _sha256(path) == expected, (
        f"{name} hash changed - the frozen FINAL document was modified")


# --- R3: structural integrity of shipped machine-readable files -------------

_SHIPPED_CSV_GLOBS = (
    "docs/*.csv",
    "scripts/figures/figA1_inputs/*.csv",
    "scripts/figures/figA2_inputs/*.csv",
    "tests/fixtures/*.csv",
    "data/auxiliary/method_a/*.csv",
)


def _shipped_csvs():
    files = []
    for pattern in _SHIPPED_CSV_GLOBS:
        files.extend(sorted(ROOT.glob(pattern)))
    assert files, "shipped CSV set resolved to nothing"
    return files


def test_shipped_csvs_strictly_rectangular():
    import csv as _csv
    for path in _shipped_csvs():
        with open(path, newline="", encoding="utf-8") as fh:
            rows = [r for r in _csv.reader(fh) if r]
        width = len(rows[0])
        for lineno, row in enumerate(rows[1:], start=2):
            assert len(row) == width, (
                f"{path.relative_to(ROOT)}:{lineno}: {len(row)} fields, "
                f"header has {width} - malformed CSV row")
        # no csv.DictReader overflow under a None key, no comment rows
        with open(path, newline="", encoding="utf-8") as fh:
            for rec in _csv.DictReader(fh):
                assert None not in rec, (
                    f"{path.relative_to(ROOT)}: DictReader overflow "
                    "(row wider than header)")
        first_cells = [r[0] for r in rows[1:] if r]
        assert not any(c.startswith("#") for c in first_cells), (
            f"{path.relative_to(ROOT)}: comment-style row in a CSV")


def test_all_shipped_json_files_parse():
    for path in sorted(ROOT.glob("docs/*.json")) + [ROOT / ".zenodo.json"]:
        json.loads(_read(path))  # raises on malformed JSON


def test_citation_cff_parses_as_yaml():
    yaml = pytest.importorskip("yaml")
    doc = yaml.safe_load(_read(ROOT / "CITATION.cff"))
    assert doc["cff-version"] == "1.2.0"
    assert doc["version"] == "1.0.0"
    assert doc["type"] == "software"


# --- R3: Table 1 publication-output provenance consistency ------------------

def test_publication_builder_table1_prose_consistent():
    src = _read(ROOT / "scripts" / "publication" /
                "build_publication_outputs.py")
    # the constants must declare a zero-difference (identity) mapping
    m = re.search(r"TABLE1_COLUMN_MAP\s*=\s*\(([^)]*)\)", src)
    assert m, "TABLE1_COLUMN_MAP not found"
    mapping = tuple(int(x) for x in m.group(1).split(",") if x.strip())
    identity = mapping == tuple(range(len(mapping)))
    renames_empty = (re.search(r"TABLE1_HEADER_RENAMES\s*=\s*\{\}", src)
                     is not None and
                     re.search(r"TABLE1_ROW_LABEL_RENAMES\s*=\s*\{\}", src)
                     is not None)
    if identity and renames_empty:
        assert "NOT a facsimile" not in src, (
            "generated prose claims the shipped table is not a facsimile "
            "while the declared mapping shows zero differences")
        assert "Table 1 presentation differences = 0." in src, (
            "zero-difference state must be stated explicitly in the "
            "generated provenance prose")
        assert "uses its own column order" not in src, (
            "obsolete different-column-order claim survives although the "
            "declared mapping is the identity")
    # manuscript (not 'published') terminology for the declared constants
    assert "TABLE1_MANUSCRIPT_HEADER" in src
    assert "TABLE1_PUBLISHED_HEADER" not in src


# --- R3: no S.1 producer contradiction ---------------------------------------

# The first version of this guard searched each LINE for the literal string
# "no runnable producer". Three things were wrong with that:
#
#   1. It pinned the guard to one phrasing. The 2026-08 correction round
#      removed that exact sentence from the generated publication text (and
#      tests/test_publication_builder_contracts.py now forbids it there), so
#      the literal is on its way out of the tree entirely. Any reworded claim
#      - "lacks a producer", "producerless", "not reproducible from code" -
#      walked straight past it.
#   2. It was line-scoped, so a hard wrap between the figure reference and the
#      claim defeated it. That was not hypothetical: in
#      assets/frozen_figures/README.md the claim sits on a line carrying
#      neither "s.1" nor "station", so the old guard skipped the one place in
#      the tree where the sentence still appears.
#   3. With no match anywhere it asserted nothing and still went green.
#
# The replacement asserts the STRUCTURED truth first - S.1 has runnable
# producers and the identity CSV classifies it accordingly - and only then
# sweeps the prose, whole-document-normalized, over a family of producerless
# phrasings, requiring a superseded/fallback label. Coverage is asserted, so
# an inspection that matched nothing is a failure rather than a pass.

_PRODUCERLESS_RX = re.compile(
    r"no runnable producer|had no producer|lacks? a(?: runnable)? producer|"
    r"producerless|without a(?: runnable)? producer|"
    r"no(?:t)? reproducible from code|no code[ -]native producer|"
    r"cannot be regenerated", re.I)

# "S.1" survives normalization as "s.1"; "s 1" covers a hyphen/space variant.
_S1_REF_RX = re.compile(r"s\.? ?1\b|station", re.I)

_S1_FALLBACK_MARKERS = (
    "fallback", "supersed", "historical", "legacy", "donor", "hand-drawn",
    "pre-correction", "provisional", "figures 1 and 4", "fig. 1",
)

_S1_PRODUCERS = (
    "scripts/figures/figS1/make_figS1_station_panels.py",
    "scripts/figures/figS1/make_figS1_station_strip.py",
    "scripts/figures/figS1/make_new_figS1_candidate.py",
)


def test_canonical_s1_has_runnable_producers_of_record():
    """The structured truth the prose guard exists to protect."""
    for rel in _S1_PRODUCERS:
        assert (ROOT / rel).is_file(), (
            f"{rel} is missing; the canonical Fig. S.1 is declared "
            f"data_generated, which requires its producers to be present")
    rows = {r["label"].strip(): r
            for r in _csv_rows(ROOT / "docs" /
                               "MANUSCRIPT_FIGURE_IDENTITY.csv")}
    s1 = rows["Fig. S.1."]
    assert s1["reproduction_class"] == "data_generated", (
        "Fig. S.1 is no longer classified data_generated; the canonical "
        "station panels are regenerated from deposited GHCN-Daily and ERA5 "
        "series, not transcribed from the frozen donor drawing")
    # shipped_asset is legitimately empty for S.1 (the reproduced output IS
    # the manuscript embed), so the producer evidence is the render hash.
    assert re.fullmatch(r"[0-9a-f]{64}", s1["script_render_sha256"]), (
        "Fig. S.1 carries no script_render_sha256; a data_generated figure "
        "must have a recorded producer render")
    assert s1["script_render_sha256"] == FIGS1_CANONICAL_SHA, (
        "Fig. S.1's producer render no longer matches the pinned canonical "
        "composite")


# The subject and the claim routinely sit in ADJACENT sentences - "...the
# superseded provisional station comparison drawing... It was transcribed from
# approved slide artwork and had no runnable producer." - so a sentence-scoped
# association finds nothing. The claim is therefore judged on a character
# window around the match, which is what a reader actually takes in.
_S1_CONTEXT_CHARS = 320


def test_canonical_s1_never_described_as_producerless():
    inspected = 0
    problems = []
    for doc in _active_docs():
        flat = _normalize_lifecycle(_read(doc))
        for m in _PRODUCERLESS_RX.finditer(flat):
            lo = max(0, m.start() - _S1_CONTEXT_CHARS)
            window = flat[lo:m.end() + _S1_CONTEXT_CHARS]
            if not _S1_REF_RX.search(window):
                continue
            inspected += 1
            if not any(mark in window for mark in _S1_FALLBACK_MARKERS):
                problems.append(
                    f"{doc.relative_to(ROOT)}: {window.strip()[:180]}")
    assert not problems, (
        "an active record claims S.1/station material lacks a producer "
        "without labelling it as the superseded donor fallback; the canonical "
        "S.1 station panels ARE regenerated by shipped producers: "
        + " ;; ".join(problems))
    assert inspected, (
        "this guard inspected ZERO sentences. The superseded station-donor "
        "drawing is still described in assets/frozen_figures/README.md, so a "
        "producerless claim about station material should have been found and "
        "checked for its fallback label. Zero matches means the phrasing "
        "moved outside _PRODUCERLESS_RX / _S1_REF_RX and the guard has gone "
        "blind - extend the pattern rather than deleting the assertion")


# --- R4: hardened lifecycle-language guard -----------------------------------
# R3 checked literal lowercase substrings line-by-line, which a line break,
# a Unicode hyphen, or shortened wording could evade (the R3 miss of
# "accepted\nmanuscript" in assets/manuscript_final/README.md was exactly
# such an evasion). R4 normalizes each whole file first - all Unicode
# hyphen/dash forms to ASCII "-", all whitespace runs (including newlines)
# to a single space, lowercased - and then applies regexes in which spaces
# and hyphens are interchangeable separators. Legitimate provider,
# bibliographic, historical, and future-conditional wording is still
# permitted via an explicit context allowance around each match.

_UNICODE_HYPHENS = (
    "­‐‑‒–—―−﹘﹣－")


def _normalize_lifecycle(text: str) -> str:
    for ch in _UNICODE_HYPHENS:
        text = text.replace(ch, "-")
    return re.sub(r"\s+", " ", text).lower()


# space/hyphen interchangeable separator (post-normalization)
_SEP = r"[ -]+"
# negations that make "published"/"accepted" truthful in context
_NEG = r"(?<!never )(?<!never-)(?<!not )(?<!un)(?<!non-)"

_FORBIDDEN_LIFECYCLE_RES = tuple(re.compile(p) for p in (
    # -- the four R1-R4 residue families, evasion-hardened ------------------
    _NEG + r"\bpublished" + _SEP + r"s\.? ?1" + _SEP + r"composite",
    _NEG + r"\bpublished" + _SEP + r"(figure|fig\.?)" + _SEP + r"s\.? ?1\b",
    _NEG + r"\bpublished" + _SEP + r"catalog(ue)?s?\b",
    r"\bthe" + _SEP + r"published" + _SEP + r"(figure|fig\.?)" + _SEP
    + r"d\b",
    _NEG + r"\baccepted" + _SEP + r"(manuscript|ms\b|paper|version)",
    # -- the R3 literal families, now normalization-proof -------------------
    _NEG + r"\bpublished" + _SEP + r"pipeline",
    _NEG + r"\bpublished" + _SEP + r"as" + _SEP + r"\*{0,2}fig",
    r"\bthe" + _SEP + r"published" + _SEP + r"values",
    _NEG + r"\bpublished" + _SEP + r"table" + _SEP + r"1\b",
    _NEG + r"\bpublished" + _SEP + r"master" + _SEP + r"schema",
    _NEG + r"\bpublished" + _SEP + r"partition",
))

# markers that make a match legitimate (provider/bibliographic/historical/
# future-conditional wording); checked in a window around the match
_ALLOWED_CONTEXT = (
    "superseded", "historical", "historically", "pre-release", "legacy",
    "never published", "never-published", "not published",
    "not yet published",
    "copernicus", "ecmwf", "noaa", "ncei", "ghcn", "era5",
    "will be published", "will become published", "once published",
    "when published", "upon publication", "upon acceptance", "if accepted",
    "once accepted", "when accepted", "after acceptance",
)

_CTX_BEFORE = 90
_CTX_AFTER = 45


def _lifecycle_violations(text: str):
    """Return forbidden lifecycle phrases found in *text* (normalized)."""
    norm = _normalize_lifecycle(text)
    hits = []
    for pat in _FORBIDDEN_LIFECYCLE_RES:
        for m in pat.finditer(norm):
            ctx = norm[max(0, m.start() - _CTX_BEFORE):m.end() + _CTX_AFTER]
            if any(marker in ctx for marker in _ALLOWED_CONTEXT):
                continue
            hits.append(m.group(0))
    return hits


def test_no_false_lifecycle_phrases_in_release_tree():
    this_file = Path(__file__).resolve()
    exts = (".py", ".md", ".csv", ".json", ".cff", ".yaml", ".yml",
            ".toml", ".in", ".txt")
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        if "__pycache__" in path.parts or ".pytest_cache" in path.parts:
            continue
        # release_staging/ is the gitignored LOCAL deposit-staging area (the
        # v1.0.1 corrected data overlay + archives). Deposit payload docs
        # carry their own approved wording and were always outside the
        # release source tree this guard scopes (the v1.0.0 deposit lived in
        # an external directory); they are validated by validate_deposit.py.
        if "release_staging" in path.parts:
            continue
        if path.resolve() == this_file:
            continue
        if path.suffix.lower() not in exts and path.name != "Makefile":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        violations = _lifecycle_violations(text)
        assert not violations, (
            f"{path.relative_to(ROOT)}: false lifecycle phrase(s) "
            f"{violations!r} - the project is pre-publication; use "
            "manuscript/canonical/publication-output wording")


# --- R4: regression fixtures proving the guard cannot be evaded --------------

_EVASIVE_VARIANTS = (
    # the exact residues R1-R3 chased, plus every evasion channel
    "Published S.1 composite",
    "Published Figure S.1",
    "Published Fig. S.1",
    "Published Fig S1",
    "Published-catalog",
    "published catalog",
    "published catalogue",
    "Published–catalog",            # en dash
    "Published‐catalog",            # Unicode hyphen
    "published\ncatalog",                # line break
    "the published Fig. D",
    "the published Figure D",
    "the published Fig.\nD",             # line break
    "the—published—Fig. D",    # em dashes
    "accepted manuscript",
    "accepted\nmanuscript",              # the R3-missed newline-spanning form
    "accepted \n\t manuscript",          # mixed whitespace
    "accepted‑manuscript",          # non-breaking hyphen
    "accepted ms",                       # shortened wording
    "accepted paper",
    "accepted version",
    "Published S.1\ncomposite",
    "PUBLISHED CATALOG",                 # case
)


@pytest.mark.parametrize("variant", _EVASIVE_VARIANTS)
def test_lifecycle_guard_detects_evasive_variant(variant):
    embedded = f"routing header\nthe {variant} is shipped here\nfooter"
    assert _lifecycle_violations(embedded), (
        f"hardened guard failed to detect evasive variant {variant!r}")


_LEGITIMATE_VARIANTS = (
    # provider wording
    "ERA5 data are published by the Copernicus Climate Change Service",
    "GHCN-Daily observations are published by NOAA NCEI",
    # future-conditional wording
    "the software record will be published upon acceptance",
    "once published, the DOI will resolve to the archived release",
    "if accepted, the manuscript will be deposited",
    # historical / superseded wording
    "the superseded pre-release notes described a published catalog",
    "historically the draft called this the published Fig. D layout",
    # truthful negation
    "the defective figure was never published",
    "this catalog was never-published pre-release material",
    # unrelated safe uses
    "the publication_outputs directory is assembled by stage 33",
    "the manuscript embed hash is pinned",
)


@pytest.mark.parametrize("text", _LEGITIMATE_VARIANTS)
def test_lifecycle_guard_allows_legitimate_wording(text):
    assert not _lifecycle_violations(text), (
        f"hardened guard wrongly flags legitimate wording {text!r}")
