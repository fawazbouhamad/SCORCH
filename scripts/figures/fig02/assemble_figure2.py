#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Assemble paper Figure 2 — Phase 2C-R2 (composition unchanged from 2C).

Layout follows PowerPoint slide 2: p95 map on the LEFT (a), capped areal-
extent ratio hexbin on the RIGHT (b). Panels are embedded unchanged (raster
passthrough); only the canonical "(a)"/"(b)" letters are added (q1_style).

Output: <phase2c_r2>/outputs/fig02/Figure2_assembled.{png,pdf}
"""
from __future__ import annotations
# --- SCORCH release bootstrap (auto-inserted; release-relative, no absolute paths) ---
import os as _os, sys as _sys
def _scorch_find_root(_p):
    while _p != _os.path.dirname(_p):
        if _os.path.isdir(_os.path.join(_p, "scripts")) and _os.path.isdir(_os.path.join(_p, "configs")):
            return _p
        _p = _os.path.dirname(_p)
    return _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_SCORCH_ROOT = _os.environ.get("SCORCH_RELEASE_ROOT") or _scorch_find_root(_os.path.dirname(_os.path.abspath(__file__)))
_os.environ["SCORCH_RELEASE_ROOT"] = _SCORCH_ROOT
_sys.path.insert(0, _os.path.join(_SCORCH_ROOT, "scripts", "figures", "common"))
from _clean_paths import GENERATED_DIR as _SCORCH_REPRO  # noqa: E402  central helper; honours SCORCH_OUT_DIR
# --- end SCORCH release bootstrap ---

import os
import sys

os.environ.setdefault("MPLBACKEND", "Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import gridspec  # noqa: E402

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_CAND = os.path.dirname(_THIS_DIR)
sys.path.insert(0, _THIS_DIR)
import q1_style as Q  # noqa: E402


def generated(sub):
    p = os.path.join(_SCORCH_REPRO, sub)
    os.makedirs(p, exist_ok=True)
    return p


SRC = os.path.join(_SCORCH_REPRO, "fig02")
PANELS = [("a", "fig02_panel_a_tmax_p95_map.png"),
          ("b", "fig02_panel_b_extent_hexbin.png")]


def main() -> None:
    imgs = []
    for letter, name in PANELS:
        path = os.path.join(SRC, name)
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"Missing panel ({letter}): {path} — run the fig02 panel "
                "scripts first.")
        imgs.append(plt.imread(path))

    h = max(im.shape[0] / im.shape[1] for im in imgs) / 2.0
    fig_w = 14.0
    fig = plt.figure(figsize=(fig_w, fig_w * h * 1.06))
    gs = gridspec.GridSpec(1, 2, figure=fig, wspace=0.02,
                           left=0.005, right=0.995, top=0.93, bottom=0.005)

    for i, ((letter, _), im) in enumerate(zip(PANELS, imgs)):
        ax = fig.add_subplot(gs[0, i])
        ax.imshow(im)
        ax.set_axis_off()
        Q.label_above(fig, ax, f"({letter})")

    out_dir = generated("fig02")
    for ext in ("png", "pdf"):
        out = os.path.join(out_dir, f"Figure2_assembled.{ext}")
        fig.savefig(out, dpi=600)
        print(f"[FIG2-ASSEMBLY-R2] saved {out}")
    plt.close(fig)


if __name__ == "__main__":
    main()
