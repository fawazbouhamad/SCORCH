#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reproduce the 4-panel **PCA Sigma Sensitivity Matrix** on EVENT-GLOBAL-MAX data.

This is the matrix coverage/overlap method of the original sensitivity
producer. The original producer was recovered from the research working
tree, sanitized for portable reproduction, and wired into the release
workflow (see the provenance note below); its regenerated output is
byte-identical to the frozen release matrices. The combined score is
Min + Max + Average; at the equal-sigma diagonal cell (1.25, 1.25) the
exact verified account is
29.20696324951644 + 100 + 75.33710405670476 = 204.5440673062212,
displayed as 205, and this cell is the maximum along the equal-sigma
diagonal.

Method
------
For every component (cluster) we fit PCA in the local km plane and measure the
canonical **target_component_purity = |H n E| / |E|** (exactly as
`outputs/all_event_reports_sigma_1p25_corrected_purity_run.py::cluster_metrics`),
where H = the component's heatwave cells and E = the ellipse FOOTPRINT (the set of
1-degree grid cells whose centres fall inside the ellipse). The ellipse's MAJOR
semi-axis is scaled by sigma_PC1 and MINOR by sigma_PC2 INDEPENDENTLY, over the
grid sigma in
    [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5].
Purity DECREASES with sigma (a larger ellipse footprint dilutes the component),
which is the behaviour seen in the original figure's Average panel. Same variance
floor (1.0 km^2) as the canonical ellipse geometry.

For each (sigma_PC1, sigma_PC2) cell we aggregate target_component_purity across
ALL components:
    A. Minimum matrix (%)  = min purity over components
    B. Maximum matrix (%)  = max purity over components
    C. Average matrix (%)  = mean purity over components
    D. Combined score      = A + B + C
The recommended sigma is the DIAGONAL cell (sigma_PC1 == sigma_PC2) with the
highest combined score. The best off-diagonal pair is reported for reference only.

Provenance note (v1.0.0 pre-release correction)
------------------------
Until the v1.0.0 pre-release alignment pass, the release shipped only the FROZEN derived
matrices at scripts/figures/figA1_inputs/ and the Figure A renderer merely
re-rendered them. Re-rendering archived numbers is not end-to-end reproduction.
This script -- the actual producer -- was recovered from the research working
tree, sanitized of its research-repo layout assumptions, and added here. Its
output is byte-identical to those frozen inputs (all four matrices, 760
components), so Figure A now reproduces from the deposit rather than from an
archived artifact.

Inputs (from the versioned processed-data deposit, via SCORCH_DATA_DIR):
    catalogs/final_labels_event_global_max.csv   (components: date, lon, lat, label)
    catalogs/scorch_new_algorithm_master_cluster_ellipse_event_global_max.csv

Outputs -> <SCORCH_OUT_DIR>/appendix_a_sigma_matrices/
    pca_sigma_matrix_minimum.csv / _maximum.csv / _average.csv / _combined.csv
    pca_sigma_matrices_global_max.xlsx   (one sheet per matrix)
    pca_sigma_sensitivity_matrix_global_max.png / .pdf   (4-panel figure)
    SIGMA_MATRIX_RECOMMENDATION_global_max.md
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import pandas as pd

_THIS = os.path.abspath(__file__)
_FIGS = os.path.dirname(os.path.dirname(_THIS))            # scripts/figures
REPO_ROOT = os.path.dirname(os.path.dirname(_FIGS))        # release root
sys.path.insert(0, os.path.join(_FIGS, "common"))
import ellipse_pca as ep  # noqa: E402  (canonical PCA + variance floor)
from _clean_paths import LABELS_CSV, MASTER_CSV, generated  # noqa: E402

os.environ.setdefault("MPLBACKEND", "Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Pre-release-correction sanitization: inputs come from the versioned processed-data deposit
# (honouring SCORCH_DATA_DIR) and outputs go to the reproduced-outputs root
# (honouring SCORCH_OUT_DIR). The research-repo layout that this script
# originally assumed -- outputs/event_global_max_algorithm/ -- is gone; no
# absolute path, temporary directory or private workspace is referenced.
LABELS = LABELS_CSV
MASTER = MASTER_CSV
OUT = generated("appendix_a_sigma_matrices")
SIGMAS = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5]
NOISE = -1


def _kmlon(clat):
    return 111.320 * math.cos(math.radians(clat))


