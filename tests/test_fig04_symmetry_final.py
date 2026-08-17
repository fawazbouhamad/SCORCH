#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression guards for the author-approved Figure 4 symmetry round.

The 2026-08 symmetry round squared the Type 4 motif onto a symmetric
lattice, levelled the Type 3 rows / arrows / ellipses, and translated the
six Type 3 time labels horizontally onto their circle columns. These guards
prove, from the artifacts themselves rather than from recorded expectations,
that:

* the canonical producer regenerates the shipped figure from the immutable
  donor, in one pass, without reading its own output. Two DISTINCT claims are
  kept apart here: the raw-RGB **pixels** are reproduced on every platform and
  that is asserted unconditionally, whereas exact PNG **byte** identity
  (SHA-256 ``74ea37f0...``) is a property of the canonical encoder stack
  (Pillow 12.2.x with zlib 1.3.1) and is asserted only there. A Linux audit
  once reproduced the pixels exactly while emitting different PNG bytes; both
  observations were correct, and claiming byte identity unconditionally was
  the error;
* Type 4 still reads horizontally two -> one -> two;
* the Type 4 lattice is symmetric within the approved 1 px tolerance;
* all six Type 3 labels are centred on their columns within 1 px;
* those labels are EXACT integer translations of the donor's glyph pixels
  (no redraw, resample, recolour or retype);
* no prohibited region (Type 1, Type 2, dividers, titles, typology names)
  changed by a single raw-RGB pixel;
* the publication-output Figure 4 equals the canonical asset;
* the Figure 4 embedded in the final DOCX equals the canonical asset.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("scipy")
from scipy import ndimage  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
FIG04 = REPO / "assets" / "frozen_figures" / "fig04" / "Figure_04.png"
DONOR = (REPO / "scripts" / "figures" / "fig04" / "donor" /
         "Figure_04_approved_horizontal.png")
PRODUCER = (REPO / "scripts" / "figures" / "fig04" /
            "make_fig04_symmetry_final.py")
PUB = (REPO / "publication_outputs" / "figures" / "Figure_04" /
       "Figure_04.png")
FINAL_DOCX = (REPO / "manuscript_revision_output" /
              "figure04_symmetry_integration_round" /
              "SCORCH_Manuscript_FINAL_Figure04Symmetry.docx")

APPROVED_SHA = ("74ea37f0ab54453a7c28895edd381cad3a75c199af88c60de6715472"
                "1db23484")
DONOR_SHA = ("c35d9ed6ccea8d7f6d8ec8ad92d65fb3c5dd2df16d82b015b7a531b2eef"
             "c829f")
CANVAS = (4500, 2531)
PURPLE = (112, 48, 160)
TOL = 1.0

# label bands and the approved horizontal translations (dy is 0 for all six)
LABEL_BANDS = ((2260, 1100, 3366, 1200), (2260, 1930, 3366, 2030))
LABEL_MOVES = {(1100, 0): -9, (1100, 1): 8, (1100, 2): 7,
               (1930, 0): -15, (1930, 1): 1, (1930, 2): 1}
LABEL_GROUP_GAP = 80

# No module-wide skip. The canonical asset, the immutable donor and the active
# producer are TRACKED files: a checkout missing any of them is broken, and a
# broken checkout must go red rather than quietly green.
def test_required_figure04_inputs_are_present():
    missing = [str(p.relative_to(REPO)) for p in (FIG04, DONOR, PRODUCER)
               if not p.is_file()]
    assert not missing, (
        f"tracked Figure 4 inputs are missing from this checkout: {missing}")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _rgb(p: Path) -> np.ndarray:
    from PIL import Image
    im = Image.open(p)
    assert im.size == CANVAS and im.mode == "RGB"
    return np.array(im)


def _purple_components(rgb):
    d = np.abs(rgb.astype(int) - np.array(PURPLE)).sum(axis=2)
    m = d < 90
    m[:, :3378] = False
    m[:900, :] = False
    lab, _n = ndimage.label(m)
    out = []
    for i, sl in enumerate(ndimage.find_objects(lab), start=1):
        core = (lab[sl] == i)
        area = int(core.sum())
        if area < 300:
            continue
        ys, xs = np.nonzero(core)
        out.append({"area": area,
                    "cx": float(xs.mean()) + sl[1].start,
                    "cy": float(ys.mean()) + sl[0].start})
    out.sort(key=lambda c: -c["area"])
    return out


