#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 2C shared Q1 style helpers — single source of truth.

Canonical panel labels
    Lowercase parenthesized, Arial bold 17 pt, black (normalized from the
    approved Figure 11 treatment). Placement is COMPUTED from panel bounding
    boxes (figure coordinates + fixed point offsets), never hand-tuned:
      * label_above(): horizontally centered over the panel, one shared
        vertical offset;
      * label_left(): one shared left offset, vertically centered on the
        panel/row.

Typology headings (Figures 4-7)
    Exact properties extracted from slide 5 XML (paper_intake pptx):
    font "Abadi", bold, colors Type1 #FF0000, Type2 #FF7401, Type3 #FFBC01,
    Type4 #7030A0 (slide size 44 pt; composites scale proportionally).
    The Abadi faces are registered from the Office cloud-font cache when
    present; Arial bold is the documented fallback.

Snapshot conventions (Figures 5-7)
    One unified horizontal legend (L1 / L2 / Centroid, styles from
    six_task_review/snapshots.py) and one date-label treatment (black,
    bold, inside bottom-right, fixed inset).
"""
from __future__ import annotations

import glob
import os

import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.lines import Line2D

# ---- fonts -------------------------------------------------------------------
# THE HEADING FACE IS AN INPUT, not an ambient convenience.
#
# Abadi ships with Microsoft 365 and is cached per user under LOCALAPPDATA. It
# is NOT redistributable, so it cannot live in this repository - the same
# position the pinned Aptos face is in. What went wrong was not that the font
# is external; it is that the dependency was INVISIBLE and the failure SILENT:
# the directory was resolved from ambient LOCALAPPDATA, and when it was not
# there the family quietly became Arial. The producers then rendered different
# glyphs, Figures 5, 6, 7 and S.1 came out a few pixels different, and the
# publication builder - which routes by SHA-256 and never by filename -
# correctly reported that the declared manuscript-final raster did not exist.
# A whole release was blocked by a fallback nobody could see.
#
# So the directory may now be named EXPLICITLY through SCORCH_SLIDE_FONT_DIR,
# and a caller that cannot tolerate the fallback sets SCORCH_REQUIRE_SLIDE_FONTS
# to make its absence an error instead of a silent substitution. The release
# finalizer sets both, so a release can never again be produced with the wrong
# glyphs and a green report.
_SLIDE_FONT_DIR_VAR = "SCORCH_SLIDE_FONT_DIR"
_REQUIRE_VAR = "SCORCH_REQUIRE_SLIDE_FONTS"
_FALLBACK_FAMILY = "Arial"

#: Every face this module actually registered, in resolution order. Read by
#: the release tooling to prove the pinned faces - and no others - were used.
SLIDE_FONT_FILES: list = []


def slide_font_dir() -> str:
    """The directory the Abadi faces are read from.

    An explicit ``SCORCH_SLIDE_FONT_DIR`` wins over the ambient Microsoft 365
    cloud-font cache, so a hermetic run can be given the same faces the
    figures were authored with without inheriting a personal machine's
    environment wholesale.
    """
    explicit = os.environ.get(_SLIDE_FONT_DIR_VAR, "").strip()
    if explicit:
        return explicit
    return os.path.join(os.environ.get("LOCALAPPDATA", ""),
                        "Microsoft", "FontCache", "4", "CloudFonts", "Abadi")


def register_slide_fonts() -> str:
    """Register the slide's Abadi faces; return the heading font family.

    Returns ``"Abadi"`` when the faces are registered. Falls back to
    ``"Arial"`` only when the caller has not demanded otherwise - and that
    fallback CHANGES THE RENDERED PIXELS, so anything reproducing declared
    figure identities must set ``SCORCH_REQUIRE_SLIDE_FONTS``.
    """
    del SLIDE_FONT_FILES[:]
    directory = slide_font_dir()
    for ttf in sorted(glob.glob(os.path.join(directory, "*.ttf"))):
        try:
            fm.fontManager.addfont(ttf)
            SLIDE_FONT_FILES.append(ttf)
        except Exception:
            pass
    names = {f.name for f in fm.fontManager.ttflist}
    if SLIDE_FONT_FILES and "Abadi" in names:
        return "Abadi"
    if os.environ.get(_REQUIRE_VAR, "").strip():
        raise RuntimeError(
            f"the Abadi slide faces are required but were not registered from "
            f"{directory!r}. Falling back to {_FALLBACK_FAMILY} would render "
            f"different glyphs, so the figures would not reproduce their "
            f"declared identities. Set {_SLIDE_FONT_DIR_VAR} to the directory "
            f"holding the faces, or clear {_REQUIRE_VAR} to accept the "
            f"substitution and the different output that comes with it")
    return _FALLBACK_FAMILY


HEADING_FAMILY = register_slide_fonts()

# ---- canonical constants -----------------------------------------------------
PANEL_LABEL = dict(fontsize=17, fontweight="bold", color="black",
                   family="Arial")
LABEL_PAD_PT = 6          # gap between panel edge and label, in points
TYPE_COLORS = {1: "#FF0000", 2: "#FF7401", 3: "#FFBC01", 4: "#7030A0"}
DATE_FS = 12
LEGEND_FS = 12


def _pt_to_fig(fig, pts: float, axis: str) -> float:
    size_in = fig.get_size_inches()[0 if axis == "x" else 1]
    return (pts / 72.0) / size_in


def label_above(fig, ax, letter: str, pad_pt: float = LABEL_PAD_PT) -> None:
    """Canonical (x) label horizontally centered above a panel."""
    b = ax.get_position()
    fig.text((b.x0 + b.x1) / 2.0, b.y1 + _pt_to_fig(fig, pad_pt, "y"),
             letter, ha="center", va="bottom", **PANEL_LABEL)


def label_left(fig, ax_or_bboxes, letter: str,
               pad_pt: float = 14.0) -> None:
    """Canonical (x) label outside the left edge, vertically centered.

    ax_or_bboxes: a single Axes, or a list of Axes forming one row (the
    label centers on the union of their bounding boxes).
    """
    axes = ax_or_bboxes if isinstance(ax_or_bboxes, (list, tuple)) \
        else [ax_or_bboxes]
    bs = [a.get_position() for a in axes]
    x0 = min(b.x0 for b in bs)
    yc = (min(b.y0 for b in bs) + max(b.y1 for b in bs)) / 2.0
    fig.text(x0 - _pt_to_fig(fig, pad_pt, "x"), yc, letter,
             ha="right", va="center", **PANEL_LABEL)


def type_heading(fig, x, y, type_n: int, fontsize: float = 26,
                 text: str | None = None) -> None:
    """Slide-5-exact typology heading (Abadi bold, exact slide color)."""
    fig.text(x, y, text or f"Type {type_n}", ha="center", va="center",
             fontsize=fontsize, fontweight="bold", family=HEADING_FAMILY,
             color=TYPE_COLORS[type_n])


def date_label(ax, text: str, fontsize: float = DATE_FS) -> None:
    """Date inside the bottom-right of a snapshot: black, bold, fixed inset."""
    ax.text(0.975, 0.03, text, transform=ax.transAxes, ha="right",
            va="bottom", fontsize=fontsize, fontweight="bold",
            color="black", zorder=20,
            bbox=dict(facecolor="white", alpha=0.75, edgecolor="none",
                      pad=1.5))


def snapshot_legend_handles():
    """Unified L1 / L2 / Centroid handles (styles from snapshots.py)."""
    return [
        Line2D([0], [0], color="black", lw=2.4, label="L1"),
        Line2D([0], [0], color="black", lw=1.5, label="L2"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="black",
               markeredgecolor="k", markersize=7, label="Centroid"),
    ]


def unified_snapshot_legend(fig, y: float = 0.012,
                            fontsize: float = LEGEND_FS):
    """One horizontal legend centered below the whole figure (Figs 5-7)."""
    return fig.legend(handles=snapshot_legend_handles(), loc="lower center",
                      bbox_to_anchor=(0.5, y), ncol=3, frameon=True,
                      fontsize=fontsize, edgecolor="black", facecolor="white",
                      handlelength=2.2, columnspacing=1.6, borderpad=0.55)
