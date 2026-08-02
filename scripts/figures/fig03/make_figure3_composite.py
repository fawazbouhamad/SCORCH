#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 2C-R3 — paper Figure 3 as ONE native composite with five EQUAL
visible plot frames.

Why native: the R2 raster standardization equalized outer canvases, but the
true visible frames could not be equalized from the rasters without
distortion (the AB sub-panel frames render at aspect 1.38419 vs 1.38814 for
Panels C/D/E — a 0.285% mismatch, several rendered pixels at publication
size). Per the author's instruction, this script instead REUSES THE
VALIDATED SOURCE PLOTTING FUNCTIONS (fig3_panels.py — an unchanged copy of
the Phase 2C Figures_2_3_Centroid_Map_Plots.py) in one composite figure:

  * five map axes with IDENTICAL width/height (6.00 x 4.32 in; the axes
    aspect equals the fixed 50/36 domain extent, so cartopy performs no
    aspect shrink and the visible frame IS the axes rectangle);
  * identical reserved right-hand gutters for the colorbars ((a)'s gutter
    stays empty — its legend sits below the map, as in the approved panel);
  * (a)/(c) and (b)/(d) share exact column positions; (e)'s frame center
    equals the figure center; identical row gaps and one column gap;
  * unchanged scientific content: same data pipeline
    (load_and_prepare_data), same setup_panel_ax, same plotting calls,
    norms, colormaps, point sizes, colorbar labels and legend as the
    approved panels;
  * canonical (a)-(e) labels (q1_style) centered above each visible frame.

Verification: the drawn frame rectangles are exported in rendered pixels
(fig03_r3_frame_boxes.json), asserted equal/aligned, and independently
re-detected from the SAVED publication PNG (longest-dark-run spine
detection). A separate QA overlay image (Figure3_alignment_debug.png) draws
a magenta rectangle on every detected frame with its pixel coordinates —
diagnostics are NOT in the publication figure.

Outputs: <phase2c_r3>/outputs/fig03/Figure3_assembled.{png,pdf}
         <phase2c_r3>/outputs/fig03/Figure3_alignment_debug.png
         <phase2c_r3>/outputs/fig03/fig03_r3_frame_boxes.json
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

import json
import os
import sys

os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_CAND = os.path.dirname(_THIS_DIR)
sys.path.insert(0, _THIS_DIR)

import fig3_panels as P  # noqa: E402  (validated plotting functions, unchanged)
import q1_style as Q     # noqa: E402

if not P.HAVE_CARTOPY:
    raise RuntimeError("Cartopy is required to reproduce the approved panels")
import cartopy.crs as ccrs  # noqa: E402

OUT_DIR = os.path.join(_SCORCH_REPRO, "fig03")
os.makedirs(OUT_DIR, exist_ok=True)
DPI = 500

# ---- layout (inches). Axes aspect == extent aspect (50/36), so the visible
# ---- frame equals the axes rectangle exactly for every panel.
AX_W = 6.00
AX_H = AX_W * (P.LAT_MAX - P.LAT_MIN) / (P.LON_MAX - P.LON_MIN)   # 4.32
L_MARGIN = 0.55          # room for the left column's y tick labels
GUTTER = 0.80            # reserved colorbar gutter, identical for all panels
COL_GAP = 0.35           # gap between column-1 gutter and column-2 labels
R_MARGIN = 0.15
TOP_MARGIN = 0.50        # headroom for row-1 panel labels
ROW_GAP = 1.00           # identical row gaps (x labels + legend + labels)
BOT_MARGIN = 0.55
CB_PAD = 0.10            # map right edge -> colorbar
CB_W = 0.16              # colorbar width

FIG_W = L_MARGIN + AX_W + GUTTER + COL_GAP + AX_W + GUTTER + R_MARGIN
FIG_H = TOP_MARGIN + 3 * AX_H + 2 * ROW_GAP + BOT_MARGIN

