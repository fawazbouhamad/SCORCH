#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Figure 2, panel (b) — Phase 2C-R4 (FINAL): naturally bounded
intersection ratio.

Final author-approved y-axis definition, from the deposit's
gridded/fig02_daily_extent.csv (one row per Apr-Sep day, 1940-2025;
columns date, n_hw, n_exceed, n_hw_exceed):

    x_t = n_heatwave / 1800                       (fraction of the domain
                                                   that is heatwave-labelled)
    y_t = |H_t ∩ E_t| / |E_t|
        = n_heatwave_and_exceedance / n_exceedance

numerator   = boxes with heatwave_id > 0 AND exceeding their local P95 on
              day t  (column n_hw_exceed)
denominator = all boxes exceeding their local P95 on day t (column n_exceed)

"Of all P95-exceeding boxes on a given day, what fraction are also
heatwave-labelled?" — naturally within [0, 1] because the intersection is a
subset of the exceedance boxes. NO capping, clipping, truncation,
winsorization, or reassignment is used anywhere (asserted at run time).
Days with n_exceedance = 0 remain NaN/excluded (zero denominator).

Display: the complete natural range 0 to 1 (all values below 0.3 and the 69
exact zeros included); no inset. Preserved from the approved composition:
hexbin gridsize 50, viridis colormap, log count normalization, full-height
"Number of days" colorbar, P97.5 threshold line (371 boxes = 0.2061),
fonts/Q1 styling, and the exact visible y-axis title
"Fraction of Heatwave Area Among Tmax Exceedances" (the intersection
formula is explained here and in METHOD_SPEC_fig02_R4_FINAL.md, not in the
visible label).

Outputs: <phase2c_r4>/outputs/fig02/fig02_panel_b_extent_hexbin.{png,pdf}
         <phase2c_r4>/outputs/fig02/fig02_daily_extent_intersection.csv
         <phase2c_r4>/outputs/fig02/fig02_ratio_diagnostics.csv
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

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LogNorm  # noqa: E402

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_CAND = os.path.dirname(_THIS_DIR)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(_CAND)),
                                "scripts"))
from _clean_paths import DATA_DIR, data_file  # noqa: E402


def generated(sub):
    p = os.path.join(_SCORCH_REPRO, sub)
    os.makedirs(p, exist_ok=True)
    return p


IN_CSV = data_file("fig02_daily_extent.csv", "gridded")
OUT_DIR = generated("fig02")
OUT_STEM = os.path.join(OUT_DIR, "fig02_panel_b_extent_hexbin")
OUT_TABLE_CSV = os.path.join(OUT_DIR, "fig02_daily_extent_intersection.csv")
OUT_DIAG_CSV = os.path.join(OUT_DIR, "fig02_ratio_diagnostics.csv")

N_BOXES = 1800  # valid 1-degree boxes in the domain (verified at build time)
GRIDSIZE = 50   # approved hex lattice parameter (unchanged)


