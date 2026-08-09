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
    """Return (rows_per_label, hashes_per_label, problems).

    Canonical presence is required for every matched label UNCONDITIONALLY -
    not only when some hash already happens to be present in the row.
    """
    ident = _identity()
    rows_per = {lab: 0 for labs in mapping.values() for lab in labs}
    hashes_per = {lab: 0 for lab in rows_per}
    problems = []
    for i, row in enumerate(_rows(rel), 2):
        key = (row.get(structured_field) or "").strip()
        labels = mapping.get(key)
        if not labels:
            continue
        for lab in labels:
            rows_per[lab] += 1
        canon = {ident[lab]["manuscript_final_sha256"] for lab in labels}
        for fld in current_fields:
            val = row.get(fld) or ""
            if not val or HIST_FIELD.search(fld):
                continue
            # Per-HASH classification works at CLAUSE level: a canonical hash
            # must still be counted even when it shares a sentence with a
            # trailing "superseded ..." note, which _units() would discard.
            for clause in CLAUSE_SPLIT.split(" ".join(val.split())):
                for h in HASH_RX.findall(clause):
                    if h in canon:
                        for lab in labels:
                            if ident[lab]["manuscript_final_sha256"] == h:
                                hashes_per[lab] += 1
                        continue
                    if HIST_CLAUSE.search(clause):
                        continue
                    problems.append(
                        f"{rel} row {i} [{key}] field {fld}: {h[:16]}... is not "
                        f"canonical and its clause is not marked historical")
        joined = " ".join((row.get(f) or "") for f in current_fields)
        for lab in labels:
            want = ident[lab]["manuscript_final_sha256"]
            if want not in joined:
                problems.append(
                    f"{rel} row {i} [{key}]: canonical hash for {lab} "
                    f"({want[:16]}...) absent from the current fields")
    return rows_per, hashes_per, problems


def test_matrix_figure_crosswalk():
    rows_per, hashes_per, problems = _crosswalk(
        "docs/REPRODUCIBILITY_MATRIX.csv", "figure_table", MATRIX_FIGURE_MAP,
        ["canonical_expected", "reproduced_value", "checksum"])
    assert set(rows_per) == EXPECTED_LABELS
    empty_rows = [lab for lab, n in rows_per.items() if n == 0]
    assert not empty_rows, f"no matrix row matched for {empty_rows}"
    empty_hash = [lab for lab, n in hashes_per.items() if n == 0]
    assert not empty_hash, f"no canonical hash inspected for {empty_hash}"
    assert not problems, "matrix crosswalk problems: " + " ;; ".join(problems)


def test_provenance_figure_crosswalk():
    rows_per, hashes_per, problems = _crosswalk(
        "docs/FIGURE_PROVENANCE.csv", "figure", PROVENANCE_FIGURE_MAP,
        ["deployed_embed_sha256", "reproduced_output_sha256",
         "reproduction_result"])
    assert set(rows_per) == EXPECTED_LABELS
    empty_rows = [lab for lab, n in rows_per.items() if n == 0]
    assert not empty_rows, f"no provenance row matched for {empty_rows}"
    empty_hash = [lab for lab, n in hashes_per.items() if n == 0]
    assert not empty_hash, f"no canonical hash inspected for {empty_hash}"
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


def _units(text):
    """Yield non-historical sentence/clause units of a CSV cell.

    A LATER sentence containing "superseded" must never exonerate an EARLIER
    sentence that states a current falsehood, so the cell is split into
    sentences FIRST (after whitespace normalization) and only then into
    clauses. Each unit is judged on its own words.
    """
    for sent in _sentences(text):
        if HIST_CLAUSE.search(sent):
            continue
        for clause in CLAUSE_SPLIT.split(sent):
            if HIST_CLAUSE.search(clause):
                continue
            yield clause


def test_sentence_scoped_classification_rejects_earlier_current_claim():
    """Regression fixture: the FIRST sentence is a current falsehood; the
    SECOND is historical. The first must still be flagged."""
    fixture = ("zone means 438/286/181/81 km unchanged. "
               "Superseded embed: abc123.")
    hits = [tok for unit in _units(fixture) for tok in STALE_TOKENS
            if tok in unit]
    assert "438/286/181/81" in hits, (
        "sentence-scoped classifier let a later 'superseded' sentence "
        "exonerate an earlier current claim")

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
                for unit in _units(val):
                    for tok, desc in STALE_TOKENS.items():
                        if tok in unit:
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


CFG_RX = re.compile(r"(\d{2,4})\s+passed[^.]*?(\d{1,3})\s+skipped", re.I)


XFAIL_RX = re.compile(r"(\d{1,3})\s+xfailed", re.I)

# Anchored so it cannot match the "failed" inside "xfailed": the digits must be
# followed by whitespace and then "failed" itself.
FAILED_RX = re.compile(r"(\d{1,3})\s+failed\b", re.I)
ERROR_RX = re.compile(r"(\d{1,3})\s+errors?\b", re.I)
XPASS_RX = re.compile(r"(\d{1,3})\s+xpassed\b", re.I)


ACCEPTANCE_OUTCOMES = ("passed", "failed", "errors", "skipped",
                       "xfailed", "xpassed")


def _pair(text, label):
    """All six pytest outcomes parsed from one measured configuration.

    Every outcome pytest can report is parsed, not just the convenient ones, so
    that the accounting below covers the whole collection with nothing left
    implicit.

    ``failed`` matters because the required-archive profile is EXPECTED to fail:
    the release gate reports the stale-NetCDF blocker as one ordinary failure
    with a nonzero exit. Without that term the accounting cannot close, and the
    only ways to close it would be to drop the blocker or absorb it back into an
    xfail - which is exactly the defect the archive-gate refactor removed.

    ``errors`` and ``xpassed`` are required to be STATED even though both are
    currently zero. A silently absent field is indistinguishable from a field
    someone stopped measuring, and an unreported collection error or an
    unexpected xpass are both real ways a release run can be wrong while every
    other number still looks tidy.
    """
    m = CFG_RX.search(text)
    assert m, f"{label} states no passed/skipped pair"
    out = {"passed": int(m.group(1)), "skipped": int(m.group(2))}
    for name, rx in (("xfailed", XFAIL_RX), ("failed", FAILED_RX),
                     ("errors", ERROR_RX), ("xpassed", XPASS_RX)):
        found = rx.search(text)
        assert found, (
            f"{label} does not state '{name}'. Every one of "
            f"{', '.join(ACCEPTANCE_OUTCOMES)} must be recorded explicitly, "
            f"including the zeros")
        out[name] = int(found.group(1))
    return out


