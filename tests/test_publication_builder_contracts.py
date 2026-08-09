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
def test_figures_1_and_4_remain_cc_by_pending(readme):
    rows = _rights_rows(readme)
    frozen = [r for r in rows if "frozen_figures" in r]
    assert len(frozen) == 1, f"expected one frozen_figures rights row: {rows}"
    row = frozen[0]
    assert "Fig. 1, 4" in row, row
    assert "PENDING" in row, (
        f"Figures 1 and 4 must remain CC BY PENDING: {row!r}")
    assert "not yet in force" in row, row
    assert "Najibi" in row, (
        "the pending row must still name the coauthor whose written "
        "authorization is required")


def test_no_active_cc_by_is_generated_for_figures_1_and_4(readme):
    """PENDING must not have quietly become an in-force grant."""
    rows = _rights_rows(readme)
    frozen = next(r for r in rows if "frozen_figures" in r)
    active = ("CC BY 4.0 for the authors' contribution only",
              "CC BY 4.0 for the authors' contributions")
    for phrase in active:
        assert phrase not in frozen, (
            f"the Figures 1/4 row carries an ACTIVE CC BY grant ({phrase!r}), "
            f"but D6 authorization is still outstanding: {frozen!r}")


# ---------------------------------------------------------------------------
# 5. Nothing was materialized by this module.
# ---------------------------------------------------------------------------
def test_readme_generation_is_pure_text(readme):
    """Guards the guard: readme_text must be pure text generation."""
    assert isinstance(readme, str) and readme.strip()