def main() -> None:
    d = pd.read_csv(IN_CSV)
    assert {"date", "n_hw", "n_exceed", "n_hw_exceed"} <= set(d.columns)

    # P97.5 threshold exactly as 3_PCA_Algorithm.py (all Apr-Sep days, zeros in)
    thr_boxes = float(d["n_hw"].quantile(0.975, interpolation="higher"))
    thr_frac = thr_boxes / N_BOXES
    n_big = int((d["n_hw"] >= thr_boxes).sum())
    print(f"[FIG2b-R4] days={len(d)}; P97.5 threshold = {thr_boxes:.0f} boxes "
          f"= {thr_frac:.4f} of domain; big days = {n_big}")

    # Runtime assertion: the intersection is a subset of the exceedance set.
    assert (d["n_hw_exceed"] <= d["n_exceed"]).all(), \
        "n_heatwave_and_exceedance must never exceed n_exceedance"

    # Final derived table (author-specified columns; NaN on zero denominator).
    ratio = np.where(d["n_exceed"] > 0,
                     d["n_hw_exceed"] / d["n_exceed"].where(d["n_exceed"] > 0),
                     np.nan)
    finite = ratio[np.isfinite(ratio)]
    assert ((finite >= 0.0) & (finite <= 1.0)).all(), \
        "heatwave_among_exceedances must lie in [0, 1]"
    pd.DataFrame({
        "date": d["date"],
        "n_domain": N_BOXES,
        "n_heatwave": d["n_hw"],
        "n_exceedance": d["n_exceed"],
        "n_heatwave_and_exceedance": d["n_hw_exceed"],
        "heatwave_fraction_domain": d["n_hw"] / N_BOXES,
        "heatwave_among_exceedances": ratio,
    }).to_csv(OUT_TABLE_CSV, index=False)
    print(f"[SAVED] {OUT_TABLE_CSV}")

    n_zero_den = int((d["n_exceed"] == 0).sum())

    # Plotted set: the existing workflow's n_hw > 0 AND n_exceed > 0 days.
    sub = d[(d["n_hw"] > 0) & (d["n_exceed"] > 0)].copy()
    x = (sub["n_hw"] / N_BOXES).to_numpy(float)
    y = (sub["n_hw_exceed"] / sub["n_exceed"]).to_numpy(float)

    # Runtime assertions: naturally bounded, no cap applied anywhere.
    assert float(y.max()) <= 1.0, "no plotted y value may exceed 1"
    assert float(y.min()) >= 0.0
    src = open(os.path.abspath(__file__), encoding="utf-8").read()
    banned = ["mini" + "mum(", ".cl" + "ip(", "winso" + "rize"]
    assert all(src.count(tok) == 0 for tok in banned), \
        "no artificial cap/clip operation may be used"

    diag = {
        "n_plotted_days": len(sub),
        "min_ratio": float(y.min()),
        "max_ratio": float(y.max()),
        "median_ratio": float(np.median(y)),
        "p95_ratio": float(np.percentile(y, 95)),
        "p97_5_ratio": float(np.percentile(y, 97.5)),
        "p99_ratio": float(np.percentile(y, 99)),
        "n_below_0_3": int((y < 0.3).sum()),
        "n_equal_0": int((y == 0.0).sum()),
        "n_equal_1": int((y == 1.0).sum()),
        "n_above_1": int((y > 1.0).sum()),
        "n_zero_denominator_excluded": n_zero_den,
    }
    pd.DataFrame([diag]).to_csv(OUT_DIAG_CSV, index=False)
    for k, v in diag.items():
        print(f"[FIG2b-R4] {k} = {v}")

    fig, ax = plt.subplots(figsize=(9.0, 6.0))
    # Approved lattice/colormap/normalization; complete natural range 0..1.
    hb = ax.hexbin(x, y, gridsize=GRIDSIZE, cmap="viridis", norm=LogNorm(),
                   mincnt=1, linewidths=0.1,
                   extent=(0.0, 0.6, 0.0, 1.0))
    print(f"[FIG2b-R4] max hexbin count = {int(hb.get_array().max())}")

    ax.axvline(thr_frac, color="red", linestyle="--", linewidth=1.8, zorder=5)
    ax.text(thr_frac - 0.006, 0.03, "P97.5", color="red", rotation=90,
            ha="right", va="bottom", fontsize=13, fontweight="bold",
            transform=ax.get_xaxis_transform())

    ax.set_xlim(0.0, 0.6)
    ax.set_ylim(0.0, 1.01)
    # Phase 3F LABEL-ONLY revision: both quantities are grid-box COUNT
    # fractions (Methods 3.2: not an equal-area measure), so "Areal
    # Extent" is replaced by count-based coverage wording (same font
    # family/size/weight, rotation, alignment, axis spacing and Q1
    # styling; two-line wrap preserved).
    # V7 grid-cell terminology: displayed axis labels use "Grid Cells"
    # (docs/TERMINOLOGY.md); console diagnostics retain legacy tokens.
    ax.set_xlabel("Fraction of Domain Grid Cells with Heatwave Label",
                  fontsize=14, fontweight="bold")
    ax.set_ylabel("Heatwave-Labeled Fraction of\nTmax-Exceedance Grid Cells",
                  fontsize=14, fontweight="bold")
    ax.tick_params(labelsize=12)

    from mpl_toolkits.axes_grid1 import make_axes_locatable
    cax = make_axes_locatable(ax).append_axes("right", size="4.5%", pad=0.1)
    cbar = fig.colorbar(hb, cax=cax)
    cbar.set_label("Number of days", fontsize=13)
    cbar.ax.tick_params(labelsize=11)

    fig.tight_layout()
    for ext in ("png", "pdf"):
        p = f"{OUT_STEM}.{ext}"
        fig.savefig(p, dpi=600, bbox_inches="tight")
        print(f"[SAVED] {p}")
    plt.close(fig)


if __name__ == "__main__":
    main()