def footprint_set(H_cells, clon, clat, eigvecs, a, b):
    """Set of 1-degree grid cells whose centres fall inside the (a,b) ellipse.

    Faithful copy of footprint_set in the canonical purity generator.
    """
    lons = np.array([c[0] for c in H_cells], float)
    lats = np.array([c[1] for c in H_cells], float)
    R = max(a, b)
    kl = int(math.ceil(R / _kmlon(clat) + 1)) + 1
    ka = int(math.ceil(R / 110.574 + 1)) + 1
    rl, ra = lons[0], lats[0]
    cl_ = rl + np.arange(round(clon - rl) - kl, round(clon - rl) + kl + 1)
    ca = ra + np.arange(round(clat - ra) - ka, round(clat - ra) + ka + 1)
    GL, GA = np.meshgrid(cl_, ca)
    gl, ga = GL.ravel(), GA.ravel()
    xy = ep.project_lonlat_to_km(gl, ga, clon, clat)
    pc = xy @ eigvecs
    ins = (pc[:, 0] / a) ** 2 + (pc[:, 1] / b) ** 2 <= 1.0 + 1e-12
    return {(round(float(x), 6), round(float(y), 6))
            for x, y in zip(gl[ins], ga[ins])}


def component_record(lon, lat):
    """(clon, clat, eigvecs, ev0, ev1, H_set) for one component."""
    clon, clat = float(lon.mean()), float(lat.mean())
    xy = ep.project_lonlat_to_km(lon, lat, clon, clat)
    _, eigvecs, eigvals = ep.fit_pca(xy)
    ev0 = max(float(eigvals[0]), ep._VAR_FLOOR)
    ev1 = max(float(eigvals[1]), ep._VAR_FLOOR)
    H = {(round(float(x), 6), round(float(y), 6)) for x, y in zip(lon, lat)}
    return clon, clat, eigvecs, ev0, ev1, H


def target_purity_pct(comp, s1, s2):
    """target_component_purity = 100 * |H n E| / |E| for the (s1,s2) ellipse."""
    clon, clat, eigvecs, ev0, ev1, H = comp
    a = s1 * math.sqrt(ev0)
    b = s2 * math.sqrt(ev1)
    E = footprint_set(list(H), clon, clat, eigvecs, a, b)
    return 100.0 * len(H & E) / len(E) if E else float("nan")


