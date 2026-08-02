#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Q1-journal 2x2 power-law panel (Najibi-style, minimalist).

Combines the two existing pooled power-law diagnostics into a SINGLE coherent,
publication-quality 2x2 figure. Panels are regenerated from the underlying data
(NOT pasted from old PNGs) using the exact same selection + Clauset bootstrap
pipeline that produced the standalone figures, so every number is identical.

Panel layout
------------
    (a) Event-day CCDF        |  (b) Event-day bootstrap alpha boxplot
    -----------------------------------------------------------------
    (c) Event-level CCDF      |  (d) Event-level bootstrap alpha boxplot

Top row    = largest ellipse per event-day, n = 395
Bottom row = largest ellipse per event,     n = 51
Left col   = empirical CCDF + fitted power-law tail + A_min line
Right col  = pooled bootstrap-alpha distribution (5000 refits)

Note: the "bootstrap alpha" boxplots are the published Clauset power-law
bootstrap (5000 semi-parametric refits of the area power law), NOT the
withdrawn event-level bootstrap validation.

Source data (single source of truth)
------------------------------------
    <data-dir>/catalogs/scorch_new_algorithm_master_cluster_ellipse_event_global_max.csv
    Columns used: new_event_id, date (str), v3_type (int 1-4),
                  ellipse_area_km2 (float, km^2).

Reused logic (so the panels match the published standalone figures exactly):
    scripts/figures/common/power_law_largest_daily_ellipse.py   -> build_largest()           (n=395)
    scripts/figures/common/power_law_largest_event_ellipse.py   -> build_largest_per_event() (n=51)
    scripts/figures/common/task6_powerlaw.py                    -> analyze_group()  (Clauset MLE + bootstrap)

The CCDF empirical/fit curves use the SAME helpers (_ccdf, _fit_tail) and the
bootstrap-alpha arrays (_alpha_boot) come straight from analyze_group, run with
the SAME constants N_BOOT=5000 and SEED=20260617. The fit is therefore fully
deterministic and reproducible.

Inputs come from the processed-data deposit (master catalog +
power_law/ tables where needed); all outputs land under reproduced/.

Outputs (does NOT overwrite any existing figure)
------------------------------------------------
    reproduced/fig11/
        q1_power_law_2x2_panel_clean.png   (dpi=600)
        q1_power_law_2x2_panel_clean.pdf   (vector)

    The original q1_power_law_2x2_panel.png/.pdf from the first iteration are
    left untouched on disk; the "_clean" pair is the simplified presentation
    version requested by Dr. Najibi (2026-07-04): x-axis label reduced to
    "Area (km^2)", panel-(a) legend keeps only the A_min entry, panel-(c)
    legend removed, per-row titles added so the two rows stay distinguishable.
    2026-07-09 pass: all fonts enlarged for publication clarity; panel labels
    changed from uppercase A-D to lowercase round-bracket (a)-(d).

Run from the release root:  python scripts/figures/fig11/make_q1_power_law_2x2_panel.py
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

import numpy as np

# Headless rendering before pyplot is imported anywhere.
os.environ.setdefault("MPLBACKEND", "Agg")

_THIS = os.path.abspath(__file__)
# Phase 2C candidate copy: helper modules still come from the validated
# clean package; only the output location and the canonical label style
# (explicit black/Arial) change. REPO_ROOT kept for the relpath prints.
_CAND = os.path.dirname(os.path.dirname(_THIS))       # scripts/figures
REPO_ROOT = os.path.dirname(os.path.dirname(_CAND))    # release root
sys.path.insert(0, os.path.join(_CAND, "common"))

import power_law_largest_daily_ellipse as LD   # noqa: E402  build_largest(), _ccdf, _fit_tail
import power_law_largest_event_ellipse as LE   # noqa: E402  build_largest_per_event()
import task6_powerlaw as PL                    # noqa: E402  analyze_group()

import matplotlib as mpl                       # noqa: E402
import matplotlib.pyplot as plt                # noqa: E402

OUT_DIR = os.path.join(_SCORCH_REPRO, "fig11")
os.makedirs(OUT_DIR, exist_ok=True)
OUT_STEM = os.path.join(OUT_DIR, "q1_power_law_2x2_panel_clean")