X_LEFT = L_MARGIN
X_RIGHT = L_MARGIN + AX_W + GUTTER + COL_GAP
X_E = FIG_W / 2.0 - AX_W / 2.0            # (e) frame centered on the figure
Y_R1 = FIG_H - TOP_MARGIN - AX_H
Y_R2 = Y_R1 - ROW_GAP - AX_H
Y_R3 = Y_R2 - ROW_GAP - AX_H

BOXES_IN = {"a": (X_LEFT, Y_R1), "b": (X_RIGHT, Y_R1),
            "c": (X_LEFT, Y_R2), "d": (X_RIGHT, Y_R2),
            "e": (X_E, Y_R3)}


def _map_axes(fig, key):
    x, y = BOXES_IN[key]
    return fig.add_axes([x / FIG_W, y / FIG_H, AX_W / FIG_W, AX_H / FIG_H],
                        projection=ccrs.PlateCarree())


def _cbar_axes(fig, key):
    x, y = BOXES_IN[key]
    return fig.add_axes([(x + AX_W + CB_PAD) / FIG_W, y / FIG_H,
                         CB_W / FIG_W, AX_H / FIG_H])


def draw_panels(fig, df):
    axes = {}

    # (a) PCA axes + centroids (legend below the map, as approved).
    ax = _map_axes(fig, "a")
    P.setup_panel_ax(ax, df)
    P.plot_panel_a_axes(ax, df)
    axes["a"] = ax                         # gutter reserved, intentionally empty

    # (b) event-frequency heatmap + quantile colorbar (as the approved AB panel).
    ax = _map_axes(fig, "b")
    P.setup_panel_ax(ax, df)
    im, quantile_levels = P.plot_panel_b_ellipse_frequency(ax, df, fig)
    cbar = fig.colorbar(im, cax=_cbar_axes(fig, "b"), orientation="vertical",
                        ticks=quantile_levels)
    # Phase 3F LABEL-ONLY revision: footprint counts per cell, not events.
    cbar.set_label("PCA-ellipse footprints per grid cell", fontsize=9)
    cbar.ax.tick_params(labelsize=8, length=2.5, width=0.6)
    cbar.outline.set_linewidth(0.6)
    axes["b"] = ax

    # (c) L2/L1 ratio scatter (as the approved Panel_C).
    ax = _map_axes(fig, "c")
    P.setup_panel_ax(ax, df)
    ratio_norm = P.robust_norm(df["L2_L1_ratio"].values,
                               use_clip=P.USE_RATIO_PERCENTILE_CLIP)
    sc = P.plot_scatter(ax, df["centroid_lon"].values,
                        df["centroid_lat"].values,
                        c=df["L2_L1_ratio"].values,
                        s=P.POINT_SIZE + 12, alpha=0.72, zorder=8)
    sc.set_cmap(P.RATIO_CMAP)
    sc.set_norm(ratio_norm)
    cbar = fig.colorbar(sc, cax=_cbar_axes(fig, "c"), orientation="vertical")
    cbar.set_label("L2 / L1", fontsize=10)
    cbar.ax.tick_params(labelsize=9, length=2.5, width=0.6)
    cbar.outline.set_linewidth(0.6)
    axes["c"] = ax

    # (d) ellipse-area scatter (as the approved Panel_D).
    ax = _map_axes(fig, "d")
    P.setup_panel_ax(ax, df)
    area_norm = P.robust_norm(df["ellipse_area_km2"].values,
                              use_clip=P.USE_AREA_PERCENTILE_CLIP)
    sc = P.plot_scatter(ax, df["centroid_lon"].values,
                        df["centroid_lat"].values,
                        c=df["ellipse_area_km2"].values,
                        s=P.POINT_SIZE + 12, alpha=0.72, zorder=8)
    sc.set_cmap(P.AREA_CMAP)
    sc.set_norm(area_norm)
    cbar = fig.colorbar(sc, cax=_cbar_axes(fig, "d"), orientation="vertical")
    cbar.set_label("Area (km²)", fontsize=10)
    cbar.ax.tick_params(labelsize=9, length=2.5, width=0.6)
    cbar.outline.set_linewidth(0.6)
    axes["d"] = ax

    # (e) L1-orientation scatter (as the approved Panel_E).
    ax = _map_axes(fig, "e")
    P.setup_panel_ax(ax, df)
    sc = P.plot_scatter(ax, df["centroid_lon"].values,
                        df["centroid_lat"].values,
                        c=df["orientation_deg"].values,
                        s=P.POINT_SIZE + 12, alpha=0.75, zorder=8)
    sc.set_cmap(P.ORIENT_CMAP)
    sc.set_clim(-90, 90)
    cbar = fig.colorbar(sc, cax=_cbar_axes(fig, "e"), orientation="vertical")
    cbar.set_label("L1 orientation (°)", fontsize=10)
    cbar.ax.tick_params(labelsize=9, length=2.5, width=0.6)
    cbar.outline.set_linewidth(0.6)
    axes["e"] = ax

    return axes


