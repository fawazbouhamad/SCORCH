#!/usr/bin/env python3
# RECOVERY TASK 3 — New Figure B candidate: DBSCAN parameter-selection
# (designated Fig. B in the appendices since 2026-07-30; the directory name
# "figA2" and the output filename are LEGACY INTERNAL names, not the current
# publication label.)
# matrices for the SIX consecutive days of Event 10 (Type 4), the exact
# representative event of main-manuscript Figure 7 (2001-08-07 .. 2001-08-12).
#
# This is the deployed figA02 generator (verbatim draw_panel/cell grammar,
# colors, typography, canonical q1_style labels) adapted ONLY in:
#   * event/dates (Event 7, 3 days  ->  Event 10, 6 days);
#   * layout (1x3  ->  2x3: (a)(b) / (c)(d) / (e)(f));
#   * data flow: the per-day matrices and highlighted cells are DERIVED HERE
#     from the canonical Method-A daily parameter grid via the SAME canonical
#     machinery the existing task05 products were built with
#     (scripts/six_task_review/common.py: load_grid_A + select_modal), then
#     saved as data slices and drawn from those slices exactly as the
#     deployed generator draws its slice CSVs. No value is typed by hand.
#   * final size declared at the manuscript's measured text width (159.2 mm).
# The provenance gate (provenance_check/) proved the unmodified generator
# reproduces the deployed Figure_A2.png byte-identically first.
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
os.environ.setdefault("SOURCE_DATE_EPOCH", "1753142400")  # fixed: PDF determinism
sys.dont_write_bytecode = True

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_CAND = os.path.dirname(_THIS_DIR)
REPO = _SCORCH_ROOT
_CLEAN = _SCORCH_ROOT
_CAND = os.path.join(_SCORCH_REPRO, "appendix_a2")
os.makedirs(_CAND, exist_ok=True)
sys.path.insert(0, _THIS_DIR)
sys.path.insert(0, os.path.join(_CLEAN, "scripts"))
sys.path.insert(0, os.path.join(REPO, "scripts", "six_task_review"))
import q1_style as Q
from _clean_paths import MASTER_CSV, data_file
import common as C          # canonical grid + modal-selection machinery

SLICE_DIR = os.path.join(_CAND, "data_slices")
os.makedirs(SLICE_DIR, exist_ok=True)

DAYS = ["2001-08-07", "2001-08-08", "2001-08-09",
        "2001-08-10", "2001-08-11", "2001-08-12"]
EVENT_ID = 10
HL_FACE = "#bcd9ec"
HL_EDGE = "#2a6ea6"
GLOBAL_PARAMS_CSV = data_file("event_global_max_parameters.csv", "catalogs")

# manuscript sectPr (read-only): A4 11906x16838 twips, margins 1440 twips
TEXT_W_IN = 9026.0 / 1440.0            # 6.2681 in = 159.21 mm


def verify_event() -> None:
    df = pd.read_csv(MASTER_CSV)
    e = df[df["new_event_id"] == EVENT_ID]
    dates = sorted(set(e["date"]))
    assert dates == DAYS, dates
    assert set(e["type"]) == {"Type 4"}, set(e["type"])
    print(f"[NEW-A2] global-max verified: event {EVENT_ID}, CURRENT type "
          f"'Type 4', days {dates}, ellipses/day "
          f"{e.groupby('date').size().to_dict()}")