# --- minimalist Q1 colour / style choices ------------------------------------
C_EMP = "black"       # empirical CCDF points: solid black (Najibi 2026-07-04)
C_FIT = "#b2182b"     # one strong clean line for the power-law tail
C_AMIN = "black"      # thin dashed A_min reference line
C_BOX = "0.90"        # very light grey box fill
C_BOXEDGE = "0.35"    # thin box edge
GRID = "0.90"         # very light grey major grid


def _apply_style() -> None:
    """Clean, consistent, white-background journal style."""
    mpl.rcParams.update({
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "font.size": 12.5,
        "axes.titlesize": 14,
        "axes.labelsize": 13.5,
        "xtick.labelsize": 12,
        "ytick.labelsize": 12,
        "legend.fontsize": 11.5,
        "axes.linewidth": 0.8,
        "axes.edgecolor": "black",
        "xtick.color": "black",
        "ytick.color": "black",
        "axes.labelcolor": "black",
        "text.color": "black",
        "xtick.direction": "out",
        "ytick.direction": "out",
        "lines.antialiased": True,
        "pdf.fonttype": 42,   # editable/vector-friendly text in PDF
        "ps.fonttype": 42,
    })


def _despine(ax) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("black")
    ax.spines["bottom"].set_color("black")


def _panel_label(ax, letter: str) -> None:
    """Canonical panel label (Phase 2C): Arial bold 17 pt black; identical
    axes-fraction offset for all four equal-size panels -> exact alignment."""
    ax.text(-0.16, 1.06, letter, transform=ax.transAxes,
            fontsize=17, fontweight="bold", va="top", ha="left",
            color="black", family="Arial")


def ccdf_panel(ax, res: dict, xlabel: str, stats_lines: list[str],
               legend: str | None = "amin_only") -> None:
    """Empirical CCDF points + fitted power-law tail + A_min line.

    legend: "amin_only" -> legend showing only the A_min entry (Dr. Najibi's
            request: drop "Empirical CCDF" and "Power-law tail" entries);
            None -> no legend at all.
    """
    a = np.sort(res["_data"])
    x, c = LD._ccdf(a)                                   # same empirical CCDF as standalone figs
    ax.loglog(x, c, ".", ms=4.5, color=C_EMP, alpha=0.85,
              label="_nolegend_", zorder=3)

    xt, ct = LD._fit_tail(res["xmin"], res["alpha"], res["n_total"],
                          res["n_tail"], a.max())        # identical tail anchoring
    ax.loglog(xt, ct, "-", color=C_FIT, lw=2.2,
              label="_nolegend_", zorder=4)

    ax.axvline(res["xmin"], ls="--", color=C_AMIN, lw=1.1,
               label=r"$A_{\min}$", zorder=2)

    ax.set_xlabel(xlabel)
    ax.set_ylabel(r"$P(\mathrm{area} \geq A)$")

    # Faint major grid only (helps read a log-log plot without clutter).
    ax.grid(True, which="major", color=GRID, lw=0.5, zorder=0)
    ax.set_axisbelow(True)
    _despine(ax)

    if legend == "amin_only":
        ax.legend(loc="upper right", frameon=False, handlelength=1.6,
                  borderaxespad=0.3)

    # Small, unobtrusive stats: bottom-left empty corner, no heavy box.
    ax.text(0.03, 0.04, "\n".join(stats_lines), transform=ax.transAxes,
            va="bottom", ha="left", fontsize=11.5, color="black",
            linespacing=1.4)