def _frame_px(ax, fig):
    """Drawn frame rectangle in rendered pixels at the save DPI."""
    b = ax.get_position()
    return dict(x0=b.x0 * FIG_W * DPI, x1=b.x1 * FIG_W * DPI,
                y0=(1 - b.y1) * FIG_H * DPI, y1=(1 - b.y0) * FIG_H * DPI,
                w=b.width * FIG_W * DPI, h=b.height * FIG_H * DPI)


def detect_frames_in_png(path, expected, tol_px=25):
    """Independently re-detect each frame's spine rectangle in the saved PNG
    (longest contiguous dark run per row within the expected neighborhood)."""
    im = plt.imread(path)
    L = im[..., :3] @ np.array([0.299, 0.587, 0.114])
    dark = L < 0.25
    H, W = dark.shape
    out = {}
    for key, e in expected.items():
        r0 = max(int(e["y0"]) - tol_px, 0)
        r1 = min(int(e["y1"]) + tol_px, H)
        c0 = max(int(e["x0"]) - tol_px, 0)
        c1 = min(int(e["x1"]) + tol_px, W)
        sub = dark[r0:r1, c0:c1]
        best = []
        for i in range(sub.shape[0]):
            idx = np.flatnonzero(sub[i])
            if idx.size == 0:
                best.append((0, 0, 0))
                continue
            sp = np.where(np.diff(idx) > 1)[0]
            st = np.r_[idx[0], idx[sp + 1]]
            en = np.r_[idx[sp], idx[-1]]
            k = int(np.argmax(en - st))
            best.append((int(st[k]), int(en[k]), int(en[k] - st[k] + 1)))
        rows = [i for i, (_, _, l) in enumerate(best) if l >= 0.9 * e["w"]]
        top, bot = min(rows), max(rows)
        x0 = min(best[top][0], best[bot][0]) + c0
        x1 = max(best[top][1], best[bot][1]) + c0
        out[key] = dict(x0=x0, y0=top + r0, x1=x1, y1=bot + r0,
                        w=x1 - x0 + 1, h=bot - top + 1)
    return out