def main():
    os.makedirs(OUT, exist_ok=True)
    lab = pd.read_csv(LABELS)
    lab["date"] = lab["date"].astype(str)

    comps = []  # (clon, clat, eigvecs, ev0, ev1, H_set)
    for (date, label), g in lab.groupby(["date", "label"]):
        if int(label) == NOISE:
            continue
        comps.append(component_record(g["lon"].to_numpy(float),
                                      g["lat"].to_numpy(float)))
    n_comp = len(comps)

    n = len(SIGMAS)
    purity = np.zeros((n, n, n_comp), dtype=float)  # [i=PC1, j=PC2, component]
    for i, s1 in enumerate(SIGMAS):
        for j, s2 in enumerate(SIGMAS):
            purity[i, j, :] = [target_purity_pct(c, s1, s2) for c in comps]
    mn = np.nanmin(purity, axis=2)
    mx = np.nanmax(purity, axis=2)
    av = np.nanmean(purity, axis=2)
    combined = mn + mx + av

    idx = pd.Index(SIGMAS, name="sigma_PC1_major")
    cols = pd.Index(SIGMAS, name="sigma_PC2_minor")
    M = pd.DataFrame(mn, idx, cols)
    X = pd.DataFrame(mx, idx, cols)
    A = pd.DataFrame(av, idx, cols)
    C = pd.DataFrame(combined, idx, cols)
    M.to_csv(os.path.join(OUT, "pca_sigma_matrix_minimum.csv"))
    X.to_csv(os.path.join(OUT, "pca_sigma_matrix_maximum.csv"))
    A.to_csv(os.path.join(OUT, "pca_sigma_matrix_average.csv"))
    C.to_csv(os.path.join(OUT, "pca_sigma_matrix_combined.csv"))
    with pd.ExcelWriter(os.path.join(OUT, "pca_sigma_matrices_global_max.xlsx"),
                        engine="openpyxl") as xw:
        M.to_excel(xw, sheet_name="minimum")
        X.to_excel(xw, sheet_name="maximum")
        A.to_excel(xw, sheet_name="average")
        C.to_excel(xw, sheet_name="combined")

    # best diagonal vs best off-diagonal
    diag = np.array([combined[k, k] for k in range(n)])
    best_diag_k = int(diag.argmax())
    best_diag_sigma = SIGMAS[best_diag_k]
    best_diag_score = float(diag[best_diag_k])
    fi, fj = np.unravel_index(int(combined.argmax()), combined.shape)
    best_off_pair = (SIGMAS[fi], SIGMAS[fj])
    best_off_score = float(combined[fi, fj])
    off_is_diag = (fi == fj)

    # 4-panel figure (mirrors the original q1-style layout)
    panels = [("A. Minimum matrix (%)", mn, "Minimum (%)"),
              ("B. Maximum matrix (%)", mx, "Maximum (%)"),
              ("C. Average matrix (%)", av, "Average (%)"),
              ("D. Combined score", combined, "Combined score")]
    fig, axes = plt.subplots(2, 2, figsize=(13.5, 11))
    fig.suptitle("PCA Sigma Sensitivity Matrix - event-global-max",
                 fontsize=15, fontweight="bold")
    for ax, (title, mat, cbar) in zip(axes.ravel(), panels):
        im = ax.imshow(mat, origin="upper", cmap="viridis", aspect="equal")
        ax.set_xticks(range(n)); ax.set_yticks(range(n))
        ax.set_xticklabels(SIGMAS); ax.set_yticklabels(SIGMAS)
        ax.set_xlabel(r"$\sigma_{PC2}$ (Minor Axis)")
        ax.set_ylabel(r"$\sigma_{PC1}$ (Major Axis)")
        ax.set_title(title, fontweight="bold")
        for k in range(n):  # highlight diagonal
            ax.add_patch(plt.Rectangle((k - 0.5, k - 0.5), 1, 1, fill=False,
                                       edgecolor="magenta", lw=2))
        thr = (mat.max() + mat.min()) / 2.0
        for ii in range(n):
            for jj in range(n):
                ax.text(jj, ii, f"{mat[ii, jj]:.0f}", ha="center", va="center",
                        color="white" if mat[ii, jj] < thr else "black",
                        fontsize=7)
        # (the best diagonal cell keeps its highlight box; no text label)
        fig.colorbar(im, ax=ax, shrink=0.8, label=cbar)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(os.path.join(OUT, "pca_sigma_sensitivity_matrix_global_max.png"),
                dpi=200)
    fig.savefig(os.path.join(OUT, "pca_sigma_sensitivity_matrix_global_max.pdf"))
    plt.close(fig)

    diag_tbl = pd.DataFrame({"sigma": SIGMAS,
                             "combined_score_on_diagonal": diag.round(2)})
    diag_tbl.to_csv(os.path.join(OUT, "diagonal_combined_scores.csv"), index=False)

    OLD_BEST = 1.25
    changed = best_diag_sigma != OLD_BEST
    md = f"""# PCA Sigma Sensitivity Matrix - event-global-max

Method (original producer recovered from the research tree, sanitized for
portable reproduction, and numerically verified):
target_component_purity = |H n E| / |E| (component cells inside the ellipse
footprint, over the footprint), with major semi-axis scaled by sigma_PC1 and minor
by sigma_PC2; per (sigma_PC1, sigma_PC2): Minimum / Maximum / Average over all
components; **Combined = Min + Max + Average**; recommended sigma = the DIAGONAL
(sigma_PC1 == sigma_PC2) with the highest combined score. Components: **{n_comp}**
event-global-max clusters. Grid: {SIGMAS}. (Diagonal combined peaks at
sigma=1.25: 29.20696324951644 + 100 + 75.33710405670476 = 204.5440673062212,
displayed as 205 - the maximum along the equal-sigma diagonal.)

## Result
- **Best DIAGONAL sigma = {best_diag_sigma}** (combined score {best_diag_score:.1f}).
- Best off-diagonal pair (reference only): sigma_PC1={best_off_pair[0]},
  sigma_PC2={best_off_pair[1]} (combined {best_off_score:.1f}); is-on-diagonal: {off_is_diag}.
- Previous method's selected diagonal sigma: **{OLD_BEST}**.
- **Did the selected diagonal sigma change under global-max? {'YES -> ' + str(best_diag_sigma) if changed else 'NO (still ' + str(OLD_BEST) + ')'}.**

### Diagonal combined scores
{diag_tbl.to_markdown(index=False)}

## Support for specific sigmas (diagonal combined score)
- sigma = 1.25 : {combined[SIGMAS.index(1.25), SIGMAS.index(1.25)]:.1f}
- sigma = 1.75 : {combined[SIGMAS.index(1.75), SIGMAS.index(1.75)]:.1f}
- sigma = 2.00 : {combined[SIGMAS.index(2.0), SIGMAS.index(2.0)]:.1f}

The recommendation is taken from the matrix coverage/overlap method on the
diagonal, NOT from area-scaling or orientation invariance.
"""
    with open(os.path.join(OUT, "SIGMA_MATRIX_RECOMMENDATION_global_max.md"),
              "w", encoding="utf-8") as fh:
        fh.write(md)

    print(f"[SIGMA-MATRIX] components={n_comp}  best diagonal sigma="
          f"{best_diag_sigma} (combined {best_diag_score:.1f})  "
          f"prev={OLD_BEST}  changed={changed}")
    print(f"[SIGMA-MATRIX] best off-diagonal pair={best_off_pair} "
          f"(combined {best_off_score:.1f}, on_diag={off_is_diag})")
    print(diag_tbl.to_string(index=False))
    print(f"[SIGMA-MATRIX] outputs -> {OUT}")


if __name__ == "__main__":
    main()
