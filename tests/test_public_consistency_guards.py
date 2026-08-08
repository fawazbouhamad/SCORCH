"""Guards against stale science re-entering the public-facing surfaces.

The pre-release v1.0.0 remediation replaced the unweighted PCA-origin locations with
raw-Celsius Tmax-weighted centroids. Everything downstream of *location*
changed: the LGCP fit, the cross-validation distances, the sector counts and
the centroid-dependent figures. These tests fail if any superseded value or
any scientifically wrong description of the heatwave definition reappears in
an active record.

Superseded values are permitted ONLY inside the explicitly historical
`legacy_unweighted_baseline` namespace of docs/CANONICAL_SCIENCE.json.
"""
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _read(rel):
    return (REPO / rel).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def canonical():
    return json.loads(_read("docs/CANONICAL_SCIENCE.json"))


# ---------------------------------------------------------------------------
# 1. The weighted results must be authoritative under the NORMAL keys
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
    assert cv["area_weighted_rank_mean"] == pytest.approx(0.6438, abs=1e-4)
    assert cv["area_weighted_rank_median"] == pytest.approx(0.6801, abs=1e-4)
    z = cv["mean_distance_by_zone_km"]
    assert z["top10"] == pytest.approx(389.670139, abs=1e-6)
    assert z["top20"] == pytest.approx(231.807728, abs=1e-6)
    assert z["top30"] == pytest.approx(151.672110, abs=1e-6)
    assert z["top50"] == pytest.approx(69.064508, abs=1e-6)


def test_superseded_fit_is_quarantined_as_historical(canonical):
    """The unweighted baseline may survive only under the legacy namespace."""
    legacy = canonical["legacy_unweighted_baseline"]
    assert "HISTORICAL" in legacy["status"].upper()
    assert legacy["lgcp"]["parameters"]["intercept"] == pytest.approx(
        -11.352611, abs=1e-6)
    # and the staging keys must not come back
    assert "lgcp_tmax_weighted" not in canonical
    assert "cross_validation_tmax_weighted" not in canonical


def test_stale_cv_distance_tuple_absent_outside_legacy(canonical):
    """438 / 286 / 181 / 81 km were the UNWEIGHTED zone distances."""
    active = dict(canonical)
    active.pop("legacy_unweighted_baseline", None)
    blob = json.dumps(active)
    for stale in ("438", "286", "181", "81"):
        for zone in ("top10", "top20", "top30", "top50"):
            assert f'"{zone}": {stale}' not in blob
    assert canonical["cross_validation"].get("heldout_mean_distance_km") != 286
    assert canonical["cross_validation"].get("heldout_median_distance_km") != 173


def test_sector_counts_are_the_weighted_ones(canonical):
    w = canonical["sector_counts_38_48E_29_37N"]["tmax_weighted"]
    assert w["structures"] == "154/760"
    assert w["daily_largest"] == "153/395"
    assert w["event_largest"] == "19/51"


# ---------------------------------------------------------------------------
# 2. README must describe the heatwave definition correctly
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def readme_flat():
    return " ".join(_read("README.md").split()).lower()


@pytest.mark.parametrize("wrong", [
    "calendar-day 95th percentile",
    "calendar-day 95th-percentile",
    "per-calendar-day",
    "three consecutive exceedance days",
    "dbscan over the exceeding boxes",
    "dbscan groups the exceeding boxes",
])
def test_readme_rejects_wrong_heatwave_description(readme_flat, wrong):
    assert wrong not in readme_flat, f"README reintroduced: {wrong!r}"


def test_readme_states_the_correct_definition(readme_flat):
    assert "pooled across" in readme_flat and "1940" in readme_flat
    assert "greater than or equal to" in readme_flat
    assert "two consecutive" in readme_flat and "non-exceedance" in readme_flat
    assert "heatwave-labeled cells" in readme_flat
    assert "bridged" in readme_flat


def test_readme_does_not_let_dbscan_create_events(readme_flat):
    """Compound events are maximal runs of selected days, not a clustering
    product."""
    assert ("not any clustering step" in readme_flat
            or "purely temporal" in readme_flat)


# ---------------------------------------------------------------------------
# 3. The weighted-centroid reproduction stage must stay wired in
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("cfg", [
    "configs/reproduction_fast.yaml",
    "src/scorch/configs/reproduction_fast.yaml",
])
def test_weighted_centroid_stage_present(cfg):
    import yaml
    stages = yaml.safe_load(_read(cfg))["stages"]
    names = [s["name"] for s in stages]
    assert "weighted-centroids" in names, f"{cfg} dropped the weighted stage"
    assert names.index("weighted-centroids") > names.index("rebuild-catalog")