def main() -> None:
    df = P.load_and_prepare_data()
    print(f"[FIG3-R3] data rows: {len(df)}; extent "
          f"{P.LON_MIN}-{P.LON_MAX}E {P.LAT_MIN}-{P.LAT_MAX}N; "
          f"axes {AX_W:.2f} x {AX_H:.2f} in each; fig "
          f"{FIG_W:.2f} x {FIG_H:.2f} in @ {DPI} dpi")

    fig = plt.figure(figsize=(FIG_W, FIG_H))
    axes = draw_panels(fig, df)

    # Canonical labels centered above each VISIBLE FRAME (post-draw boxes).
    fig.canvas.draw()
    for key in ("a", "b", "c", "d", "e"):
        Q.label_above(fig, axes[key], f"({key})")

    # Drawn-frame geometry, asserted before saving.
    frames = {k: _frame_px(axes[k], fig) for k in axes}
    ws = {round(f["w"], 6) for f in frames.values()}
    hs = {round(f["h"], 6) for f in frames.values()}
    assert len(ws) == 1 and len(hs) == 1, (ws, hs)
    assert abs(frames["a"]["x0"] - frames["c"]["x0"]) < 1e-6
    assert abs(frames["b"]["x0"] - frames["d"]["x0"]) < 1e-6
    e_cx = (frames["e"]["x0"] + frames["e"]["x1"]) / 2.0
    assert abs(e_cx - FIG_W * DPI / 2.0) <= 0.5, e_cx
    print("[FIG3-R3] drawn visible frames (rendered px @ save dpi):")
    for k, f in frames.items():
        print(f"    ({k}) x0={f['x0']:.1f} y0={f['y0']:.1f} "
              f"w={f['w']:.1f} h={f['h']:.1f}")

    out_png = os.path.join(OUT_DIR, "Figure3_assembled.png")
    fig.savefig(out_png, dpi=DPI)
    fig.savefig(os.path.join(OUT_DIR, "Figure3_assembled.pdf"), dpi=DPI)
    print(f"[FIG3-R3] saved {out_png} (+pdf)")

    # Independent re-detection from the saved publication PNG.
    detected = detect_frames_in_png(out_png, frames)
    print("[FIG3-R3] independently detected frames in the saved PNG:")
    for k, d in detected.items():
        print(f"    ({k}) x0={d['x0']} y0={d['y0']} w={d['w']} h={d['h']}")
    dws = [d["w"] for d in detected.values()]
    dhs = [d["h"] for d in detected.values()]
    assert max(dws) - min(dws) <= 1, dws
    assert max(dhs) - min(dhs) <= 1, dhs
    assert abs(detected["a"]["x0"] - detected["c"]["x0"]) <= 1
    assert abs(detected["b"]["x0"] - detected["d"]["x0"]) <= 1
    det_e_cx = (detected["e"]["x0"] + detected["e"]["x1"]) / 2.0
    img_w = plt.imread(out_png).shape[1]
    assert abs(det_e_cx - img_w / 2.0) <= 1.5, (det_e_cx, img_w / 2.0)
    print(f"[FIG3-R3] ACCEPTANCE: width spread = {max(dws)-min(dws)} px, "
          f"height spread = {max(dhs)-min(dhs)} px (tolerance 1 px); "
          f"(a)/(c) x0 delta = {abs(detected['a']['x0']-detected['c']['x0'])}"
          f" px; (b)/(d) x0 delta = "
          f"{abs(detected['b']['x0']-detected['d']['x0'])} px; "
          f"(e) center offset from figure center = "
          f"{det_e_cx - img_w/2.0:+.1f} px")

    with open(os.path.join(OUT_DIR, "fig03_r3_frame_boxes.json"), "w",
              encoding="utf-8", newline="\n") as fh:
        json.dump({"drawn_px": frames, "detected_px": detected,
                   "dpi": DPI, "axes_in": [AX_W, AX_H]}, fh, indent=2,
                  sort_keys=True)

    # QA overlay (NOT part of the publication figure): magenta rectangle +
    # printed pixel geometry on every detected frame.
    img_h = FIG_H * DPI
    for k, d in detected.items():
        fig.add_artist(plt.Rectangle(
            (d["x0"] / img_w, 1 - (d["y1"] + 1) / img_h),
            d["w"] / img_w, d["h"] / img_h,
            transform=fig.transFigure, fill=False, edgecolor="magenta",
            linewidth=1.6, zorder=100))
        fig.text(d["x0"] / img_w, 1 - (d["y0"] - 12) / img_h,
                 f"({k}) x0={d['x0']} y0={d['y0']} w={d['w']} h={d['h']} px",
                 color="magenta", fontsize=9, fontweight="bold",
                 ha="left", va="bottom", zorder=100)
    fig.suptitle("QA OVERLAY — detected visible plot frames (not for "
                 "publication)", color="magenta", fontsize=13, y=0.998)
    dbg = os.path.join(OUT_DIR, "Figure3_alignment_debug.png")
    fig.savefig(dbg, dpi=DPI)
    print(f"[FIG3-R3] saved {dbg}")
    plt.close(fig)


if __name__ == "__main__":
    main()