def _measured(canonical):
    """Structured, configuration-bound acceptance counts at the CURRENT head.

    Deliberately NOT reduced to an unordered set of numbers: each measured
    configuration keeps its own passed/skipped pair and label. Prior-head
    results live under their own explicitly labelled keys and are never read
    here, so a superseded count cannot be mistaken for a current one.
    """
    cur = canonical["acceptance"]["test_suite_current_head"]
    return {
        "with_deposit": _pair(cur["deposit_and_archive_configured"],
                              "test_suite_current_head."
                              "deposit_and_archive_configured"),
        "source_only": _pair(cur["source_only"],
                             "test_suite_current_head.source_only"),
    }


def test_acceptance_counts_are_configuration_bound(canonical):
    """Structure and internal consistency only - the literal totals live in
    the metadata (one source of truth) and are deliberately NOT duplicated
    here, where they would go stale the moment a test is added."""
    m = _measured(canonical)
    assert set(m) == {"with_deposit", "source_only"}
    for cfg, v in m.items():
        assert isinstance(v["passed"], int) and v["passed"] > 0, cfg
        assert isinstance(v["skipped"], int) and v["skipped"] >= 0, cfg
    assert m["source_only"]["skipped"] > 0, "source-only run must record its skips"
    assert m["source_only"]["passed"] < m["with_deposit"]["passed"], (
        "source-only cannot pass more tests than the configured run")

    cur = canonical["acceptance"]["test_suite_current_head"]
    total = cur["collected_total"]
    for cfg, v in m.items():
        got = sum(v[k] for k in ACCEPTANCE_OUTCOMES)
        assert got == total, (
            f"{cfg} accounts for {got} tests but the collected total is "
            f"{total}: " + "+".join(ACCEPTANCE_OUTCOMES) +
            " must cover every collected test")
        # Neither profile may carry a collection error or an unexpected xpass.
        # These are zero today; requiring them to stay zero means a future run
        # cannot bury one behind an otherwise-tidy set of numbers.
        assert v["errors"] == 0, (
            f"{cfg} records {v['errors']} error(s); a release-relevant profile "
            f"must have none - an error is an unrun test, not a result")
        assert v["xpassed"] == 0, (
            f"{cfg} records {v['xpassed']} xpass(es); a test expected to fail "
            f"that passes means the expectation is stale and must be resolved, "
            f"not recorded")

    # The two profiles differ in KIND, not merely in count, and the records must
    # say so. Source-only is a clean pass; the required-archive profile is the
    # release gate, and at this head it is expected to report exactly one
    # ordinary failure - the stale-NetCDF deposit blocker - with a nonzero exit.
    # Asserting both directions stops the records from drifting into either lie:
    # a source-only run quietly carrying a failure, or a required-archive run
    # recorded as green while the archive is still stale.
    assert m["source_only"]["failed"] == 0, (
        "the source-only profile must record zero failures; it is the profile "
        "that has to be green")
    assert m["with_deposit"]["failed"] == 1, (
        "the required-archive profile must record exactly ONE failure - the "
        "stale-NetCDF release blocker. Zero would mean the gate was recorded "
        "as passing while the archive is still stale; more than one would mean "
        "the release run is no longer reporting a single unambiguous cause")
    assert m["with_deposit"]["xfailed"] == 0, (
        "the required-archive blocker must be an ordinary failure, not an "
        "xfail: absorbing it into an expected-failure marker is the defect the "
        "archive-gate refactor removed")

    # This head does NOT claim a 0-skip fully configured acceptance run; the
    # non-redistributable Aptos face makes one unachievable here, so acceptance
    # is explicitly deferred rather than asserted.
    assert m["with_deposit"]["skipped"] > 0, (
        "the configured run at this head really does skip - do not record it "
        "as a 0-skip acceptance run")
    assert "PENDING" in cur["fully_configured_acceptance"].upper(), (
        "fully configured acceptance must be recorded as PENDING until the "
        "final section 9 gate")
    assert "aptos" in cur["deposit_and_archive_configured"].lower(), (
        "the current-head record must name the Aptos-font skip")
    assert "archive" in cur["deposit_and_archive_configured"].lower(), (
        "the configured-run record must name the configuration it measured")
    assert "source-only" in cur["source_only"].lower()


def test_prior_head_counts_are_labelled_as_prior_head(canonical):
    """363/0 and 327+36 are PRIOR-head results and must say so."""
    acc = canonical["acceptance"]
    assert "test_suite" not in acc, (
        "the bare acceptance.test_suite key is gone on purpose: an unqualified "
        "key is what let a prior-head count read as a current result")
    assert "test_suite_source_only" not in acc
    checked = 0
    for key in ("test_suite_prior_head", "test_suite_source_only_prior_head"):
        rec = acc[key]
        assert "PRIOR HEAD" in rec["status"].upper(), key
        assert "NOT A CURRENT-HEAD RESULT" in rec["status"].upper(), key
        assert re.search(r"\b[0-9a-f]{40}\b", rec["status"]), (
            f"{key} does not record which commit it was measured at")
        checked += 1
    assert checked == 2
    # the superseded numbers must not appear as current-head figures
    cur = json.dumps(acc["test_suite_current_head"])
    for stale in ("363 passed", "327 passed"):
        assert stale not in cur, f"{stale} recorded as a current-head result"