# ---------------------------------------------------------------------------
# 4. Weighting convention must not be called an "absolute" temperature level
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("rel", [
    "src/scorch/_kernel/tmax_weighted_centroid.py",
    "scripts/figures/common/tmax_weighted_centroid.py",
    "docs/CANONICAL_SCIENCE.json",
])
def test_no_absolute_temperature_wording(rel):
    t = _read(rel).lower()
    for bad in ('"absolute tmax"', "absolute observed level"):
        assert bad not in t, f"{rel} describes Celsius as an absolute level"


# ===========================================================================
# 5. ACTIVE EVIDENCE COLUMNS - not just headline labels (Phase 2.1B)
# ===========================================================================
WEIGHTED_LGCP = ("-11.457776", "-0.016147", "0.066264", "0.546415",
                 "-0.010951", "1.642911", "272.455153")
UNWEIGHTED_LGCP = ("-11.352611", "-0.016062", "0.063142", "0.464404",
                   "-0.007187", "1.647219", "287.707960")
ZONES_WEIGHTED = "389.670139/231.807728/151.672110/69.064508"
ZONES_UNWEIGHTED = "437.854964/285.656041/180.807535/81.475518"
FIGD_HASH = "88f9e177cf396d0d20325dbcea07c31b5838b49306b7847425d5231a2f993e72"
FIGD_SUPERSEDED = "b7c48232d9f48c9dbf29291470562699590f7ed4f5be50ecb7087f37684574ae"

CANONICAL_FIGURE_HASHES = {
    "Fig. 1.": "d3e0ca5eeefd811777480a412e5f4ec7f79007f7b2f15b2dc150ff3808f99280",
    "Fig. 4.": "74ea37f0ab54453a7c28895edd381cad3a75c199af88c60de67154721db23484",
    "Fig. 5.": "5eeec34640e91ea346165b06aa81a14c2ed2eaa055cc70395863b34f2621085d",
    "Fig. 6.": "ac2ebeaf5037fe7dafb00daf595aff91485b52c2af89127a52006e508c07afcb",
    "Fig. 7.": "769161f776249555f48be2dec12456a8a0afc26d8b2e7627f8df6e933eadeadd",
    "Fig. 12.": "ce09ab2fa492c5b1321031d07aadf6bcfe819d21159c3c269e380335d596801b",
    "Fig. D.": FIGD_HASH,
    "Fig. S.1.": "d125a87d0f3a875a737a9175c43f133f9d353adf95bc307e4c3885731d38e634",
}


