#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Assemble the publication-output tree for the SCORCH manuscript.

WHAT THIS PRODUCES
------------------
One clean, self-describing directory holding exactly the approved
publication inventory and nothing else:

    publication_outputs/
      README.md   PUBLICATION_OUTPUTS_MANIFEST.csv   SHA256SUMS
      figures/<Folder>/<Folder>.png          manuscript-final raster
                      /PROVENANCE.txt
                      /panels/<Folder>_panel_<x>.png
                      /source_components/    Fig. 8 and Fig. 9 ONLY
      tables/  Table_01_Compound_Heatwave_Typologies.{csv,pdf,png}
               Table_Trend_Analysis.{csv,pdf,png}
               PROVENANCE.txt

17 composites (Figs. 1-12, Figs. A-D, Fig. S.1), 45 declared panels across
the 12 lettered figures, 2 source components, 2 table sets. Figures 1, 4, 5,
7 and 12 carry no panel letters in the manuscript and get no panels/
directory at all.

HOW SOURCES ARE SELECTED -- BY HASH, NEVER BY NAME
--------------------------------------------------
Asset names in this project invert across eras and are actively misleading:
``figure5_*`` is the current Fig. 8, ``Fig11_*`` is the current Fig. 10,
``New_Figure_S2_candidate`` is the current Fig. D. So every source is chosen
by hashing every candidate under the search roots and selecting the file
whose SHA-256 equals the ``manuscript_final_sha256`` declared in
``docs/MANUSCRIPT_FIGURE_IDENTITY.csv``. A figure with no hash match, or
more than one, is a hard error naming the figure. The winning file must also
sit under the root its ``materialization`` predicts -- a hash hit under the
wrong root is an error, not a pass.

HONEST REPRODUCTION CLASSES
---------------------------
The four classes are carried through to every PROVENANCE.txt and manifest
row unchanged. In particular this builder never claims that frozen artwork
(Figs. 1, 4) was regenerated from data, and never presents the data-derived
pre-post-processing render of Fig. 8 as the publication figure -- it
ships only under ``source_components/`` under a name that says so.

SAFETY
------
Strictly two-phase. Phase 1 validates every source, every panel rectangle,
every pixel hash, the ink accounting, the table reconciliation and the
destination, and writes nothing. Phase 2 materializes into a scratch
directory and swaps it into place in one rename, so a failure can never
leave a partial output tree. Phase 3 re-reads the finished tree from disk
and re-verifies it. An existing destination holding anything this builder
did not produce is refused unless --force is given.

DETERMINISM AND PORTABILITY
---------------------------
No timestamps, no absolute paths and no environment detail are written into
any output, so two runs of the same inputs produce the same tree. Needs only
Python, numpy and Pillow (``pip install .[figures]``) plus this repository
and its ``reproduced/`` outputs. It needs no manuscript, no private
repository, no network access and no PowerPoint.

Panel PNG *file* hashes depend on which Pillow build encodes them, so they
are recorded for reference only and are never asserted. Panel identity is
asserted on the raw RGB pixel buffer instead (``pixels_sha256``), which no
encoder can change.

USAGE
-----
    python scripts/publication/build_publication_outputs.py
        [--root DIR] [--reproduced-dir DIR] [--out-dir DIR]
        [--force] [--verify-only]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
from pathlib import Path

import numpy as np
from PIL import Image

# Fig. 3 is 58.6 Mpx; Pillow's decompression-bomb guard would refuse it.
Image.MAX_IMAGE_PIXELS = None

ROOT_DEFAULT = Path(__file__).resolve().parents[2]

IDENTITY_CSV = Path("docs") / "MANUSCRIPT_FIGURE_IDENTITY.csv"
PANEL_GEOMETRY_JSON = Path("docs") / "PANEL_GEOMETRY.json"

# Where a routed source is allowed to live, keyed by its materialization.
# reproduced/ is resolved separately because run_reproduction.py can relocate
# it with --out-dir; the other two are fixed, shipped assets.
MATERIALIZATION_ROOT = {
    # Relocatable: resolved through --reproduced-dir, falling back to
    # SCORCH_OUT_DIR (see main()), never joined to the repository root.
    "reproduced_output": "reproduced",
    "frozen_artwork_asset": "assets/frozen_figures",
    "manuscript_final_asset": "assets/manuscript_final",
}

REPRODUCTION_CLASSES = {
    "data_generated":
        "Script output is BYTE-IDENTICAL to the raster embedded in the "
        "manuscript. This figure is fully regenerated from the deposited "
        "data by the producing script.",
    "frozen_approved_artwork":
        "Author-created slide export. NO runnable producer exists and none "
        "is claimed: this figure is NOT regenerated from data. The shipped "
        "PNG is the frozen approved artwork, materialized and hash-verified "
        "against the manuscript embed.",
    "deployment_export_of_reproduced_original":
        "The plotted content is fully data-reproducible: the producing "
        "script output is BYTE-IDENTICAL to the approved full-resolution "
        "original. The raster embedded in the manuscript is a frozen "
        "downscaled deployment export of that original, so the embed bytes "
        "themselves are not a script output and are shipped as a "
        "hash-verified asset.",
    "deterministic_producer":
        "Schematic figure with a deterministic runnable producer (2026-08 "
        "correction round). The producing script regenerates the shipped "
        "asset BYTE-IDENTICALLY without reading deposited data (Figure 1: "
        "code-native vector schematic; Figure 4: localized deterministic "
        "correction of the archived approved slide export). The shipped PNG "
        "is hash-verified against the manuscript embed.",
    "manually_postprocessed_approved_artwork":
        "The approved full-resolution original carries a MANUAL "
        "post-processing pass that the producing script does not reproduce, "
        "and the manuscript embed is a downscale of that post-processed "
        "original. The script reproduces the plotted CONTENT only. The "
        "data-derived pre-post-processing render is shipped under "
        "source_components/ as a clearly labelled source component and is "
        "NEVER the publication figure.",
}

EXPECTED_FOLDERS = (
    "Figure_01", "Figure_02", "Figure_03", "Figure_04", "Figure_05",
    "Figure_06", "Figure_07", "Figure_08", "Figure_09", "Figure_10",
    "Figure_11", "Figure_12", "Appendix_A", "Appendix_B", "Appendix_C",
    "Appendix_D", "Figure_S1",
)
EXPECTED_LABELS = (
    "Fig. 1.", "Fig. 2.", "Fig. 3.", "Fig. 4.", "Fig. 5.", "Fig. 6.",
    "Fig. 7.", "Fig. 8.", "Fig. 9.", "Fig. 10.", "Fig. 11.", "Fig. 12.",
    "Fig. A.", "Fig. B.", "Fig. C.", "Fig. D.", "Fig. S.1.",
)
# The manuscript gives these five no panel letters. They must never be given
# panels, and must never gain a panels/ directory.
NO_PANEL_FOLDERS = ("Figure_01", "Figure_04", "Figure_05", "Figure_07",
                    "Figure_12")
DECLARED_PANELS_TOTAL = 45
LETTERED_FIGURES = 12

# Figures whose approved original is a manual post-processing pass: their
# data-derived script render ships as a source component, nothing else does.
# Figure 9 left this set in the v1.0.0 pre-release correction: its approved
# original is now BYTE-IDENTICAL to the script render (the axial-mean fix
# regenerated it end-to-end), so no manual pass remains and no source
# component is shipped for it.
SOURCE_COMPONENT_FOLDERS = ("Figure_08",)

# --- tables ---------------------------------------------------------------
#
# Table 1 as presented in the FINAL MANUSCRIPT CANDIDATE. Held here as a declared constant so
# the reconciliation runs offline: reading the manuscript at reproduction
# time is not permitted and not necessary.
TABLE1_MANUSCRIPT_HEADER = (
    "Compound Heatwave Typologies",
    "Frequency of Occurrence (Number of Selected Event-Days)",
    "Number of Compound Events",
    "Longest Compound Event (days)",
    "Average Duration (days/event)",
    "Average Number of Ellipses per Compound Event",
    "Min Ellipses per Compound Event",
    "Max Ellipses per Compound Event",
)
TABLE1_MANUSCRIPT_ROWS = (
    ("Type 1: Widespread (Isolated)", "3", "3", "1", "1.0", "1.0", "1", "1"),
    ("Type 2: Spatially Clustered", "4", "4", "1", "1.0", "3.25", "2", "4"),
    ("Type 3: Temporally Clustered", "75", "20", "10", "3.75", "9.25",
     "2", "26"),
    ("Type 4: Compound Clustering (Multi-Type)", "313", "24", "40", "13.04",
     "23.29", "5", "80"),
)
# v1.0.0 pre-release correction: the producing script now emits the manuscript column order, so the
# map is the identity. It was (0, 1, 2, 5, 3, 4, 6, 7) while the reproduced CSV
# placed "Longest Compound Event" at column 6 instead of column 4.
TABLE1_COLUMN_MAP = (0, 1, 2, 3, 4, 5, 6, 7)
# v1.0.0 pre-release correction: no renames remain. The producing script now emits the manuscript
# header wording ("Number of Selected Event-Days" -- these values are event-DAYS,
# not events) and the canonical public typology vocabulary, so manuscript and
# reproduced agree literally. Any future divergence must be declared here rather
# than tolerated silently.
TABLE1_HEADER_RENAMES = {}
TABLE1_ROW_LABEL_RENAMES = {}

