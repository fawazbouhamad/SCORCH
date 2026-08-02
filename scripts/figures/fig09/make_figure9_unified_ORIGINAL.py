#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 2C-R2 — rebuild paper Figure 9 as ONE unified Q1-style 1x3 figure.

Rebuilt from the validated data/scripts (NOT raster manipulation). The data
pipeline is copied verbatim from the validated Phase 2C panel scripts
(Figure_11_CDFs.py / Figure_11_Orientation_Density.py): master-CSV ellipse
rows -> per-event averages (one value per catalogue event, typology straight
from the master's v3 columns), the same smoothed empirical CDFs, the same
dynamic x-limits, and the same gaussian_kde orientation density on
linspace(-90, 90, 600). All numerical curves are therefore unchanged.

Composition per the author's Phase 2C-R2 instructions:
  * one balanced 1x3 layout; (a)/(b)/(c) data axes EXACTLY equal in width
    and height (manual add_axes), identical gaps, aligned top and bottom;
  * one shared plotting style (Arial, one tick/label size, one spine spec,
    one grid policy, one curve line width, validated Type 1-4 colors, no
    internal titles);
  * canonical (a)/(b)/(c) labels centered above each DATA-AXIS box with one
    shared vertical offset; for (c) the x-axis is symmetric (-90..90), so
    the label center sits exactly above orientation = 0 (verified at run
    time from the data transform);
  * NO per-panel legends; ONE shared horizontal Type 1-4 legend centered in
    a dedicated bottom region, colors/line meanings unchanged.

Outputs: <phase2c_r2>/outputs/fig09/Figure9_assembled.{png,pdf}
         figure9_panel_{a,b,c}_*.png/pdf (reproducibility components)
         figure_CDF_event_average_geometry_values.csv (same schema as 2C)
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

import math
import os
import sys
import warnings

os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from scipy.stats import gaussian_kde  # noqa: E402

warnings.filterwarnings("ignore", category=RuntimeWarning)

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_CAND = os.path.dirname(_THIS_DIR)
sys.path.insert(0, _THIS_DIR)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(_CAND)),
                                "scripts"))
from _clean_paths import MASTER_CSV  # noqa: E402
import q1_style as Q  # noqa: E402

OUT_DIR = os.path.join(_SCORCH_REPRO, "fig09")
os.makedirs(OUT_DIR, exist_ok=True)

TYPE_ORDER = ["Type 1", "Type 2", "Type 3", "Type 4"]
TYPE_COLORS = {          # validated plot palette (unchanged from 2A/2B/2C)
    "Type 1": "#d7191c",
    "Type 2": "#f57c00",
    "Type 3": "#d9a300",
    "Type 4": "#6a3d9a",
}

# ---- one shared style ---------------------------------------------------------
LINE_WIDTH = 2.15
LABEL_FS = 11.5
TICK_FS = 9.5
LEGEND_FS = 11
SPINE_LW = 0.8
GRID_KW = dict(alpha=0.22, linewidth=0.45)

# ---- unified layout (figure fractions; identical axes by construction) -------
FIG_W, FIG_H = 15.0, 4.9
AX_W, AX_H = 0.28, 0.655
AX_BOTTOM = 0.225            # dedicated bottom region reserved for the legend
AX_LEFT0, AX_GAP = 0.050, 0.0455
LEGEND_Y = 0.035


# =============================================================================
# DATA PIPELINE — copied verbatim from the validated Phase 2C panel scripts
# =============================================================================
def orientation_from_north_deg(pc1_vec_x, pc1_vec_y):
    vx = float(pc1_vec_x)
    vy = float(pc1_vec_y)
    if not np.isfinite(vx) or not np.isfinite(vy):
        return np.nan
    n = math.hypot(vx, vy)
    if n <= 0:
        return np.nan
    vx /= n
    vy /= n
    theta = np.degrees(np.arctan2(vx, vy))
    if theta > 90:
        theta -= 180
    if theta < -90:
        theta += 180
    return theta