NO_SKIPS_CLAIM = re.compile(
    r"\bno\b[^.]{0,40}\bremaining skips\b|\b0 skipped\b|\bzero skips\b|"
    r"\bno\b[^.]{0,20}\bskips\b", re.I)


def test_no_active_claim_of_a_zero_skip_configured_run(canonical):
    """The configured run at this head DOES skip, so no prose may deny it.

    This inverts an earlier guard. At the prior head the fully configured run
    reached 0 skipped and the risk was stale prose claiming skips remained. At
    this head the pinned Aptos face is absent, the configured run skips, and the
    risk is the opposite: prose claiming a 0-skip acceptance run that was not
    measured here.
    """
    assert _measured(canonical)["with_deposit"]["skipped"] > 0
    for rel in ("docs/REPRODUCIBILITY_REPORT.md", "README.md", "CHANGELOG.md"):
        for sent in _sentences(_read(rel)):
            if HIST_CLAUSE.search(sent):
                continue          # prior-head/historical sentences are exempt
            if not NO_SKIPS_CLAIM.search(sent):
                continue
            assert "prior head" in sent.lower() or "pending" in sent.lower(), (
                f"{rel} asserts a zero-skip run as current, but the measured "
                f"configured run at this head skips: {sent.strip()[:140]}")


@pytest.mark.parametrize("rel", ["README.md", "CHANGELOG.md",
                                 "docs/REPRODUCIBILITY_REPORT.md"])
def test_documents_agree_with_authoritative_test_count(canonical, rel):
    allowed = {c["passed"] for c in _measured(canonical).values()}
    current = [s for s in _sentences(_read(rel))
               if COUNT_RX.search(s) and not HIST_CLAUSE.search(s)]
    assert current, f"{rel} states no current test count"
    for s in current:
        for n in COUNT_RX.findall(s):
            assert int(n) in allowed, (
                f"{rel} states {n} passed but the measured configurations are "
                f"{sorted(allowed)}: {s.strip()[:110]}")


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
    """Verify ALL 29 entries, each according to its declared relocation state.

    A path that has left the repository must NOT be read from Git or from
    disk - that would be a vacuous pass once the file is gone. Each state is
    verified against what actually still exists for it:

    * ``repository``       - the Git blob (or on-disk bytes in a source
                             extraction) must match the repository scope.
    * ``relocated``        - the pinned package identity, the exact archive
                             member path, the member hash/bytes and the
                             declared EOL relationship must all be present and
                             mutually consistent.
    * ``approved_removal`` - both byte identities must survive, and an
                             approval, a reason and a resolvable equivalence
                             evidence path must be recorded.
    """
    repo = manifest["scopes"]["repository_normalized_bytes"]["files"]
    hist = manifest["scopes"]["historical_windows_worktree_bytes"]["files"]
    rel = manifest["relocation"]
    states = rel["files"]
    have_git = (REPO / ".git").exists()
    seen = {"repository": 0, "relocated": 0, "approved_removal": 0}

    for path, meta in repo.items():
        ent = states[path]
        state = ent["state"]
        assert state in seen, f"{path}: unknown state {state!r}"
        seen[state] += 1

        if state == "repository":
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
            assert len(data) == meta["bytes"], \
                f"repository-scope size mismatch: {path}"

        elif state == "relocated":
            assert not (REPO / path).exists(), (
                f"{path} is declared relocated but is still in the tree")
            pkg = rel["packages"][ent["package"]]
            member = ent["archive_member_path"]
            assert member and not member.startswith("/"), \
                f"{path}: bad archive_member_path {member!r}"
            assert len(pkg["archive_sha256"]) == 64, \
                f"{path}: package archive_sha256 is not a SHA-256"
            form = ent["archive_member_byte_form"]
            assert form in ("repository_normalized_bytes",
                            "historical_windows_worktree_bytes"), \
                f"{path}: bad archive_member_byte_form {form!r}"
            declared = (meta if form == "repository_normalized_bytes"
                        else hist[path])
            assert ent["member_sha256"] == declared["sha256"], (
                f"{path}: member sha256 does not equal the declared "
                f"{form} identity")
            assert ent["member_bytes"] == declared["bytes"], (
                f"{path}: member bytes do not equal the declared {form} size")
            binary = hist[path]["sha256"] == meta["sha256"]
            assert ("binary" in ent["eol_relationship"]) == binary, (
                f"{path}: declared eol_relationship contradicts the two scopes")

        else:  # approved_removal
            assert not (REPO / path).exists(), (
                f"{path} is declared approved_removal but is still in the tree")
            assert ent["package"] is None and ent["archive_member_path"] is None, (
                f"{path}: a removal is not a relocation; package and "
                f"archive_member_path must be null")
            assert ent["removal_approval"], f"{path}: no removal approval"
            assert ent["removal_reason"], f"{path}: no removal reason"
            ev = ent.get("equivalence_evidence")
            assert ev and (REPO / ev).is_file(), (
                f"{path}: equivalence evidence {ev!r} does not resolve")
            assert len(meta["sha256"]) == 64 and meta["bytes"] > 0
            assert len(hist[path]["sha256"]) == 64 and hist[path]["bytes"] > 0

    checked = sum(seen.values())
    assert checked == EXPECTED_MANIFEST_ENTRIES, (
        f"verified {checked} entries, expected {EXPECTED_MANIFEST_ENTRIES}")
    assert seen["repository"] and seen["relocated"] and seen["approved_removal"], (
        f"a state went entirely unexercised: {seen}")


