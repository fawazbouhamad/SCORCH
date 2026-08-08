"""Guards against stale science re-entering the public-facing surfaces.

The pre-release v1.0.0 remediation replaced the unweighted PCA-origin
locations with raw-Celsius Tmax-weighted centroids. Everything downstream of
*location* changed: the LGCP fit, the cross-validation distances, the sector
counts and the centroid-dependent figures. These tests fail if any superseded
value or any scientifically wrong description reappears in an active record.

Design rules for these guards
-----------------------------
* Figures are identified from the STRUCTURED field (`figure_table` in the
  matrix, `figure` in the provenance table) via an explicit normalized-label
  mapping - never by prose word-boundary matching.
* Coverage is asserted: every expected figure must be matched, and a guard
  that inspects zero rows or zero hashes is a FAILURE, not a pass.
* A cell is never exempted wholesale because it contains the word
  "superseded". Each non-canonical value is classified in its own clause.
* Markdown is classified per sentence, never by a +/- N line context window.
* Canonical figure identity is read from docs/MANUSCRIPT_FIGURE_IDENTITY.csv,
  the single source of truth; it is not duplicated here.
"""
import csv
import hashlib
import json
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _read(rel):
    return (REPO / rel).read_text(encoding="utf-8")


def _rows(rel):
    with open(REPO / rel, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def canonical():
    return json.loads(_read("docs/CANONICAL_SCIENCE.json"))


# ---------------------------------------------------------------------------
# 0. No stray control characters (the 0x08 incident)
# ---------------------------------------------------------------------------
CONTROL_ALLOWED = {0x09, 0x0A, 0x0D}

CONTROL_SCANNED = [
    "tests/test_public_consistency_guards.py",
    "tests/test_readme_license_citation.py",
    "src/scorch/pipeline.py",
    "src/scorch/_kernel/tmax_weighted_centroid.py",
    "scripts/figures/common/tmax_weighted_centroid.py",
    "scripts/pipeline/build_event_global_max_master.py",
    "scripts/figures/fig01/restore_fig01_original_threshold.py",
    "docs/REPRODUCIBILITY_MATRIX.csv",
    "docs/FIGURE_PROVENANCE.csv",
    "docs/MANUSCRIPT_FIGURE_IDENTITY.csv",
    "docs/CANONICAL_SCIENCE.json",
    "docs/REPRODUCIBILITY_REPORT.md",
    "README.md",
    "CHANGELOG.md",
]


@pytest.mark.parametrize("rel", CONTROL_SCANNED)
def test_no_unexpected_control_characters(rel):
    """A literal 0x08 once made a regex word boundary unmatchable, silently
    turning a crosswalk guard into a no-op. Never again."""
    data = (REPO / rel).read_bytes()
    bad = sorted({b for b in data if b < 0x20 and b not in CONTROL_ALLOWED})
    assert not bad, (
        f"{rel} contains control bytes "
        + ", ".join(hex(b) for b in bad)
        + " (only TAB/LF/CR permitted)")


# ---------------------------------------------------------------------------
# 1. Canonical figure identity - single source of truth
# ---------------------------------------------------------------------------
def _identity():
    return {r["label"].strip(): r
            for r in _rows("docs/MANUSCRIPT_FIGURE_IDENTITY.csv")}


MATRIX_FIGURE_MAP = {
    "Fig 1": ["Fig. 1."],
    "Fig 3": ["Fig. 3."],
    "Fig 4": ["Fig. 4."],
    "Figs 5 and 7": ["Fig. 5.", "Fig. 7."],
    "Fig 6": ["Fig. 6."],
    "Fig 12": ["Fig. 12."],
    "Fig D": ["Fig. D."],
    "Fig S.1": ["Fig. S.1."],
}
PROVENANCE_FIGURE_MAP = {
    "Figure 1": ["Fig. 1."],
    "Figure 3": ["Fig. 3."],
    "Figure 4": ["Fig. 4."],
    "Figure 5": ["Fig. 5."],
    "Figure 6": ["Fig. 6."],
    "Figure 7": ["Fig. 7."],
    "Figure 12": ["Fig. 12."],
    "Figure D": ["Fig. D."],
    "Figure S.1": ["Fig. S.1."],
}
EXPECTED_LABELS = {"Fig. 1.", "Fig. 3.", "Fig. 4.", "Fig. 5.", "Fig. 6.",
                   "Fig. 7.", "Fig. 12.", "Fig. D.", "Fig. S.1."}

HASH_RX = re.compile(r"[0-9a-f]{64}")
CLAUSE_SPLIT = re.compile(r"[;()]|,\s")
HIST_CLAUSE = re.compile(
    r"histor|supersed|pre-remediat|legacy|earlier|previous|deprecat|"
    r"approved.original|prior|formerly|not current|no longer|pre-correction|"
    r"pre-label|pre-rearrangement|then-deployed", re.I)
HIST_FIELD = re.compile(r"original|historical|supersed|legacy|prior", re.I)


@pytest.mark.parametrize("rel", ["docs/REPRODUCIBILITY_MATRIX.csv",
                                 "docs/FIGURE_PROVENANCE.csv",
                                 "docs/MANUSCRIPT_FIGURE_IDENTITY.csv",
                                 "docs/TABLE_PROVENANCE.csv"])
def test_csv_rows_are_well_formed(rel):
    """Every row must have exactly the header's field count.

    An unquoted comma introduced by a careless text-level edit silently shifts
    every column to the right - `figure_table` ends up holding prose and
    `checksum` holding a tolerance word - while the file still 'parses'.
    """
    with open(REPO / rel, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    n = len(rows[0])
    bad = [(i, len(r)) for i, r in enumerate(rows[1:], 2) if len(r) != n]
    assert not bad, (
        f"{rel} has rows whose field count differs from the header ({n}): "
        + ", ".join(f"row {i} has {k}" for i, k in bad))


def test_figure_mappings_are_unique_and_complete():
    ident = _identity()
    for name, mapping in (("matrix", MATRIX_FIGURE_MAP),
                          ("provenance", PROVENANCE_FIGURE_MAP)):
        flat = [lab for labs in mapping.values() for lab in labs]
        assert len(flat) == len(set(flat)), f"{name} map has duplicate labels"
        assert set(flat) == EXPECTED_LABELS, (
            f"{name} map does not cover exactly the expected figures; "
            f"missing={EXPECTED_LABELS - set(flat)} "
            f"extra={set(flat) - EXPECTED_LABELS}")
        for lab in flat:
            assert lab in ident, f"{lab} absent from MANUSCRIPT_FIGURE_IDENTITY.csv"


def _crosswalk(rel, structured_field, mapping, current_fields):
    ident = _identity()
    matched, checked, problems = set(), 0, []
    for i, row in enumerate(_rows(rel), 2):
        key = (row.get(structured_field) or "").strip()
        labels = mapping.get(key)
        if not labels:
            continue
        matched.update(labels)
        canon = {ident[lab]["manuscript_final_sha256"] for lab in labels}
        for fld in current_fields:
            val = row.get(fld) or ""
            if not val or HIST_FIELD.search(fld):
                continue
            for clause in CLAUSE_SPLIT.split(val):
                for h in HASH_RX.findall(clause):
                    checked += 1
                    if h in canon or HIST_CLAUSE.search(clause):
                        continue
                    problems.append(
                        f"{rel} row {i} [{key}] field {fld}: {h[:16]}... is not "
                        f"canonical and its clause is not marked historical")
        joined = " ".join((row.get(f) or "") for f in current_fields)
        if HASH_RX.search(joined):
            for lab in labels:
                want = ident[lab]["manuscript_final_sha256"]
                if want not in joined:
                    problems.append(
                        f"{rel} row {i} [{key}]: canonical hash for {lab} "
                        f"({want[:16]}...) absent from the current fields")
    return matched, checked, problems


def test_matrix_figure_crosswalk():
    matched, checked, problems = _crosswalk(
        "docs/REPRODUCIBILITY_MATRIX.csv", "figure_table", MATRIX_FIGURE_MAP,
        ["canonical_expected", "reproduced_value", "checksum"])
    assert matched == EXPECTED_LABELS, (
        f"matrix crosswalk missed {EXPECTED_LABELS - matched}")
    assert checked > 0, "matrix crosswalk inspected ZERO hashes (vacuous guard)"
    assert not problems, "matrix crosswalk problems: " + " ;; ".join(problems)


def test_provenance_figure_crosswalk():
    matched, checked, problems = _crosswalk(
        "docs/FIGURE_PROVENANCE.csv", "figure", PROVENANCE_FIGURE_MAP,
        ["deployed_embed_sha256", "reproduced_output_sha256",
         "reproduction_result"])
    assert matched == EXPECTED_LABELS, (
        f"provenance crosswalk missed {EXPECTED_LABELS - matched}")
    assert checked > 0, "provenance crosswalk inspected ZERO hashes (vacuous guard)"
    assert not problems, "provenance crosswalk problems: " + " ;; ".join(problems)


def test_figure_1_and_4_declared_deterministic():
    ident = _identity()
    for lab in ("Fig. 1.", "Fig. 4."):
        assert ident[lab]["reproduction_class"] == "deterministic_producer"


# ---------------------------------------------------------------------------
# 2. Weighted results authoritative under the NORMAL keys
# ---------------------------------------------------------------------------
def test_lgcp_key_holds_the_weighted_fit(canonical):
    p = canonical["lgcp"]["parameters"]
    assert p["intercept"] == pytest.approx(-11.457776, abs=1e-6)
    assert p["lon"] == pytest.approx(-0.016147, abs=1e-6)
    assert p["lat"] == pytest.approx(0.066264, abs=1e-6)
    assert p["mean_tmax_z"] == pytest.approx(0.546415, abs=1e-6)
    assert p["std_tmax_z"] == pytest.approx(-0.010951, abs=1e-6)
    assert p["sigma2"] == pytest.approx(1.642911, abs=1e-6)
    assert p["scale_km"] == pytest.approx(272.455153, abs=1e-6)
    assert canonical["lgcp"]["intensity_ratio"] == pytest.approx(21.8254, abs=1e-4)


def test_cross_validation_key_holds_the_weighted_results(canonical):
    cv = canonical["cross_validation"]
    assert cv["pooled_hit_top20"] == pytest.approx(0.344737, abs=1e-6)
    assert cv["mean_dist_top20_km"] == pytest.approx(231.808, abs=1e-3)
    assert cv["median_dist_top20_km"] == pytest.approx(134.919, abs=1e-3)
    z = cv["mean_distance_by_zone_km"]
    assert z["top10"] == pytest.approx(389.670139, abs=1e-6)
    assert z["top20"] == pytest.approx(231.807728, abs=1e-6)
    assert z["top30"] == pytest.approx(151.672110, abs=1e-6)
    assert z["top50"] == pytest.approx(69.064508, abs=1e-6)


def test_superseded_fit_is_quarantined_as_historical(canonical):
    legacy = canonical["legacy_unweighted_baseline"]
    assert "HISTORICAL" in legacy["status"].upper()
    assert legacy["lgcp"]["parameters"]["intercept"] == pytest.approx(
        -11.352611, abs=1e-6)
    assert "lgcp_tmax_weighted" not in canonical
    assert "cross_validation_tmax_weighted" not in canonical


def test_sector_counts_are_the_weighted_ones(canonical):
    w = canonical["sector_counts_38_48E_29_37N"]["tmax_weighted"]
    assert w["structures"] == "154/760"
    assert w["daily_largest"] == "153/395"
    assert w["event_largest"] == "19/51"


# ---------------------------------------------------------------------------
# 3. README describes the heatwave definition correctly
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def readme_flat():
    return " ".join(_read("README.md").split()).lower()


@pytest.mark.parametrize("wrong", [
    "calendar-day 95th percentile", "calendar-day 95th-percentile",
    "per-calendar-day", "three consecutive exceedance days",
    "dbscan over the exceeding boxes", "dbscan groups the exceeding boxes",
])
def test_readme_rejects_wrong_heatwave_description(readme_flat, wrong):
    assert wrong not in readme_flat


def test_readme_states_the_correct_definition(readme_flat):
    assert "pooled across" in readme_flat and "1940" in readme_flat
    assert "greater than or equal to" in readme_flat
    assert "two consecutive" in readme_flat and "non-exceedance" in readme_flat
    assert "heatwave-labeled cells" in readme_flat and "bridged" in readme_flat


def test_readme_does_not_let_dbscan_create_events(readme_flat):
    assert ("not any clustering step" in readme_flat
            or "purely temporal" in readme_flat)


# ---------------------------------------------------------------------------
# 4. Reproduction stage + weighting wording
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("cfg", ["configs/reproduction_fast.yaml",
                                 "src/scorch/configs/reproduction_fast.yaml"])
def test_weighted_centroid_stage_present(cfg):
    import yaml
    names = [s["name"] for s in yaml.safe_load(_read(cfg))["stages"]]
    assert "weighted-centroids" in names
    assert names.index("weighted-centroids") > names.index("rebuild-catalog")


@pytest.mark.parametrize("rel", [
    "src/scorch/_kernel/tmax_weighted_centroid.py",
    "scripts/figures/common/tmax_weighted_centroid.py",
    "docs/CANONICAL_SCIENCE.json",
])
def test_no_absolute_temperature_wording(rel):
    t = _read(rel).lower()
    for bad in ('"absolute tmax"', "absolute observed level"):
        assert bad not in t


# ---------------------------------------------------------------------------
# 5. Current-vs-historical sweep, classified per SENTENCE / per CLAUSE
# ---------------------------------------------------------------------------
STALE_TOKENS = {
    "-11.352611": "LGCP intercept (unweighted)",
    "0.464404": "LGCP mean_tmax_z (unweighted)",
    "1.647219": "LGCP sigma2 (unweighted)",
    "287.707960": "LGCP scale (unweighted)",
    "287.70796": "LGCP scale (unweighted)",
    "84.934649": "CV distance (unweighted)",
    "437.854964": "zone top10 (unweighted)",
    "285.656041": "zone top20 (unweighted)",
    "180.807535": "zone top30 (unweighted)",
    "81.475518": "zone top50 (unweighted)",
    "438/286/181/81": "zone tuple (unweighted)",
}

SWEEP_FILES = [
    "docs/REPRODUCIBILITY_MATRIX.csv", "docs/REPRODUCIBILITY_REPORT.md",
    "docs/FIGURE_PROVENANCE.csv", "docs/ALIGNMENT_DECISIONS.md",
    "docs/SANITIZATION_NOTES.md", "CHANGELOG.md", "README.md",
    "remediation/MANUSCRIPT_IMPACT_INVENTORY.md",
]

# A sentence is a sentence regardless of hard wrapping, so the text is
# whitespace-normalized FIRST and only then split on sentence terminators.
# Splitting on raw newlines would tear "The superseded / unweighted fit ..."
# into two units and misclassify the second half as a current claim.
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _sentences(text):
    return SENTENCE_SPLIT.split(" ".join(text.split()))


@pytest.mark.parametrize("rel", SWEEP_FILES)
def test_no_unclassified_superseded_values(rel):
    problems = []
    if rel.endswith(".csv"):
        for i, row in enumerate(_rows(rel), 2):
            for fld, val in row.items():
                if isinstance(val, list):
                    val = " ".join(val)
                if not val or not isinstance(fld, str):
                    continue
                if HIST_FIELD.search(fld):
                    continue
                for clause in CLAUSE_SPLIT.split(val):
                    if HIST_CLAUSE.search(clause):
                        continue
                    for tok, desc in STALE_TOKENS.items():
                        if tok in clause:
                            problems.append(f"row {i} / {fld}: {tok} [{desc}]")
    else:
        for sent in _sentences(_read(rel)):
            if HIST_CLAUSE.search(sent):
                continue
            for tok, desc in STALE_TOKENS.items():
                if tok in sent:
                    problems.append(f"{tok} [{desc}] in: {sent.strip()[:90]}")
    assert not problems, (f"{rel} presents superseded values as current: "
                          + " ;; ".join(problems))


def test_figure12_claim_is_scoped():
    """'Plotted data unchanged' must name the comparison it describes."""
    for rel in ("docs/FIGURE_PROVENANCE.csv", "docs/REPRODUCIBILITY_REPORT.md"):
        flat = " ".join(_read(rel).split())
        if "lotted data" in flat:
            assert ("V3 OPERATION ONLY" in flat or "BY THE V3 STEP" in flat), (
                f"{rel} claims plotted data unchanged without naming the "
                f"comparison")


# ---------------------------------------------------------------------------
# 6. Test-count consistency against ONE authoritative value
# ---------------------------------------------------------------------------
COUNT_RX = re.compile(r"(\d{2,4})\s+passed")


def _authoritative_counts(canonical):
    """Both separately MEASURED configurations are authoritative.

    The with-deposit run and the source-only run legitimately differ; a
    document may quote either, but nothing else.
    """
    acc = canonical["acceptance"]
    counts = set()
    for key in ("test_suite", "test_suite_source_only"):
        if key in acc:
            m = COUNT_RX.search(acc[key])
            assert m, f"acceptance.{key} states no passed count"
            counts.add(m.group(1))
    assert counts, "no authoritative test count in acceptance"
    return counts


@pytest.mark.parametrize("rel", ["README.md", "CHANGELOG.md",
                                 "docs/REPRODUCIBILITY_REPORT.md"])
def test_documents_agree_with_authoritative_test_count(canonical, rel):
    want = _authoritative_counts(canonical)
    current = [s for s in _sentences(_read(rel))
               if COUNT_RX.search(s) and not HIST_CLAUSE.search(s)]
    assert current, f"{rel} states no current test count"
    for s in current:
        for n in COUNT_RX.findall(s):
            assert n in want, (
                f"{rel} states {n} passed but the authoritative measured "
                f"counts are {sorted(want)}: {s.strip()[:110]}")


def test_historical_counts_are_labelled(canonical):
    hist = canonical["acceptance"]["test_suite_historical"]
    assert "HISTORICAL" in hist["status"].upper()


# ---------------------------------------------------------------------------
# 7. Dual-scope manifest - full verification, no silent skips
# ---------------------------------------------------------------------------
EXPECTED_MANIFEST_ENTRIES = 29
EXPECTED_EOL_DIFFERENCES = 21


@pytest.fixture(scope="module")
def manifest():
    return json.loads(_read("remediation/corrected_outputs/SHA256_MANIFEST.json"))


def test_manifest_declares_both_scopes_with_equal_path_sets(manifest):
    s = manifest["scopes"]
    hist = s["historical_windows_worktree_bytes"]["files"]
    repo = s["repository_normalized_bytes"]["files"]
    assert len(hist) == EXPECTED_MANIFEST_ENTRIES
    assert set(hist) == set(repo), (
        f"path sets differ: only-historical={set(hist) - set(repo)} "
        f"only-repo={set(repo) - set(hist)}")
    assert manifest["files"] == hist, "legacy 'files' must equal the historical scope"
    assert "not interchangeable" in manifest["scope_note"].lower()


def test_manifest_repository_scope_matches_every_file(manifest):
    """Verify ALL entries - git blob bytes in a checkout, on-disk bytes in a
    source extraction. Never silently continue past a failure."""
    repo = manifest["scopes"]["repository_normalized_bytes"]["files"]
    have_git = (REPO / ".git").exists()
    checked = 0
    for path, meta in repo.items():
        if have_git:
            out = subprocess.run(["git", "show", f"HEAD:{path}"],
                                 capture_output=True, cwd=REPO)
            assert out.returncode == 0, f"git show failed for {path}"
            data = out.stdout
        else:
            fp = REPO / path
            assert fp.exists(), f"{path} missing from source extraction"
            data = fp.read_bytes()
        assert hashlib.sha256(data).hexdigest() == meta["sha256"], \
            f"repository-scope sha mismatch: {path}"
        assert len(data) == meta["bytes"], f"repository-scope size mismatch: {path}"
        checked += 1
    assert checked == EXPECTED_MANIFEST_ENTRIES, (
        f"verified {checked} entries, expected {EXPECTED_MANIFEST_ENTRIES}")


def test_manifest_scope_difference_is_exactly_the_eol_transform(manifest):
    """Exactly 21 text entries differ, each solely by LF<->CRLF; the 8 binary
    entries are identical in both scopes."""
    hist = manifest["scopes"]["historical_windows_worktree_bytes"]["files"]
    repo = manifest["scopes"]["repository_normalized_bytes"]["files"]
    have_git = (REPO / ".git").exists()
    differing, identical, unexplained = [], [], []
    for path in hist:
        if hist[path]["sha256"] == repo[path]["sha256"]:
            identical.append(path)
            continue
        differing.append(path)
        if have_git:
            out = subprocess.run(["git", "show", f"HEAD:{path}"],
                                 capture_output=True, cwd=REPO)
            assert out.returncode == 0, f"git show failed for {path}"
            lf = out.stdout
        else:
            lf = (REPO / path).read_bytes().replace(b"\r\n", b"\n")
        crlf = lf.replace(b"\n", b"\r\n")
        if (hashlib.sha256(crlf).hexdigest() != hist[path]["sha256"]
                or len(crlf) != hist[path]["bytes"]):
            unexplained.append(path)
    assert not unexplained, (
        "difference not explained by the declared LF<->CRLF transform: "
        + ", ".join(unexplained))
    assert len(differing) == EXPECTED_EOL_DIFFERENCES, (
        f"expected {EXPECTED_EOL_DIFFERENCES} EOL-differing entries, "
        f"got {len(differing)}")
    assert len(identical) == EXPECTED_MANIFEST_ENTRIES - EXPECTED_EOL_DIFFERENCES


def test_manifest_does_not_claim_to_be_the_deposit_zip(manifest):
    """The 29-artifact scope is NOT the 94-file corrected data overlay."""
    blob = json.dumps(manifest).lower()
    assert "deposit zip" not in blob
    assert "historical_windows_worktree_bytes" in manifest["scopes"]
    assert "relocation" in blob, "relocation-ready metadata missing"