# The trend-analysis table is UNNUMBERED in the manuscript and is NEVER
# "Table 2". Its values are reported in the running text; those manuscript-reported
# per-decade figures are asserted against the reproduced per-year CSV.
TREND_MANUSCRIPT_REPORTED = (
    # (type, metric, manuscript-reported Sen slope per DECADE, manuscript-reported MK p)
    ("Type 4: Compound Clustering (Multi-Type)", "Duration", 4.12, 0.0086),
    ("Type 3: Temporally Clustered", "Duration", 0.08, 0.66),
)

TABLE_SOURCES = (
    # (source file under reproduced/tables/, publication-output name)
    ("Table_Compound_Heatwave_Typologies_global_max.csv",
     "Table_01_Compound_Heatwave_Typologies.csv"),
    ("Table_Compound_Heatwave_Typologies_global_max.pdf",
     "Table_01_Compound_Heatwave_Typologies.pdf"),
    ("Table_Compound_Heatwave_Typologies_global_max.png",
     "Table_01_Compound_Heatwave_Typologies.png"),
    ("Table_Trend_Analysis_global_max.csv", "Table_Trend_Analysis.csv"),
    ("Table_Trend_Analysis_global_max.pdf", "Table_Trend_Analysis.pdf"),
    ("Table_Trend_Analysis_global_max.png", "Table_Trend_Analysis.png"),
)

MANIFEST_NAME = "PUBLICATION_OUTPUTS_MANIFEST.csv"
SHA256SUMS_NAME = "SHA256SUMS"
README_NAME = "README.md"

MANIFEST_COLUMNS = (
    "kind", "label", "folder", "panel", "path", "bytes", "sha256",
    "pixels_sha256", "width", "height", "document", "reproduction_class",
    "materialization", "source_path", "source_sha256", "note",
)

IDENTITY_REQUIRED_COLUMNS = (
    "label", "folder", "document", "reproduction_class", "materialization",
    "manuscript_final_sha256", "bytes", "width", "height", "panels",
    "panel_count", "script_render_sha256", "reproduction_note",
)


class BuildError(Exception):
    """A validation failure. Raised before anything is written."""


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------
def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def to_gray(im: Image.Image) -> np.ndarray:
    """8-bit grayscale, transparency composited over opaque white.

    This is the ink-measurement view declared by PANEL_GEOMETRY.json.
    """
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        im = Image.alpha_composite(bg, im)
    return np.asarray(im.convert("L"))


def split_boxes(blocks, width: int, height: int):
    """Panel rectangles in reading order, from the measured block splits.

    Each block is a region (or the whole composite) cut by row and column
    coordinates. ``cols`` may be one list shared by every row, or one list
    per row when the rows differ (Fig. 3).
    """
    out = []
    for blk in blocks:
        region = blk["region"]
        x0, y0, x1, y1 = region if region else (0, 0, width, height)
        y_edges = [y0] + list(blk["rows"]) + [y1]
        nrows = len(y_edges) - 1
        cols = blk["cols"]
        if not cols:
            per_row = [[] for _ in range(nrows)]
        elif isinstance(cols[0], list):
            per_row = cols
        else:
            per_row = [list(cols) for _ in range(nrows)]
        if len(per_row) != nrows:
            raise BuildError(
                f"panel geometry: {len(per_row)} column specs for {nrows} rows")
        for r in range(nrows):
            x_edges = [x0] + list(per_row[r]) + [x1]
            for c in range(len(x_edges) - 1):
                out.append((x_edges[c], y_edges[r],
                            x_edges[c + 1], y_edges[r + 1]))
    return out


def trim_box(gray: np.ndarray, box, threshold: int):
    """Shrink a split rectangle onto its own ink, then restore a margin.

    A split rectangle inherits the composite's outer margins. Trimming only
    ever removes blank rows and columns, so an exported panel is always a
    sub-rectangle of the manuscript composite and no plotted content can be
    lost. The margin formula is the one declared in PANEL_GEOMETRY.json.
    """
    x0, y0, x1, y1 = box
    ink = gray[y0:y1, x0:x1] < threshold
    rows = np.nonzero(ink.any(axis=1))[0]
    cols = np.nonzero(ink.any(axis=0))[0]
    if not len(rows) or not len(cols):
        raise BuildError(f"panel split box {box} contains no ink")
    margin = int(min(60, max(8, round(0.01 * min(x1 - x0, y1 - y0)))))
    return (max(x0, x0 + int(cols[0]) - margin),
            max(y0, y0 + int(rows[0]) - margin),
            min(x1, x0 + int(cols[-1]) + 1 + margin),
            min(y1, y0 + int(rows[-1]) + 1 + margin))


