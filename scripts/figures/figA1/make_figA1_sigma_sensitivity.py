#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 2E — Figure A candidate: PCA sigma sensitivity matrices
(slide 17 rebuilt from the validated derived matrices).

Designated Fig. A in the appendices since 2026-07-30. The directory name
"figA1" and the output filename are LEGACY INTERNAL names, not the current
publication label.

The four matrices were computed from the current global-max labels/master
by the research repository's sigma-sensitivity script; the frozen derived
CSVs ship with this release at scripts/figures/figA1_inputs/ (env
SCORCH_FIGA1_INPUTS). This candidate RE-RENDERS those unchanged derived
matrices (values identical to the slide) in the canonical Q1 style:

  * (a) Minimum (%)  (b) Maximum (%)  (c) Average (%)  (d) Combined score
  * four exactly aligned equal heatmap panels;
  * per-panel colorbars kept (the four quantities have DIFFERENT scales —
    verified: %, %, %, unitless score — so a shared colorbar would be wrong);
  * the sigma_PC1 = sigma_PC2 diagonal outline preserved (magenta), cell
    values preserved; the long slide header removed (caption carries it).

Not event-classification-dependent (sensitivity is computed over the whole
760-ellipse global-max set).

Outputs: reproduced/appendix/Figure_A1_pca_sigma_sensitivity.{png,pdf}
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("MPLBACKEND", "Agg")
sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_FIGS = os.path.dirname(_THIS_DIR)                       # scripts/figures
_ROOT = os.path.dirname(os.path.dirname(_FIGS))          # release root
sys.path.insert(0, os.path.join(_FIGS, "common"))
import q1_style as Q  # noqa: E402

# Fig A inputs: the four frozen sigma-sensitivity matrices ship with the
# release under scripts/figures/figA1_inputs/ (env-overridable).
SRC_DIR = os.environ.get("SCORCH_FIGA1_INPUTS",
                         os.path.join(_FIGS, "figA1_inputs"))
OUT_DIR = os.path.join(os.environ.get(
    "SCORCH_OUT_DIR", os.path.join(_ROOT, "reproduced")), "appendix")
os.makedirs(OUT_DIR, exist_ok=True)

PANELS = [("a", "pca_sigma_matrix_minimum.csv", "Minimum (%)", "%.0f"),
          ("b", "pca_sigma_matrix_maximum.csv", "Maximum (%)", "%.0f"),
          ("c", "pca_sigma_matrix_average.csv", "Average (%)", "%.0f"),
          ("d", "pca_sigma_matrix_combined.csv", "Combined score", "%.0f")]
LABEL_FS = 11
TICK_FS = 9


def draw_matrix(ax, fig, mat, cbar_label, fmt):
    sig_rows = [float(s) for s in mat.index]
    sig_cols = [float(c) for c in mat.columns]
    vals = mat.to_numpy(float)
    im = ax.imshow(vals, cmap="viridis", aspect="equal")
    vmin, vmax = np.nanmin(vals), np.nanmax(vals)
    for i in range(vals.shape[0]):
        for j in range(vals.shape[1]):
            frac = (vals[i, j] - vmin) / (vmax - vmin) if vmax > vmin else 1
            ax.text(j, i, fmt % vals[i, j], ha="center", va="center",
                    fontsize=7.2,
                    color="white" if frac < 0.55 else "black")
        if i < vals.shape[1]:      # sigma_PC1 == sigma_PC2 diagonal outline
            ax.add_patch(plt.Rectangle((i - 0.5, i - 0.5), 1, 1, fill=False,
                                       edgecolor="magenta", linewidth=1.6,
                                       zorder=5))
    ax.set_xticks(range(len(sig_cols)), [f"{s:g}" for s in sig_cols],
                  fontsize=TICK_FS)
    ax.set_yticks(range(len(sig_rows)), [f"{s:g}" for s in sig_rows],
                  fontsize=TICK_FS)
    ax.set_xlabel(r"$\sigma_{PC2}$ (Minor Axis)", fontsize=LABEL_FS)
    ax.set_ylabel(r"$\sigma_{PC1}$ (Major Axis)", fontsize=LABEL_FS)
    b = ax.get_position()
    cax = fig.add_axes([b.x1 + 0.012, b.y0, 0.012, b.height])
    cbar = fig.colorbar(im, cax=cax)
    cbar.set_label(cbar_label, fontsize=10)
    cbar.ax.tick_params(labelsize=8.5)


def main() -> None:
    plt.rcParams.update({"font.family": "Arial", "pdf.fonttype": 42,
                         "ps.fonttype": 42})
    mats = {}
    for letter, name, label, fmt in PANELS:
        m = pd.read_csv(os.path.join(SRC_DIR, name), index_col=0)
        assert m.shape == (9, 9), (name, m.shape)
        mats[letter] = (m, label, fmt)
        print(f"[FIGA1] ({letter}) {name}: {m.shape}, "
              f"range {m.min().min():.0f}..{m.max().max():.0f}")

    fig = plt.figure(figsize=(11.6, 10.6))
    AX_W, AX_H = 0.335, 0.365
    X0 = {0: 0.075, 1: 0.575}
    Y0 = {0: 0.565, 1: 0.075}
    axes = {}
    for letter, (r, c) in (("a", (0, 0)), ("b", (0, 1)),
                           ("c", (1, 0)), ("d", (1, 1))):
        ax = fig.add_axes([X0[c], Y0[r], AX_W, AX_H])
        m, label, fmt = mats[letter]
        draw_matrix(ax, fig, m, label, fmt)
        axes[letter] = ax
    fig.canvas.draw()
    for letter, ax in axes.items():
        Q.label_above(fig, ax, f"({letter})")

    for ext in ("png", "pdf"):
        p = os.path.join(OUT_DIR, f"Figure_A1_pca_sigma_sensitivity.{ext}")
        fig.savefig(p, dpi=600)
        print(f"[SAVED] {p}")
    plt.close(fig)


if __name__ == "__main__":
    main()
