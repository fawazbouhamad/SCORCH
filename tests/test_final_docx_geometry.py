#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R5 final-DOCX display-geometry and content-identity guards.

The R5 remediation corrected the display geometry of two manuscript
figures (Fig. A / Picture 13 / image13.png and Fig. B / Picture 14 /
image14.png) and the stale cached page count in the supplement's
``docProps/app.xml``. Nothing else in either FINAL DOCX changed. These
guards pin that state:

* Fig. A and Fig. B carry the exact corrected EMU extents, identically
  in ``wp:extent`` and ``pic:spPr/a:xfrm/a:ext``;
* both displayed aspect ratios match the native PNG pixel aspect ratios
  to better than 0.001 %; neither figure is cropped (no ``a:srcRect``);
* all 17 embedded publication images (16 manuscript + 1 supplement)
  retain their canonical SHA-256 hashes, byte for byte;
* the supplement ``docProps/app.xml`` reports ``<Pages>2</Pages>``;
* Table 1's OOXML, both figures' alt text, the visible text (all
  captions and prose), the image relationship table, and the
  no-comments / no-tracked-changes state are unchanged.

Like the whole-file DOCX hash guards in ``test_stale_provenance.py``,
every test skips with a clear message when the FINAL documents are not
present (set ``SCORCH_FINAL_DOCX_DIR`` to enable).
"""
from __future__ import annotations

import hashlib
import os
import re
import struct
import zipfile
from pathlib import Path

import pytest

MANUSCRIPT_NAME = "SCORCH_Manuscript_FINAL_v1.0.0.docx"
SUPPLEMENT_NAME = "SCORCH_Supplementary_Material_FINAL_v1.0.0.docx"

# --- corrected display geometry (EMU), R5 Section A -------------------------
# native 1950 x 1781 px
FIGA = dict(rid="rId20", media="word/media/image13.png",
            cx=5697940, cy=5204119, px=(1950, 1781))
# native 5340 x 7488 px
FIGB = dict(rid="rId21", media="word/media/image14.png",
            cx=4128400, cy=5789038, px=(5340, 7488))

MAX_ASPECT_REL_ERROR = 1e-5          # 0.001 %

# --- canonical publication-image hashes (17 = 16 manuscript + 1 supplement) --
MANUSCRIPT_MEDIA_SHA = {
    "word/media/image1.png":
        "cc561b368f84b298b3ee38a39415799cc31d8ca932fa586a32bd7624831ec787",
    "word/media/image2.png":
        "62c20697282bddc0aa199782dec574fe0d84048ed6d3eaf117c839d31505b46f",
    "word/media/image3.png":
        "cc3ea5e16261601023a3fa2f83ea4885c567de6eb761fee98210942f5bac93f6",
    "word/media/image4.png":
        "d595fb363d0a284abc1f9cc3049661f5786d1e42cf5e30ea3e50cea143a3bcde",
    "word/media/image5.png":
        "7af1b41383a7e519f2574ca6fd27936c9f4bb96ea92a17ca12fd894035556fcc",
    "word/media/image6.png":
        "f45272bc0030022fda3d5bdfdbe51e33b4d96d749e5f120d07cbabef8fb01cfe",
    "word/media/image7.png":
        "5136d35c7e7cc1504afececdff5386d2835826fbb0b0e78f3abd457214cdd6bd",
    "word/media/image8.png":
        "c64f1a16441b3f73d57bde6a75953d261e45cade7d7b7766ca36977aa6bccb6b",
    "word/media/image9.png":
        "7859acbd9ea69047d5a85bda65c4eed25d3592d52c4b0bfaad0a3068226a1431",
    "word/media/image10.png":
        "be5a528857a05843560d277d1c11cee02c944c21bfda1cd24324e13846b1def1",
    "word/media/image11.png":
        "9ada5400232aa424b109fe32f0d22b7fa09ec632be42bda7f8bfa44063c37fd4",
    "word/media/image12.png":
        "6a1a5a767c8c63262633914c484b973acc46696e23e661f8cbc58955cd38d2ac",
    "word/media/image13.png":
        "ca9c49e703aa28fe20dd5a463e57beea5c4adc62e5dd3b0086c05660325acb74",
    "word/media/image14.png":
        "916fed8eafbd535028fd1c1f04f611db58c9b78f9a1d7ee0cdc95567ed1b3fd5",
    "word/media/image15.png":
        "07872152bae8bd2b215bddc8e3db23df4c052824f7ee329eefa64c55eda274e4",
    "word/media/image16.png":
        "b7c48232d9f48c9dbf29291470562699590f7ed4f5be50ecb7087f37684574ae",
}
SUPPLEMENT_MEDIA_SHA = {
    "word/media/image1.png":
        "050a0721509656d7337102fe451a400b2bed35ee967965e19ad444b54675f538",
}

# --- pinned content identities (computed from the R5 FINAL documents) --------
MANUSCRIPT_TABLE1_XML_SHA = (
    "60917600dddfc626e8074b7c7286a8dc7c4d807a60835160d800e8721f509dcf")
MANUSCRIPT_VISIBLE_TEXT_SHA = (
    "c53c72cfcf8c6b74a59c06b666073c5c8db99e08e4f96970f90309d1d40a2739")
SUPPLEMENT_VISIBLE_TEXT_SHA = (
    "c497d78b8e6de3fbd6798397a270489cdbfe4b5181d37e4f5de9e5526b6ac0f5")
MANUSCRIPT_RELS_SHA = (
    "f0eb74f7f984d637d2afcf53b7fce2307126820035ea412fb1fcfc4e776eaee5")

FIGA_ALT_TEXT = (
    "Four nine-by-nine matrices showing the sensitivity of the PCA-ellipse "
    "construction to the sigma scaling of the major and minor axes: "
    "minimum, maximum and average of the sensitivity metric, and a "
    "combined score, with the equal-sigma diagonal outlined.")
FIGB_ALT_TEXT = (
    "Six DBSCAN parameter-selection matrices, one per day of Event 10, "
    "reporting the number of ellipse clusters for each eps and min_samples "
    "combination, with the stable parameter region shaded.")

MANUSCRIPT_IMAGE_RELS = {
    "rId8": "media/image1.png", "rId9": "media/image2.png",
    "rId10": "media/image3.png", "rId11": "media/image4.png",
    "rId12": "media/image5.png", "rId13": "media/image6.png",
    "rId14": "media/image7.png", "rId15": "media/image8.png",
    "rId16": "media/image9.png", "rId17": "media/image10.png",
    "rId18": "media/image11.png", "rId19": "media/image12.png",
    "rId20": "media/image13.png", "rId21": "media/image14.png",
    "rId22": "media/image15.png", "rId23": "media/image16.png",
}
SUPPLEMENT_IMAGE_RELS = {"rId6": "media/image1.png"}


def _find_final_docx(name):
    env = os.environ.get("SCORCH_FINAL_DOCX_DIR")
    if env and (Path(env) / name).exists():
        return Path(env) / name
    for parent in Path(__file__).resolve().parents:
        cand = parent / name
        if cand.exists():
            return cand
    return None


def _open_or_skip(name):
    path = _find_final_docx(name)
    if path is None:
        pytest.skip(f"{name} not present in this checkout "
                    "(set SCORCH_FINAL_DOCX_DIR to enable)")
    return zipfile.ZipFile(path)


def _document_xml(zf):
    return zf.read("word/document.xml").decode("utf-8")


def _drawing_fragment(doc, rid):
    i = doc.find(f'r:embed="{rid}"')
    assert i != -1, f"no drawing embeds {rid}"
    start = doc.rfind("<w:drawing>", 0, i)
    end = doc.find("</w:drawing>", i) + len("</w:drawing>")
    assert start != -1 and end > start
    return doc[start:end]


def _png_size(data):
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    width, height = struct.unpack(">II", data[16:24])
    return width, height


# --- Fig. A / Fig. B exact corrected extents ---------------------------------

@pytest.mark.parametrize("fig", [FIGA, FIGB], ids=["figA", "figB"])
def test_figure_extent_exact_and_matching(fig):
    zf = _open_or_skip(MANUSCRIPT_NAME)
    frag = _drawing_fragment(_document_xml(zf), fig["rid"])
    wp = re.search(r'<wp:extent cx="(\d+)" cy="(\d+)"/>', frag)
    ax = re.search(r'<a:ext cx="(\d+)" cy="(\d+)"/>', frag)
    assert wp and ax, "extent elements missing"
    assert (int(wp.group(1)), int(wp.group(2))) == (fig["cx"], fig["cy"]), (
        f"wp:extent is {wp.groups()}, expected ({fig['cx']}, {fig['cy']})")
    assert (int(ax.group(1)), int(ax.group(2))) == (fig["cx"], fig["cy"]), (
        f"a:xfrm/a:ext is {ax.groups()}, expected ({fig['cx']}, {fig['cy']})"
        " - display extent and shape transform must be identical")


@pytest.mark.parametrize("fig", [FIGA, FIGB], ids=["figA", "figB"])
def test_figure_display_aspect_matches_native(fig):
    zf = _open_or_skip(MANUSCRIPT_NAME)
    width, height = _png_size(zf.read(fig["media"]))
    assert (width, height) == fig["px"], (
        f"{fig['media']} native pixel size changed")
    native = width / height
    display = fig["cx"] / fig["cy"]
    rel_err = abs(display - native) / native
    assert rel_err < MAX_ASPECT_REL_ERROR, (
        f"{fig['media']}: display aspect {display} deviates from native "
        f"{native} by {rel_err:.2e} (limit {MAX_ASPECT_REL_ERROR:.0e})")


@pytest.mark.parametrize("fig", [FIGA, FIGB], ids=["figA", "figB"])
def test_figure_not_cropped_and_centered(fig):
    zf = _open_or_skip(MANUSCRIPT_NAME)
    doc = _document_xml(zf)
    frag = _drawing_fragment(doc, fig["rid"])
    assert "srcRect" not in frag, "unexpected crop (a:srcRect) on figure"
    i = doc.find(frag)
    pstart = doc.rfind("<w:p ", 0, i)
    para_head = doc[pstart:i]
    assert '<w:jc w:val="center"/>' in para_head, (
        "figure paragraph is no longer centered")


# --- 17 canonical publication images -----------------------------------------

@pytest.mark.parametrize("name,expected", [
    (MANUSCRIPT_NAME, MANUSCRIPT_MEDIA_SHA),
    (SUPPLEMENT_NAME, SUPPLEMENT_MEDIA_SHA),
], ids=["manuscript-16", "supplement-1"])
def test_embedded_publication_images_byte_identical(name, expected):
    zf = _open_or_skip(name)
    media = {n for n in zf.namelist() if n.startswith("word/media/")}
    assert media == set(expected), (
        f"{name}: media member set changed: {sorted(media)}")
    for member, sha in expected.items():
        actual = hashlib.sha256(zf.read(member)).hexdigest()
        assert actual == sha, (
            f"{name}:{member}: embedded image bytes changed "
            f"({actual} != {sha})")


def test_seventeen_publication_images_total():
    assert len(MANUSCRIPT_MEDIA_SHA) + len(SUPPLEMENT_MEDIA_SHA) == 17


# --- supplement cached metadata ----------------------------------------------

def test_supplement_app_xml_pages_is_two():
    zf = _open_or_skip(SUPPLEMENT_NAME)
    app = zf.read("docProps/app.xml").decode("utf-8")
    m = re.search(r"<Pages>(\d+)</Pages>", app)
    assert m, "docProps/app.xml has no Pages element"
    assert m.group(1) == "2", (
        f"supplement app.xml Pages is {m.group(1)}, expected the actual "
        "page count 2 (the stale cached value was 4)")


# --- unchanged content: Table 1, alt text, captions/prose, comments, rels ----

def test_table1_ooxml_unchanged():
    zf = _open_or_skip(MANUSCRIPT_NAME)
    tables = re.findall(r"<w:tbl>.*?</w:tbl>", _document_xml(zf), flags=re.S)
    assert len(tables) == 1, f"expected exactly 1 table, found {len(tables)}"
    actual = hashlib.sha256("".join(tables).encode("utf-8")).hexdigest()
    assert actual == MANUSCRIPT_TABLE1_XML_SHA, (
        "Table 1 OOXML changed - the R5 pass must not touch Table 1")


def test_figure_alt_text_preserved():
    zf = _open_or_skip(MANUSCRIPT_NAME)
    doc = _document_xml(zf)
    for fig, alt in ((FIGA, FIGA_ALT_TEXT), (FIGB, FIGB_ALT_TEXT)):
        frag = _drawing_fragment(doc, fig["rid"])
        # once on wp:docPr, once on pic:cNvPr
        assert frag.count(f'descr="{alt}"') == 2, (
            f"alt text for {fig['media']} missing or altered")


@pytest.mark.parametrize("name,expected", [
    (MANUSCRIPT_NAME, MANUSCRIPT_VISIBLE_TEXT_SHA),
    (SUPPLEMENT_NAME, SUPPLEMENT_VISIBLE_TEXT_SHA),
], ids=["manuscript", "supplement"])
def test_visible_text_including_captions_unchanged(name, expected):
    zf = _open_or_skip(name)
    text = "".join(re.findall(r"<w:t(?: [^>]*)?>(.*?)</w:t>",
                              _document_xml(zf), flags=re.S))
    actual = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert actual == expected, (
        f"{name}: visible text (prose/captions) changed - the R5 pass is "
        "display-geometry and cached-metadata only")


def test_figure_captions_present_after_figures():
    zf = _open_or_skip(MANUSCRIPT_NAME)
    doc = _document_xml(zf)
    for fig, head in ((FIGA, "Fig. A."), (FIGB, "Fig. B.")):
        i = doc.find(f'r:embed="{fig["rid"]}"')
        window = "".join(re.findall(r"<w:t(?: [^>]*)?>(.*?)</w:t>",
                                    doc[i:i + 7000]))
        assert window.startswith(head), (
            f"caption {head!r} no longer follows its figure")


@pytest.mark.parametrize("name", [MANUSCRIPT_NAME, SUPPLEMENT_NAME],
                         ids=["manuscript", "supplement"])
def test_no_comments_and_no_tracked_changes(name):
    zf = _open_or_skip(name)
    comment_members = [n for n in zf.namelist() if "comment" in n.lower()]
    assert not comment_members, f"unexpected comment parts: {comment_members}"
    doc = _document_xml(zf)
    assert "<w:ins " not in doc and "<w:del " not in doc, (
        "tracked changes present in a FINAL document")


@pytest.mark.parametrize("name,expected", [
    (MANUSCRIPT_NAME, MANUSCRIPT_IMAGE_RELS),
    (SUPPLEMENT_NAME, SUPPLEMENT_IMAGE_RELS),
], ids=["manuscript", "supplement"])
def test_media_relationships_unchanged(name, expected):
    zf = _open_or_skip(name)
    rels = zf.read("word/_rels/document.xml.rels").decode("utf-8")
    pairs = dict(re.findall(
        r'Id="([^"]+)"[^>]*Target="(media/[^"]+)"', rels))
    assert pairs == expected, f"{name}: image relationship table changed"


def test_manuscript_rels_part_byte_identical():
    zf = _open_or_skip(MANUSCRIPT_NAME)
    actual = hashlib.sha256(
        zf.read("word/_rels/document.xml.rels")).hexdigest()
    assert actual == MANUSCRIPT_RELS_SHA, (
        "word/_rels/document.xml.rels changed byte-wise")