def prepare_ellipse_dataframe(metrics_csv):
    if not os.path.exists(metrics_csv):
        raise FileNotFoundError(metrics_csv)
    df = pd.read_csv(metrics_csv)
    required_cols = [
        "date",
        "centroid_lon", "centroid_lat",
        "axis1_len_km", "axis2_len_km",
        "pc1_vec_x", "pc1_vec_y",
        "pc2_vec_x", "pc2_vec_y",
    ]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(missing))
    df["date"] = pd.to_datetime(df["date"])
    df = df[
        np.isfinite(df["centroid_lon"]) &
        np.isfinite(df["centroid_lat"]) &
        np.isfinite(df["axis1_len_km"]) &
        np.isfinite(df["axis2_len_km"]) &
        np.isfinite(df["pc1_vec_x"]) &
        np.isfinite(df["pc1_vec_y"]) &
        np.isfinite(df["pc2_vec_x"]) &
        np.isfinite(df["pc2_vec_y"])
    ].copy()
    df = df[(df["axis1_len_km"] > 0) & (df["axis2_len_km"] > 0)].copy()
    # Event id and typology straight from the master's v3 columns
    # (new_event_id, type, event_type_original) — the validated repair.
    df["event_id"] = df["new_event_id"]
    df = df[df["type"].isin(TYPE_ORDER)].copy()
    df["orientation_deg"] = df.apply(
        lambda r: orientation_from_north_deg(r["pc1_vec_x"], r["pc1_vec_y"]),
        axis=1
    )
    df["ellipse_area_km2"] = (
        np.pi * (df["axis1_len_km"] / 2.0) *
        (df["axis2_len_km"] / 2.0)
    )
    df["ellipse_area_million_km2"] = df["ellipse_area_km2"] / 1e6
    df["ratio_L2_L1"] = df["axis2_len_km"] / df["axis1_len_km"]
    df = df[
        np.isfinite(df["orientation_deg"]) &
        np.isfinite(df["ellipse_area_million_km2"]) &
        np.isfinite(df["ratio_L2_L1"])
    ].copy()
    return df


def convert_to_event_average_dataframe(df):
    event_df = (
        df.groupby(["event_id", "event_type_original", "type"], as_index=False)
        .agg(
            start_date=("date", "min"),
            end_date=("date", "max"),
            n_ellipse_rows=("date", "size"),
            n_active_dates=("date", "nunique"),
            orientation_deg=("orientation_deg", "mean"),
            ellipse_area_million_km2=("ellipse_area_million_km2", "mean"),
            ratio_L2_L1=("ratio_L2_L1", "mean"),
        )
    )
    event_df["event_id"] = event_df["event_id"].astype(int)
    return event_df


def smooth_empirical_cdf(values, x_min, x_max, n_grid=700):
    vals = np.asarray(values, dtype=float)
    vals = vals[np.isfinite(vals)]
    vals = np.sort(vals)
    if len(vals) == 0:
        return None, None
    y_emp = np.arange(1, len(vals) + 1) / len(vals)
    x_anchor = np.concatenate(([x_min], vals, [x_max]))
    y_anchor = np.concatenate(([0.0], y_emp, [1.0]))
    x_grid = np.linspace(x_min, x_max, n_grid)
    y_grid = np.interp(x_grid, x_anchor, y_anchor)
    return x_grid, y_grid


def get_dynamic_xlim(event_df, metric_col):
    vals = event_df[metric_col].replace([np.inf, -np.inf], np.nan).dropna().values
    xmin = np.nanmin(vals)
    xmax = np.nanmax(vals)
    if not np.isfinite(xmin) or not np.isfinite(xmax):
        raise ValueError(f"No finite values found for {metric_col}")
    if xmin == xmax:
        pad = 0.05 if xmin == 0 else abs(xmin) * 0.05
    else:
        pad = 0.035 * (xmax - xmin)
    return xmin - pad, xmax + pad


