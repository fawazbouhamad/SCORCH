#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared event-day snapshot renderer in the ORIGINAL representative-snapshot
style (cartopy map: land + coastlines + national borders + graticule), WITHOUT
any number inside the centroid markers.

Style replicated from the representative snapshot-day code in
the research repository's 3_PCA_Algorithm.py (setup_snapshot_ax / draw_cells /
plot_centroid): PlateCarree projection, 1-degree heatwave-labelled grid cells (orange =
clustered, grey = noise), black sigma=1.25 PCA ellipse + L1/L2 axes + black
centroid marker (no numeric label). Used by Task 2 and Task 4.
"""
from __future__ import annotations

import os
import sys

import numpy as np
from matplotlib.patches import Rectangle
from matplotlib.lines import Line2D as _L
from matplotlib.patches import Patch

try:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    HAVE_CARTOPY = True
    PROJ = ccrs.PlateCarree()
except Exception:                      # pragma: no cover
    HAVE_CARTOPY = False
    PROJ = None

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "common"))
import ellipse_pca as ep   # noqa: E402
import matplotlib.pyplot as plt   # noqa: E402

# Style constants (match 3_PCA_Algorithm.py)
COL_ACCEPTED = "orange"
COL_OTHER_HW = "0.55"
COL_ELLIPSE = "black"
COL_MAJOR = "black"
COL_MINOR = "black"
COL_CENTROID = "black"
SIGMA = 1.25
DPI = 600
# Fixed study-domain extent (full SCORCH grid + 1 deg pad) so maps never zoom
# tightly and stay stable across panels/frames.
STUDY_EXTENT = (19.5, 70.5, 9.5, 46.5)   # lon_min, lon_max, lat_min, lat_max


def _tr(ax):
    return PROJ if HAVE_CARTOPY else ax.transData


def make_panel(nrows, ncols, figsize):
    """Figure + flat axis list with the map projection (cartopy when present)."""
    kw = dict(subplot_kw={"projection": PROJ}) if HAVE_CARTOPY else {}
    fig, axes = plt.subplots(nrows, ncols, figsize=figsize, squeeze=False, **kw)
    return fig, list(np.array(axes).reshape(-1))


def setup_ax(ax, extent) -> None:
    lon_min, lon_max, lat_min, lat_max = extent
    if HAVE_CARTOPY:
        ax.set_extent([lon_min, lon_max, lat_min, lat_max], crs=PROJ)
        ax.add_feature(cfeature.LAND.with_scale("50m"), alpha=0.12, zorder=0)
        ax.add_feature(cfeature.COASTLINE.with_scale("50m"), linewidth=0.55,
                       zorder=8)
        ax.add_feature(cfeature.BORDERS.with_scale("50m"), linewidth=0.45,
                       zorder=8)
        gl = ax.gridlines(crs=PROJ, draw_labels=True, linewidth=0.28,
                          alpha=0.18, linestyle="-")
        gl.top_labels = False
        gl.right_labels = False
        gl.xlabel_style = {"size": 7}
        gl.ylabel_style = {"size": 7}
    else:
        ax.set_xlim(lon_min, lon_max)
        ax.set_ylim(lat_min, lat_max)
        ax.grid(True, alpha=0.20, linewidth=0.35)
        ax.set_aspect("equal")


def component_geometry(lon, lat, sigma=SIGMA) -> dict:
    lon = np.asarray(lon, float)
    lat = np.asarray(lat, float)
    clon, clat = float(lon.mean()), float(lat.mean())
    xy = ep.project_lonlat_to_km(lon, lat, clon, clat)
    center_xy, eigvecs, eigvals = ep.fit_pca(xy)
    a, b = ep.ellipse_semi_axes_km(eigvals, sigma)
    return dict(clon=clon, clat=clat, center_xy=center_xy, eigvecs=eigvecs,
                eigvals=eigvals, sigma=sigma,
                area_km2=float(np.pi * a * b), n_cells=int(lon.size))


def _draw_cells(ax, cells, facecolor, alpha, lw, zorder) -> None:
    tr = _tr(ax)
    for lon, lat in cells:
        ax.add_patch(Rectangle((lon - 0.5, lat - 0.5), 1.0, 1.0,
                               facecolor=facecolor, edgecolor="k",
                               linewidth=lw, alpha=alpha, zorder=zorder,
                               transform=tr))


def render_day(ax, lon, lat, labels, extent, *, draw_ellipses=True,
               show_centroid_numbers=False, title=None) -> dict:
    """Representative-style event-day map. No number inside the centroid."""
    setup_ax(ax, extent)
    tr = _tr(ax)
    lon = np.asarray(lon, float)
    lat = np.asarray(lat, float)
    labels = np.asarray(labels, int)
    clustered = [(round(float(lon[i]), 6), round(float(lat[i]), 6))
                 for i in range(lon.size) if labels[i] >= 0]
    noise = [(round(float(lon[i]), 6), round(float(lat[i]), 6))
             for i in range(lon.size) if labels[i] < 0]
    if noise:
        _draw_cells(ax, noise, COL_OTHER_HW, 0.70, 0.20, 3)
    if clustered:
        _draw_cells(ax, clustered, COL_ACCEPTED, 0.92, 0.24, 5)

    comps = []
    for lab in sorted(set(labels.tolist()) - {-1}):
        m = labels == lab
        g = component_geometry(lon[m], lat[m])
        comps.append(dict(label=int(lab), **{k: g[k] for k in
                                              ("clon", "clat", "area_km2",
                                               "n_cells")}))
        if draw_ellipses:
            elon, ela = ep.ellipse_points_lonlat_from_km(
                g["clon"], g["clat"], np.zeros(2), g["eigvecs"], g["eigvals"],
                g["sigma"])
            ax.plot(elon, ela, lw=2.0, color=COL_ELLIPSE, zorder=7, transform=tr)
            p1a, p1b, p2a, p2b = ep.axes_segments_lonlat_from_km(
                g["clon"], g["clat"], np.zeros(2), g["eigvecs"], g["eigvals"],
                g["sigma"])
            ax.plot([p1a[0], p1b[0]], [p1a[1], p1b[1]], lw=2.4, color=COL_MAJOR,
                    zorder=7, transform=tr)
            ax.plot([p2a[0], p2b[0]], [p2a[1], p2b[1]], lw=1.5, color=COL_MINOR,
                    zorder=7, transform=tr)
        # centroid MARKER always drawn; numeric label intentionally omitted
        ax.scatter([g["clon"]], [g["clat"]], s=60, marker="o", c=COL_CENTROID,
                   edgecolors="k", linewidths=0.7, zorder=8, transform=tr)
        if show_centroid_numbers:   # explicit opt-in only (default off)
            ax.text(g["clon"], g["clat"], str(int(lab) + 1), fontsize=7,
                    fontweight="bold", ha="center", va="center", zorder=9,
                    color="black", transform=tr,
                    bbox=dict(boxstyle="circle", fc="white", ec="black",
                              alpha=0.85))
    if title:
        ax.set_title(title, fontsize=10)
    return dict(n_components=len(comps), components=comps)


def legend_handles():
    return [
        _L([0], [0], color=COL_MAJOR, lw=2.4, label="L1"),
        _L([0], [0], color=COL_MINOR, lw=1.5, label="L2"),
        _L([0], [0], marker="o", color="w", markerfacecolor=COL_CENTROID,
           markeredgecolor="k", markersize=7, label="Centroid"),
    ]


def event_extent(coords, pad=1.5):
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return (min(lons) - pad, max(lons) + pad, min(lats) - pad, max(lats) + pad)