def _matrix_row(substr):
    import csv
    with open(REPO / "docs/REPRODUCIBILITY_MATRIX.csv", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        for r in rd:
            if substr in " | ".join(v or "" for v in r.values()):
                return r
    raise AssertionError(f"matrix row not found: {substr}")


def test_matrix_lgcp_row_evidence_columns_are_weighted():
    """Not just the label: expected/reproduced columns must carry the weighted fit."""
    row = _matrix_row("variant3 LGCP")
    blob = " | ".join(v or "" for v in row.values())
    for v in WEIGHTED_LGCP:
        assert v in blob, f"LGCP row missing weighted value {v}"
    for v in UNWEIGHTED_LGCP:
        assert v not in blob, f"LGCP row still asserts unweighted value {v}"


def test_matrix_cv_row_uses_verified_distance():
    row = _matrix_row("mean held-out centroid distance")
    blob = " | ".join(v or "" for v in row.values())
    assert "85.009602" in blob
    assert "84.934649" not in blob and "84.935" not in blob


def test_matrix_zone_distance_row_is_corrected():
    row = _matrix_row("concentration-zone distances")
    blob = " | ".join(v or "" for v in row.values())
    assert ZONES_WEIGHTED in blob
    assert ZONES_UNWEIGHTED not in blob, "unweighted zone distances still asserted"


def test_matrix_figure_d_identity_is_canonical():
    row = _matrix_row("Figure D occurrence-level five-fold")
    blob = " | ".join(v or "" for v in row.values())
    assert FIGD_HASH in blob, "Figure D row does not carry the canonical hash"
    if FIGD_SUPERSEDED in blob:
        assert "superseded" in blob.lower(),             "superseded Figure D hash present without a superseded label"


def test_figure_provenance_figure_d_zone_claim_corrected():
    t = _read("docs/FIGURE_PROVENANCE.csv")
    assert "438/286/181/81 km are unchanged and are asserted at run time." not in t
    assert "389.670139/231.807728/151.672110/69.064508" in t


@pytest.mark.parametrize("label,sha", sorted(CANONICAL_FIGURE_HASHES.items()))
def test_active_figure_identities_match_canonical_record(label, sha):
    import csv
    with open(REPO / "docs/MANUSCRIPT_FIGURE_IDENTITY.csv", encoding="utf-8") as f:
        rows = {r["label"].strip(): r for r in csv.DictReader(f)}
    assert label in rows, f"{label} missing from MANUSCRIPT_FIGURE_IDENTITY.csv"
    assert rows[label]["manuscript_final_sha256"] == sha


@pytest.mark.parametrize("label", ["Fig. 1.", "Fig. 4."])
def test_figures_1_and_4_declared_deterministic(label):
    import csv
    with open(REPO / "docs/MANUSCRIPT_FIGURE_IDENTITY.csv", encoding="utf-8") as f:
        rows = {r["label"].strip(): r for r in csv.DictReader(f)}
    assert rows[label]["reproduction_class"] == "deterministic_producer"


@pytest.mark.parametrize("rel", ["docs/REPRODUCIBILITY_REPORT.md",
                                 "docs/SANITIZATION_NOTES.md"])
def test_no_claim_that_figures_1_and_4_lack_producers(rel):
    flat = " ".join(_read(rel).split()).lower()
    for bad in ("no runnable producer exists and none is claimed",
                "no runnable producer exists (frozen assets only)",
                "without a shipped producing command"):
        assert bad not in flat, f"{rel} still denies the Fig 1/4 producers"


def test_legacy_phi_not_presented_as_current_manuscript(canonical):
    legacy = json.dumps(canonical["legacy_unweighted_baseline"])
    assert "The manuscript's phi = 287.7" not in legacy
    assert "pre-remediation manuscript candidate" in legacy


# ===========================================================================
# 6. MANIFEST BYTE-SCOPE SEPARATION (archive CRLF vs git-normalized LF)
# ===========================================================================
@pytest.fixture(scope="module")
def manifest():
    return json.loads(_read("remediation/corrected_outputs/SHA256_MANIFEST.json"))


def test_manifest_declares_both_byte_scopes(manifest):
    s = manifest["scopes"]
    assert "archive_bytes" in s and "repository_normalized_bytes" in s
    assert manifest["scopes"]["archive_bytes"]["files"] == manifest["files"],         "legacy 'files' key must remain identical to the archive scope"
    assert "not interchangeable" in manifest["scope_note"].lower()


def test_manifest_scopes_are_not_conflated(manifest):
    """The two scopes genuinely differ; collapsing them would be a real error."""
    a = manifest["scopes"]["archive_bytes"]["files"]
    r = manifest["scopes"]["repository_normalized_bytes"]["files"]
    assert set(a) == set(r)
    differing = [p for p in a if a[p]["sha256"] != r[p]["sha256"]]
    assert differing, ("archive and repository scopes are identical - either "
                       "normalization changed or the scopes were conflated")


def test_repository_scope_matches_what_git_actually_stores(manifest):
    """A fresh clone must verify against repository_normalized_bytes."""
    import hashlib
    import subprocess
    r = manifest["scopes"]["repository_normalized_bytes"]["files"]
    checked = 0
    for path, meta in list(r.items())[:6]:
        out = subprocess.run(["git", "show", f"HEAD:{path}"],
                             capture_output=True, cwd=REPO)
        if out.returncode:
            continue
        assert hashlib.sha256(out.stdout).hexdigest() == meta["sha256"], path
        checked += 1
    assert checked, "no manifest entry could be checked against git"


# ===========================================================================
# 7. STRUCTURED FIGURE CROSSWALK + CURRENT-vs-HISTORICAL SWEEP (Phase 2.1C)
# ===========================================================================
import csv as _csv
import re as _re

_IN_SCOPE = {"Fig. 1.": "Figure 1", "Fig. 4.": "Figure 4", "Fig. 5.": "Figure 5",
             "Fig. 6.": "Figure 6", "Fig. 7.": "Figure 7", "Fig. 12.": "Figure 12",
             "Fig. D.": "Figure D"}

# fields that carry a CURRENT identity (historical fields excluded by name)
_CURRENT_FIELDS = {
    "docs/REPRODUCIBILITY_MATRIX.csv":
        ["canonical_expected", "reproduced_value", "checksum"],
    "docs/FIGURE_PROVENANCE.csv":
        ["deployed_embed_sha256", "reproduced_output_sha256", "reproduction_result"],
}

_HIST_MARK = _re.compile(
    r"histor|supersed|pre-remediat|legacy|earlier|previous|deprecat|"
    r"approved.original|prior|formerly|not current|no longer", _re.I)


def _identity():
    with open(REPO / "docs/MANUSCRIPT_FIGURE_IDENTITY.csv", encoding="utf-8") as f:
        return {r["label"].strip(): r for r in _csv.DictReader(f)}


def test_figure_crosswalk_current_hashes_agree_everywhere():
    """Every in-scope figure's CURRENT-identity fields in the matrix and the
    provenance table must carry the canonical hash. A different hash is allowed
    only when the same cell explicitly marks it historical/superseded."""
    ident = _identity()
    canon = {name: ident[lab]["manuscript_final_sha256"]
             for lab, name in _IN_SCOPE.items()}
    problems = []
    for path, fields in _CURRENT_FIELDS.items():
        with open(REPO / path, encoding="utf-8") as f:
            for i, row in enumerate(_csv.DictReader(f), 2):
                blob = " | ".join(v or "" for v in row.values())
                names = [n for n in _IN_SCOPE.values()
                         if _re.search(rf"{_re.escape(n)}", blob)]
                if not names:
                    continue
                for fld in fields:
                    val = row.get(fld) or ""
                    for h in _re.findall(r"[0-9a-f]{64}", val):
                        if any(h == canon[n] for n in names):
                            continue
                        if _HIST_MARK.search(val):
                            continue
                        problems.append(f"{path} row {i} / {fld} ({','.join(names)}): {h[:16]}...")
    assert not problems, ("unclassified non-canonical figure hashes: "
                          + "; ".join(problems))


_STALE_TOKENS = {
    "-11.352611": "LGCP intercept (unweighted)",
    "0.464404": "LGCP mean_tmax_z (unweighted)",
    "1.647219": "LGCP sigma2 (unweighted)",
    "287.707960": "LGCP scale (unweighted)",
    "287.70796": "LGCP scale (unweighted)",
    "84.934649": "CV distance (unweighted)",
    "437.854964": "zone top10 (unweighted)",
    "285.656041": "zone top20 (unweighted)",
    "438/286/181/81": "zone tuple (unweighted)",
    "212 passed": "historical acceptance count",
    "244 passed": "historical acceptance count",
}

_SWEEP_FILES = [
    "docs/REPRODUCIBILITY_MATRIX.csv", "docs/REPRODUCIBILITY_REPORT.md",
    "docs/FIGURE_PROVENANCE.csv", "docs/CANONICAL_SCIENCE.json",
    "docs/ALIGNMENT_DECISIONS.md", "docs/SANITIZATION_NOTES.md",
    "CHANGELOG.md", "README.md",
    "remediation/MANUSCRIPT_IMPACT_INVENTORY.md",
    "remediation/corrected/event_global_max_algorithm/build_manifest.json",
]


@pytest.mark.parametrize("rel", _SWEEP_FILES)
def test_no_unclassified_superseded_values(rel):
    """Superseded values may appear ONLY in a cell/line that marks them as
    historical. Bare numbers are never banned globally - classification is
    contextual."""
    p = REPO / rel
    problems = []
    if rel.endswith(".csv"):
        with open(p, encoding="utf-8") as f:
            for i, row in enumerate(_csv.DictReader(f), 2):
                for fld, val in row.items():
                    if not val or _HIST_MARK.search(val):
                        continue
                    for tok, desc in _STALE_TOKENS.items():
                        if tok in val:
                            problems.append(f"row {i} / {fld}: {tok} [{desc}]")
    else:
        lines = p.read_text(encoding="utf-8").splitlines()
        in_legacy = False
        for i, line in enumerate(lines, 1):
            if rel.endswith(".json"):
                if "legacy_unweighted_baseline" in line or "_historical" in line:
                    in_legacy = True
                elif in_legacy and _re.match(r'^  "[a-z_]+":', line):
                    in_legacy = False
            ctx = " ".join(lines[max(0, i - 4):i + 3])
            if in_legacy or _HIST_MARK.search(ctx):
                continue
            for tok, desc in _STALE_TOKENS.items():
                if tok in line:
                    problems.append(f"line {i}: {tok} [{desc}]")
    assert not problems, (f"{rel} presents superseded values as current: "
                          + "; ".join(problems))


def test_current_acceptance_count_is_recorded(canonical):
    ts = canonical["acceptance"]["test_suite"]
    assert "339 passed" in ts
    assert "test_suite_historical" in canonical["acceptance"]
    assert "HISTORICAL" in canonical["acceptance"]["test_suite_historical"]["status"].upper()


def test_figure12_does_not_claim_plotted_data_unchanged():
    t = _read("docs/REPRODUCIBILITY_MATRIX.csv")
    assert "plotted data and quantile ranks unchanged" not in t