def kde_curve(values, x_grid):
    vals = np.asarray(values, dtype=float)
    vals = vals[np.isfinite(vals)]
    if len(vals) < 2 or np.nanstd(vals) == 0:
        return None
    kde = gaussian_kde(vals)
    return kde(x_grid)


# =============================================================================
# UNIFIED PANEL RENDERERS (one shared style; curves numerically unchanged)
# =============================================================================
def _style_axes(ax):
    ax.grid(True, **GRID_KW)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_linewidth(SPINE_LW)
    ax.spines["bottom"].set_linewidth(SPINE_LW)
    ax.tick_params(axis="both", labelsize=TICK_FS, length=3,
                   width=SPINE_LW, direction="out")


def draw_cdf(ax, event_df, metric_col, xlabel):
    x_min, x_max = get_dynamic_xlim(event_df, metric_col)
    for typ in TYPE_ORDER:
        sub = event_df[event_df["type"] == typ]
        values = sub[metric_col].replace([np.inf, -np.inf],
                                         np.nan).dropna().values
        if len(values) == 0:
            continue
        x_curve, y_curve = smooth_empirical_cdf(values, x_min, x_max)
        ax.plot(x_curve, y_curve, color=TYPE_COLORS[typ],
                linewidth=LINE_WIDTH, solid_capstyle="round",
                solid_joinstyle="round")
    ax.set_xlim(x_min, x_max)
    ax.set_ylim(0, 1.02)
    ax.set_xlabel(xlabel, fontsize=LABEL_FS)
    ax.set_ylabel("Cumulative probability", fontsize=LABEL_FS)
    _style_axes(ax)


def draw_orientation(ax, event_df):
    x_grid = np.linspace(-90, 90, 600)
    for typ in TYPE_ORDER:
        vals = event_df.loc[event_df["type"] == typ,
                            "orientation_deg"].dropna().values
        density = kde_curve(vals, x_grid)
        if density is None:
            ax.scatter(vals, np.zeros_like(vals), color=TYPE_COLORS[typ],
                       s=18, edgecolor="white", linewidth=0.35, zorder=4)
            continue
        ax.plot(x_grid, density, color=TYPE_COLORS[typ],
                linewidth=LINE_WIDTH, zorder=3)
    ax.axvline(0, color="0.35", linewidth=0.75, linestyle="--", zorder=1)
    ax.set_xlim(-90, 90)
    ax.set_xticks(np.arange(-90, 91, 30))
    ax.set_ylim(bottom=0)
    ax.set_xlabel("Orientation (°)", fontsize=LABEL_FS)
    ax.set_ylabel("Probability Density", fontsize=LABEL_FS)
    _style_axes(ax)


PANELS = [
    ("a", "area CDF",
     lambda ax, e: draw_cdf(ax, e, "ellipse_area_million_km2",
                            "Area (km² × 10⁶)")),
    ("b", "ratio CDF",
     lambda ax, e: draw_cdf(ax, e, "ratio_L2_L1", "Ratio (L2/L1)")),
    ("c", "orientation density",
     lambda ax, e: draw_orientation(ax, e)),
]


def legend_handles():
    return [Line2D([0], [0], color=TYPE_COLORS[t], lw=LINE_WIDTH, label=t)
            for t in TYPE_ORDER]