def test_manifest_scope_difference_is_exactly_the_eol_transform(manifest):
    """Exactly 21 text entries differ, each solely by LF<->CRLF; the 8 binary
    entries are identical in both scopes.

    State-aware: the transform is RECOMPUTED from the bytes for every path
    still in the repository. For a path that has been relocated or removed the
    bytes are gone, so the declared relationship is verified instead - the two
    scope hashes must still disagree, the declared ``eol_relationship`` must say
    so, and the archive member must carry the CRLF (historical) byte form. A
    missing file is never allowed to turn this guard into a silent pass.
    """
    hist = manifest["scopes"]["historical_windows_worktree_bytes"]["files"]
    repo = manifest["scopes"]["repository_normalized_bytes"]["files"]
    states = manifest["relocation"]["files"]
    have_git = (REPO / ".git").exists()
    differing, identical, unexplained = [], [], []
    recomputed = declared_only = 0

    for path in hist:
        if hist[path]["sha256"] == repo[path]["sha256"]:
            identical.append(path)
            continue
        differing.append(path)
        ent = states[path]

        if ent["state"] == "repository":
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
            recomputed += 1
        else:
            rel_text = ent.get("eol_relationship", "")
            if "CRLF" not in rel_text or "LF" not in rel_text:
                unexplained.append(path)
            elif ent["state"] == "relocated" and (
                    ent.get("archive_member_byte_form")
                    != "historical_windows_worktree_bytes"
                    or ent.get("member_sha256") != hist[path]["sha256"]):
                unexplained.append(path)
            declared_only += 1

    assert not unexplained, (
        "difference not explained by the declared LF<->CRLF transform: "
        + ", ".join(unexplained))
    assert len(differing) == EXPECTED_EOL_DIFFERENCES, (
        f"expected {EXPECTED_EOL_DIFFERENCES} EOL-differing entries, "
        f"got {len(differing)}")
    assert len(identical) == EXPECTED_MANIFEST_ENTRIES - EXPECTED_EOL_DIFFERENCES
    assert recomputed + declared_only == EXPECTED_EOL_DIFFERENCES
    assert recomputed, "no EOL entry was recomputed from real bytes"


def test_manifest_does_not_claim_to_be_the_deposit_zip(manifest):
    """The 29-artifact scope is NOT the 94-file corrected data overlay."""
    blob = json.dumps(manifest).lower()
    assert "deposit zip" not in blob
    assert "historical_windows_worktree_bytes" in manifest["scopes"]
    assert "relocation" in blob, "relocation-ready metadata missing"


def test_manifest_rejects_duplicate_json_keys():
    """A duplicate key would let one identity silently shadow another."""
    seen_dupes = []

    def hook(pairs):
        keys = [k for k, _ in pairs]
        for k in keys:
            if keys.count(k) > 1 and k not in seen_dupes:
                seen_dupes.append(k)
        return dict(pairs)

    json.loads(_read("remediation/corrected_outputs/SHA256_MANIFEST.json"),
               object_pairs_hook=hook)
    assert not seen_dupes, f"duplicate JSON keys in manifest: {seen_dupes}"


def test_manifest_expected_path_set_is_frozen(manifest):
    expected = manifest["expected_paths"]
    assert len(expected) == EXPECTED_MANIFEST_ENTRIES
    assert len(set(expected)) == len(expected), "duplicate path in expected_paths"
    for scope in ("historical_windows_worktree_bytes",
                  "repository_normalized_bytes"):
        assert set(manifest["scopes"][scope]["files"]) == set(expected), (
            f"{scope} does not match the frozen expected path set")


def test_manifest_identical_binaries_are_explicit(manifest):
    hist = manifest["scopes"]["historical_windows_worktree_bytes"]["files"]
    repo = manifest["scopes"]["repository_normalized_bytes"]["files"]
    declared = manifest["identical_binary_paths"]
    assert len(declared) == 8, f"expected 8 identical binaries, got {len(declared)}"
    actual = sorted(p for p in hist if hist[p]["sha256"] == repo[p]["sha256"])
    assert sorted(declared) == actual, (
        f"declared identical binaries != actual; declared_only="
        f"{set(declared) - set(actual)} actual_only={set(actual) - set(declared)}")
    for p in declared:
        assert hist[p]["bytes"] == repo[p]["bytes"], (
            f"{p} declared identical but byte counts differ")
    assert sorted(manifest["eol_differing_text_paths"]) == sorted(
        set(hist) - set(declared))


def test_manifest_relocation_schema(manifest):
    r = manifest["relocation"]
    assert set(r["allowed_states"]) == {"repository", "relocated",
                                        "approved_removal"}
    assert isinstance(r["packages"], dict), "packages must support MULTIPLE archives"
    files = r["files"]
    assert set(files) == set(manifest["expected_paths"])
    for path, ent in files.items():
        st = ent["state"]
        assert st in r["allowed_states"], f"{path}: bad state {st}"
        if st == "repository":
            assert (REPO / path).exists(), f"{path} declared repository but absent"
            assert ent["package"] is None
        elif st == "relocated":
            pkg = ent["package"]
            assert pkg in r["packages"], f"{path}: unknown package {pkg}"
            meta = r["packages"][pkg]
            for k in ("doi", "archive_filename", "archive_sha256",
                      "verification_status"):
                assert meta.get(k), f"package {pkg} missing {k}"
            assert ent["archive_member_path"], f"{path}: no archive_member_path"
        else:
            assert ent["removal_approval"] and ent["removal_reason"], path
        # both byte identities survive regardless of state
        assert path in manifest["scopes"]["historical_windows_worktree_bytes"]["files"]
        assert path in manifest["scopes"]["repository_normalized_bytes"]["files"]


# ---------------------------------------------------------------------------
# 8. Relocation crosswalk - the manifest and the public sidecar together must
#    account for every relocation exactly once, with no path counted twice.
# ---------------------------------------------------------------------------
TOTAL_RELOCATIONS = 21

SIDECAR_COLUMNS = (
    "old_repository_path", "repository_sha256", "repository_bytes",
    "historical_byte_identity_sha256", "historical_byte_identity_bytes",
    "historical_identity_source", "archive_member_byte_form",
    "eol_relationship", "reserved_data_doi", "archive_filename",
    "archive_sha256", "archive_member_path", "member_sha256", "member_bytes",
    "state", "recorded_in_sha256_manifest", "archive_publication_state",
    "verification_status",
)

# The archive candidate is built and verified LOCALLY and has not been
# uploaded, deposited or published. A bare "VERIFIED" would read as public
# availability, so both the state and the verification wording are pinned.
ARCHIVE_PUBLICATION_STATE = (
    "LOCAL_CANDIDATE_NOT_UPLOADED_NOT_DEPOSITED_NOT_PUBLISHED")
