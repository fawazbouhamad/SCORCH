"""Guards for the README figure references, licensing metadata and citation.

These lock in the invariants established by the final repository
finalization round so that a later edit cannot silently:

  * point the README at a non-canonical or re-encoded copy of Figure 1 or
    Figure 4, or drop their accessible alt text;
  * leave a licence identifier behind at MIT after the GPL-3.0-only
    migration, or truncate the verbatim GPL text;
  * badge an unpublished Zenodo record as a live public archive;
  * reintroduce an incomplete journal article as the machine-readable
    preferred citation.
"""
import hashlib
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

FIG01_PNG = "assets/frozen_figures/fig01/Figure_01.png"
FIG04_PNG = "assets/frozen_figures/fig04/Figure_04.png"

FIG01_SHA = "d3e0ca5eeefd811777480a412e5f4ec7f79007f7b2f15b2dc150ff3808f99280"
FIG04_SHA = "74ea37f0ab54453a7c28895edd381cad3a75c199af88c60de67154721db23484"

DATA_DOI = "10.5281/zenodo.21717752"
SOFTWARE_DOI = "10.5281/zenodo.21717874"


def _sha256(rel):
    return hashlib.sha256((REPO / rel).read_bytes()).hexdigest()


def _read(rel):
    return (REPO / rel).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def readme():
    return _read("README.md")


# ---------------------------------------------------------------------------
# README figure routing
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("rel,sha", [(FIG01_PNG, FIG01_SHA), (FIG04_PNG, FIG04_SHA)])
def test_readme_figure_targets_are_the_canonical_assets(readme, rel, sha):
    """The README must reference the canonical frozen asset by relative path,
    and that asset must still hash to the approved figure."""
    assert rel in readme, f"README no longer references {rel}"
    assert (REPO / rel).is_file(), f"{rel} is missing"
    assert _sha256(rel) == sha, (
        f"{rel} changed: {_sha256(rel)} != approved {sha}")


def test_readme_figures_have_accessible_alt_text(readme):
    """Both figure images carry meaningful alt text (not empty, not a stub)."""
    for src in (FIG01_PNG, FIG04_PNG):
        m = re.search(r'<img[^>]*src="' + re.escape(src) + r'"[^>]*>',
                      readme, re.S)
        assert m, f"no <img> element for {src}"
        alt = re.search(r'alt="([^"]*)"', m.group(0))
        assert alt, f"{src} has no alt attribute"
        assert len(alt.group(1)) > 40, f"{src} alt text is too short to be useful"


def test_readme_does_not_embed_a_reencoded_figure_copy(readme):
    """No screenshot/derived copy may stand in for the canonical assets."""
    for bad in ("figure_01_readme", "figure_04_readme", "readme_fig",
                "screenshot"):
        assert bad not in readme.lower(), f"README references a derived copy: {bad}"


# ---------------------------------------------------------------------------
# Licensing
# ---------------------------------------------------------------------------
def test_license_file_is_verbatim_gpl3():
    text = _read("LICENSE")
    assert "GNU GENERAL PUBLIC LICENSE" in text
    assert "Version 3, 29 June 2007" in text
    # the operative sections must all be present, i.e. not a summary stub
    assert "TERMS AND CONDITIONS" in text
    assert "END OF TERMS AND CONDITIONS" in text
    assert len(text.splitlines()) > 600, "LICENSE looks truncated"
    assert "MIT License" not in text


def test_software_license_identifiers_are_gpl3_only():
    assert 'license = { text = "GPL-3.0-only" }' in _read("pyproject.toml")
    assert "GNU General Public License v3 (GPLv3)" in _read("pyproject.toml")
    assert "license: GPL-3.0-only" in _read("CITATION.cff")
    assert '"license": "GPL-3.0-only"' in _read(".zenodo.json")


def test_readme_states_gpl_and_path_specific_terms(readme):
    assert "GPL-3.0-only" in readme
    assert "docs/LICENSES_AND_ATTRIBUTION.md" in readme
    # citation must never be presented as a licence condition
    flat = " ".join(readme.split())
    assert "not an additional condition of the GPL" in flat


def test_licensing_history_records_the_prior_mit_grant():
    text = _read("docs/LICENSING_HISTORY.md")
    assert "MIT" in text and "GPL-3.0-only" in text
    assert "retroactively" in text or "remain under the licence" in text


def test_no_stale_mit_identifier_in_software_metadata():
    """The migrated files must not still declare MIT for the software."""
    assert "License :: OSI Approved :: MIT License" not in _read("pyproject.toml")
    assert not re.search(r"^license: MIT\s*$", _read("CITATION.cff"), re.M)


# ---------------------------------------------------------------------------
# Citation and unpublished-record honesty
# ---------------------------------------------------------------------------
def test_citation_declares_no_preferred_citation_while_unpublished():
    """An article with no DOI must not be the machine-readable preferred
    citation (it would make tools emit an unverifiable reference)."""
    cff = _read("CITATION.cff")
    assert not re.search(r"^preferred-citation:", cff, re.M), (
        "preferred-citation reintroduced before the article is published")
    assert SOFTWARE_DOI in cff


def test_reserved_dois_are_not_badged_as_live_archives(readme):
    """While the Zenodo records are drafts, no badge may imply a live
    public archive."""
    assert "zenodo.org/badge/DOI" not in readme, (
        "Zenodo archive badge present while the records are unpublished")
    assert "Reserved DOI; record forthcoming" in readme
    for doi in (DATA_DOI, SOFTWARE_DOI):
        assert doi in readme


def test_readme_does_not_overclaim_availability_or_scope(readme):
    low = " ".join(readme.split()).lower()
    # SCORCH does not track structures, and makes no risk/forecast claim
    assert "does not track structures across days" in low
    assert "not a probability, risk, hazard" in low


def test_readme_relative_links_resolve(readme):
    """Every relative markdown/img link in the README points at a real file."""
    targets = re.findall(r"\]\((?!https?:)([^)#]+)\)", readme)
    targets += re.findall(r'<img[^>]*src="(?!https?:)([^"]+)"', readme)
    missing = [t for t in targets if not (REPO / t).exists()]
    assert not missing, f"README links to missing paths: {missing}"