def write_text(path: Path, text: str) -> None:
    """UTF-8 with LF endings on every platform, so builds stay identical."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def write_png(path: Path, im: Image.Image) -> None:
    """Metadata-free PNG. Pixel identity is asserted separately."""
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, format="PNG", optimize=False, compress_level=6)


def rel_posix(path: Path, base: Path) -> str:
    return path.relative_to(base).as_posix()


def longpath(path: Path) -> Path:
    """Windows extended-length form, so deep trees still build.

    Windows' legacy MAX_PATH is 260 characters. A release staging directory
    is nested deeply enough that the longest members of this tree cross that
    line, and the failure mode is silent-ish and misleading: the parent
    directory is created successfully and only the final open() raises
    FileNotFoundError, which reads like a missing directory rather than a
    path that is 24 characters too long. Prefixing a FULLY QUALIFIED path
    with \\\\?\\ opts out of the limit, and because every path derived from it
    keeps the prefix, applying this to the three roots makes the whole
    builder long-path safe.

    The prefix disables normalization, so callers must pass an already
    resolved absolute path. Nothing derived from these roots is ever written
    into an output file -- the manifest, SHA256SUMS and PROVENANCE.txt all
    record paths relative to the destination -- so no build output can
    differ because of it.
    """
    if os.name != "nt":
        return path
    text = str(path)
    if text.startswith("\\\\?\\"):
        return path
    if text.startswith("\\\\"):
        # UNC \\server\share -> \\?\UNC\server\share
        return Path("\\\\?\\UNC" + text[1:])
    return Path("\\\\?\\" + text)


def showpath(path: Path) -> str:
    """A path as a human should read it, without the \\\\?\\ machinery."""
    text = str(path)
    if text.startswith("\\\\?\\UNC\\"):
        return "\\\\" + text[8:]
    if text.startswith("\\\\?\\"):
        return text[4:]
    return text


# --------------------------------------------------------------------------
# phase 1: validation
# --------------------------------------------------------------------------
def load_identity(root: Path):
    path = root / IDENTITY_CSV
    if not path.is_file():
        raise BuildError(f"routing table not found: {path}")
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise BuildError(f"{IDENTITY_CSV.as_posix()}: no rows")
    absent = [c for c in IDENTITY_REQUIRED_COLUMNS if c not in rows[0]]
    if absent:
        raise BuildError(f"{IDENTITY_CSV.as_posix()}: missing column(s) "
                         f"{', '.join(absent)}")
    if len(rows) != len(EXPECTED_FOLDERS):
        raise BuildError(f"{IDENTITY_CSV.as_posix()}: {len(rows)} rows, "
                         f"expected {len(EXPECTED_FOLDERS)}")
    folders = tuple(r["folder"] for r in rows)
    labels = tuple(r["label"] for r in rows)
    if folders != EXPECTED_FOLDERS:
        raise BuildError(f"{IDENTITY_CSV.as_posix()}: folder column is "
                         f"{folders}, expected {EXPECTED_FOLDERS}")
    if labels != EXPECTED_LABELS:
        raise BuildError(f"{IDENTITY_CSV.as_posix()}: label column is "
                         f"{labels}, expected {EXPECTED_LABELS}")
    for r in rows:
        if r["document"] not in ("main_manuscript", "supplementary_material"):
            raise BuildError(f"{r['label']}: document is {r['document']!r}, "
                             "expected main_manuscript or "
                             "supplementary_material")
        if r["reproduction_class"] not in REPRODUCTION_CLASSES:
            raise BuildError(f"{r['label']}: unknown reproduction_class "
                             f"{r['reproduction_class']!r}")
        if r["materialization"] not in MATERIALIZATION_ROOT:
            raise BuildError(f"{r['label']}: unknown materialization "
                             f"{r['materialization']!r}")
        if len(r["manuscript_final_sha256"]) != 64:
            raise BuildError(f"{r['label']}: manuscript_final_sha256 is not "
                             "a SHA-256")
        if len(r["panels"]) != int(r["panel_count"]):
            raise BuildError(f"{r['label']}: panels {r['panels']!r} does not "
                             f"match panel_count {r['panel_count']}")
        no_panels = r["folder"] in NO_PANEL_FOLDERS
        if no_panels and r["panels"]:
            raise BuildError(f"{r['label']}: carries no panel letters in the "
                             f"manuscript but declares {r['panels']!r}")
        if not no_panels and not r["panels"]:
            raise BuildError(f"{r['label']}: is a lettered figure but "
                             "declares no panels")
    total = sum(int(r["panel_count"]) for r in rows)
    if total != DECLARED_PANELS_TOTAL:
        raise BuildError(f"{IDENTITY_CSV.as_posix()}: declares {total} "
                         f"panels, expected {DECLARED_PANELS_TOTAL}")
    return rows


def load_geometry(root: Path, identity):
    path = root / PANEL_GEOMETRY_JSON
    if not path.is_file():
        raise BuildError(f"panel geometry not found: {path}")
    geom = json.loads(path.read_text(encoding="utf-8"))
    name = PANEL_GEOMETRY_JSON.as_posix()
    if geom.get("declared_panels_total") != DECLARED_PANELS_TOTAL:
        raise BuildError(f"{name}: declared_panels_total is "
                         f"{geom.get('declared_panels_total')}, expected "
                         f"{DECLARED_PANELS_TOTAL}")
    if geom.get("lettered_figures") != LETTERED_FIGURES:
        raise BuildError(f"{name}: lettered_figures is "
                         f"{geom.get('lettered_figures')}, expected "
                         f"{LETTERED_FIGURES}")
    trim = geom.get("trim") or {}
    if trim.get("ink_threshold") != 250:
        raise BuildError(f"{name}: trim.ink_threshold is "
                         f"{trim.get('ink_threshold')!r}, expected 250")

    by_folder = {f["folder"]: f for f in geom["figures"]}
    if len(by_folder) != len(geom["figures"]):
        raise BuildError(f"{name}: duplicate folder entries")
    lettered = {r["folder"] for r in identity if r["panels"]}
    if set(by_folder) != lettered:
        extra = sorted(set(by_folder) - lettered)
        gone = sorted(lettered - set(by_folder))
        raise BuildError(
            f"{name}: geometry covers {sorted(by_folder)} but the routing "
            f"table declares panels for {sorted(lettered)}"
            + (f"; unexpected {extra}" if extra else "")
            + (f"; missing {gone}" if gone else ""))
    for folder in NO_PANEL_FOLDERS:
        if folder in by_folder:
            raise BuildError(f"{name}: {folder} has no panel letters in the "
                             "manuscript but carries geometry")

    total = 0
    for row in identity:
        fig = by_folder.get(row["folder"])
        if fig is None:
            continue
        if fig["manuscript_final_sha256"] != row["manuscript_final_sha256"]:
            raise BuildError(
                f"{row['label']}: geometry names composite "
                f"{fig['manuscript_final_sha256'][:16]}, routing table names "
                f"{row['manuscript_final_sha256'][:16]}")
        if "".join(fig["panels"]) != row["panels"]:
            raise BuildError(f"{row['label']}: geometry panels "
                             f"{''.join(fig['panels'])!r} != routing table "
                             f"{row['panels']!r}")
        if len(fig["declared_panels"]) != int(row["panel_count"]):
            raise BuildError(f"{row['label']}: geometry declares "
                             f"{len(fig['declared_panels'])} panel "
                             f"rectangles for {row['panel_count']} panels")
        if [p["panel"] for p in fig["declared_panels"]] != list(row["panels"]):
            raise BuildError(f"{row['label']}: geometry panel letters are "
                             f"{[p['panel'] for p in fig['declared_panels']]}, "
                             f"expected {list(row['panels'])}")
        total += len(fig["declared_panels"])
    if total != DECLARED_PANELS_TOTAL:
        raise BuildError(f"{name}: carries {total} panel rectangles, expected "
                         f"{DECLARED_PANELS_TOTAL}")
    return geom, by_folder, int(trim["ink_threshold"])


def hash_census(search_roots):
    """SHA-256 -> [paths] for every file under the search roots."""
    index = {}
    count = 0
    for root in search_roots:
        if not root.is_dir():
            raise BuildError(f"search root not found: {root}")
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames.sort()
            for fname in sorted(filenames):
                path = Path(dirpath) / fname
                index.setdefault(sha_file(path), []).append(path)
                count += 1
    return index, count


def route(index, digest: str, what: str, allowed_root: Path) -> Path:
    """Select the single file whose SHA-256 is `digest`, under `allowed_root`.

    Never compares filenames: in this project ``figure5_*`` is the current
    Fig. 8 and ``Fig11_*`` is the current Fig. 10, so a name-based match
    would route the wrong artwork with total confidence.
    """
    hits = index.get(digest, [])
    if not hits:
        raise BuildError(
            f"{what}: no file under the search roots has SHA-256 {digest}. "
            "The declared manuscript-final raster is not present; routing by "
            "filename is not permitted, so the build cannot continue.")
    if len(hits) > 1:
        listed = ", ".join(str(h) for h in hits)
        raise BuildError(f"{what}: SHA-256 {digest[:16]} matches "
                         f"{len(hits)} files ({listed}); the source is "
                         "ambiguous")
    hit = hits[0]
    try:
        hit.relative_to(allowed_root)
    except ValueError:
        raise BuildError(
            f"{what}: hash matched {hit}, which is NOT under the expected "
            f"root {allowed_root}. A hash hit under the wrong root is an "
            "error, not a pass.") from None
    return hit


def validate_figure(row, fig_geom, source: Path, threshold: int):
    """Re-derive every geometric claim for one figure from the routed bytes."""
    label = row["label"]
    size = source.stat().st_size
    if size != int(row["bytes"]):
        raise BuildError(f"{label}: routed source is {size} B, routing table "
                         f"declares {row['bytes']} B")
    im = Image.open(source)
    width, height = im.size
    if (width, height) != (int(row["width"]), int(row["height"])):
        raise BuildError(f"{label}: routed source is {width}x{height}, "
                         f"routing table declares "
                         f"{row['width']}x{row['height']}")
    if fig_geom is None:
        return []

    if (fig_geom["composite_width"], fig_geom["composite_height"]) \
            != (width, height):
        raise BuildError(f"{label}: geometry composite is "
                         f"{fig_geom['composite_width']}x"
                         f"{fig_geom['composite_height']}, routed source is "
                         f"{width}x{height}")

    rgb = im.convert("RGB")
    gray = to_gray(im)
    raw = split_boxes(fig_geom["blocks"], width, height)
    declared = fig_geom["declared_panels"]
    if len(raw) != len(declared):
        raise BuildError(f"{label}: blocks yield {len(raw)} rectangles for "
                         f"{len(declared)} declared panels")

    # split rectangles must stay inside the composite and must not overlap
    for i, a in enumerate(raw):
        if not (0 <= a[0] < a[2] <= width and 0 <= a[1] < a[3] <= height):
            raise BuildError(f"{label}: split box {a} escapes the composite")
        for b in raw[i + 1:]:
            if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                raise BuildError(f"{label}: split boxes overlap: {a} / {b}")

    panels = []
    for split, decl in zip(raw, declared):
        if list(split) != list(decl["split_box"]):
            raise BuildError(f"{label} panel ({decl['panel']}): recomputed "
                             f"split box {list(split)} != declared "
                             f"{decl['split_box']}")
        box = trim_box(gray, split, threshold)
        if list(box) != list(decl["box"]):
            raise BuildError(f"{label} panel ({decl['panel']}): recomputed "
                             f"crop box {list(box)} != declared "
                             f"{decl['box']}")
        crop = rgb.crop(box)
        if crop.size != (decl["width"], decl["height"]):
            raise BuildError(f"{label} panel ({decl['panel']}): crop is "
                             f"{crop.size[0]}x{crop.size[1]}, declared "
                             f"{decl['width']}x{decl['height']}")
        pixels = sha_bytes(crop.tobytes())
        if pixels != decl["pixels_sha256"]:
            raise BuildError(f"{label} panel ({decl['panel']}): raw-RGB pixel "
                             f"hash {pixels[:16]} != declared "
                             f"{decl['pixels_sha256'][:16]}")
        panels.append({"panel": decl["panel"], "box": list(box),
                       "split_box": list(split), "image": crop,
                       "width": crop.size[0], "height": crop.size[1],
                       "pixels_sha256": pixels})

    # Ink accounting. Split rectangles tile their block exactly and trimming
    # only ever drops blank rows and columns, so for a figure whose blocks
    # span the WHOLE composite every inked pixel must land inside some
    # exported panel: uncovered ink must be exactly zero. Where a region was
    # used to exclude shared chrome, the uncovered ink IS that chrome, and it
    # must equal the declared count exactly -- which keeps the exclusion
    # honest instead of letting it silently swallow plotted content.
    ink = gray < threshold
    covered = np.zeros(ink.shape, dtype=bool)
    for p in panels:
        x0, y0, x1, y1 = p["box"]
        covered[y0:y1, x0:x1] = True
    total = int(ink.sum())
    outside = int((ink & ~covered).sum())
    if total != fig_geom["ink_px"]:
        raise BuildError(f"{label}: measured {total} ink px, geometry "
                         f"declares {fig_geom['ink_px']}")
    whole = all(b["region"] is None for b in fig_geom["blocks"])
    if whole == bool(fig_geom["shared_chrome_excluded"]):
        raise BuildError(f"{label}: shared_chrome_excluded is "
                         f"{fig_geom['shared_chrome_excluded']} but the "
                         f"blocks {'do' if whole else 'do not'} span the "
                         "whole composite")
    if whole:
        if outside != 0:
            raise BuildError(
                f"{label}: {outside} ink px fall outside every panel although "
                "no shared chrome is excluded; plotted content would be lost")
    elif outside != fig_geom["ink_outside_panels_px"]:
        raise BuildError(f"{label}: {outside} ink px outside the panels, "
                         f"geometry declares "
                         f"{fig_geom['ink_outside_panels_px']}")
    return panels


def _num(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        raise BuildError(f"expected a number, got {value!r}") from None


def validate_table1(path: Path):
    """Reconcile the reproduced Table 1 value-by-value with the manuscript table.

    Since the v1.0.0 pre-release correction the producing script emits the
    exact manuscript column order and the identical canonical public
    labels (identity column map; no renames). Any divergence must be
    declared in the constants above; any undeclared difference, and any
    value difference at all, is a hard error.
    """
    with open(path, encoding="utf-8", newline="") as fh:
        rows = [r for r in csv.reader(fh) if r]
    if len(rows) != 1 + len(TABLE1_MANUSCRIPT_ROWS):
        raise BuildError(f"Table 1: {path.name} has {len(rows)} non-empty "
                         f"lines, expected {1 + len(TABLE1_MANUSCRIPT_ROWS)}")
    header, body = rows[0], rows[1:]
    if len(header) != len(TABLE1_MANUSCRIPT_HEADER):
        raise BuildError(f"Table 1: {len(header)} columns, expected "
                         f"{len(TABLE1_MANUSCRIPT_HEADER)}")

    notes = []
    for pub_idx, manuscript_col in enumerate(TABLE1_MANUSCRIPT_HEADER):
        src_idx = TABLE1_COLUMN_MAP[pub_idx]
        want = TABLE1_HEADER_RENAMES.get(manuscript_col, manuscript_col)
        if header[src_idx] != want:
            raise BuildError(
                f"Table 1: manuscript column {pub_idx + 1} ({manuscript_col!r}) "
                f"maps to reproduced column {src_idx + 1}, which is "
                f"{header[src_idx]!r}, expected {want!r}")
        if want != manuscript_col:
            notes.append(f"header column {pub_idx + 1}: manuscript "
                         f"{manuscript_col!r} = reproduced {want!r}")
        if src_idx != pub_idx:
            notes.append(f"column order: manuscript column {pub_idx + 1} "
                         f"({manuscript_col!r}) is reproduced column "
                         f"{src_idx + 1}")

    for pub_row, src_row in zip(TABLE1_MANUSCRIPT_ROWS, body):
        if len(src_row) != len(TABLE1_MANUSCRIPT_HEADER):
            raise BuildError(f"Table 1: row {src_row[:1]} has "
                             f"{len(src_row)} fields, expected "
                             f"{len(TABLE1_MANUSCRIPT_HEADER)}")
        want_label = TABLE1_ROW_LABEL_RENAMES.get(pub_row[0], pub_row[0])
        if src_row[0] != want_label:
            raise BuildError(f"Table 1: manuscript row {pub_row[0]!r} maps to "
                             f"{want_label!r}, found {src_row[0]!r}")
        if want_label != pub_row[0]:
            notes.append(f"row label: manuscript {pub_row[0]!r} = reproduced "
                         f"{want_label!r}")
        for pub_idx in range(1, len(TABLE1_MANUSCRIPT_HEADER)):
            src_idx = TABLE1_COLUMN_MAP[pub_idx]
            got, want = _num(src_row[src_idx]), _num(pub_row[pub_idx])
            if abs(got - want) > 1e-9:
                raise BuildError(
                    f"Table 1: {pub_row[0]} / "
                    f"{TABLE1_MANUSCRIPT_HEADER[pub_idx]} is {got}, the "
                    f"manuscript reports {want}")
    # de-duplicate while keeping order
    return list(dict.fromkeys(notes))


def validate_trend_table(path: Path):
    """Check the reproduced trend table against the manuscript-reported prose values.

    The manuscript reports these in the running text, per DECADE. The
    reproduced CSV carries Sen slopes per YEAR. The table is UNNUMBERED and
    is never "Table 2".
    """
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    wanted = ("Heatwave Type", "Metric", "Sen's Slope", "Mann-Kendall p-value")
    got_cols = tuple(rows[0].keys()) if rows else ()
    if got_cols != wanted:
        raise BuildError(f"trend table: columns are {got_cols}, expected "
                         f"{wanted}")
    checked = []
    for htype, metric, slope_decade, pvalue in TREND_MANUSCRIPT_REPORTED:
        match = [r for r in rows
                 if r["Heatwave Type"] == htype and r["Metric"] == metric]
        if len(match) != 1:
            raise BuildError(f"trend table: {len(match)} rows for {htype} / "
                             f"{metric}, expected exactly 1")
        got_slope = round(_num(match[0]["Sen's Slope"]) * 10.0, 2)
        got_p = _num(match[0]["Mann-Kendall p-value"])
        if abs(got_slope - slope_decade) > 5e-3:
            raise BuildError(f"trend table: {htype} {metric} Sen slope is "
                             f"{got_slope} days/decade, the manuscript "
                             f"reports {slope_decade}")
        if abs(round(got_p, 2) - pvalue) > 5e-3 \
                and abs(round(got_p, 4) - pvalue) > 5e-3:
            raise BuildError(f"trend table: {htype} {metric} Mann-Kendall p "
                             f"is {got_p}, the manuscript reports {pvalue}")
        checked.append(f"{htype} / {metric}: Sen slope {got_slope} "
                       f"days/decade, Mann-Kendall p = {got_p}")
    return checked


def classify_destination(out_dir: Path):
    """new | empty | prior_build | foreign -- with the offending paths."""
    if not out_dir.exists():
        return "new", []
    if not out_dir.is_dir():
        return "foreign", [out_dir]
    # Tool caches are not part of the materialized tree. The ruff hook drops
    # a .ruff_cache/ beside any Python file it lints -- including this
    # builder -- so counting them would make --verify-only report a healthy
    # tree as 'foreign' purely because a linter had run, which is not a
    # property of the release. audit_docs.py check 20 excludes exactly this
    # set for the same reason; the two must stay in agreement. A destination
    # holding real unlisted files is still 'foreign', so the refuse-unsafe-
    # overwrite guarantee is unchanged.
    cache_parts = {"__pycache__", ".pytest_cache", ".ruff_cache",
                   "build", "dist"}
    present = sorted(
        p for p in out_dir.rglob("*")
        if p.is_file() and p.suffix != ".pyc"
        and not (cache_parts & set(p.relative_to(out_dir).parts)))
    if not present:
        return "empty", []
    manifest = out_dir / MANIFEST_NAME
    if not manifest.is_file():
        return "foreign", present
    try:
        with open(manifest, encoding="utf-8", newline="") as fh:
            listed = {r["path"] for r in csv.DictReader(fh)}
    except (OSError, csv.Error, KeyError, TypeError):
        return "foreign", present
    listed |= {MANIFEST_NAME, SHA256SUMS_NAME}
    unexpected = [p for p in present if rel_posix(p, out_dir) not in listed]
    return ("prior_build", []) if not unexpected else ("foreign", unexpected)


# --------------------------------------------------------------------------
# phase 2: rendering the output tree
# --------------------------------------------------------------------------
def figure_provenance_text(row, fig_geom, source_rel, panels, component):
    lines = [
        f"{row['label']}  ({row['folder']})",
        "=" * 68,
        "",
        f"document              : {row['document']}",
        f"reproduction class    : {row['reproduction_class']}",
        f"materialization       : {row['materialization']}",
        f"manuscript-final PNG  : {row['folder']}.png",
        f"  sha256              : {row['manuscript_final_sha256']}",
        f"  bytes               : {row['bytes']}",
        f"  pixels              : {row['width']} x {row['height']}",
        f"routed from           : {source_rel}",
        "  (selected by SHA-256 equality with the declared manuscript-final",
        "   raster, never by filename)",
        "",
        "WHAT THIS CLASS MEANS",
        "-" * 68,
        REPRODUCTION_CLASSES[row["reproduction_class"]],
        "",
        "PER-FIGURE NOTE",
        "-" * 68,
        row["reproduction_note"],
        "",
        "PANELS",
        "-" * 68,
    ]

    if panels:
        lines += [
            f"{len(panels)} declared panel(s): "
            f"{', '.join('(' + p['panel'] + ')' for p in panels)}",
            "",
            "Each panel is a sub-rectangle of the composite above. Shared",
            "chrome (figure title, headers spanning more than one panel,",
            "shared legends, shared colorbars) is never bisected and stays",
            "only in the composite. Panel identity is asserted on the raw RGB",
            "pixel buffer, so it does not depend on the PNG encoder.",
            "",
        ]
        for p in panels:
            lines += [
                f"  ({p['panel']}) box {tuple(p['box'])}  "
                f"{p['width']} x {p['height']}",
                f"       raw-RGB sha256 {p['pixels_sha256']}",
            ]
        lines += [
            "",
            f"ink pixels in the composite            : {fig_geom['ink_px']}",
            f"ink outside every exported panel       : "
            f"{fig_geom['ink_outside_panels_px']} "
            f"({fig_geom['ink_outside_panels_pct']:.2f} %)",
            f"shared chrome excluded from the panels : "
            f"{'yes' if fig_geom['shared_chrome_excluded'] else 'no'}",
        ]
        if fig_geom["shared_chrome_excluded"]:
            lines += ["  The uncovered ink is exactly the shared chrome named",
                      "  above; it is preserved in the composite."]
        else:
            lines += ["  Nothing is excluded, so the panels account for every",
                      "  inked pixel of the composite."]
        lines += [""]
    else:
        lines += ["This figure carries no panel letters in the manuscript.",
                  "No panels are derived for it and none may be invented.",
                  ""]

    if component:
        lines += [
            "SOURCE COMPONENTS",
            "-" * 68,
            f"source_components/{component['name']}",
            f"  sha256      : {component['sha256']}",
            f"  pixels      : {component['width']} x {component['height']}",
            f"  routed from : {component['source_rel']}",
            "",
            "This is the DATA-DERIVED script render, BEFORE the manual",
            "post-processing pass carried by the approved original. It is a",
            "source component only. It is NOT the publication figure and must",
            "never be presented as one.",
            "",
        ]
    return "\n".join(lines) + "\n"


def tables_provenance_text(table1_notes, trend_checks):
    lines = [
        "PUBLICATION TABLES",
        "=" * 68,
        "",
        "Table 1 -- Compound Heatwave Typologies",
        "-" * 68,
        "Files : Table_01_Compound_Heatwave_Typologies.{csv,pdf,png}",
        "Source: reproduced/tables/"
        "Table_Compound_Heatwave_Typologies_global_max.*",
        "",
        "Every value was reconciled against the table as presented in the",
        "final manuscript candidate, cell by cell: all 8 columns x 4 type",
        "rows agree.",
        "",
    ]
    if table1_notes:
        lines += [
            "Declared presentation differences (checked at build time, not",
            "assumed):",
            "",
        ]
        lines += [f"  * {n}" for n in table1_notes]
    else:
        lines += [
            "Since the v1.0.0 pre-release correction the producing script",
            "emits the exact manuscript column order and the identical",
            "canonical public type labels: no rename or column-permutation",
            "exception remains, and the shipped CSV is a value- and",
            "layout-faithful rendering of the manuscript table.",
            "Table 1 presentation differences = 0.",
        ]
    lines += ["", "The manuscript header row is:", ""]
    lines += [f"  {i + 1}. {h}"
              for i, h in enumerate(TABLE1_MANUSCRIPT_HEADER)]
    lines += [
        "",
        "and the manuscript type labels are "
        + ", ".join(r[0] for r in TABLE1_MANUSCRIPT_ROWS) + ".",
        "",
        "The PDF and PNG are renderings of the reproduced CSV, which since",
        "the v1.0.0 pre-release correction matches the manuscript column",
        "order and labels exactly.",
        "",
        "Trend-analysis table -- UNNUMBERED",
        "-" * 68,
        "Files : Table_Trend_Analysis.{csv,pdf,png}",
        "Source: reproduced/tables/Table_Trend_Analysis_global_max.*",
        "",
        "This table is UNNUMBERED in the manuscript. It is NOT 'Table 2' and",
        "must never be cited as one: the manuscript reports its content in",
        "the running text of the trend results, not as a numbered table.",
        "",
        "The CSV carries Sen slopes per YEAR; the manuscript reports them per",
        "DECADE. The manuscript-reported values were reconciled against it:",
        "",
    ]
    lines += [f"  * {c}" for c in trend_checks]
    lines += [
        "",
        "Annual event counts are reported descriptively in the manuscript,",
        "without a trend test. Since the v1.0.0 pre-release correction the",
        "trend CSV carries ONLY the two approved duration analyses; no",
        "frequency trend row exists in any current output.",
        "",
    ]
    return "\n".join(lines) + "\n"


def readme_text(identity, geom):
    n_panels = sum(int(r["panel_count"]) for r in identity)
    lines = [
        "# SCORCH publication outputs",
        "",
        "This directory is the assembled publication inventory for the SCORCH",
        "manuscript: every figure and table that appears in the paper, and",
        "nothing else. It is built by",
        "`scripts/publication/build_publication_outputs.py` from this",
        "repository and its `reproduced/` outputs. Building it needs no",
        "manuscript, no private repository, no network access and no",
        "presentation software.",
        "",
        "## Inventory",
        "",
        f"* {len(identity)} figures: Figs. 1-12, Figs. A-D (appendices) and",
        "  Fig. S.1, the only supplementary figure.",
        f"* {n_panels} declared panels across the "
        f"{geom['lettered_figures']} lettered figures.",
        "* Table 1 (compound heatwave typologies) and the unnumbered",
        "  trend-analysis table.",
        "",
        "Figures 1, 4, 5, 7 and 12 carry no panel letters in the manuscript,",
        "so they have no `panels/` directory. Panels are never invented.",
        "",
        "## Layout",
        "",
        "```",
        "figures/<Folder>/<Folder>.png          the manuscript-final raster",
        "                /PROVENANCE.txt        class, source, panel geometry",
        "                /panels/               declared panels only",
        "                /source_components/    Fig. 8 only",
        "tables/                                Table 1 + trend analysis",
        "PUBLICATION_OUTPUTS_MANIFEST.csv       every file, with hashes",
        "SHA256SUMS                             verify with sha256sum -c",
        "```",
        "",
        "## How sources are chosen",
        "",
        "By hash, never by name. Asset filenames in this project invert",
        "across eras -- `figure5_*` is the current Fig. 8, `Fig11_*` is the",
        "current Fig. 10 -- so the builder hashes every candidate and selects",
        "the file whose SHA-256 equals the `manuscript_final_sha256` declared",
        "in `docs/MANUSCRIPT_FIGURE_IDENTITY.csv`. The winning file must also",
        "sit under the root its `materialization` predicts. Anything else is",
        "a hard error.",
        "",
        "## Reproduction classes",
        "",
        "Each figure carries one of four classes, stated verbatim in its",
        "`PROVENANCE.txt`. They are not interchangeable and the distinction",
        "is deliberate:",
        "",
    ]
    for cls in ("data_generated", "frozen_approved_artwork",
                "deployment_export_of_reproduced_original",
                "manually_postprocessed_approved_artwork"):
        members = [r["label"] for r in identity
                   if r["reproduction_class"] == cls]
        lines += [f"* **`{cls}`** ({', '.join(members)})",
                  f"  {REPRODUCTION_CLASSES[cls]}", ""]
    lines += [
        "Two consequences worth stating plainly:",
        "",
        "* Figures 1 and 4 are frozen author-created artwork with no runnable",
        "  producer. They are **not** regenerated from data and no such claim",
        "  is made anywhere in this tree.",
        "* Figure 8 carries a manual post-processing pass that the",
        "  producing script does not reproduce. The script's data-derived",
        "  render ships under `source_components/`, named so it cannot be",
        "  mistaken for the publication figure. Figure 9 no longer does:",
        "  since the v1.0.0 pre-release correction its approved original is",
        "  byte-identical to the script render.",
        "",
        "## Verifying this tree",
        "",
        "```sh",
        "sha256sum -c SHA256SUMS",
        "```",
        "",
        "`SHA256SUMS` covers every file here. The manifest additionally",
        "carries `pixels_sha256` for each panel: the SHA-256 of the raw RGB",
        "pixel buffer. Panel PNG *file* hashes depend on which Pillow build",
        "encoded them, so the pixel hash -- which no encoder can change -- is",
        "what the builder asserts. Composite figures are byte-for-byte copies",
        "of their routed sources, so their file hashes are stable and equal",
        "the declared manuscript-final digests.",
        "",
        "Re-check an existing tree at any time with:",
        "",
        "```sh",
        "python scripts/publication/build_publication_outputs.py --verify-only",
        "```",
        "",
        "## Tables",
        "",
        "See `tables/PROVENANCE.txt`. Table 1's values were reconciled cell",
        "by cell against the manuscript table; since the v1.0.0 pre-release",
        "correction the shipped CSV/PDF/PNG match the manuscript column",
        "order and canonical public labels exactly (0 presentation",
        "differences). The trend-analysis table is",
        "UNNUMBERED -- it is not 'Table 2' and must not be cited as one.",
        "",
        "## Licensing",
        "",
        "This tree is materialized OUTPUT, not source. It is assembled from",
        "files that are already licensed by",
        "`docs/LICENSES_AND_ATTRIBUTION.md`, so it carries no licence of its",
        "own and is deliberately excluded from that document's path table --",
        "classifying it would licence the same material a second time.",
        "**Each file here inherits the licence of the input it was",
        "materialized from**, and every figure's `PROVENANCE.txt` names that",
        "input by SHA-256 so the inheritance can be checked rather than",
        "assumed:",
        "",
        "| Materialized from | Rights it inherits |",
        "|---|---|",
        "| `assets/manuscript_final/**` (Fig. 8, 9, 10, 11, A, C) |"
        " CC BY 4.0 for the authors' contribution only + Copernicus ERA5"
        " terms and required attribution |",
        "| `reproduced/**` (Fig. 5, 6, 7) | CC BY 4.0 for the authors'"
        " contribution only + Copernicus ERA5 terms and required"
        " attribution |",
        "| `assets/frozen_figures/**` (Fig. 1, 4) | CC BY 4.0 PENDING --"
        " not yet in force; requires written authorization from coauthor"
        " Dr. Nasser Najibi |",
        "| `reproduced/**` (Fig. 2, 3, 12, B, D, S.1 and both table sets) |"
        " CC BY 4.0 for the authors' contributions + current Copernicus ERA5"
        " terms and required attribution for the depicted ERA5-derived"
        " values |",
        "",
        "Panels and source components inherit from the figure they were cut",
        "from. The ERA5 attribution requirement therefore reaches every",
        "figure in this tree except Fig. 1 and Fig. 4, which are author slide",
        "exports depicting no reanalysis values.",
        "",
    ]
    return "\n".join(lines) + "\n"


def build_tree(dest: Path, plan, identity, geom, tables, table1_notes,
               trend_checks):
    """Write the complete tree under `dest`. Returns the manifest rows."""
    rows = []

    for item in plan:
        row, fig_geom, source = item["row"], item["geom"], item["source"]
        panels, component = item["panels"], item["component"]
        folder = row["folder"]
        fig_dir = dest / "figures" / folder
        fig_dir.mkdir(parents=True, exist_ok=True)

        # The composite is a byte-for-byte copy: re-encoding it would break
        # its byte identity with the authenticated manuscript embed.
        composite = fig_dir / f"{folder}.png"
        shutil.copyfile(source, composite)
        got = sha_file(composite)
        if got != row["manuscript_final_sha256"]:
            raise BuildError(f"{row['label']}: copied composite hashes "
                             f"{got[:16]}, expected "
                             f"{row['manuscript_final_sha256'][:16]}")
        rows.append({
            "kind": "figure", "label": row["label"], "folder": folder,
            "panel": "", "path": rel_posix(composite, dest),
            "bytes": composite.stat().st_size, "sha256": got,
            "pixels_sha256": "", "width": row["width"],
            "height": row["height"], "document": row["document"],
            "reproduction_class": row["reproduction_class"],
            "materialization": row["materialization"],
            "source_path": item["source_rel"], "source_sha256": got,
            "note": "manuscript-final raster, byte-identical to the routed "
                    "source",
        })

        for p in panels:
            panel_path = (fig_dir / "panels"
                          / f"{folder}_panel_{p['panel']}.png")
            write_png(panel_path, p["image"])
            reread = Image.open(panel_path)
            if reread.mode != "RGB":
                reread = reread.convert("RGB")
            if sha_bytes(reread.tobytes()) != p["pixels_sha256"]:
                raise BuildError(
                    f"{row['label']} panel ({p['panel']}): the written PNG "
                    "does not read back to the asserted raw RGB pixels")
            rows.append({
                "kind": "panel", "label": row["label"], "folder": folder,
                "panel": p["panel"], "path": rel_posix(panel_path, dest),
                "bytes": panel_path.stat().st_size,
                "sha256": sha_file(panel_path),
                "pixels_sha256": p["pixels_sha256"], "width": p["width"],
                "height": p["height"], "document": row["document"],
                "reproduction_class": row["reproduction_class"],
                "materialization": row["materialization"],
                "source_path": item["source_rel"],
                "source_sha256": row["manuscript_final_sha256"],
                "note": f"crop {tuple(p['box'])} of the composite; identity "
                        "asserted on raw RGB pixels",
            })

        if component:
            comp_path = fig_dir / "source_components" / component["name"]
            comp_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(component["source"], comp_path)
            got_c = sha_file(comp_path)
            if got_c != component["sha256"]:
                raise BuildError(f"{row['label']}: copied source component "
                                 f"hashes {got_c[:16]}, expected "
                                 f"{component['sha256'][:16]}")
            rows.append({
                "kind": "source_component", "label": row["label"],
                "folder": folder, "panel": "",
                "path": rel_posix(comp_path, dest),
                "bytes": comp_path.stat().st_size, "sha256": got_c,
                "pixels_sha256": "", "width": component["width"],
                "height": component["height"], "document": row["document"],
                "reproduction_class": row["reproduction_class"],
                "materialization": "reproduced_output",
                "source_path": component["source_rel"],
                "source_sha256": got_c,
                "note": "DATA-DERIVED SCRIPT RENDER BEFORE THE MANUAL "
                        "POST-PROCESSING PASS; NOT THE PUBLICATION FIGURE",
            })

        prov = fig_dir / "PROVENANCE.txt"
        write_text(prov, figure_provenance_text(
            row, fig_geom, item["source_rel"], panels, component))
        rows.append({
            "kind": "provenance", "label": row["label"], "folder": folder,
            "panel": "", "path": rel_posix(prov, dest),
            "bytes": prov.stat().st_size, "sha256": sha_file(prov),
            "pixels_sha256": "", "width": "", "height": "",
            "document": row["document"],
            "reproduction_class": row["reproduction_class"],
            "materialization": row["materialization"], "source_path": "",
            "source_sha256": "",
            "note": "per-figure provenance and panel geometry",
        })

    # --- tables -----------------------------------------------------------
    tables_dir = dest / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    for source, out_name in tables:
        target = tables_dir / out_name
        shutil.copyfile(source, target)
        digest = sha_file(target)
        rows.append({
            "kind": "table",
            "label": ("Table 1." if out_name.startswith("Table_01")
                      else "trend analysis (unnumbered)"),
            "folder": "tables", "panel": "",
            "path": rel_posix(target, dest),
            "bytes": target.stat().st_size, "sha256": digest,
            "pixels_sha256": "", "width": "", "height": "",
            "document": "main_manuscript",
            "reproduction_class": "data_generated",
            "materialization": "reproduced_output",
            "source_path": f"reproduced/tables/{source.name}",
            "source_sha256": digest,
            "note": "values reconciled against the manuscript; see "
                    "tables/PROVENANCE.txt",
        })
    tprov = tables_dir / "PROVENANCE.txt"
    write_text(tprov, tables_provenance_text(table1_notes, trend_checks))
    rows.append({
        "kind": "provenance", "label": "tables", "folder": "tables",
        "panel": "", "path": rel_posix(tprov, dest),
        "bytes": tprov.stat().st_size, "sha256": sha_file(tprov),
        "pixels_sha256": "", "width": "", "height": "",
        "document": "main_manuscript", "reproduction_class": "data_generated",
        "materialization": "reproduced_output", "source_path": "",
        "source_sha256": "",
        "note": "table provenance and the value-by-value reconciliation",
    })

    # --- README, manifest, checksums --------------------------------------
    readme = dest / README_NAME
    write_text(readme, readme_text(identity, geom))
    rows.append({
        "kind": "readme", "label": "", "folder": "", "panel": "",
        "path": README_NAME, "bytes": readme.stat().st_size,
        "sha256": sha_file(readme), "pixels_sha256": "", "width": "",
        "height": "", "document": "", "reproduction_class": "",
        "materialization": "", "source_path": "", "source_sha256": "",
        "note": "what this tree is and how to verify it",
    })

    rows.sort(key=lambda r: r["path"])
    manifest = dest / MANIFEST_NAME
    with open(manifest, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(MANIFEST_COLUMNS),
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    sums = sorted((rel_posix(p, dest), sha_file(p))
                  for p in dest.rglob("*")
                  if p.is_file() and p.name != SHA256SUMS_NAME)
    write_text(dest / SHA256SUMS_NAME,
               "".join(f"{h}  {rel}\n" for rel, h in sums))
    return rows


# --------------------------------------------------------------------------
# phase 3: verify the finished tree from disk
# --------------------------------------------------------------------------
def verify_tree(dest: Path, identity, echo) -> None:
    manifest = dest / MANIFEST_NAME
    if not manifest.is_file():
        raise BuildError(f"{MANIFEST_NAME} is missing from {dest}")
    with open(manifest, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise BuildError(f"{MANIFEST_NAME} is empty")
    if tuple(rows[0].keys()) != MANIFEST_COLUMNS:
        raise BuildError(f"{MANIFEST_NAME}: unexpected columns "
                         f"{tuple(rows[0].keys())}")

    # Same cache exclusion as classify_destination() and audit_docs.py
    # check 20: a linter's .ruff_cache/ is not part of the materialized
    # tree, and verification must not depend on whether a linter has run.
    cache_parts = {"__pycache__", ".pytest_cache", ".ruff_cache",
                   "build", "dist"}
    on_disk = {rel_posix(p, dest) for p in dest.rglob("*")
               if p.is_file() and p.suffix != ".pyc"
               and not (cache_parts & set(p.relative_to(dest).parts))}
    listed = {r["path"] for r in rows} | {MANIFEST_NAME, SHA256SUMS_NAME}
    extra = sorted(on_disk - listed)
    missing = sorted(listed - on_disk)
    if extra:
        raise BuildError(f"the output tree holds {len(extra)} file(s) the "
                         f"manifest does not declare: {extra[:8]}")
    if missing:
        raise BuildError(f"the manifest declares {len(missing)} file(s) that "
                         f"are not on disk: {missing[:8]}")

    for r in rows:
        path = dest / r["path"]
        got = sha_file(path)
        if got != r["sha256"]:
            raise BuildError(f"{r['path']}: on disk {got[:16]}, manifest "
                             f"{r['sha256'][:16]}")
        if int(r["bytes"]) != path.stat().st_size:
            raise BuildError(f"{r['path']}: size disagrees with the manifest")

    # SHA256SUMS must cover everything but itself, and must agree.
    sums = {}
    for line in (dest / SHA256SUMS_NAME).read_text(
            encoding="utf-8").splitlines():
        digest, sep, rel = line.partition("  ")
        if not sep:
            raise BuildError(f"{SHA256SUMS_NAME}: malformed line {line!r}")
        sums[rel] = digest
    want = on_disk - {SHA256SUMS_NAME}
    if set(sums) != want:
        raise BuildError(f"{SHA256SUMS_NAME} covers {len(sums)} files, the "
                         f"tree holds {len(want)}")
    for rel, digest in sums.items():
        if sha_file(dest / rel) != digest:
            raise BuildError(f"{SHA256SUMS_NAME}: {rel} does not match")

    # --- inventory counts, exactly ----------------------------------------
    by_kind = {}
    for r in rows:
        by_kind.setdefault(r["kind"], []).append(r)
    expected = {
        "figure": len(EXPECTED_FOLDERS),
        "panel": DECLARED_PANELS_TOTAL,
        "source_component": len(SOURCE_COMPONENT_FOLDERS),
        "table": len(TABLE_SOURCES),
        "provenance": len(EXPECTED_FOLDERS) + 1,
        "readme": 1,
    }
    for kind, n in expected.items():
        got_n = len(by_kind.get(kind, []))
        if got_n != n:
            raise BuildError(f"inventory: {got_n} {kind} entries, expected "
                             f"{n}")
    unknown = sorted(set(by_kind) - set(expected))
    if unknown:
        raise BuildError(f"inventory: unexpected manifest kind(s) {unknown}")

    # composites must still be byte-identical to the declared embeds
    declared = {r["folder"]: r["manuscript_final_sha256"] for r in identity}
    for r in by_kind["figure"]:
        if r["sha256"] != declared[r["folder"]]:
            raise BuildError(f"{r['folder']}: shipped composite is not the "
                             "declared manuscript-final raster")

    # panels must round-trip to the asserted raw RGB pixels
    for r in by_kind["panel"]:
        im = Image.open(dest / r["path"])
        if im.mode != "RGB":
            im = im.convert("RGB")
        if sha_bytes(im.tobytes()) != r["pixels_sha256"]:
            raise BuildError(f"{r['path']}: raw-RGB pixels do not match the "
                             "manifest")

    # the five unlettered figures must have no panels/ directory at all
    for folder in NO_PANEL_FOLDERS:
        if (dest / "figures" / folder / "panels").exists():
            raise BuildError(f"{folder} carries no panel letters in the "
                             "manuscript but a panels/ directory exists")
    # source_components only where a manual post-processing pass exists
    for folder in EXPECTED_FOLDERS:
        comp = dest / "figures" / folder / "source_components"
        if comp.exists() and folder not in SOURCE_COMPONENT_FOLDERS:
            raise BuildError(f"{folder} has a source_components/ directory "
                             "but no manual post-processing pass")
        if not comp.exists() and folder in SOURCE_COMPONENT_FOLDERS:
            raise BuildError(f"{folder} is missing its source_components/ "
                             "directory")

    per_folder = {}
    for r in by_kind["panel"]:
        per_folder.setdefault(r["folder"], []).append(r["panel"])
    for row in identity:
        want_panels = row["panels"]
        got_panels = "".join(sorted(per_folder.get(row["folder"], [])))
        if got_panels != want_panels:
            raise BuildError(f"{row['label']}: shipped panels "
                             f"{got_panels!r}, manuscript declares "
                             f"{want_panels!r}")

    echo(f"  verified {len(rows)} manifest entries, {len(sums)} checksums, "
         f"{len(by_kind['figure'])} composites, {len(by_kind['panel'])} "
         f"panels, {len(by_kind['table'])} table files")


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(ROOT_DEFAULT),
                    help="release repository root (default: this checkout)")
    ap.add_argument("--reproduced-dir", default=None,
                    help="reproduction output root (default: $SCORCH_OUT_DIR, "
                         "else <root>/reproduced)")
    ap.add_argument("--out-dir", default=None,
                    help="publication output root "
                         "(default: <root>/publication_outputs)")
    ap.add_argument("--force", action="store_true",
                    help="replace a destination holding files this builder "
                         "did not produce")
    ap.add_argument("--verify-only", action="store_true",
                    help="validate the inputs and re-verify an existing "
                         "output tree; write nothing")
    args = ap.parse_args(argv)

    def echo(msg=""):
        print(msg, flush=True)

    # longpath() must wrap an already-resolved absolute path: the \\?\ form
    # disables normalization, so '..' and '.' would otherwise survive.
    root = longpath(Path(args.root).resolve())
    reproduced = longpath(Path(
        args.reproduced_dir
        or os.environ.get("SCORCH_OUT_DIR")
        or (root / "reproduced")).resolve())
    out_dir = longpath(
        Path(args.out_dir or (root / "publication_outputs")).resolve())

    echo("=" * 72)
    echo("SCORCH publication outputs")
    echo("=" * 72)
    echo(f"  root        {showpath(root)}")
    echo(f"  reproduced  {showpath(reproduced)}")
    echo(f"  destination {showpath(out_dir)}")
    echo()

    try:
        return run(root, reproduced, out_dir, args, echo)
    except BuildError as exc:
        echo()
        echo(f"[ERROR] {exc}")
        echo("RESULT: FAIL - nothing was written")
        return 1


def run(root: Path, reproduced: Path, out_dir: Path, args, echo) -> int:
    if out_dir in (reproduced, root):
        raise BuildError(f"refusing to build into {out_dir}: the destination "
                         "must be its own directory")
    if root == out_dir or out_dir in root.parents:
        raise BuildError(f"refusing to build into {out_dir}: it contains the "
                         "repository root")

    echo("PHASE 1 - VALIDATE (nothing is written)")
    echo("-" * 72)

    identity = load_identity(root)
    echo(f"  [1] routing table   {len(identity)} figures, "
         f"{sum(int(r['panel_count']) for r in identity)} declared panels")

    geom, geom_by_folder, threshold = load_geometry(root, identity)
    echo(f"  [2] panel geometry  {geom['lettered_figures']} lettered "
         f"figures, {geom['declared_panels_total']} panels, ink threshold "
         f"{threshold}")

    search_roots = {
        "reproduced_output": reproduced,
        "frozen_artwork_asset":
            root / MATERIALIZATION_ROOT["frozen_artwork_asset"],
        "manuscript_final_asset":
            root / MATERIALIZATION_ROOT["manuscript_final_asset"],
    }
    index, n_hashed = hash_census(sorted(set(search_roots.values())))
    echo(f"  [3] hash census     {n_hashed} files, {len(index)} distinct "
         f"SHA-256 under {len(set(search_roots.values()))} search roots")

    def display(path: Path) -> str:
        """A portable, repository-relative label for a routed source."""
        try:
            return path.resolve().relative_to(root).as_posix()
        except ValueError:
            return path.name

    plan = []
    echo("  [4] routing by SHA-256 (filenames are never compared)")
    for row in identity:
        allowed = search_roots[row["materialization"]]
        source = route(index, row["manuscript_final_sha256"],
                       f"{row['label']} ({row['folder']})", allowed)
        fig_geom = geom_by_folder.get(row["folder"])
        panels = validate_figure(row, fig_geom, source, threshold)
        component = None
        if row["folder"] in SOURCE_COMPONENT_FOLDERS:
            digest = row["script_render_sha256"]
            if len(digest) != 64:
                raise BuildError(f"{row['label']}: script_render_sha256 is "
                                 "not a SHA-256, so the source component "
                                 "cannot be routed")
            comp_src = route(index, digest,
                             f"{row['label']} source component",
                             search_roots["reproduced_output"])
            comp_im = Image.open(comp_src)
            component = {
                # Kept deliberately short: the fully spelled-out name put
                # this file 24 characters past the Windows MAX_PATH limit in
                # a deep staging tree, and would leave a distributed release archive
                # that cannot be extracted on a default Windows install.
                # The unabbreviated, honest statement of what this render is
                # lives in the figure's PROVENANCE.txt and in the manifest
                # row, which no path limit constrains.
                "name": f"{row['folder']}_script_render_NOT_PUBLICATION.png",
                "source": comp_src, "source_rel": display(comp_src),
                "sha256": digest, "width": comp_im.size[0],
                "height": comp_im.size[1],
            }
        plan.append({"row": row, "geom": fig_geom, "source": source,
                     "source_rel": display(source), "panels": panels,
                     "component": component})
        echo(f"      {row['label']:<9s} {row['folder']:<11s} "
             f"{len(panels):>2d} panel(s)  <- {display(source)}")

    n_panels = sum(len(p["panels"]) for p in plan)
    if n_panels != DECLARED_PANELS_TOTAL:
        raise BuildError(f"derived {n_panels} panels, the manuscript declares "
                         f"{DECLARED_PANELS_TOTAL}")
    echo(f"  [5] panels          {n_panels}/{DECLARED_PANELS_TOTAL} "
         "rectangles, pixel hashes and ink accounts re-derived and matched")

    tables_dir = reproduced / "tables"
    tables = []
    for src_name, out_name in TABLE_SOURCES:
        src = tables_dir / src_name
        if not src.is_file():
            raise BuildError(f"table source not found: {src}")
        tables.append((src, out_name))
    table1_notes = validate_table1(
        tables_dir / "Table_Compound_Heatwave_Typologies_global_max.csv")
    trend_checks = validate_trend_table(
        tables_dir / "Table_Trend_Analysis_global_max.csv")
    echo(f"  [6] tables          {len(tables)} files; Table 1 reconciled "
         f"cell by cell ({len(table1_notes)} declared presentation "
         f"difference(s)); {len(trend_checks)} manuscript-reported trend value(s) "
         "matched")

    state, offenders = classify_destination(out_dir)
    echo(f"  [7] destination     {state}")

    if args.verify_only:
        if state != "prior_build":
            raise BuildError(f"--verify-only needs an existing build at "
                             f"{out_dir}; it is '{state}'")
        echo()
        echo("PHASE 3 - VERIFY THE EXISTING TREE")
        echo("-" * 72)
        verify_tree(out_dir, identity, echo)
        echo()
        echo("RESULT: PASS - the existing publication output tree verifies")
        return 0

    if state == "foreign" and not args.force:
        shown = "\n".join(f"        {showpath(p)}" for p in offenders[:12])
        raise BuildError(
            f"{showpath(out_dir)} already holds {len(offenders)} file(s) "
            "this builder "
            f"did not produce:\n{shown}\n"
            "        Refusing to overwrite. Move them aside, or pass --force "
            "to replace the directory.")

    echo()
    echo("PHASE 2 - MATERIALIZE (scratch tree, then one atomic swap)")
    echo("-" * 72)
    scratch = out_dir.parent / f".{out_dir.name}.build-{os.getpid()}"
    previous = out_dir.parent / f".{out_dir.name}.previous-{os.getpid()}"
    if scratch.exists():
        shutil.rmtree(scratch)
    if previous.exists():
        shutil.rmtree(previous)
    swapped = False
    try:
        scratch.mkdir(parents=True)
        rows = build_tree(scratch, plan, identity, geom, tables,
                          table1_notes, trend_checks)
        echo(f"  wrote {len(rows)} manifest entries into the scratch tree")
        if out_dir.exists():
            os.replace(out_dir, previous)
            swapped = True
        os.replace(scratch, out_dir)
    except BaseException:
        # Nothing partial may survive. If the swap had already moved the old
        # tree aside, put it back exactly as it was.
        if scratch.exists():
            shutil.rmtree(scratch, ignore_errors=True)
        if swapped and previous.exists() and not out_dir.exists():
            os.replace(previous, out_dir)
        raise
    finally:
        if previous.exists() and out_dir.is_dir():
            shutil.rmtree(previous, ignore_errors=True)
    echo(f"  swapped into place: {showpath(out_dir)}")

    echo()
    echo("PHASE 3 - VERIFY THE WRITTEN TREE (re-read from disk)")
    echo("-" * 72)
    verify_tree(out_dir, identity, echo)

    echo()
    echo(f"RESULT: PASS - {len(EXPECTED_FOLDERS)} figures, "
         f"{DECLARED_PANELS_TOTAL} panels, "
         f"{len(SOURCE_COMPONENT_FOLDERS)} source components and "
         f"{len(TABLE_SOURCES)} table files assembled and verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