ARCHIVE_VERIFICATION_STATUS = "VERIFIED_IN_LOCAL_ARCHIVE_CANDIDATE"


@pytest.fixture(scope="module")
def sidecar():
    return _rows("docs/RELOCATED_ARTIFACTS.csv")


def test_relocation_sidecar_is_complete_and_well_formed(sidecar):
    assert len(sidecar) == TOTAL_RELOCATIONS, (
        f"sidecar has {len(sidecar)} rows, expected {TOTAL_RELOCATIONS}")
    assert tuple(sidecar[0]) == SIDECAR_COLUMNS, "sidecar column set changed"
    paths = [r["old_repository_path"] for r in sidecar]
    assert len(set(paths)) == TOTAL_RELOCATIONS, "duplicate relocation in sidecar"
    members = [r["archive_member_path"] for r in sidecar]
    assert len(set(members)) == TOTAL_RELOCATIONS, "duplicate archive member"
    for r in sidecar:
        assert r["state"] == "relocated", f"{r['old_repository_path']}: bad state"
        assert r["archive_publication_state"] == ARCHIVE_PUBLICATION_STATE, (
            f"{r['old_repository_path']}: archive_publication_state must record "
            f"that the candidate is local-only, got "
            f"{r['archive_publication_state']!r}")
        # a bare "VERIFIED" could be read as "publicly available"
        assert r["verification_status"] == ARCHIVE_VERIFICATION_STATUS, (
            f"{r['old_repository_path']}: verification_status must scope the "
            f"verification to the local archive candidate, got "
            f"{r['verification_status']!r}")
        assert r["verification_status"] != "VERIFIED", (
            "bare VERIFIED implies public availability and is forbidden")
        assert r["reserved_data_doi"] == "10.5281/zenodo.21717752"
        assert r["archive_filename"] == "scorch_processed_data_v1.0.0.zip"
        for col in ("repository_sha256", "historical_byte_identity_sha256",
                    "member_sha256", "archive_sha256"):
            assert len(r[col]) == 64, f"{r['old_repository_path']}: bad {col}"
        assert int(r["repository_bytes"]) > 0 and int(r["member_bytes"]) > 0
        # the relocated file must really be gone from the repository
        assert not (REPO / r["old_repository_path"]).exists(), (
            f"{r['old_repository_path']} is listed as relocated but still present")
        # the member must carry exactly the byte form the row declares
        want = (r["repository_sha256"]
                if r["archive_member_byte_form"] == "repository_normalized_bytes"
                else r["historical_byte_identity_sha256"])
        assert r["member_sha256"] == want, (
            f"{r['old_repository_path']}: member sha256 does not match its "
            f"declared {r['archive_member_byte_form']}")


def test_relocation_union_covers_every_relocation_once(manifest, sidecar):
    """Manifest records + sidecar == exactly the 21 relocations, once each."""
    in_manifest = {p for p, e in manifest["relocation"]["files"].items()
                   if e["state"] == "relocated"}
    sidecar_paths = {r["old_repository_path"] for r in sidecar}
    flagged = {r["old_repository_path"] for r in sidecar
               if r["recorded_in_sha256_manifest"] == "true"}

    assert in_manifest == flagged, (
        f"sidecar disagrees with the manifest about which relocations it "
        f"records: manifest_only={in_manifest - flagged} "
        f"sidecar_only={flagged - in_manifest}")
    assert in_manifest <= sidecar_paths, (
        f"manifest relocations missing from the sidecar: "
        f"{in_manifest - sidecar_paths}")
    assert len(in_manifest | sidecar_paths) == TOTAL_RELOCATIONS, (
        f"union is {len(in_manifest | sidecar_paths)}, "
        f"expected {TOTAL_RELOCATIONS}")

    outside = sidecar_paths - in_manifest
    frozen = set(manifest["expected_paths"])
    assert not (outside & frozen), (
        f"paths outside the frozen 29-path manifest scope must not appear in "
        f"it: {outside & frozen}")
    assert len(outside) == TOTAL_RELOCATIONS - len(in_manifest)

    xw = manifest["relocation"]["relocation_crosswalk"]
    assert xw["total_relocations"] == TOTAL_RELOCATIONS
    assert xw["recorded_here"] == len(in_manifest)
    assert xw["recorded_only_in_sidecar"] == len(outside)
    assert (REPO / xw["public_sidecar"]).is_file()


def test_frozen_manifest_scopes_were_not_widened_by_relocation(manifest):
    """The 29-file scopes are frozen: relocation must never add paths to them."""
    expected = set(manifest["expected_paths"])
    assert len(expected) == EXPECTED_MANIFEST_ENTRIES
    for key in ("historical_windows_worktree_bytes",
                "repository_normalized_bytes"):
        assert set(manifest["scopes"][key]["files"]) == expected
    assert set(manifest["relocation"]["files"]) == expected
    assert (len(manifest["identical_binary_paths"])
            + len(manifest["eol_differing_text_paths"])
            == EXPECTED_MANIFEST_ENTRIES)
    assert set(manifest["identical_binary_paths"]) <= expected
    assert set(manifest["eol_differing_text_paths"]) <= expected


# ---------------------------------------------------------------------------
# 9. Repository scope statistics are RECOMPUTED from Git, never asserted from
#    prose. The recorded totals are bound to explicit commits so that a later
#    commit adding files cannot silently falsify them.
# ---------------------------------------------------------------------------
def _tracked_totals(commit):
    """(files, bytes) for every tracked blob at `commit`, or None if absent."""
    if subprocess.run(["git", "cat-file", "-e", f"{commit}^{{commit}}"],
                      cwd=REPO, capture_output=True).returncode != 0:
        return None
    out = subprocess.run(["git", "ls-tree", "-r", "-l", commit],
                         cwd=REPO, capture_output=True, text=True, check=True).stdout
    files = nbytes = 0
    for line in out.splitlines():
        if not line.strip():
            continue
        # "<mode> <type> <sha>\t<path>" with size in field 4 ("-" for submodules)
        size = line.split("\t", 1)[0].split()[3]
        if size == "-":
            continue
        files += 1
        nbytes += int(size)
    return files, nbytes