def main() -> None:
    plt.rcParams.update({
        "font.family": "Arial",
        "font.size": TICK_FS,
        "axes.labelsize": LABEL_FS,
        "xtick.labelsize": TICK_FS,
        "ytick.labelsize": TICK_FS,
        "axes.linewidth": SPINE_LW,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })

    df_ellipse = prepare_ellipse_dataframe(MASTER_CSV)
    event_df = convert_to_event_average_dataframe(df_ellipse)
    csv_out = os.path.join(OUT_DIR,
                           "figure_CDF_event_average_geometry_values.csv")
    event_df.to_csv(csv_out, index=False)
    counts = event_df["type"].value_counts().reindex(TYPE_ORDER).fillna(0)
    print("[FIG9-R2] events per type:",
          ", ".join(f"{t}={int(counts[t])}" for t in TYPE_ORDER),
          f"(total {len(event_df)})")
    print(f"[SAVED] {csv_out}")

    # ---- unified 1x3 assembly -------------------------------------------------
    fig = plt.figure(figsize=(FIG_W, FIG_H))
    axes = []
    for i, (letter, _, drawer) in enumerate(PANELS):
        ax = fig.add_axes([AX_LEFT0 + i * (AX_W + AX_GAP), AX_BOTTOM,
                           AX_W, AX_H])
        drawer(ax, event_df)
        axes.append(ax)

    # Canonical labels centered above each DATA-AXIS box (q1_style).
    for (letter, _, _), ax in zip(PANELS, axes):
        Q.label_above(fig, ax, f"({letter})")

    # One shared horizontal legend, dedicated bottom region, one row.
    fig.legend(handles=legend_handles(), loc="lower center",
               bbox_to_anchor=(0.5, LEGEND_Y), ncol=4, frameon=False,
               fontsize=LEGEND_FS, handlelength=2.6, columnspacing=1.8)

    # ---- measurements for the report ------------------------------------------
    fig.canvas.draw()
    print("[FIG9-R2] axes boxes (inches):")
    sizes = set()
    for (letter, _, _), ax in zip(PANELS, axes):
        b = ax.get_position()
        w_in, h_in = b.width * FIG_W, b.height * FIG_H
        sizes.add((round(w_in, 9), round(h_in, 9)))
        print(f"    ({letter}) x0={b.x0*FIG_W:.3f} y0={b.y0*FIG_H:.3f} "
              f"w={w_in:.3f} h={h_in:.3f}")
    assert len(sizes) == 1, sizes
    print(f"[FIG9-R2] identical data-axis size confirmed: "
          f"{sizes.pop()} in; gaps = {AX_GAP*FIG_W:.3f} in")
    # (c) label sits exactly above orientation = 0 (symmetric x-axis).
    ax_c = axes[2]
    x0_disp = ax_c.transData.transform((0.0, 0.0))[0]
    cx_disp = (ax_c.get_position().x0 + ax_c.get_position().x1) / 2.0 \
        * FIG_W * fig.dpi
    print(f"[FIG9-R2] (c): orientation=0 display x = {x0_disp:.2f} px; "
          f"axes-center display x = {cx_disp:.2f} px "
          f"(delta {abs(x0_disp - cx_disp):.4f} px)")
    assert abs(x0_disp - cx_disp) < 0.51

    for ext in ("png", "pdf"):
        out = os.path.join(OUT_DIR, f"Figure9_assembled.{ext}")
        fig.savefig(out, dpi=600)
        print(f"[FIG9-R2] saved {out}")
    plt.close(fig)

    # ---- reproducibility component panels (same style, one per file) ----------
    stems = {"a": "figure9_panel_a_area_cdf",
             "b": "figure9_panel_b_ratio_cdf",
             "c": "figure9_panel_c_orientation_density"}
    for letter, _, drawer in PANELS:
        f1 = plt.figure(figsize=(5.6, 4.2))
        ax = f1.add_axes([0.13, 0.14, 0.83, 0.82])
        drawer(ax, event_df)
        for ext in ("png", "pdf"):
            p = os.path.join(OUT_DIR, f"{stems[letter]}.{ext}")
            f1.savefig(p, dpi=600)
        plt.close(f1)
        print(f"[FIG9-R2] saved component {stems[letter]}.png/.pdf")

    print("[DONE] Figure 9 unified rebuild complete")


if __name__ == "__main__":
    main()