def derive_slices() -> None:
    """Event-10 per-day matrix + highlighted-cell slices from the canonical
    Method-A grid, using the same code path as the existing task05 products
    (task5_heatmaps.build_matrix / modal_cells logic via common.py)."""
    grid = C.load_grid_A()
    for d in DAYS:
        sub = grid[grid["date"] == d]
        assert len(sub) == len(C.MIN_SAMPLES) * len(C.METHOD_A_EPS), (d, len(sub))
        M = np.full((len(C.MIN_SAMPLES), len(C.METHOD_A_EPS)), np.nan)
        for r in sub.itertuples():
            i = C.MIN_SAMPLES.index(int(r.min_samples))
            j = C.METHOD_A_EPS.index(float(r.eps))
            M[i, j] = int(r.n_components)
        assert np.isfinite(M).all()
        rows = C.day_grid_rows(grid, d)
        sel = C.select_modal(rows)
        tied = set(sel["modal_counts"])
        cells = [(r["eps"], r["min_samples"], r["n_components"])
                 for r in rows if r["n_components"] in tied]
        tag = f"event{EVENT_ID:02d}_type4_{d}"
        pd.DataFrame(M, index=[f"ms{m}" for m in C.MIN_SAMPLES],
                     columns=[f"eps{e_:.1f}" for e_ in C.METHOD_A_EPS]
                     ).to_csv(os.path.join(SLICE_DIR, f"matrix_{tag}.csv"))
        pd.DataFrame(cells, columns=["eps", "min_samples", "n_ellipses"]
                     ).to_csv(os.path.join(SLICE_DIR,
                                           f"highlighted_cells_{tag}.csv"),
                              index=False)
        sub.to_csv(os.path.join(SLICE_DIR, f"grid_rows_{tag}.csv"),
                   index=False)
        print(f"[NEW-A2] {d}: modal counts {sel['modal_counts']}, "
              f"{len(cells)} selected cells, avg eps {sel['avg_eps']:.3f}, "
              f"avg min_samples {sel['raw_avg_min_samples']:.3f}")


def draw_panel(ax, mat, hl, date, show_ylabel, show_xlabel):
    # VERBATIM cell grammar from the deployed figA02 generator; the only
    # signature change is show_xlabel (bottom row only in the 2x3 layout).
    ms = [int(s[2:]) for s in mat.index]          # ms4..ms12 -> 4..12
    eps = [float(c[3:]) for c in mat.columns]     # eps1.0.. -> 1.0..
    vals = mat.to_numpy(float)
    n_r, n_c = vals.shape
    hl_set = {(int(r.min_samples), float(r.eps)) for r in hl.itertuples()}
    for i in range(n_r):
        for j in range(n_c):
            is_hl = (ms[i], eps[j]) in hl_set
            if is_hl:
                ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1,
                                           facecolor=HL_FACE,
                                           edgecolor=HL_EDGE, linewidth=1.4,
                                           zorder=2))
            ax.text(j, i, f"{vals[i, j]:.0f}", ha="center", va="center",
                    fontsize=8.5, zorder=3,
                    fontweight="bold" if is_hl else "normal",
                    color="black")
    ax.set_xlim(-0.5, n_c - 0.5)
    ax.set_ylim(-0.5, n_r - 0.5)
    ax.set_xticks(range(n_c), [f"{e:g}" for e in eps], fontsize=9)
    ax.set_yticks(range(n_r), [str(m) for m in ms], fontsize=9)
    if show_xlabel:
        ax.set_xlabel("eps (grid-cell units)", fontsize=11)
    if show_ylabel:
        ax.set_ylabel("min_samples", fontsize=11)
    ax.set_xticks(np.arange(-0.5, n_c, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, n_r, 1), minor=True)
    ax.grid(which="minor", color="0.85", linewidth=0.5)
    ax.tick_params(which="minor", length=0)
    for s in ax.spines.values():
        s.set_linewidth(0.8)
    return hl["min_samples"].mean(), hl["eps"].mean()