def test_repository_scope_measurements_recompute_from_git(manifest):
    scope = manifest["repository_scope_measurements"]
    checked = 0
    for key in ("baseline_before_scope_cleanup", "after_scope_cleanup"):
        rec = scope[key]
        actual = _tracked_totals(rec["commit"])
        if actual is None:
            pytest.skip(f"commit {rec['commit'][:8]} unavailable "
                        f"(shallow clone) - cannot recompute {key}")
        files, nbytes = actual
        assert files == rec["tracked_files"], (
            f"{key}: recorded {rec['tracked_files']} tracked files but "
            f"{rec['commit'][:8]} really has {files}")
        assert nbytes == rec["tracked_bytes"], (
            f"{key}: recorded {rec['tracked_bytes']} tracked bytes but "
            f"{rec['commit'][:8]} really has {nbytes}")
        checked += 1
    assert checked == 2, "both commits must be recomputed, not one"

    before = scope["baseline_before_scope_cleanup"]["tracked_bytes"]
    after = scope["after_scope_cleanup"]["tracked_bytes"]
    pct = round(100.0 * (1.0 - after / before), 3)
    assert pct == scope["reduction_percent"], (
        f"recorded reduction {scope['reduction_percent']} != recomputed {pct}")
    # the superseded wrong values must never reappear as current claims
    assert "186" not in json.dumps(scope["after_scope_cleanup"])
    assert scope["after_scope_cleanup"]["tracked_files"] == 189
    assert scope["after_scope_cleanup"]["tracked_bytes"] == 9372392


# ---------------------------------------------------------------------------
# 10. Figure 1 / Figure 4 artwork licensing: PENDING must not coexist anywhere
#     with an active CC BY 4.0 claim over the same artwork.
# ---------------------------------------------------------------------------
LICENCE_RECORDS = [
    "docs/LICENSES_AND_ATTRIBUTION.md",
    "assets/frozen_figures/README.md",
    "assets/manuscript_final/README.md",
    ".zenodo.json",
]

# "Figure 1"/"Fig. 4" but never "Figure 11"/"Fig. 10"; plus the path tokens.
ARTWORK_RX = re.compile(
    r"fig0[14]\b|Figure_0[14]|Figure [14](?!\d)|Fig\. [14](?!\d)", re.I)
CCBY_RX = re.compile(r"CC BY 4\.0|Creative Commons Attribution 4\.0", re.I)
# Any wording that withholds, excludes, defers or FORBIDS the grant. The
# prohibition forms matter: a sentence saying "no record may assert CC BY over
# Figure 1" is the opposite of a grant and must not be flagged as one.
PENDING_RX = re.compile(
    r"PENDING|not yet in force|EXCLUDED FROM THE CC BY|NOT Figure|"
    r"no CC BY|never be read as licensing|no public licence|"
    r"requires separate written authorization|has not been recorded|"
    r"no record may|must not|may not|forbidden|prohibited", re.I)

PENDING_SENTINEL = "CC BY 4.0 PENDING"


def test_artwork_licence_pending_is_declared_in_the_authoritative_table():
    """The gate must exist in the path table, not only in a figure README."""
    text = _read("docs/LICENSES_AND_ATTRIBUTION.md")
    assert PENDING_SENTINEL in text, (
        "the authoritative path table does not declare the artwork gate")
    assert "Najibi" in text and "has not been recorded" in text
    # the three donor/original rasters must be carved out of the software row
    for rel in ("scripts/figures/fig01/original/Figure_01_original.png",
                "scripts/figures/fig04/original/Figure_04_original.png",
                "scripts/figures/fig04/donor/"
                "Figure_04_approved_horizontal.png"):
        assert rel in text, f"{rel} is not classified in the path table"
        assert (REPO / rel).is_file(), f"{rel} is missing from the tree"


@pytest.mark.parametrize("rel", LICENCE_RECORDS)
def test_no_active_cc_by_claim_over_figure_1_or_4_artwork(rel):
    """Every sentence tying Fig. 1/4 artwork to CC BY must withhold the grant.

    This is the contradiction guard: while the PENDING gate stands, no record
    may assert an active CC BY 4.0 licence over that artwork.
    """
    text = _read(rel)
    for sent in _sentences(text):
        if not (ARTWORK_RX.search(sent) and CCBY_RX.search(sent)):
            continue
        assert PENDING_RX.search(sent), (
            f"{rel} asserts an ACTIVE CC BY 4.0 grant over Figure 1/4 "
            f"artwork while the licence is PENDING: {sent.strip()[:160]}")
    # Coverage is asserted at DOCUMENT level, not per sentence: the artwork and
    # the withholding wording legitimately live in adjacent sentences ("Figures
    # 1 and 4 carry no such material. Their CC BY 4.0 licensing is PENDING."),
    # so a co-occurrence requirement would be unsatisfiable rather than strict.
    assert ARTWORK_RX.search(text), (
        f"{rel} does not mention Figure 1/4 artwork at all - this record is in "
        f"LICENCE_RECORDS because it is supposed to; the guard inspected "
        f"nothing, which is a failure, not a pass")
    assert PENDING_RX.search(text), (
        f"{rel} mentions Figure 1/4 artwork but nowhere withholds the CC BY "
        f"4.0 grant while the licence is PENDING")


def test_gpl_software_row_does_not_swallow_the_artwork():
    """The scripts/** GPL row must not classify the donor rasters as software."""
    text = _read("docs/LICENSES_AND_ATTRIBUTION.md")
    row = next(ln for ln in text.splitlines()
               if ln.startswith("| `src/**`, `scripts/**`"))
    low = row.lower()
    assert "excluding" in low or "except" in low, (
        "the GPL software row does not carve out the frozen artwork rasters: "
        f"{row[:160]}")
    assert "GPL-3.0-only" in row


