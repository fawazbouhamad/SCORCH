#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compose the regenerated Figure S.1 station row (panels c and d).

Until the v1.0.0 pre-release correction the station panels of Figure S.1 came from FROZEN donor artwork
(assets/frozen_figures/figS1_station_donor/) that had no runnable producer --
only its statistics were independently recomputed. That made Figure S.1 a
hybrid composite, and the release could not honestly claim it was regenerated
from deposited data.

The original producer was recovered from the research working tree, sanitized
of its absolute Windows paths and interactive backend, and now ships as
``make_figS1_station_panels.py``. It regenerates the two station panels from the
deposited GHCNd and ERA5 series, and its merged daily series is bit-identical to
the deposit's own ``validation_station/merged_station_validation.csv``.

This script places those two regenerated panels side by side to form the
station row that the Figure S.1 compositor consumes in place of the frozen
donor. Composition only -- nothing is recomputed, restyled or relabelled here;
the panel letters (c) and (d) are added by the compositor, exactly as before.

Both panels are top-aligned on a common canvas whose height is the taller of the
two, on a white background, at their native pixel scale. No resampling is
applied, so the regenerated panels reach the figure unaltered.
"""
from __future__ import annotations

import os
import sys

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

_THIS = os.path.dirname(os.path.abspath(__file__))
_FIGS = os.path.dirname(_THIS)
sys.path.insert(0, os.path.join(_FIGS, "common"))
from _clean_paths import generated  # noqa: E402

#: Horizontal gap between the two panels, in pixels at native scale.
GAP_PX = 60

#: Background colour (opaque white) behind the panels.
BG = (255, 255, 255, 255)


def _top_spine_row(im, minfrac=0.30):
    """First row carrying a long horizontal dark run -- the panel's top spine.

    Mirrors the detection the Figure S.1 compositor uses (``frame_spans``), so
    the two agree on where each panel's frame begins.
    """
    a = np.asarray(im, dtype=float) / 255.0
    lum = a[..., :3] @ np.array([0.299, 0.587, 0.114])
    dark = lum < 0.35
    if a.shape[2] == 4:
        dark &= a[..., 3] > 0.5
    width = dark.shape[1]
    for r in range(dark.shape[0]):
        idx = np.flatnonzero(dark[r])
        if idx.size == 0:
            continue
        brk = np.where(np.diff(idx) > 1)[0]
        st = np.r_[idx[0], idx[brk + 1]]
        en = np.r_[idx[brk], idx[-1]]
        if any((b - a_ + 1) >= minfrac * width for a_, b in zip(st, en)):
            return r
    raise SystemExit("FATAL: no top spine found in a station panel")


def _load(path):
    if not os.path.exists(path):
        raise SystemExit(
            f"FATAL: station panel not found: {path}\n"
            f"       run make_figS1_station_panels.py first")
    return Image.open(path).convert("RGBA")


def main():
    src_dir = generated("supplement_station_panels")
    left = _load(os.path.join(src_dir, "validation_timeseries_Q1.png"))
    right = _load(os.path.join(src_dir, "validation_scatter_Q1.png"))

    # Align the two panels on their TOP SPINE row. The Figure S.1 compositor
    # locates panel frames by scanning for the first image row carrying long
    # horizontal dark runs -- the top spines. If the two spines sit on
    # different canvas rows, that scan returns only the higher panel and the
    # (c)/(d) letters would be mispositioned. Neither top- nor bottom-aligning
    # the raw images achieves this, because each panel carries a different
    # amount of title/margin above its axes.
    ly, ry = _top_spine_row(left), _top_spine_row(right)
    off_l, off_r = max(0, ry - ly), max(0, ly - ry)
    w = left.size[0] + GAP_PX + right.size[0]
    h = max(left.size[1] + off_l, right.size[1] + off_r)
    canvas = Image.new("RGBA", (w, h), BG)
    canvas.alpha_composite(left, (0, off_l))
    canvas.alpha_composite(right, (left.size[0] + GAP_PX, off_r))
    print(f"[S1-STRIP] top-spine rows: left {ly}, right {ry} -> "
          f"offsets ({off_l}, {off_r}); aligned at row {max(ly, ry)}")

    out_dir = generated("supplement")
    out = os.path.join(out_dir, "Figure_S1_station_panels_strip.png")
    canvas.save(out, "PNG", optimize=False, compress_level=6)

    print(f"[S1-STRIP] left  {left.size[0]}x{left.size[1]} (timeseries)")
    print(f"[S1-STRIP] right {right.size[0]}x{right.size[1]} (scatter)")
    print(f"[S1-STRIP] strip {w}x{h} -> {out}")

    # The compositor locates the two panel frames by scanning for vertical ink
    # runs. Fail loudly here if the strip does not present exactly two, rather
    # than letting the compositor mislabel the panels downstream.
    arr = np.asarray(canvas.convert("L"), dtype=float) / 255.0
    ink = (arr < 0.92).any(axis=0)
    runs, start = [], None
    for i, v in enumerate(ink):
        if v and start is None:
            start = i
        elif not v and start is not None:
            runs.append((start, i - 1))
            start = None
    if start is not None:
        runs.append((start, len(ink) - 1))
    wide = [r for r in runs if (r[1] - r[0]) > 0.10 * w]
    if len(wide) != 2:
        raise SystemExit(
            f"FATAL: expected exactly 2 wide ink runs in the station strip, "
            f"found {len(wide)}: {wide}")
    print(f"[S1-STRIP] verified 2 panel frames: {wide}")


if __name__ == "__main__":
    main()
