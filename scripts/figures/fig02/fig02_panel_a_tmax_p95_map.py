#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Figure 2, panel (a): Warm-Season Tmax p95 (1940-2025) map.

Reconstruction of the lost original. Plots the per-1°-box warm-season p95
of daily Tmax (the deposit's gridded/fig02_box_p95.csv, derived unchanged
from the thr_p95 column written by
scripts/pipeline/build_master_dataset.py) over the
20-70E / 10-46N domain with black 1° box edges — the layout of the raster
embedded in the PowerPoint (slide 2, left panel), re-rendered at
publication resolution.

Output: generated_outputs/fig02_domain_threshold/fig02_panel_a_tmax_p95_map.{png,pdf}
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

# Release copy: inputs from the processed-data deposit, outputs under
# reproduced/. Author revision: internal title/header REMOVED
# (the description moves to the manuscript caption).
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_CAND = os.path.dirname(_THIS_DIR)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(_CAND)),
                                "scripts"))
from _clean_paths import DATA_DIR, data_file  # noqa: E402


def generated(sub):
    p = os.path.join(_SCORCH_REPRO, sub)
    os.makedirs(p, exist_ok=True)
    return p

try:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    HAVE_CARTOPY = True
except Exception:
    HAVE_CARTOPY = False

IN_CSV = data_file("fig02_box_p95.csv", "gridded")
OUT_DIR = generated("fig02")
OUT_STEM = os.path.join(OUT_DIR, "fig02_panel_a_tmax_p95_map")

LON_MIN, LON_MAX = 20.0, 70.0
LAT_MIN, LAT_MAX = 10.0, 46.0


def main() -> None:
    df = pd.read_csv(IN_CSV)
    lats = np.sort(df["lat1"].unique())
    lons = np.sort(df["lon1"].unique())
    grid = (df.pivot(index="lat1", columns="lon1", values="thr_p95")
              .reindex(index=lats, columns=lons).to_numpy())
    print(f"[FIG2a] boxes={len(df)}, p95 range "
          f"{np.nanmin(grid):.1f}..{np.nanmax(grid):.1f} degC")

    # Box EDGES for pcolormesh (centers are at .5 degrees).
    lon_e = np.arange(lons.min() - 0.5, lons.max() + 0.51, 1.0)
    lat_e = np.arange(lats.min() - 0.5, lats.max() + 0.51, 1.0)

    kw = dict(subplot_kw={"projection": ccrs.PlateCarree()}) if HAVE_CARTOPY else {}
    fig, ax = plt.subplots(figsize=(9.0, 6.0), **kw)

    mesh_kw = dict(cmap="YlOrRd", edgecolors="black", linewidth=0.25)
    if HAVE_CARTOPY:
        im = ax.pcolormesh(lon_e, lat_e, grid, transform=ccrs.PlateCarree(),
                           **mesh_kw)
        ax.add_feature(cfeature.COASTLINE.with_scale("50m"), linewidth=0.7)
        ax.add_feature(cfeature.BORDERS.with_scale("50m"), linewidth=0.5)
        ax.set_extent([LON_MIN, LON_MAX, LAT_MIN, LAT_MAX],
                      crs=ccrs.PlateCarree())
        gl = ax.gridlines(draw_labels=True, linewidth=0.0,
                          xlocs=np.arange(30, 70, 10),
                          ylocs=np.arange(20, 41, 10))
        gl.top_labels = gl.right_labels = False
        gl.xlabel_style = {"size": 11}
        gl.ylabel_style = {"size": 11}
    else:  # pragma: no cover - cartopy present in the validated environment
        im = ax.pcolormesh(lon_e, lat_e, grid, **mesh_kw)
        ax.set_xlim(LON_MIN, LON_MAX)
        ax.set_ylim(LAT_MIN, LAT_MAX)

    # No internal title (Phase 2C author revision — caption carries it).
    cbar = fig.colorbar(im, ax=ax, orientation="vertical",
                        fraction=0.035, pad=0.02)
    cbar.set_label("Tmax p95 (°C)", fontsize=12)
    cbar.ax.tick_params(labelsize=10)

    fig.tight_layout()
    for ext in ("png", "pdf"):
        out = f"{OUT_STEM}.{ext}"
        fig.savefig(out, dpi=600, bbox_inches="tight")
        print(f"[SAVED] {out}")
    plt.close(fig)


if __name__ == "__main__":
    main()