def _label_groups(rgb, band):
    """Ink components of one label band, clustered into the three groups."""
    x0, y0, x1, y1 = band
    ink = np.zeros(rgb.shape[:2], bool)
    ink[y0:y1, x0:x1] = np.any(rgb[y0:y1, x0:x1] != 255, axis=2)
    lab, _n = ndimage.label(ink, structure=np.ones((3, 3), int))
    objs = ndimage.find_objects(lab)
    comps = sorted(
        [{"id": i, "x0": s[1].start, "x1": s[1].stop}
         for i, s in enumerate(objs, start=1) if s is not None],
        key=lambda c: c["x0"])
    groups, cur = [], [comps[0]]
    for c in comps[1:]:
        if c["x0"] - max(z["x1"] for z in cur) > LABEL_GROUP_GAP:
            groups.append(cur)
            cur = [c]
        else:
            cur.append(c)
    groups.append(cur)
    return lab, groups


def _type3_column_x(rgb):
    """The three Type 3 time-column centres, from the circle cores."""
    cols = []
    for colour, tol in (((255, 188, 1), 45), ((255, 206, 67), 45)):
        d = np.abs(rgb.astype(int) - np.array(colour)).sum(axis=2)
        m = d < tol
        m[:, :2254] = False
        m[:, 3372:] = False
        m[:800, :] = False
        lab, _n = ndimage.label(m)
        for i, sl in enumerate(ndimage.find_objects(lab), start=1):
            core = (lab[sl] == i)
            if int(core.sum()) < 20000:
                continue
            _ys, xs = np.nonzero(core)
            cols.append(float(xs.mean()) + sl[1].start)
    cols.sort()
    assert len(cols) == 9, f"expected 9 Type 3 circles, found {len(cols)}"
    return [float(np.mean(cols[0:3])), float(np.mean(cols[3:6])),
            float(np.mean(cols[6:9]))]


# --------------------------------------------------------------------------
def test_canonical_asset_matches_approved_hash():
    assert _sha(FIG04) == APPROVED_SHA
    assert _sha(DONOR) == DONOR_SHA


def test_producer_regenerates_pixel_identically(tmp_path):
    """One deterministic pass from the immutable donor.

    PIXEL identity is the portable guarantee and is required unconditionally.
    PNG BYTE identity is a property of the canonical encoder toolchain, not of
    the figure: a Linux audit reproduced this figure pixel-for-pixel while
    emitting different PNG bytes, because the byte stream depends on the
    Pillow/zlib build. Byte identity is asserted separately, and only where the
    canonical toolchain is present - see
    tests/test_fig04_cross_platform_determinism.py.
    """
    subprocess.run([sys.executable, str(PRODUCER), "--out", str(tmp_path),
                    "--src", str(DONOR)], check=True, cwd=REPO)
    generated = _rgb(tmp_path / "Figure_04.png")
    shipped = _rgb(FIG04)
    assert generated.shape == shipped.shape, (
        f"regenerated canvas {generated.shape} != shipped {shipped.shape}")
    assert np.array_equal(generated, shipped), (
        "regenerated Figure 4 is not pixel-identical to the shipped asset: "
        f"{int((generated != shipped).any(axis=-1).sum())} differing pixels")


def test_type4_reads_horizontally_two_one_two():
    circles = _purple_components(_rgb(FIG04))[:5]
    xs = sorted(c["cx"] for c in circles)
    # three distinct, strictly increasing columns holding 2, 1 and 2 circles
    cols = []
    for x in xs:
        if cols and abs(x - cols[-1][0]) < 50:
            cols[-1][1] += 1
        else:
            cols.append([x, 1])
    assert [n for _x, n in cols] == [2, 1, 2], cols
    assert cols[0][0] < cols[1][0] < cols[2][0]


