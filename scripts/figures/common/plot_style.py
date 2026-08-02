#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Centralized publication plotting style for the six-task ellipse review.

Single source of truth for typography, palette, and figure-saving so every
task figure looks consistent and is Q1-journal ready (vector text embedded,
colorblind-safe colors, restrained styling). Imported by every task script.

No data file IO here -- pure matplotlib configuration and color constants.
"""
from __future__ import annotations

import os
from typing import Iterable

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Colorblind-safe qualitative palette (Okabe-Ito) keyed to the four event types.
TYPE_COLORS = {
    1: "#0072B2",   # blue   - Type 1 Independent
    2: "#009E73",   # green  - Type 2 Spatially clustered
    3: "#E69F00",   # orange - Type 3 Temporally clustered
    4: "#D55E00",   # vermillion - Type 4 Mixed
}
TYPE_LABELS = {1: "Type 1", 2: "Type 2", 3: "Type 3", 4: "Type 4"}
TYPE_NAMES = {
    1: "Independent",
    2: "Spatially clustered",
    3: "Temporally clustered",
    4: "Mixed",
}
ALL_COLOR = "#444444"           # "All types" pooled series

# Task 5 modal-cell highlight (accessible light blue + darker boundary).
HIGHLIGHT_FACE = "#9ecae1"
HIGHLIGHT_EDGE = "#08519c"

# Figure DPI conventions.
DPI_PNG = 600
DPI_PNG_LARGE = 300             # use for very large/dense rasters

_RC = {
    "figure.dpi": 110,
    "savefig.dpi": DPI_PNG,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.05,
    "pdf.fonttype": 42,         # embed TrueType (editable text in vector output)
    "ps.fonttype": 42,
    "svg.fonttype": "none",     # keep text as text in SVG
    "font.family": "DejaVu Sans",
    "font.size": 11,
    "axes.titlesize": 12,
    "axes.titleweight": "bold",
    "axes.labelsize": 11,
    "axes.linewidth": 0.8,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.color": "#dddddd",
    "grid.linewidth": 0.6,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "legend.fontsize": 9.5,
    "legend.frameon": False,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "lines.linewidth": 1.6,
}


def apply() -> None:
    """Apply the shared rcParams. Call once at the top of each task script."""
    plt.rcParams.update(_RC)


def type_color(type_int: int) -> str:
    return TYPE_COLORS.get(int(type_int), "#777777")


def save(fig, path_noext: str, formats: Iterable[str] = ("png", "pdf", "svg"),
         dpi: int | None = None) -> list[str]:
    """Save a figure to several vector/raster formats; return written paths."""
    written = []
    os.makedirs(os.path.dirname(os.path.abspath(path_noext)), exist_ok=True)
    for fmt in formats:
        p = f"{path_noext}.{fmt}"
        fig.savefig(p, format=fmt, dpi=(dpi or DPI_PNG) if fmt == "png" else None)
        written.append(p)
    plt.close(fig)
    return written