# ---------------------------------------------------------------------------
# 11. The data-archive candidate is LOCAL. No record may imply otherwise.
# ---------------------------------------------------------------------------
POINTER_RECORDS = [
    "legacy_defective_figure09/README.md",
    "assets/manuscript_final/README.md",
]

FORBIDDEN_DEPOSIT_CLAIM = re.compile(
    r"relocated to the (processed-data )?deposit|already (in|deposited)"
    r" (a|the) (zenodo )?deposit", re.I)


@pytest.mark.parametrize("rel", POINTER_RECORDS)
def test_pointer_records_do_not_claim_a_published_deposit(rel):
    text = _read(rel)
    for sent in _sentences(text):
        assert not FORBIDDEN_DEPOSIT_CLAIM.search(sent), (
            f"{rel} describes the relocated artifacts as already deposited: "
            f"{sent.strip()[:160]}")
    low = " ".join(text.split()).lower()
    assert "has not been uploaded, deposited, or published" in low, (
        f"{rel} does not state the archive candidate's unpublished status")
    assert "10.5281/zenodo.21717752" in text, f"{rel} omits the reserved DOI"


# ---------------------------------------------------------------------------
# 12. Reproduction-class counts are DERIVED from the identity CSV.
#
# The public report used to assert "6 data_generated / 8 deployment_export /
# 2 frozen_approved_artwork (Fig. 1, 4)" as literal prose. Every one of those
# numbers was wrong by the time Figures 1 and 4 gained deterministic
# producers, and nothing in the test suite noticed, because no guard tied the
# prose to docs/MANUSCRIPT_FIGURE_IDENTITY.csv. These guards close that gap:
# the CSV is the source of truth and the prose must agree with it.
# ---------------------------------------------------------------------------
KNOWN_REPRODUCTION_CLASSES = {
    "data_generated",
    "deployment_export_of_reproduced_original",
    "deterministic_producer",
    "manually_postprocessed_approved_artwork",
    "frozen_approved_artwork",
}

EXPECTED_FIGURE_TOTAL = 17

# "9 `data_generated`" / "2 `deterministic_producer`" in any prose position.
CLASS_COUNT_RX = re.compile(r"(\d+)\s+`([a-z_]+)`")


def _derived_class_counts():
    """Members per reproduction class, straight from the identity CSV."""
    counts = {name: 0 for name in KNOWN_REPRODUCTION_CLASSES}
    for row in _rows("docs/MANUSCRIPT_FIGURE_IDENTITY.csv"):
        name = row["reproduction_class"].strip()
        counts[name] = counts.get(name, 0) + 1
    return counts


def test_identity_csv_uses_only_the_declared_class_vocabulary():
    counts = _derived_class_counts()
    unknown = set(counts) - KNOWN_REPRODUCTION_CLASSES
    assert not unknown, (
        f"docs/MANUSCRIPT_FIGURE_IDENTITY.csv uses undeclared reproduction "
        f"class(es) {sorted(unknown)}; add them to the vocabulary "
        f"deliberately rather than by typo")
    assert sum(counts.values()) == EXPECTED_FIGURE_TOTAL, (
        f"identity CSV holds {sum(counts.values())} figures, not "
        f"{EXPECTED_FIGURE_TOTAL}")


def test_reproducibility_report_class_counts_match_the_identity_csv():
    """Every 'N `class`' the report states must equal the derived count."""
    derived = _derived_class_counts()
    text = _read("docs/REPRODUCIBILITY_REPORT.md")
    seen, problems = set(), []
    for sent in _sentences(text):
        if HIST_CLAUSE.search(sent):
            continue  # an explicitly superseded statement may quote old counts
        for stated, name in CLASS_COUNT_RX.findall(sent):
            if name not in KNOWN_REPRODUCTION_CLASSES:
                continue
            seen.add(name)
            if int(stated) != derived[name]:
                problems.append(
                    f"report says {stated} {name}, identity CSV says "
                    f"{derived[name]}: {sent.strip()[:140]}")
    assert not problems, (
        "docs/REPRODUCIBILITY_REPORT.md contradicts "
        "docs/MANUSCRIPT_FIGURE_IDENTITY.csv: " + " ;; ".join(problems))
    # Coverage: a guard that matched nothing is a failure, not a pass.
    in_use = {n for n, c in derived.items() if c}
    missing = in_use - seen
    assert not missing, (
        f"the report never states a count for the populated class(es) "
        f"{sorted(missing)}; the guard inspected nothing for them")


def test_empty_reproduction_classes_are_not_presented_as_populated():
    """A class with zero members must never be given a figure count."""
    derived = _derived_class_counts()
    empty = {n for n, c in derived.items() if c == 0}
    assert empty, (
        "no reproduction class is currently empty - if that is a real change, "
        "update this guard deliberately; it exists because "
        "frozen_approved_artwork was left in the prose after it lost both "
        "of its figures")
    problems = []
    for rel in ("docs/REPRODUCIBILITY_REPORT.md", "README.md",
                "assets/frozen_figures/README.md",
                "assets/manuscript_final/README.md"):
        for sent in _sentences(_read(rel)):
            if HIST_CLAUSE.search(sent):
                continue
            for stated, name in CLASS_COUNT_RX.findall(sent):
                if name in empty and int(stated) > 0:
                    problems.append(f"{rel}: '{stated} {name}' - "
                                    f"{sent.strip()[:140]}")
    assert not problems, (
        "an empty reproduction class is described as though it still holds "
        "figures: " + " ;; ".join(problems))


# ---------------------------------------------------------------------------
# 13. The defective Figure 9 rasters left the Git tree. Structural truth
#     first; wording second.
# ---------------------------------------------------------------------------
LEGACY_FIG9_DIR = "legacy_defective_figure09"

LEGACY_RASTER_NAMES = (
    "Figure9_assembled_LEGACY_ARITHMETIC_DEFECTIVE.png",
    "Figure_09_LEGACY_ARITHMETIC_DEFECTIVE.png",
)