def main() -> None:
    plt.rcParams.update({"font.family": "Arial", "pdf.fonttype": 42,
                         "ps.fonttype": 42})
    verify_event()
    derive_slices()

    # 2x3 layout in design inches (deployed panel proportions, then a final
    # uniform declare at the manuscript text width)
    AX_W, AX_H = 3.55, 3.24
    L_M, COL_GAP, R_M = 0.85, 0.75, 0.20
    LBL, ROW_GAP, TOP_M = 0.42, 0.30, 0.12
    XLB, BOT_M = 0.68, 0.10
    FIG_W = L_M + 2 * AX_W + COL_GAP + R_M
    FIG_H = TOP_M + 3 * (LBL + AX_H) + 2 * ROW_GAP + XLB + BOT_M
    FIG_W = round(FIG_W * 600) / 600.0
    FIG_H = round(FIG_H * 600) / 600.0

    fig = plt.figure(figsize=(FIG_W, FIG_H))
    axes = {}
    rows_stats = []
    for k, d in enumerate(DAYS):
        r, c = divmod(k, 2)
        x = L_M + c * (AX_W + COL_GAP)
        y = BOT_M + XLB + (2 - r) * (AX_H + LBL + ROW_GAP)
        tag = f"event{EVENT_ID:02d}_type4_{d}"
        mat = pd.read_csv(os.path.join(SLICE_DIR, f"matrix_{tag}.csv"),
                          index_col=0)
        hl = pd.read_csv(os.path.join(SLICE_DIR,
                                      f"highlighted_cells_{tag}.csv"))
        assert mat.shape == (9, 7), mat.shape
        ax = fig.add_axes([x / FIG_W, y / FIG_H, AX_W / FIG_W, AX_H / FIG_H])
        mean_ms, mean_eps = draw_panel(ax, mat, hl, d,
                                       show_ylabel=(c == 0),
                                       show_xlabel=(r == 2))
        rows_stats.append(dict(date=d, event_id=EVENT_ID,
                               current_type="Type 4",
                               n_selected_cells=len(hl),
                               mean_min_samples=mean_ms, mean_eps=mean_eps))
        axes[chr(ord("a") + k)] = ax
        print(f"[NEW-A2] {d}: {len(hl)} selected cells; selected means "
              f"min_samples {mean_ms:.3f} / eps {mean_eps:.3f}")
    fig.canvas.draw()
    for letter, ax in axes.items():
        Q.label_above(fig, ax, f"({letter})")

    gp = pd.read_csv(GLOBAL_PARAMS_CSV)
    gp10 = gp[gp["new_event_id"] == EVENT_ID]
    assert len(gp10) == 1
    stats = pd.DataFrame(rows_stats)
    stats["event_global_eps_max"] = gp10["event_global_eps_max"].iloc[0]
    stats["event_global_minpts_max_raw"] = gp10["event_global_minpts_max_raw"].iloc[0]
    stats["event_global_minpts_used"] = gp10["event_global_minpts_used"].iloc[0]
    stats_csv = os.path.join(_CAND, "New_Figure_A2_Event10_selected_cells_stats.csv")
    stats.to_csv(stats_csv, index=False)
    print(f"[SAVED] {stats_csv}")

    for ext in ("png", "pdf"):
        p = os.path.join(_CAND, f"New_Figure_A2_Event10_candidate.{ext}")
        fig.savefig(p, dpi=600)
        print(f"[SAVED] {p}")
    plt.close(fig)

    # final uniform declare at the manuscript text width (content untouched)
    from PIL import Image
    p_png = os.path.join(_CAND, "New_Figure_A2_Event10_candidate.png")
    im = Image.open(p_png)
    eff = im.size[0] / TEXT_W_IN
    im.save(p_png, dpi=(eff, eff))
    print(f"[NEW-A2] PNG {im.size[0]}x{im.size[1]} px declared {eff:.2f} ppi "
          f"-> {im.size[0]/eff*25.4:.1f} x {im.size[1]/eff*25.4:.1f} mm")
    from pypdf import PdfReader, PdfWriter, Transformation
    s = TEXT_W_IN / FIG_W
    p_pdf = os.path.join(_CAND, "New_Figure_A2_Event10_candidate.pdf")
    rd = PdfReader(p_pdf); wr = PdfWriter(); pg = rd.pages[0]
    pg.add_transformation(Transformation().scale(s, s))
    pg.mediabox.upper_right = (float(pg.mediabox.width) * s,
                               float(pg.mediabox.height) * s)
    wr.add_page(pg)
    with open(p_pdf, "wb") as fh:
        wr.write(fh)
    print(f"[NEW-A2] PDF scaled by {s:.4f} -> "
          f"{FIG_W*s*25.4:.1f} x {FIG_H*s*25.4:.1f} mm")


if __name__ == "__main__":
    main()