def test_type4_lattice_symmetry_within_tolerance():
    circles = _purple_components(_rgb(FIG04))[:5]
    xmid = sorted(c["cx"] for c in circles)[2]
    left = sorted([c for c in circles if c["cx"] < xmid - 50],
                  key=lambda c: c["cy"])
    right = sorted([c for c in circles if c["cx"] > xmid + 50],
                   key=lambda c: c["cy"])
    centre = [c for c in circles if abs(c["cx"] - xmid) <= 50][0]
    assert len(left) == 2 and len(right) == 2
    (ul, ll), (ur, lr) = left, right
    assert abs(ul["cx"] - ll["cx"]) <= TOL          # left column shares x
    assert abs(ur["cx"] - lr["cx"]) <= TOL          # right column shares x
    assert abs(ul["cy"] - ur["cy"]) <= TOL          # upper row shares y
    assert abs(ll["cy"] - lr["cy"]) <= TOL          # lower row shares y
    lx = (ul["cx"] + ll["cx"]) / 2
    rx = (ur["cx"] + lr["cx"]) / 2
    uy = (ul["cy"] + ur["cy"]) / 2
    ly = (ll["cy"] + lr["cy"]) / 2
    assert abs(centre["cx"] - (lx + rx) / 2) <= TOL   # centred horizontally
    assert abs(centre["cy"] - (uy + ly) / 2) <= TOL   # centred vertically
    # mirror symmetry about both centrelines
    assert abs((ul["cy"] + ll["cy"]) / 2 - centre["cy"]) <= TOL
    assert abs((centre["cx"] - lx) - (rx - centre["cx"])) <= TOL


def test_type3_labels_centred_on_columns_within_one_pixel():
    rgb = _rgb(FIG04)
    colx = _type3_column_x(rgb)
    for band in LABEL_BANDS:
        _lab, groups = _label_groups(rgb, band)
        assert len(groups) == 3, f"band {band[1]}: {len(groups)} groups"
        for gi, g in enumerate(groups):
            x0 = min(c["x0"] for c in g)
            x1 = max(c["x1"] for c in g)
            centre = (x0 + x1 - 1) / 2.0
            assert abs(centre - colx[gi]) <= TOL, (
                f"band {band[1]} group {gi}: offset "
                f"{centre - colx[gi]:.3f} px")


def test_type3_labels_are_exact_translations_of_donor_glyphs():
    donor = _rgb(DONOR)
    final = _rgb(FIG04)
    for band in LABEL_BANDS:
        x0, y0, x1, y1 = band
        lab, groups = _label_groups(donor, band)
        expected = np.full_like(final[y0:y1, x0:x1], 255)
        src = donor[y0:y1, x0:x1]
        for gi, g in enumerate(groups):
            dx = LABEL_MOVES[(y0, gi)]
            m = np.isin(lab, [c["id"] for c in g])[y0:y1, x0:x1]
            ys, xs = np.nonzero(m)
            expected[ys, xs + dx] = src[ys, xs]
        assert np.array_equal(expected, final[y0:y1, x0:x1]), (
            f"label band {y0} is not an exact translation of the donor")
        # ink is conserved exactly: nothing redrawn, nothing dropped
        assert (np.any(src != 255, axis=2).sum() ==
                np.any(final[y0:y1, x0:x1] != 255, axis=2).sum())


def test_no_prohibited_region_changed():
    donor = _rgb(DONOR)
    final = _rgb(FIG04)
    assert donor.shape == final.shape                      # canvas unchanged
    diff = np.any(donor != final, axis=-1)
    assert diff[:, :1123].sum() == 0, "Type 1 panel changed"
    assert diff[:, 1129:2248].sum() == 0, "Type 2 panel changed"
    assert diff[:800, :].sum() == 0, "panel title band changed"
    assert diff[2150:, :].sum() == 0, "typology name band changed"
    for a, b in ((1123, 1129), (2248, 2254), (3372, 3378)):
        assert diff[:, a:b].sum() == 0, f"divider {a}-{b} changed"
    # no new colours may be introduced
    pack = np.array([65536, 256, 1], np.uint32)
    before = np.unique(donor.reshape(-1, 3).astype(np.uint32) @ pack)
    after = np.unique(final.reshape(-1, 3).astype(np.uint32) @ pack)
    assert np.setdiff1d(after, before).size == 0, "new colours introduced"


@pytest.mark.skipif(not PUB.exists(), reason="publication outputs not built")
def test_publication_output_equals_canonical_asset():
    assert _sha(PUB) == APPROVED_SHA


@pytest.mark.skipif(not FINAL_DOCX.exists(),
                    reason="final integration DOCX not present")
def test_final_docx_embed_equals_canonical_asset():
    with zipfile.ZipFile(FINAL_DOCX) as z:
        payload = z.read("word/media/image4.png")
    assert hashlib.sha256(payload).hexdigest() == APPROVED_SHA