def alpha_box_panel(ax, res: dict) -> None:
    """Single pooled bootstrap-alpha box; outliers hidden.

    Najibi cleanup (2026-07-04): no x-axis label, no x tick labels, no x tick
    marks and no median annotation - the y-axis alone carries the information.
    """
    series = res["_alpha_boot"][~np.isnan(res["_alpha_boot"])]

    ax.boxplot(series, positions=[1], widths=0.45, showfliers=False,
               patch_artist=True, whis=(2.5, 97.5),
               medianprops=dict(color="black", lw=1.6),
               boxprops=dict(facecolor=C_BOX, edgecolor=C_BOXEDGE, lw=1.0),
               whiskerprops=dict(color=C_BOXEDGE, lw=1.0),
               capprops=dict(color=C_BOXEDGE, lw=1.0))

    ax.set_xlim(0.4, 1.6)
    ax.set_xticks([])
    ax.tick_params(axis="x", which="both", length=0)
    ax.set_ylabel(r"Bootstrap $\alpha$ estimate")
    ax.grid(True, axis="y", which="major", color=GRID, lw=0.5, zorder=0)
    ax.set_axisbelow(True)
    _despine(ax)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    _apply_style()

    # --- regenerate the two pooled fits from the master CSV (deterministic) ---
    sel_daily = LD.build_largest()                       # one largest ellipse / event-day
    assert sel_daily.shape[0] == 395, f"expected 395 event-days, got {sel_daily.shape[0]}"
    daily = PL.analyze_group(
        "All types (pooled)", sel_daily["ellipse_area_km2"].to_numpy(float),
        LD.N_BOOT, LD.SEED)

    sel_event = LE.build_largest_per_event()             # one largest ellipse / event
    assert sel_event.shape[0] == 51, f"expected 51 events, got {sel_event.shape[0]}"
    event = PL.analyze_group(
        "All types (pooled)", sel_event["ellipse_area_km2"].to_numpy(float),
        LE.N_BOOT, LE.SEED)

    # --- compose the 2x2 figure ----------------------------------------------
    fig, axes = plt.subplots(2, 2, figsize=(10.0, 8.4))
    (axA, axB), (axC, axD) = axes

    # Simplified x-label per Dr. Najibi; NO panel titles (2026-07-04 pass):
    # the n= values in the stats blocks distinguish the two rows.
    ccdf_panel(
        axA, daily,
        r"Area (km$^2$)",
        [f"$n$ = {daily['n_total']}",
         f"$n_{{\\mathrm{{tail}}}}$ = {daily['n_tail']}",
         rf"$\alpha \approx$ {daily['alpha']:.2f}",
         rf"$p \approx$ {daily['p_value']:.3f}"],
        legend="amin_only")
    _panel_label(axA, "(a)")

    alpha_box_panel(axB, daily)
    _panel_label(axB, "(b)")

    ccdf_panel(
        axC, event,
        r"Area (km$^2$)",
        [f"$n$ = {event['n_total']}",
         f"$n_{{\\mathrm{{tail}}}}$ = {event['n_tail']}",
         rf"$\alpha \approx$ {event['alpha']:.2f}",
         rf"$p \approx$ {event['p_value']:.3f}",
         "low statistical power"],
        legend=None)
    _panel_label(axC, "(c)")

    alpha_box_panel(axD, event)
    _panel_label(axD, "(d)")

    fig.subplots_adjust(left=0.085, right=0.975, top=0.955, bottom=0.075,
                        wspace=0.28, hspace=0.30)

    png = OUT_STEM + ".png"
    pdf = OUT_STEM + ".pdf"
    fig.savefig(png, dpi=600, bbox_inches="tight")
    fig.savefig(pdf, bbox_inches="tight")               # vector PDF
    plt.close(fig)

    # --- console confirmation -------------------------------------------------
    print("[Q1-2x2] regenerated from master CSV (seed=%d, n_boot=%d)"
          % (LD.SEED, LD.N_BOOT))
    print("[Q1-2x2] (a/b) event-day : n=%d  n_tail=%d  alpha=%.3f  p=%.4f"
          % (daily["n_total"], daily["n_tail"], daily["alpha"], daily["p_value"]))
    print("[Q1-2x2] (c/d) event-lvl : n=%d  n_tail=%d  alpha=%.3f  p=%.4f"
          % (event["n_total"], event["n_tail"], event["alpha"], event["p_value"]))
    print("[Q1-2x2] PNG -> %s" % os.path.relpath(png, REPO_ROOT))
    print("[Q1-2x2] PDF -> %s" % os.path.relpath(pdf, REPO_ROOT))


if __name__ == "__main__":
    main()