# Present-tense claims that the artifacts are still carried by the repository.
SHIPPED_CLAIM_RX = re.compile(
    r"shipped in this release|ships? (in|with) (this|the) "
    r"(release|repository|tree)|(are|is) (still )?(in|shipped in) "
    r"the (git )?tree", re.I)

# Wording that makes such a sentence truthful: it is reporting the former
# state and saying so, or naming the relocation.
RELOCATED_RX = re.compile(
    r"\bWERE\b|have since|since been|relocated|staged at|no longer", re.I)


def test_legacy_figure09_directory_tracks_only_its_pointer_readme():
    """Unfakeable by prose: ask Git what is actually tracked there."""
    out = subprocess.run(
        ["git", "ls-files", LEGACY_FIG9_DIR],
        cwd=REPO, capture_output=True, text=True, check=True).stdout
    tracked = sorted(p for p in out.splitlines() if p.strip())
    assert tracked == [f"{LEGACY_FIG9_DIR}/README.md"], (
        f"{LEGACY_FIG9_DIR}/ must track only its explanatory pointer README; "
        f"Git reports {tracked}")
    for name in LEGACY_RASTER_NAMES:
        assert not (REPO / LEGACY_FIG9_DIR / name).exists(), (
            f"{name} is back in the working tree; it was relocated to the "
            f"local processed-data archive candidate")


@pytest.mark.parametrize("rel", [
    "docs/ALIGNMENT_DECISIONS.md",
    "docs/CANONICAL_SCIENCE.json",
    "CHANGELOG.md",
    "assets/manuscript_final/README.md",
    f"{LEGACY_FIG9_DIR}/README.md",
])
def test_no_record_claims_the_legacy_rasters_are_still_shipped(rel):
    text = _read(rel)
    inspected, problems = 0, []
    for sent in _sentences(text):
        if not (LEGACY_FIG9_DIR in sent
                or any(n in sent for n in LEGACY_RASTER_NAMES)):
            continue
        inspected += 1
        # The subject's own names contain "LEGACY"/"legacy", which HIST_CLAUSE
        # matches. Left in place they would exempt EVERY sentence naming the
        # rasters - the guard would inspect them and then always pass. The
        # historical label has to come from the surrounding prose, so the
        # subject tokens are removed before asking whether one is present.
        stripped = sent
        for token in (*LEGACY_RASTER_NAMES, LEGACY_FIG9_DIR):
            stripped = stripped.replace(token, " ")
        if HIST_CLAUSE.search(stripped) or RELOCATED_RX.search(stripped):
            continue
        if SHIPPED_CLAIM_RX.search(sent):
            problems.append(sent.strip()[:180])
    assert not problems, (
        f"{rel} states as CURRENT fact that the defective Figure 9 rasters "
        f"are shipped in the repository; they were relocated: "
        + " ;; ".join(problems))
    assert inspected, (
        f"{rel} never mentions {LEGACY_FIG9_DIR} or the defective rasters - "
        f"it is in this parametrization because it is supposed to, so an "
        f"empty inspection is a failure, not a pass")


# ---------------------------------------------------------------------------
# 14. CANONICAL_SCIENCE.json: the author-input baselines are inputs, and the
#     superseded Fig. S.1 baseline is not the current canonical S.1.
#
# The block used to be called "originals_untouched" and listed the
# pre-correction HYBRID COMPOSITE S.1 hash under a neutral key, so a reader
# could reasonably take a5632323... for the current canonical figure. It is
# not: the canonical S.1 was fully regenerated from deposited series.
# ---------------------------------------------------------------------------
SUPERSEDED_S1_BASELINE = (
    "a5632323514961c61a1b367c1cc2c950c93e1beac48cf7f134826e1367664bdc")


def _walk_json(node, path=()):
    if isinstance(node, dict):
        for key, value in node.items():
            yield path + (key,), value
            yield from _walk_json(value, path + (key,))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            yield from _walk_json(item, path + (str(i),))


def test_author_input_baselines_are_scoped_and_not_called_originals(canonical):
    keys = {p[-1] for p, _ in _walk_json(canonical)}
    assert "originals_untouched" not in keys, (
        "the neutral key 'originals_untouched' is back; author-supplied "
        "inputs must not be presented as untouched canonical originals")
    assert "author_input_baselines_untouched" in keys, (
        "the author-input baseline block is missing from "
        "docs/CANONICAL_SCIENCE.json")

    block = next(v for p, v in _walk_json(canonical)
                 if p[-1] == "author_input_baselines_untouched")
    assert isinstance(block, dict)
    note = block.get("scope_note", "")
    assert "AUTHOR-INPUT BASELINES ONLY" in note, (
        "the baseline block does not scope itself as author input")
    assert "not current canonical outputs" in note, (
        "the baseline block does not deny being a current canonical output")


def test_superseded_figS1_baseline_is_labelled_superseded(canonical):
    """a5632323... may appear, but never unlabelled."""
    hits = [(p, v) for p, v in _walk_json(canonical)
            if isinstance(v, str) and SUPERSEDED_S1_BASELINE in v]
    assert hits, (
        "the superseded Fig. S.1 author-input baseline is no longer recorded "
        "anywhere; it is provenance and must be retained, not deleted")
    for path, value in hits:
        context = " ".join(path) + " " + value
        assert HIST_CLAUSE.search(context), (
            f"{'.'.join(path)} carries the superseded Fig. S.1 baseline "
            f"{SUPERSEDED_S1_BASELINE[:8]}... with no superseded/historical "
            f"label; a reader would take it for the current canonical S.1")

    # And the current canonical S.1 must be the identity CSV's figure, not it.
    s1 = _identity()["Fig. S.1."]
    assert s1["manuscript_final_sha256"] != SUPERSEDED_S1_BASELINE, (
        "the identity CSV now names the superseded hybrid composite as the "
        "canonical Fig. S.1")
    assert s1["reproduction_class"] == "data_generated", (
        "Fig. S.1 must remain data_generated: its panels are regenerated "
        "from the deposited GHCN-Daily and ERA5 series")
