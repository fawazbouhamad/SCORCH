
import os
import math
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Patch
from matplotlib.lines import Line2D
from matplotlib.backends.backend_pdf import PdfPages

warnings.filterwarnings("ignore", category=RuntimeWarning)

# -----------------------------
# OPTIONAL: Cartopy for borders/coastlines
# -----------------------------
HAVE_CARTOPY = False
try:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    HAVE_CARTOPY = True
except Exception:
    HAVE_CARTOPY = False

# =============================================================================
# USER SETTINGS
# =============================================================================

# Path to master_exceed_heatwaves_long.csv
MASTER_CSV = r"ENTER_PATH_TO_MASTER_EXCEED_HEATWAVES_LONG_CSV"

# Output folder for all figures, metrics, and PCA results
OUT_DIR = r"ENTER_OUTPUT_DIRECTORY"

MONTHS_IN_SCOPE = [4, 5, 6, 7, 8, 9]

# Big-day selection
BIGDAY_QUANTILE = 0.975
QUANTILE_METHOD = "higher"

# Connectivity
CONNECTIVITY = "queen"   # "queen" or "rook"

# Blob logic requested by user
CLOSE_MERGE_RELATIVE_THRESHOLD = 0.30   # close blob can merge into Blob 1 if >= 40% of ORIGINAL biggest raw blob
SECOND_BLOB_RELATIVE_THRESHOLD = 0.50   # far blob kept separately if >= 50% of FINAL Blob 1
MERGE_GAP_CELLS = 2
MAX_ELLIPSES = None                     # None = keep all accepted blobs


SIGMA_DEFAULT = 1.25



# Plot settings
MAX_PAGES = None
SHOW_GRIDLINES = True
MAJOR_TICK_STEP_DEG = 10
MINOR_GRIDLINE_STEP_DEG = 1
MAP_W_IN = 10.8
MAP_H_IN = 7.1
LEG_H_IN = 0.85

# Plot colors
COL_ACCEPTED = "orange"
COL_OTHER_HW = "0.55"
COL_ELLIPSE = "black"
COL_MAJOR = "black"
COL_MINOR = "black"
COL_CENTROID = "black"


# -----------------------------
# Helpers
# -----------------------------
def round_cell(cell):
    return (round(float(cell[0]), 6), round(float(cell[1]), 6))


def quantile_threshold_intlike(series: pd.Series, q: float, method: str = "higher") -> float:
    try:
        return float(series.quantile(q, method=method))           # pandas >= 2.0
    except TypeError:
        return float(series.quantile(q, interpolation=method))    # older pandas


def safe_weighted_mean(values, weights):
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)

    good = np.isfinite(values) & np.isfinite(weights)
    if not np.any(good):
        return np.nan

    values = values[good]
    weights = weights[good]
    weights = np.where(weights > 0, weights, 0.0)

    sw = float(np.sum(weights))

    if sw <= 0.0:
        return float(np.mean(values))

    return float(np.sum(values * weights) / sw)


def tmax_weighted_centroid_from_cells(cells, cell_to_val):
    cell_list = sorted(cells)
    if len(cell_list) == 0:
        return np.nan, np.nan, 0.0

    lon = np.array([c[0] for c in cell_list], dtype=float)
    lat = np.array([c[1] for c in cell_list], dtype=float)
    w = np.array([max(float(cell_to_val.get(c, np.nan)), 0.0) for c in cell_list], dtype=float)

    lon_w = safe_weighted_mean(lon, w)
    lat_w = safe_weighted_mean(lat, w)
    wsum = float(np.nansum(np.where(np.isfinite(w), w, 0.0)))
    return lon_w, lat_w, wsum
def centroid_shift_km_and_direction(lon_from, lat_from, lon_to, lat_to):
    """
    Compute the translation from the PCA centroid to the Tmax-weighted centroid.
    Returns:
        shift_km   : scalar distance in km
        dx_km      : east-west shift in km (+ east)
        dy_km      : north-south shift in km (+ north)
        direction  : professional compass text
    """
    if not (np.isfinite(lon_from) and np.isfinite(lat_from) and np.isfinite(lon_to) and np.isfinite(lat_to)):
        return np.nan, np.nan, np.nan, "undetermined"

    lat0_rad = math.radians(lat_from)
    km_per_deg_lon = 111.320 * math.cos(lat0_rad)
    km_per_deg_lat = 110.574

    dx_km = (lon_to - lon_from) * km_per_deg_lon
    dy_km = (lat_to - lat_from) * km_per_deg_lat
    shift_km = math.hypot(dx_km, dy_km)

    if shift_km < 1e-9:
        return 0.0, dx_km, dy_km, "no displacement"

    angle = (math.degrees(math.atan2(dy_km, dx_km)) + 360.0) % 360.0

    directions = [
        "east",
        "northeast",
        "north",
        "northwest",
        "west",
        "southwest",
        "south",
        "southeast",
    ]
    idx = int(((angle + 22.5) % 360) // 45)
    direction = directions[idx]

    return float(shift_km), float(dx_km), float(dy_km), direction

def build_grid_index(df_points: pd.DataFrame):
    lats = np.sort(df_points["lat1"].unique())
    lons = np.sort(df_points["lon1"].unique())
    lat_to_i = {v: i for i, v in enumerate(lats)}
    lon_to_j = {v: j for j, v in enumerate(lons)}
    return lats, lons, lat_to_i, lon_to_j


def neighbors(i, j, n_i, n_j, connectivity="queen"):
    if connectivity == "rook":
        deltas = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    else:
        deltas = [(-1, 0), (1, 0), (0, -1), (0, 1),
                  (-1, -1), (-1, 1), (1, -1), (1, 1)]
    for di, dj in deltas:
        ni, nj = i + di, j + dj
        if 0 <= ni < n_i and 0 <= nj < n_j:
            yield ni, nj


def connected_components(points_ij, n_i, n_j, connectivity="queen"):
    """Connected components on the grid from 'on' (i,j) points."""
    on = set(points_ij)
    comps = []
    visited = set()

    for p in on:
        if p in visited:
            continue
        stack = [p]
        visited.add(p)
        comp = []
        while stack:
            ci, cj = stack.pop()
            comp.append((ci, cj))
            for ni, nj in neighbors(ci, cj, n_i, n_j, connectivity):
                q = (ni, nj)
                if q in on and q not in visited:
                    visited.add(q)
                    stack.append(q)
        comps.append(comp)

    comps.sort(key=len, reverse=True)
    return comps


def expanded_cells(cells, buffer_cells):
    if buffer_cells <= 0:
        return set(cells)
    out = set()
    for lon, lat in cells:
        for dx in range(-buffer_cells, buffer_cells + 1):
            for dy in range(-buffer_cells, buffer_cells + 1):
                out.add(round_cell((lon + dx * 1.0, lat + dy * 1.0)))
    return out


def make_blob_record(member_ids, cells, role, component_id=None):
    cells = set(cells)
    out = {
        "member_ids": list(member_ids),
        "raw_cells": set(cells),
        "retained_cells": set(cells),
        "n_members": len(member_ids),
        "raw_size": len(cells),
        "retained_size": len(cells),
        "blob_role": role,
    }
    if component_id is not None:
        out["component_id"] = int(component_id)
    return out


def select_blob_groups(comp_records):
    """
    Build:
    - original_main_blob: the single biggest raw component only
    - tentative_main_blob: original main blob after optional close-merge absorption
    - all_components: all raw components in size-sorted order

    Close merge rule:
    - another raw component can be absorbed into Blob 1 if:
        * it is within MERGE_GAP_CELLS of the CURRENT Blob 1
        * and its size is >= CLOSE_MERGE_RELATIVE_THRESHOLD * ORIGINAL biggest raw blob size

    The caller will later test whether tentative_main_blob produces a valid ellipse.
    If it fails, the caller can revert to original_main_blob.
    """
    if not comp_records:
        return None, None, [], 0, 0

    # Sort raw components from largest to smallest
    comps_sorted = sorted(comp_records, key=lambda rec: len(rec["raw_cells"]), reverse=True)

    all_components = []
    for idx, rec in enumerate(comps_sorted):
        cells = set(rec["raw_cells"])
        all_components.append(
            make_blob_record([idx], cells, "raw_component", component_id=idx)
        )

    # Original biggest raw component
    original_main_blob = make_blob_record([0], all_components[0]["raw_cells"], "original_main_blob")
    largest_component_size = len(original_main_blob["raw_cells"])

    close_merge_cutoff = max(
        1,
        int(math.ceil(CLOSE_MERGE_RELATIVE_THRESHOLD * largest_component_size))
    )

    # Tentative merged Blob 1
    main_blob_cells = set(original_main_blob["raw_cells"])
    main_member_ids = [0]
    used_ids = {0}

    changed = True
    while changed:
        changed = False
        expanded_main = expanded_cells(main_blob_cells, MERGE_GAP_CELLS)

        for comp in all_components:
            cid = comp["component_id"]
            if cid in used_ids:
                continue

            other_cells = set(comp["raw_cells"])
            other_size = len(other_cells)

            # Close-merge rule:
            # big enough relative to ORIGINAL biggest blob, and close enough to CURRENT Blob 1
            if other_size >= close_merge_cutoff and (expanded_main & other_cells):
                main_blob_cells |= other_cells
                main_member_ids.append(cid)
                used_ids.add(cid)
                changed = True

    tentative_main_blob = make_blob_record(main_member_ids, main_blob_cells, "tentative_merged_main_blob")

    return original_main_blob, tentative_main_blob, all_components, largest_component_size, close_merge_cutoff


def select_far_secondary_blobs(main_blob, all_components):
    """
    Keep far secondary blobs only if:
    - they are farther than MERGE_GAP_CELLS from main_blob
    - and their size is >= SECOND_BLOB_RELATIVE_THRESHOLD * size(main_blob)

    IMPORTANT:
    This works relative to the FINAL main blob:
    - tentative merged Blob 1 if merge is accepted
    - original biggest raw blob if merge is reverted
    """
    if main_blob is None:
        return [], 0

    blob1_size = len(main_blob["raw_cells"])
    second_blob_cutoff = max(
        1,
        int(math.ceil(SECOND_BLOB_RELATIVE_THRESHOLD * blob1_size))
    )

    used_ids = set(main_blob["member_ids"])
    expanded_main = expanded_cells(main_blob["raw_cells"], MERGE_GAP_CELLS)

    accepted_far = []
    for comp in all_components:
        cid = comp["component_id"]
        if cid in used_ids:
            continue

        other_cells = set(comp["raw_cells"])
        other_size = len(other_cells)

        is_far = len(expanded_main & other_cells) == 0
        is_big_enough = other_size >= second_blob_cutoff

        if is_far and is_big_enough:
            accepted_far.append(
                make_blob_record([cid], other_cells, "far_secondary_blob", component_id=cid)
            )

    accepted_far.sort(key=lambda rec: rec["retained_size"], reverse=True)

    if MAX_ELLIPSES is not None:
        remaining_slots = max(0, MAX_ELLIPSES - 1)
        accepted_far = accepted_far[:remaining_slots]

    return accepted_far, second_blob_cutoff


# -----------------------------
# PCA / ellipse geometry
# -----------------------------
def project_lonlat_to_km(lon, lat, lon0, lat0):
    lat0_rad = math.radians(lat0)
    km_per_deg_lon = 111.320 * math.cos(lat0_rad)
    km_per_deg_lat = 110.574
    x = (lon - lon0) * km_per_deg_lon
    y = (lat - lat0) * km_per_deg_lat
    return np.column_stack((x, y))


def fit_pca(points_xy):
    if points_xy.shape[0] == 1:
        center = points_xy[0].copy()
        eigvecs = np.eye(2)
        eigvals = np.array([1.0, 1.0], dtype=float)
        return center, eigvecs, eigvals

    center = points_xy.mean(axis=0)
    centered = points_xy - center
    cov = np.cov(centered, rowvar=False, bias=False)

    eigvals, eigvecs = np.linalg.eigh(cov)
    order = np.argsort(eigvals)[::-1]

    eigvals = eigvals[order]
    eigvals = np.maximum(eigvals, 1.0)

    eigvecs = eigvecs[:, order]

    return center, eigvecs, eigvals


def ellipse_mask(lon_arr, lat_arr, center_lon, center_lat, center_xy, eigvecs, eigvals, sigma):
    all_xy = project_lonlat_to_km(lon_arr, lat_arr, center_lon, center_lat)
    rel = all_xy - center_xy
    pc = rel @ eigvecs
    a = max(sigma * math.sqrt(float(eigvals[0])), 1.0)
    b = max(sigma * math.sqrt(float(eigvals[1])), 1.0)
    return ((pc[:, 0] / a) ** 2 + (pc[:, 1] / b) ** 2) <= 1.0 + 1e-12


def ellipse_points_lonlat_from_km(center_lon, center_lat, center_xy, eigvecs, eigvals, sigma=2.0, n=240):
    a = max(sigma * math.sqrt(float(eigvals[0])), 1.0)
    b = max(sigma * math.sqrt(float(eigvals[1])), 1.0)
    t = np.linspace(0.0, 2.0 * np.pi, n)
    circle = np.vstack([a * np.cos(t), b * np.sin(t)])
    ell = center_xy.reshape(2, 1) + eigvecs @ circle
    xs, ys = ell[0, :], ell[1, :]
    lat0_rad = math.radians(center_lat)
    km_per_deg_lon = 111.320 * math.cos(lat0_rad)
    km_per_deg_lat = 110.574
    lon_e = center_lon + xs / km_per_deg_lon
    lat_e = center_lat + ys / km_per_deg_lat
    return lon_e, lat_e


def axes_segments_lonlat_from_km(center_lon, center_lat, center_xy, eigvecs, eigvals, sigma=2.0):
    a = max(sigma * math.sqrt(float(eigvals[0])), 1.0)
    b = max(sigma * math.sqrt(float(eigvals[1])), 1.0)
    v1 = eigvecs[:, 0] * a
    v2 = eigvecs[:, 1] * b

    lat0_rad = math.radians(center_lat)
    km_per_deg_lon = 111.320 * math.cos(lat0_rad)
    km_per_deg_lat = 110.574

    def inv(pt_xy):
        return (
            center_lon + pt_xy[0] / km_per_deg_lon,
            center_lat + pt_xy[1] / km_per_deg_lat,
        )

    c = center_xy
    p1a = inv(c - v1)
    p1b = inv(c + v1)
    p2a = inv(c - v2)
    p2b = inv(c + v2)
    return p1a, p1b, p2a, p2b


# -----------------------------
# Clean ellipse evaluation
# -----------------------------
def mahalanobis_radius(points_xy, center_xy, eigvecs, eigvals):
    rel = points_xy - center_xy
    pc = rel @ eigvecs
    return np.sqrt((pc[:, 0] ** 2) / eigvals[0] + (pc[:, 1] ** 2) / eigvals[1])
def centroid_shift_km_and_direction(lon_from, lat_from, lon_to, lat_to):
    """
    Translation from PCA centroid to Tmax-weighted centroid.
    Returns:
        shift_km   : total displacement in km
        dx_km      : zonal shift in km (+ east, - west)
        dy_km      : meridional shift in km (+ north, - south)
        direction  : compass direction text
    """
    if not (np.isfinite(lon_from) and np.isfinite(lat_from) and np.isfinite(lon_to) and np.isfinite(lat_to)):
        return np.nan, np.nan, np.nan, "undetermined"

    lat0_rad = math.radians(lat_from)
    km_per_deg_lon = 111.320 * math.cos(lat0_rad)
    km_per_deg_lat = 110.574

    dx_km = (lon_to - lon_from) * km_per_deg_lon
    dy_km = (lat_to - lat_from) * km_per_deg_lat
    shift_km = math.hypot(dx_km, dy_km)

    if shift_km < 1e-9:
        return 0.0, dx_km, dy_km, "no displacement"

    angle = (math.degrees(math.atan2(dy_km, dx_km)) + 360.0) % 360.0

    directions = [
        "east",
        "northeast",
        "north",
        "northwest",
        "west",
        "southwest",
        "south",
        "southeast",
    ]
    idx = int(((angle + 22.5) % 360) // 45)
    direction = directions[idx]

    return float(shift_km), float(dx_km), float(dy_km), direction
def evaluate_blob_ellipse_clean(
    blob_cells,
    blob_label,
    grid_lon,
    grid_lat,
    grid_cells,
    grid_is_hw,
    cell_to_val,
    source_plot_cells=None,
):
    """
    Clean full-blob PCA version:
    - uses all accepted blob cells
    - no PCA tail trimming
    - no purity rejection
    - sigma fixed at SIGMA_DEFAULT
    - ellipse is translated from PCA centroid to Tmax-weighted centroid
    """
    blob_list = sorted(blob_cells)
    if len(blob_list) == 0:
        return None

    centroid_source_cells = set(source_plot_cells) if source_plot_cells is not None else set(blob_cells)

    blob_lon = np.array([c[0] for c in blob_list], dtype=float)
    blob_lat = np.array([c[1] for c in blob_list], dtype=float)

    # PCA using the full blob only
    center_lon_pca = float(blob_lon.mean())
    center_lat_pca = float(blob_lat.mean())

    blob_xy = project_lonlat_to_km(blob_lon, blob_lat, center_lon_pca, center_lat_pca)
    center_xy_pca, eigvecs, eigvals = fit_pca(blob_xy)

    # Tmax-weighted centroid
    center_lon_weighted, center_lat_weighted, weight_sum = tmax_weighted_centroid_from_cells(
        centroid_source_cells,
        cell_to_val,
    )

    if not (np.isfinite(center_lon_weighted) and np.isfinite(center_lat_weighted)):
        center_lon_weighted = center_lon_pca
        center_lat_weighted = center_lat_pca

    shift_km, shift_dx_km, shift_dy_km, shift_direction = centroid_shift_km_and_direction(
        center_lon_pca,
        center_lat_pca,
        center_lon_weighted,
        center_lat_weighted,
    )

    translated_center_xy = np.zeros(2, dtype=float)
    sigma = SIGMA_DEFAULT

    a = max(sigma * math.sqrt(float(eigvals[0])), 1.0)
    b = max(sigma * math.sqrt(float(eigvals[1])), 1.0)

    inside_mask = ellipse_mask(
        grid_lon,
        grid_lat,
        center_lon_weighted,
        center_lat_weighted,
        translated_center_xy,
        eigvecs,
        eigvals,
        sigma,
    )

    total_inside = int(inside_mask.sum())
    if total_inside <= 0:
        return None

    hw_inside = int(grid_is_hw[inside_mask].sum())
    white_inside = total_inside - hw_inside
    purity = hw_inside / total_inside

    inside_ids = set(np.where(inside_mask)[0].tolist())
    inside_cells = {grid_cells[i] for i in inside_ids}

    return {
        "blob_label": blob_label,
        "blob_cells": set(blob_cells),
        "source_plot_cells": set(source_plot_cells) if source_plot_cells is not None else set(blob_cells),
        "inside_ids": inside_ids,
        "inside_cells": inside_cells,
        "sigma": float(round(sigma, 4)),
        "trim_quantile": 1.00,
        "center_lon": float(center_lon_weighted),
        "center_lat": float(center_lat_weighted),
        "center_xy": translated_center_xy.copy(),
        "pca_center_lon": float(center_lon_pca),
        "pca_center_lat": float(center_lat_pca),
        "pca_center_xy": center_xy_pca.copy(),
        "weight_sum": float(weight_sum),
        "centroid_shift_km": float(shift_km),
        "centroid_shift_dx_km": float(shift_dx_km),
        "centroid_shift_dy_km": float(shift_dy_km),
        "centroid_shift_direction": shift_direction,
        "eigvecs": eigvecs,
        "eigvals": eigvals,
        "axis1_km": float(2.0 * a),
        "axis2_km": float(2.0 * b),
        "purity": float(purity),
        "white_frac": float(white_inside / total_inside),
        "blob_size": int(len(blob_list)),
        "trimmed_blob_size": int(len(blob_list)),
        "total_inside": int(total_inside),
        "hw_inside": int(hw_inside),
        "white_inside": int(white_inside),
        "valid": True,
    }
def summarize_kept_ellipses(kept):
    if not kept:
        return 0, 0, 0.0
    hw_inside = sum(e["hw_inside"] for e in kept)
    total_inside = sum(e["total_inside"] for e in kept)
    mean_purity = float(np.mean([e["purity"] for e in kept]))
    return hw_inside, total_inside, mean_purity


def make_map_ax(lon_min, lon_max, lat_min, lat_max, reserve_legend=True):
    fig_h = MAP_H_IN + (LEG_H_IN if reserve_legend else 0.0)
    fig = plt.figure(figsize=(MAP_W_IN, fig_h))

    if HAVE_CARTOPY:
        ax = plt.axes(projection=ccrs.PlateCarree())
        ax.set_extent([lon_min, lon_max, lat_min, lat_max], crs=ccrs.PlateCarree())
        ax.add_feature(cfeature.COASTLINE.with_scale("50m"), linewidth=0.6)
        ax.add_feature(cfeature.BORDERS.with_scale("50m"), linewidth=0.5)
        ax.add_feature(cfeature.LAND.with_scale("50m"), alpha=0.12)

        if reserve_legend:
            bottom_frac = LEG_H_IN / fig_h
            ax.set_position([0.06, bottom_frac + 0.06, 0.90, 0.83 - bottom_frac])
        else:
            ax.set_position([0.06, 0.08, 0.90, 0.84])

        xticks = np.arange(math.ceil(lon_min / MAJOR_TICK_STEP_DEG) * MAJOR_TICK_STEP_DEG,
                           math.floor(lon_max / MAJOR_TICK_STEP_DEG) * MAJOR_TICK_STEP_DEG + MAJOR_TICK_STEP_DEG,
                           MAJOR_TICK_STEP_DEG)
        yticks = np.arange(math.ceil(lat_min / MAJOR_TICK_STEP_DEG) * MAJOR_TICK_STEP_DEG,
                           math.floor(lat_max / MAJOR_TICK_STEP_DEG) * MAJOR_TICK_STEP_DEG + MAJOR_TICK_STEP_DEG,
                           MAJOR_TICK_STEP_DEG)

        if SHOW_GRIDLINES:
            minor_x = np.arange(math.floor(lon_min), math.ceil(lon_max) + MINOR_GRIDLINE_STEP_DEG, MINOR_GRIDLINE_STEP_DEG)
            minor_y = np.arange(math.floor(lat_min), math.ceil(lat_max) + MINOR_GRIDLINE_STEP_DEG, MINOR_GRIDLINE_STEP_DEG)

            gl_minor = ax.gridlines(
                crs=ccrs.PlateCarree(),
                draw_labels=False,
                linewidth=0.30,
                alpha=0.14,
                linestyle='-',
                xlocs=minor_x,
                ylocs=minor_y,
            )
            gl_minor.xlines = True
            gl_minor.ylines = True

            gl_major = ax.gridlines(
                crs=ccrs.PlateCarree(),
                draw_labels=True,
                linewidth=0.55,
                alpha=0.45,
                linestyle='-',
                xlocs=xticks,
                ylocs=yticks,
                x_inline=False,
                y_inline=False,
            )
            gl_major.top_labels = False
            gl_major.right_labels = False
            gl_major.bottom_labels = True
            gl_major.left_labels = True
            gl_major.rotate_labels = False
            gl_major.xlabel_style = {"size": 9}
            gl_major.ylabel_style = {"size": 9}
            gl_major.xlines = False
            gl_major.ylines = False
        return fig, ax

    ax = plt.gca()
    ax.set_xlim(lon_min, lon_max)
    ax.set_ylim(lat_min, lat_max)

    if reserve_legend:
        bottom_frac = LEG_H_IN / fig_h
        ax.set_position([0.06, bottom_frac + 0.06, 0.90, 0.83 - bottom_frac])
    else:
        ax.set_position([0.06, 0.08, 0.90, 0.84])

    xticks_major = np.arange(math.ceil(lon_min / MAJOR_TICK_STEP_DEG) * MAJOR_TICK_STEP_DEG,
                             math.floor(lon_max / MAJOR_TICK_STEP_DEG) * MAJOR_TICK_STEP_DEG + MAJOR_TICK_STEP_DEG,
                             MAJOR_TICK_STEP_DEG)
    yticks_major = np.arange(math.ceil(lat_min / MAJOR_TICK_STEP_DEG) * MAJOR_TICK_STEP_DEG,
                             math.floor(lat_max / MAJOR_TICK_STEP_DEG) * MAJOR_TICK_STEP_DEG + MAJOR_TICK_STEP_DEG,
                             MAJOR_TICK_STEP_DEG)
    ax.set_xticks(xticks_major)
    ax.set_yticks(yticks_major)

    if SHOW_GRIDLINES:
        xticks_minor = np.arange(math.floor(lon_min), math.ceil(lon_max) + MINOR_GRIDLINE_STEP_DEG, MINOR_GRIDLINE_STEP_DEG)
        yticks_minor = np.arange(math.floor(lat_min), math.ceil(lat_max) + MINOR_GRIDLINE_STEP_DEG, MINOR_GRIDLINE_STEP_DEG)
        ax.set_xticks(xticks_minor, minor=True)
        ax.set_yticks(yticks_minor, minor=True)
        ax.grid(True, which="major", alpha=0.35, linewidth=0.55)
        ax.grid(True, which="minor", alpha=0.14, linewidth=0.30)

    ax.tick_params(axis="both", labelsize=9)
    return fig, ax

def draw_cells(ax, cells, facecolor, alpha=1.0, edgecolor="k", lw=0.35, zorder=3):
    for lon, lat in cells:
        rect = Rectangle(
            (lon - 0.5, lat - 0.5),
            1.0,
            1.0,
            facecolor=facecolor,
            edgecolor=edgecolor,
            linewidth=lw,
            alpha=alpha,
            zorder=zorder,
            transform=ccrs.PlateCarree() if HAVE_CARTOPY else ax.transData,
        )
        ax.add_patch(rect)


def draw_cartopy_overlay(ax, lon_min, lon_max, lat_min, lat_max):
    if not HAVE_CARTOPY:
        return

    if SHOW_GRIDLINES:
        minor_x = np.arange(math.floor(lon_min), math.ceil(lon_max) + MINOR_GRIDLINE_STEP_DEG, MINOR_GRIDLINE_STEP_DEG)
        minor_y = np.arange(math.floor(lat_min), math.ceil(lat_max) + MINOR_GRIDLINE_STEP_DEG, MINOR_GRIDLINE_STEP_DEG)
        major_x = np.arange(math.ceil(lon_min / MAJOR_TICK_STEP_DEG) * MAJOR_TICK_STEP_DEG,
                            math.floor(lon_max / MAJOR_TICK_STEP_DEG) * MAJOR_TICK_STEP_DEG + MAJOR_TICK_STEP_DEG,
                            MAJOR_TICK_STEP_DEG)
        major_y = np.arange(math.ceil(lat_min / MAJOR_TICK_STEP_DEG) * MAJOR_TICK_STEP_DEG,
                            math.floor(lat_max / MAJOR_TICK_STEP_DEG) * MAJOR_TICK_STEP_DEG + MAJOR_TICK_STEP_DEG,
                            MAJOR_TICK_STEP_DEG)

        for x in minor_x:
            ax.plot([x, x], [lat_min, lat_max], transform=ccrs.PlateCarree(),
                    color="0.35", linewidth=0.30, alpha=0.16, zorder=6)
        for y in minor_y:
            ax.plot([lon_min, lon_max], [y, y], transform=ccrs.PlateCarree(),
                    color="0.35", linewidth=0.30, alpha=0.16, zorder=6)

        for x in major_x:
            ax.plot([x, x], [lat_min, lat_max], transform=ccrs.PlateCarree(),
                    color="0.20", linewidth=0.55, alpha=0.32, zorder=6.2)
        for y in major_y:
            ax.plot([lon_min, lon_max], [y, y], transform=ccrs.PlateCarree(),
                    color="0.20", linewidth=0.55, alpha=0.32, zorder=6.2)

    ax.add_feature(cfeature.COASTLINE.with_scale("50m"), linewidth=0.8, zorder=8.6)
    ax.add_feature(cfeature.BORDERS.with_scale("50m"), linewidth=0.7, zorder=8.7)

def plot_line(ax, x, y, lw, zorder=4, color=None):
    kwargs = dict(linewidth=lw, zorder=zorder)
    if color is not None:
        kwargs["color"] = color
    if HAVE_CARTOPY:
        ax.plot(x, y, transform=ccrs.PlateCarree(), **kwargs)
    else:
        ax.plot(x, y, **kwargs)


def plot_centroid(ax, lon, lat, size=60, zorder=8, color=None):
    kwargs = dict(
        s=size,
        marker="o",
        zorder=zorder,
        edgecolors="k",
        linewidths=0.7,
    )
    if color is not None:
        kwargs["c"] = color

    if HAVE_CARTOPY:
        ax.scatter([lon], [lat], transform=ccrs.PlateCarree(), **kwargs)
    else:
        ax.scatter([lon], [lat], **kwargs)


def plot_text_lonlat(ax, lon, lat, text, fontsize=8.5, zorder=9):
    kwargs = dict(
        fontsize=fontsize,
        zorder=zorder,
        ha="left",
        va="bottom",
        fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.15", facecolor="white", edgecolor="0.4", alpha=0.85),
    )
    if HAVE_CARTOPY:
        ax.text(lon, lat, text, transform=ccrs.PlateCarree(), **kwargs)
    else:
        ax.text(lon, lat, text, **kwargs)


def add_custom_legend(fig):
    handles = [
        Patch(facecolor=COL_ACCEPTED, edgecolor="k", label="Accepted HW cells"),
        Patch(facecolor=COL_OTHER_HW, edgecolor="k", label="Other HW cells"),
        Line2D([0], [0], color=COL_ELLIPSE, lw=2.0, label="Ellipse"),
        Line2D([0], [0], color=COL_MAJOR, lw=2.5, label="Major axis"),
        Line2D([0], [0], color=COL_MINOR, lw=1.5, label="Minor axis"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=COL_CENTROID,
               markeredgecolor="k", markersize=7, label="centroid"),
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=6,
        frameon=True,
        bbox_to_anchor=(0.5, 0.02),
        fontsize=8.5,
        borderaxespad=0.2,
        handlelength=2.0,
        columnspacing=1.4,
    )
def add_snapshot_legend(fig):
    handles = [
        Line2D([0], [0], color=COL_MAJOR, lw=2.6, label="L1"),
        Line2D([0], [0], color=COL_MINOR, lw=1.6, label="L2"),
        Line2D([0], [0], marker="o", color="w",
               markerfacecolor=COL_CENTROID, markeredgecolor="k",
               markersize=7, label="Centroid"),
    ]

    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=3,
        frameon=True,
        bbox_to_anchor=(0.5, 0.025),
        fontsize=9,
        handlelength=2.4,
        columnspacing=1.8,
    )


def setup_snapshot_ax(ax, lon_min, lon_max, lat_min, lat_max):
    if HAVE_CARTOPY:
        ax.set_extent([lon_min, lon_max, lat_min, lat_max], crs=ccrs.PlateCarree())
        ax.add_feature(cfeature.LAND.with_scale("50m"), alpha=0.12, zorder=0)
        ax.add_feature(cfeature.COASTLINE.with_scale("50m"), linewidth=0.55, zorder=8)
        ax.add_feature(cfeature.BORDERS.with_scale("50m"), linewidth=0.45, zorder=8)

        if SHOW_GRIDLINES:
            gl = ax.gridlines(
                crs=ccrs.PlateCarree(),
                draw_labels=False,
                linewidth=0.28,
                alpha=0.18,
                linestyle="-",
            )
            gl.top_labels = False
            gl.right_labels = False
            gl.xlabel_style = {"size": 8}
            gl.ylabel_style = {"size": 8}
            gl.xlines = True
            gl.ylines = True
    else:
        ax.set_xlim(lon_min, lon_max)
        ax.set_ylim(lat_min, lat_max)
        ax.grid(True, alpha=0.20, linewidth=0.35)


    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.set_title("")


def compute_snapshot_day(
    day,
    df,
    lats_full,
    lons_full,
    lat_to_i,
    lon_to_j,
    n_i,
    n_j,
    grid_cells,
    grid_lon,
    grid_lat,
):
    day = pd.to_datetime(day)
    dday = df[df["date"] == day].copy()
    dday_hw = dday[dday["heatwave_id"] > 0].copy()

    day_val_lookup = (
        dday_hw.groupby(["lon1", "lat1"], as_index=False)["val"]
        .mean()
    )
    cell_to_val = {
        round_cell((row["lon1"], row["lat1"])): row["val"]
        for _, row in day_val_lookup.iterrows()
    }

    day_hw_cells_raw = {
        round_cell((lo, la))
        for lo, la in zip(dday_hw["lon1"].values, dday_hw["lat1"].values)
    }

    if not day_hw_cells_raw:
        return [], set(), set()

    day_hw_list_sorted = sorted(day_hw_cells_raw)
    day_hw_lons = np.array([c[0] for c in day_hw_list_sorted], dtype=float)
    day_hw_lats = np.array([c[1] for c in day_hw_list_sorted], dtype=float)

    pts = list(zip(
        pd.Series(day_hw_lats).map(lat_to_i).values,
        pd.Series(day_hw_lons).map(lon_to_j).values,
    ))

    comps_raw = connected_components(pts, n_i, n_j, connectivity=CONNECTIVITY)

    comp_records = []
    for comp in comps_raw:
        raw_cells = {round_cell((lons_full[j], lats_full[i])) for i, j in comp}
        comp_records.append({
            "raw_cells": raw_cells,
            "retained_cells": raw_cells,
        })

    original_main_blob, tentative_main_blob, all_components, _, _ = select_blob_groups(comp_records)

    hw_cell_set = set(day_hw_cells_raw)
    grid_is_hw = np.array([c in hw_cell_set for c in grid_cells], dtype=bool)

    accepted = []
    final_main_blob = None

    if original_main_blob is not None:
        main_had_close_merges = len(tentative_main_blob["member_ids"]) > 1

        if main_had_close_merges:
            e_main = evaluate_blob_ellipse_clean(
                blob_cells=tentative_main_blob["retained_cells"],
                blob_label="blob_1",
                grid_lon=grid_lon,
                grid_lat=grid_lat,
                grid_cells=grid_cells,
                grid_is_hw=grid_is_hw,
                cell_to_val=cell_to_val,
                source_plot_cells=tentative_main_blob["raw_cells"],
            )

            if e_main is not None:
                final_main_blob = tentative_main_blob
                e_main["group_index"] = 1
                accepted.append(e_main)
            else:
                final_main_blob = original_main_blob
                e_main = evaluate_blob_ellipse_clean(
                    blob_cells=original_main_blob["retained_cells"],
                    blob_label="blob_1",
                    grid_lon=grid_lon,
                    grid_lat=grid_lat,
                    grid_cells=grid_cells,
                    grid_is_hw=grid_is_hw,
                    cell_to_val=cell_to_val,
                    source_plot_cells=original_main_blob["raw_cells"],
                )
                if e_main is not None:
                    e_main["group_index"] = 1
                    accepted.append(e_main)
        else:
            final_main_blob = original_main_blob
            e_main = evaluate_blob_ellipse_clean(
                blob_cells=original_main_blob["retained_cells"],
                blob_label="blob_1",
                grid_lon=grid_lon,
                grid_lat=grid_lat,
                grid_cells=grid_cells,
                grid_is_hw=grid_is_hw,
                cell_to_val=cell_to_val,
                source_plot_cells=original_main_blob["raw_cells"],
            )
            if e_main is not None:
                e_main["group_index"] = 1
                accepted.append(e_main)

        far_blobs, _ = select_far_secondary_blobs(final_main_blob, all_components)

        for ib, blob in enumerate(far_blobs, start=2):
            e = evaluate_blob_ellipse_clean(
                blob_cells=blob["retained_cells"],
                blob_label=f"blob_{ib}",
                grid_lon=grid_lon,
                grid_lat=grid_lat,
                grid_cells=grid_cells,
                grid_is_hw=grid_is_hw,
                cell_to_val=cell_to_val,
                source_plot_cells=blob["raw_cells"],
            )
            if e is not None:
                e["group_index"] = ib
                accepted.append(e)

    orange_plot_cells = set().union(*(e["source_plot_cells"] for e in accepted)) if accepted else set()
    grey_plot_cells = set(day_hw_cells_raw) - orange_plot_cells

    return accepted, orange_plot_cells, grey_plot_cells


def draw_snapshot_day(ax, accepted, orange_plot_cells, grey_plot_cells, lon_min, lon_max, lat_min, lat_max):
    setup_snapshot_ax(ax, lon_min, lon_max, lat_min, lat_max)

    if grey_plot_cells:
        draw_cells(ax, sorted(grey_plot_cells), facecolor=COL_OTHER_HW, alpha=0.70, lw=0.20, zorder=3)

    if orange_plot_cells:
        draw_cells(ax, sorted(orange_plot_cells), facecolor=COL_ACCEPTED, alpha=0.92, lw=0.24, zorder=5)

    for e in accepted:
        elon, elat = ellipse_points_lonlat_from_km(
            e["center_lon"], e["center_lat"], e["center_xy"],
            e["eigvecs"], e["eigvals"], sigma=e["sigma"]
        )
        plot_line(ax, elon, elat, lw=2.0, zorder=7, color=COL_ELLIPSE)

        p1a, p1b, p2a, p2b = axes_segments_lonlat_from_km(
            e["center_lon"], e["center_lat"], e["center_xy"],
            e["eigvecs"], e["eigvals"], sigma=e["sigma"]
        )

        plot_line(ax, [p1a[0], p1b[0]], [p1a[1], p1b[1]], lw=2.6, zorder=7, color=COL_MAJOR)
        plot_line(ax, [p2a[0], p2b[0]], [p2a[1], p2b[1]], lw=1.6, zorder=7, color=COL_MINOR)
        plot_centroid(ax, e["center_lon"], e["center_lat"], size=50, zorder=8, color=COL_CENTROID)
def export_requested_snapshot_pngs(
    df,
    lats_full,
    lons_full,
    lat_to_i,
    lon_to_j,
    n_i,
    n_j,
    grid_cells,
    grid_lon,
    grid_lat,
    lon_min,
    lon_max,
    lat_min,
    lat_max,
):
    snap_dir = os.path.join(OUT_DIR, "requested_date_snapshots_png")
    os.makedirs(snap_dir, exist_ok=True)

    independent_days = [
        "2002-07-31",
        "1983-07-13",
    ]

    back_to_back_events = [
        ("BTB_2000_07_28_to_2000_08_02", "2000-07-28", "2000-08-02"),
        ("BTB_2002_08_06_to_2002_08_07", "2002-08-06", "2002-08-07"),
        ("BTB_1998_08_01_to_1998_08_11", "1998-08-01", "1998-08-11"),
    ]

    # -----------------------------
    # Independent HW snapshots
    # -----------------------------
    for d in independent_days:
        accepted, orange_cells, grey_cells = compute_snapshot_day(
            d, df, lats_full, lons_full, lat_to_i, lon_to_j,
            n_i, n_j, grid_cells, grid_lon, grid_lat
        )

        if HAVE_CARTOPY:
            fig, ax = plt.subplots(
                figsize=(8.2, 6.3),
                subplot_kw={"projection": ccrs.PlateCarree()}
            )
        else:
            fig, ax = plt.subplots(figsize=(8.2, 6.3))

        draw_snapshot_day(
            ax,
            accepted,
            orange_cells,
            grey_cells,
            lon_min,
            lon_max,
            lat_min,
            lat_max
        )

        # Coordinate labels for independent PNGs
        if HAVE_CARTOPY:
            gl = ax.gridlines(
                crs=ccrs.PlateCarree(),
                draw_labels=True,
                linewidth=0.28,
                alpha=0.18,
                linestyle="-",
            )
            gl.top_labels = False
            gl.right_labels = False
            gl.left_labels = True
            gl.bottom_labels = True
            gl.xlabel_style = {"size": 8}
            gl.ylabel_style = {"size": 8}
            gl.xlines = True
            gl.ylines = True
        else:
            ax.set_xlabel("Longitude (°)")
            ax.set_ylabel("Latitude (°)")

        add_snapshot_legend(fig)

        fig.subplots_adjust(
            left=0.075,
            right=0.985,
            top=0.985,
            bottom=0.125,
        )

        out_png = os.path.join(snap_dir, f"Independent_HW_{d}.png")
        fig.savefig(out_png, dpi=600, bbox_inches="tight")
        plt.close(fig)
        print("[SAVED SNAPSHOT]", out_png)

    # -----------------------------
    # Back-to-back HW multi-panel snapshots
    # -----------------------------
    for event_name, start_date, end_date in back_to_back_events:
        dates = pd.date_range(start_date, end_date, freq="D")
        n = len(dates)

        if n <= 2:
            ncols = n
        elif n <= 6:
            ncols = 3
        else:
            ncols = 4

        nrows = int(math.ceil(n / ncols))

        if HAVE_CARTOPY:
            fig, axes = plt.subplots(
                nrows=nrows,
                ncols=ncols,
                figsize=(4.25 * ncols, 3.85 * nrows + 0.65),
                subplot_kw={"projection": ccrs.PlateCarree()}
            )
        else:
            fig, axes = plt.subplots(
                nrows=nrows,
                ncols=ncols,
                figsize=(4.25 * ncols, 3.85 * nrows + 0.65)
            )

        axes = np.array(axes).reshape(-1)

        for i, d in enumerate(dates):
            accepted, orange_cells, grey_cells = compute_snapshot_day(
                d, df, lats_full, lons_full, lat_to_i, lon_to_j,
                n_i, n_j, grid_cells, grid_lon, grid_lat
            )

            draw_snapshot_day(
                axes[i],
                accepted,
                orange_cells,
                grey_cells,
                lon_min,
                lon_max,
                lat_min,
                lat_max
            )

            # Coordinate label control for B2B panels
            if HAVE_CARTOPY:
                gl = axes[i].gridlines(
                    crs=ccrs.PlateCarree(),
                    draw_labels=True,
                    linewidth=0.28,
                    alpha=0.18,
                    linestyle="-",
                )

                gl.top_labels = False
                gl.right_labels = False

                # Y labels only on first snapshot of each row
                gl.left_labels = (i % ncols == 0)

                # X labels on every snapshot / every row
                gl.bottom_labels = True

                gl.xlabel_style = {"size": 6}
                gl.ylabel_style = {"size": 6}
                gl.xlines = True
                gl.ylines = True

            else:
                if i % ncols != 0:
                    axes[i].set_yticklabels([])
                else:
                    axes[i].set_ylabel("Latitude (°)")

                axes[i].set_xlabel("Longitude (°)")

        for j in range(n, len(axes)):
            axes[j].axis("off")

        # Dynamic legend scaling based on number of panels
        # Dynamic legend scaling based on number of panels
        if n <= 2:
            legend_font = 13
            legend_handle = 3.4
            legend_cols = 3
            legend_marker = 11
        
        elif n <= 6:
            legend_font = 14
            legend_handle = 3.6
            legend_cols = 3
            legend_marker = 12
        
        else:
            legend_font = 15
            legend_handle = 3.8
            legend_cols = 3
            legend_marker = 13
        
        handles = [
            Line2D([0], [0], color=COL_MAJOR, lw=3.4, label="L1"),
            Line2D([0], [0], color=COL_MINOR, lw=2.3, label="L2"),
            Line2D(
                [0], [0],
                marker="o",
                color="w",
                markerfacecolor=COL_CENTROID,
                markeredgecolor="k",
                markersize=legend_marker,
                label="Centroid"
            ),
        ]
        
        fig.legend(
            handles=handles,
            loc="lower center",
            ncol=legend_cols,
            frameon=True,
            bbox_to_anchor=(0.5, 0.03),
            fontsize=legend_font,
            handlelength=legend_handle,
            columnspacing=2.6,
            borderpad=0.9,
        )
        
        fig.subplots_adjust(
            left=0.055,
            right=0.985,
            top=0.985,
            bottom=0.14,
            wspace=0.095,
            hspace=0.185,
        )

        out_png = os.path.join(snap_dir, f"{event_name}.png")
        fig.savefig(out_png, dpi=600, bbox_inches="tight")
        plt.close(fig)
        print("[SAVED SNAPSHOT]", out_png)
        
        
        
def compose_summary_line(accepted):
    if not accepted:
        return "No accepted ellipse"

    lines = []
    for idx, e in enumerate(accepted, start=1):
        shift_km = e.get("centroid_shift_km", np.nan)
        shift_dir = e.get("centroid_shift_direction", "undetermined")

        if np.isfinite(shift_km):
            if shift_km < 0.5:
                shift_text = "Centroid shift=0 km (negligible)"
            else:
                shift_text = f"Centroid shift={shift_km:.0f} km toward the {shift_dir}"
        else:
            shift_text = "Centroid shift=undetermined"

        lines.append(
            f"E{idx}: HW coverage {100.0 * e['purity']:.1f}% | "
            f"N={e['total_inside']} | "
            f"Blob cells={e['blob_size']} | "
            f"PCA trim={e.get('trim_quantile', 1.00):.2f} | "
            f"Major axis={e['axis1_km']:.0f} km | "
            f"Minor axis={e['axis2_km']:.0f} km | "
            f"σ={e['sigma']:.2f} | "
            f"{shift_text}"
        )

    return "\n".join(lines)



import textwrap

def add_titles(fig, ax, day, day_hw_n, raw_comp_n, major_comp_n, blob_group_n, accepted, status, selection_note):

    fig.suptitle(
        "Spatial Footprints of Simultaneous Heatwave Structures",
        y=0.965,
        fontsize=13,
        fontweight="bold",
    )

    subtitle_main = (
        f"{day.strftime('%Y-%m-%d')} | "
        f"HW cells={day_hw_n} | "
        f"Raw components={raw_comp_n} | "
        f"Major components={major_comp_n} | "
        f"Retained structures={blob_group_n} | "
        f"Retained ellipses={len(accepted)}"
    )

    # Do NOT show OK in the subtitle
    # Only show status when something is not fully normal
    if status and status != "OK":
        subtitle_main += f" | Status: {status.replace('_', ' ')}"

    if selection_note:
        subtitle_main += f" | {selection_note}"

    metrics_line = compose_summary_line(accepted)

    ax.set_title(
        subtitle_main + "\n" + metrics_line,
        fontsize=9,
        pad=2,
    )

    if not HAVE_CARTOPY:
        ax.set_xlabel("Longitude (°)")
        ax.set_ylabel("Latitude (°)")
        
# -----------------------------
# Main
# -----------------------------
def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    print("=" * 120)
    print("Spatial Characterization of Simultaneous Heatwave Events (SHWEs)")
    print("Clean blob-first version with merge-revert safeguard")
    print(f"Sigma is fixed at {SIGMA_DEFAULT:.2f} (no adaptive shrinking)")
    print(f"Close-merge threshold = {CLOSE_MERGE_RELATIVE_THRESHOLD:.2f} of ORIGINAL biggest raw component")
    print(f"Secondary blob threshold = {SECOND_BLOB_RELATIVE_THRESHOLD:.2f} of FINAL Blob 1")
    print(f"Near-gap merge buffer = {MERGE_GAP_CELLS} cell(s)")
    print("MIN_HW_PURITY = not used (no purity rejection)")
    print("PCA filtering = not used (full blob PCA)")
    print("Ellipse geometry is fit first, then translated to a Tmax-weighted centroid.")
    print("HAVE_CARTOPY =", HAVE_CARTOPY)
    print("- MASTER :", MASTER_CSV)
    print("- OUT    :", OUT_DIR)

    usecols = ["date", "lat1", "lon1", "heatwave_id", "val"]
    print("[LOAD] Reading master CSV (usecols=date,lat1,lon1,heatwave_id,val)...")
    df = pd.read_csv(MASTER_CSV, usecols=usecols)

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "lat1", "lon1", "heatwave_id"])
    df["heatwave_id"] = df["heatwave_id"].astype(int)
    df["val"] = pd.to_numeric(df["val"], errors="coerce")

    # Restrict to Apr-Sep
    df = df[df["date"].dt.month.isin(MONTHS_IN_SCOPE)].copy()

    # Full Apr-Sep calendar from all available dates
    all_dates = pd.Series(sorted(df["date"].unique()))
    if len(all_dates) == 0:
        raise RuntimeError("No dates found after filtering to Apr-Sep. Check master file and MONTHS_IN_SCOPE.")

    print(f"[INFO] All Apr-Sep days in master (days with data): {len(all_dates):,}")
    print(f"[INFO] Date range: {all_dates.iloc[0].strftime('%Y-%m-%d')} to {all_dates.iloc[-1].strftime('%Y-%m-%d')}")

    # Big-day selection
    circles = df[df["heatwave_id"] > 0].copy()
    print(f"[INFO] Circle rows (heatwave_id>0): {len(circles):,}")
    
    day_counts_hw = circles.groupby("date").size()
    day_counts_all = day_counts_hw.reindex(all_dates, fill_value=0)
    
    # No minimum-cells-per-day filter
    eligible = day_counts_all
    
    thr = quantile_threshold_intlike(
        eligible,
        BIGDAY_QUANTILE,
        method=QUANTILE_METHOD
    )
    
    big_days = eligible[eligible >= thr].index
    
    print(f"[BIGDAYS] Minimum cells/day filter: not used")
    print(f"[BIGDAYS] Eligible days={len(eligible):,}")
    print(f"[BIGDAYS] P{BIGDAY_QUANTILE * 100:.1f} (method={QUANTILE_METHOD}) => threshold circles/day >= {thr:.0f}")
    print(f"[BIGDAYS] Selected days: {len(big_days):,}")

    bigdays_csv = os.path.join(OUT_DIR, "bigdays_p97p5_all_days.csv")
    day_counts_all.loc[big_days].rename("circles_per_day").to_frame().to_csv(bigdays_csv, index=True)
    print("[SAVED] Big-day list:", bigdays_csv)

    # FULL fixed grid from all rows
    lats_full, lons_full, lat_to_i, lon_to_j = build_grid_index(df)
    n_i, n_j = len(lats_full), len(lons_full)
    print(f"[GRID] n_lat={n_i}, n_lon={n_j}, total_cells={n_i * n_j}")

    grid_cells = [round_cell((lon, lat)) for lat in lats_full for lon in lons_full]
    grid_lon = np.array([c[0] for c in grid_cells], dtype=float)
    grid_lat = np.array([c[1] for c in grid_cells], dtype=float)

    # Map extent
    lon_min = float(lons_full.min() - 1)
    lon_max = float(lons_full.max() + 1)
    lat_min = float(lats_full.min() - 1)
    lat_max = float(lats_full.max() + 1)

    # Outputs
    pdf_filtered = os.path.join(OUT_DIR, "SHWE_spatial_PCA_ellipses_blobfirst_clean_p60_merge_revert.pdf")
    metrics_csv = os.path.join(OUT_DIR, "SHWE_spatial_PCA_metrics_blobfirst_clean_p60_merge_revert.csv")
    daylog_csv = os.path.join(OUT_DIR, "SHWE_day_log_blobfirst_clean_p60_merge_revert.csv")
    flagged_txt = os.path.join(OUT_DIR, "flagged_days_blobfirst_clean_p60_merge_revert.txt")

    metrics = []
    day_log = []
    flagged_days = []

    day_list = sorted(list(big_days))
    if MAX_PAGES is not None:
            day_list = day_list[:MAX_PAGES]
    
    export_requested_snapshot_pngs(
            df=df,
            lats_full=lats_full,
            lons_full=lons_full,
            lat_to_i=lat_to_i,
            lon_to_j=lon_to_j,
            n_i=n_i,
            n_j=n_j,
            grid_cells=grid_cells,
            grid_lon=grid_lon,
            grid_lat=grid_lat,
            lon_min=lon_min,
            lon_max=lon_max,
            lat_min=lat_min,
            lat_max=lat_max,
        )

    with PdfPages(pdf_filtered) as ppdf:
        for k_day, day in enumerate(day_list, 1):
            dday = df[df["date"] == day].copy()
            dday_hw = dday[dday["heatwave_id"] > 0].copy()

            day_val_lookup = (
                dday_hw.groupby(["lon1", "lat1"], as_index=False)["val"]
                .mean()
            )
            cell_to_val = {
                round_cell((row["lon1"], row["lat1"])): row["val"]
                for _, row in day_val_lookup.iterrows()
            }

            day_hw_cells_raw = {round_cell((lo, la)) for lo, la in zip(dday_hw["lon1"].values, dday_hw["lat1"].values)}

            if not day_hw_cells_raw:
                fig, ax = make_map_ax(lon_min, lon_max, lat_min, lat_max, reserve_legend=True)
                add_titles(fig, ax, day, 0, 0, 0, 0, [], "NO HW CELLS", "")
                add_custom_legend(fig)
                ppdf.savefig(fig)
                plt.close(fig)

                day_log.append({
                    "date": day.strftime("%Y-%m-%d"),
                    "cells_day": 0,
                    "n_components_day": 0,
                    "largest_component_raw": 0,
                    "close_merge_cutoff": 0,
                    "second_blob_cutoff": 0,
                    "n_major_components": 0,
                    "n_blob_groups": 0,
                    "largest_blob_size": 0,
                    "accepted_ellipses": 0,
                    "total_hw_inside": 0,
                    "total_inside": 0,
                    "mean_hw_purity_pct": np.nan,
                    "merge_mode": "",
                    "status": "no_hw_cells",
                    "selection_note": "",
                })
                flagged_days.append(f"{day.strftime('%Y-%m-%d')}: no_hw_cells")
                continue

            # RAW daily components
            day_hw_list_sorted = sorted(day_hw_cells_raw)
            day_hw_lons = np.array([c[0] for c in day_hw_list_sorted], dtype=float)
            day_hw_lats = np.array([c[1] for c in day_hw_list_sorted], dtype=float)

            pts = list(zip(
                pd.Series(day_hw_lats).map(lat_to_i).values,
                pd.Series(day_hw_lons).map(lon_to_j).values,
            ))
            comps_raw = connected_components(pts, n_i, n_j, connectivity=CONNECTIVITY)

            comp_records = []
            for comp in comps_raw:
                raw_cells = {round_cell((lons_full[j], lats_full[i])) for i, j in comp}
                comp_records.append({
                    "raw_cells": raw_cells,
                    "retained_cells": raw_cells,
                })

            original_main_blob, tentative_main_blob, all_components, largest_component_size, close_merge_cutoff = select_blob_groups(comp_records)

            major_comp_n = sum(
                1 for rec in all_components
                if len(rec["raw_cells"]) >= close_merge_cutoff
            ) if all_components else 0

            hw_cell_set = set(day_hw_cells_raw)
            grid_is_hw = np.array([c in hw_cell_set for c in grid_cells], dtype=bool)

            accepted = []
            failed_blob_ids = []
            far_blobs = []
            second_blob_cutoff = 0
            final_main_blob = None

            merge_used = False
            merge_reverted = False
            main_had_close_merges = False
            main_blob_ok = False

            if original_main_blob is not None:
                main_had_close_merges = len(tentative_main_blob["member_ids"]) > 1

                if main_had_close_merges:
                    # First try merged main blob
                    e_main = evaluate_blob_ellipse_clean(
                        blob_cells=tentative_main_blob["retained_cells"],
                        blob_label="blob_1",
                        grid_lon=grid_lon,
                        grid_lat=grid_lat,
                        grid_cells=grid_cells,
                        grid_is_hw=grid_is_hw,
                        cell_to_val=cell_to_val,
                        source_plot_cells=tentative_main_blob["raw_cells"],
                    )

                    if e_main is not None:
                        merge_used = True
                        final_main_blob = tentative_main_blob
                        e_main["group_index"] = 1
                        accepted.append(e_main)
                        main_blob_ok = True
                    else:
                        # Merge rejected for this day -> revert to original biggest raw blob
                        merge_reverted = True
                        final_main_blob = original_main_blob

                        e_main = evaluate_blob_ellipse_clean(
                            blob_cells=original_main_blob["retained_cells"],
                            blob_label="blob_1",
                            grid_lon=grid_lon,
                            grid_lat=grid_lat,
                            grid_cells=grid_cells,
                            grid_is_hw=grid_is_hw,
                            cell_to_val=cell_to_val,
                            source_plot_cells=original_main_blob["raw_cells"],
                        )

                        if e_main is not None:
                            e_main["group_index"] = 1
                            accepted.append(e_main)
                            main_blob_ok = True
                        else:
                            failed_blob_ids.append(1)
                else:
                    # No close merge to try; just use original main blob
                    final_main_blob = original_main_blob

                    e_main = evaluate_blob_ellipse_clean(
                        blob_cells=original_main_blob["retained_cells"],
                        blob_label="blob_1",
                        grid_lon=grid_lon,
                        grid_lat=grid_lat,
                        grid_cells=grid_cells,
                        grid_is_hw=grid_is_hw,
                        cell_to_val=cell_to_val,
                        source_plot_cells=original_main_blob["raw_cells"],
                    )

                    if e_main is not None:
                        e_main["group_index"] = 1
                        accepted.append(e_main)
                        main_blob_ok = True
                    else:
                        failed_blob_ids.append(1)

                # After final main blob is decided, search for far secondary blobs
                far_blobs, second_blob_cutoff = select_far_secondary_blobs(final_main_blob, all_components)

                for ib, blob in enumerate(far_blobs, start=2):
                    e = evaluate_blob_ellipse_clean(
                        blob_cells=blob["retained_cells"],
                        blob_label=f"blob_{ib}",
                        grid_lon=grid_lon,
                        grid_lat=grid_lat,
                        grid_cells=grid_cells,
                        grid_is_hw=grid_is_hw,
                        cell_to_val=cell_to_val,
                        source_plot_cells=blob["raw_cells"],
                    )
                    if e is not None:
                        e["group_index"] = ib
                        accepted.append(e)
                    else:
                        failed_blob_ids.append(ib)

            hw_inside_sum, total_inside_sum, mean_purity = summarize_kept_ellipses(accepted)

            orange_plot_cells = set().union(*(e["source_plot_cells"] for e in accepted)) if accepted else set()
            grey_plot_cells = set(day_hw_cells_raw) - orange_plot_cells

            fig, ax = make_map_ax(lon_min, lon_max, lat_min, lat_max, reserve_legend=True)

            if grey_plot_cells:
                draw_cells(ax, sorted(grey_plot_cells), facecolor=COL_OTHER_HW, alpha=0.80, lw=0.28, zorder=3)
            if orange_plot_cells:
                draw_cells(ax, sorted(orange_plot_cells), facecolor=COL_ACCEPTED, alpha=0.95, lw=0.32, zorder=5)

            draw_cartopy_overlay(ax, lon_min, lon_max, lat_min, lat_max)

            for idx, e in enumerate(accepted, start=1):
                elon, elat = ellipse_points_lonlat_from_km(
                    e["center_lon"], e["center_lat"], e["center_xy"], e["eigvecs"], e["eigvals"], sigma=e["sigma"]
                )
                p1a, p1b, p2a, p2b = axes_segments_lonlat_from_km(
                    e["center_lon"], e["center_lat"], e["center_xy"], e["eigvecs"], e["eigvals"], sigma=e["sigma"]
                )

                plot_line(ax, elon, elat, lw=2.1, zorder=7, color=COL_ELLIPSE)
                plot_line(ax, [p1a[0], p1b[0]], [p1a[1], p1b[1]], lw=2.7, zorder=7, color=COL_MAJOR)
                plot_line(ax, [p2a[0], p2b[0]], [p2a[1], p2b[1]], lw=1.5, zorder=7, color=COL_MINOR)
                plot_centroid(ax, e["center_lon"], e["center_lat"], size=55, zorder=8, color=COL_CENTROID)
                plot_text_lonlat(ax, e["center_lon"] + 0.35, e["center_lat"] + 0.25, f"E{idx}", fontsize=8.2, zorder=9)

                metrics.append({
                    "date": day.strftime("%Y-%m-%d"),
                    "cells_day": int(len(day_hw_cells_raw)),
                    "bigday_quantile": float(BIGDAY_QUANTILE),
                    "bigday_threshold_cells_day": float(thr),
                    "n_components_day": int(len(comps_raw)),
                    "largest_component_raw": int(largest_component_size),
                    "close_merge_cutoff": int(close_merge_cutoff),
                    "second_blob_cutoff": int(second_blob_cutoff),
                    "n_major_components": int(major_comp_n),
                    "n_blob_groups": int((1 if final_main_blob is not None else 0) + len(far_blobs)),
                    "accepted_ellipse_id": int(idx),
                    "group_index": int(e.get("group_index", -1)),
                    "blob_label": e["blob_label"],
                    "blob_size": int(e["blob_size"]),
                    "centroid_lon": float(e["center_lon"]),
                    "centroid_lat": float(e["center_lat"]),
                    "pca_centroid_lon": float(e.get("pca_center_lon", np.nan)),
                    "pca_centroid_lat": float(e.get("pca_center_lat", np.nan)),
                    "centroid_shift_km": float(e.get("centroid_shift_km", np.nan)),
                    "centroid_shift_dx_km": float(e.get("centroid_shift_dx_km", np.nan)),
                    "centroid_shift_dy_km": float(e.get("centroid_shift_dy_km", np.nan)),
                    "centroid_shift_direction": e.get("centroid_shift_direction", ""),
                    "weight_sum": float(e.get("weight_sum", np.nan)),
                    "sigma": float(e["sigma"]),
                    "axis1_len_km": float(e["axis1_km"]),
                    "axis2_len_km": float(e["axis2_km"]),
                    "pc1_vec_x": float(e["eigvecs"][0, 0]),
                    "pc1_vec_y": float(e["eigvecs"][1, 0]),
                    "pc2_vec_x": float(e["eigvecs"][0, 1]),
                    "pc2_vec_y": float(e["eigvecs"][1, 1]),
                    "total_inside": int(e["total_inside"]),
                    "hw_inside": int(e["hw_inside"]),
                    "white_inside": int(e["white_inside"]),
                    "hw_pct": float(100.0 * e["purity"]),
                    "white_pct": float(100.0 * e["white_frac"]),
                    "trim_quantile": float(e.get("trim_quantile", 1.00)),
                    "trimmed_blob_size": int(e.get("trimmed_blob_size", e["blob_size"])),
                    "merge_mode": (
                        "merge_used" if merge_used else
                        "merge_reverted" if merge_reverted else
                        "no_close_merge"
                    ),
                    "valid": True,
                })

            draw_cartopy_overlay(ax, lon_min, lon_max, lat_min, lat_max)

            if original_main_blob is None:
                status = "NO_MAIN_BLOB"
                selection_note = "no raw components found"
                merge_mode = ""
            else:
                merge_mode = (
                    "merge_used" if merge_used else
                    "merge_reverted" if merge_reverted else
                    "no_close_merge"
                )

                candidate_blob_groups = (1 if final_main_blob is not None else 0) + len(far_blobs)

                if not main_blob_ok and len(accepted) == 0:
                    status = "NO_VALID_ELLIPSE"
                    if merge_reverted:
                        selection_note = "merged main failed; reverted main also failed 60% purity"
                    else:
                        selection_note = "main blob failed the 60% purity test"
                elif main_blob_ok and len(accepted) == candidate_blob_groups:
                    status = "OK"
                    if merge_used:
                        selection_note = "close merge accepted"
                    elif merge_reverted:
                        selection_note = "close merge rejected; reverted to original main blob"
                    else:
                        selection_note = "no close merge applied"
                else:
                    status = "PARTIAL_OK"
                    note_parts = []
                    if merge_used:
                        note_parts.append("close merge accepted")
                    elif merge_reverted:
                        note_parts.append("close merge rejected; reverted to original main blob")
                    else:
                        note_parts.append("no close merge applied")
                    if failed_blob_ids:
                        note_parts.append(f"failed blobs={failed_blob_ids}")
                    selection_note = " | ".join(note_parts)

            if status != "OK":
                flagged_days.append(f"{day.strftime('%Y-%m-%d')}: {status} | {selection_note}")

            add_titles(
                fig, ax,
                day=day,
                day_hw_n=len(day_hw_cells_raw),
                raw_comp_n=len(comps_raw),
                major_comp_n=major_comp_n,
                blob_group_n=(1 if final_main_blob is not None else 0) + len(far_blobs),
                accepted=accepted,
                status=status,
                selection_note=selection_note,
            )
            add_custom_legend(fig)
            plt.tight_layout(rect=[0, 0.08, 1, 0.94])
            ppdf.savefig(fig)
            plt.close(fig)

            largest_blob_size = len(final_main_blob["raw_cells"]) if final_main_blob is not None else 0

            day_log.append({
                "date": day.strftime("%Y-%m-%d"),
                "cells_day": int(len(day_hw_cells_raw)),
                "n_components_day": int(len(comps_raw)),
                "largest_component_raw": int(largest_component_size),
                "close_merge_cutoff": int(close_merge_cutoff),
                "second_blob_cutoff": int(second_blob_cutoff),
                "n_major_components": int(major_comp_n),
                "n_blob_groups": int((1 if final_main_blob is not None else 0) + len(far_blobs)),
                "largest_blob_size": int(largest_blob_size),
                "accepted_ellipses": int(len(accepted)),
                "total_hw_inside": int(hw_inside_sum),
                "total_inside": int(total_inside_sum),
                "mean_hw_purity_pct": float(100.0 * mean_purity) if len(accepted) > 0 else np.nan,
                "merge_mode": merge_mode,
                "status": status,
                "selection_note": selection_note,
            })

            if k_day % 25 == 0:
                print(f"[PROGRESS] {k_day}/{len(day_list)} days processed...")

    pd.DataFrame(metrics).to_csv(metrics_csv, index=False)
    pd.DataFrame(day_log).to_csv(daylog_csv, index=False)

    with open(flagged_txt, "w", encoding="utf-8") as f:
        f.write("Days flagged by the clean blob-first adaptive PCA workflow with merge-revert safeguard\n")
        f.write("=" * 90 + "\n")
        if flagged_days:
            for line in flagged_days:
                f.write(line + "\n")
        else:
            f.write("None\n")

    print("=" * 120)
    print("[SAVED]")
    print(" PDF (filtered): ", pdf_filtered)
    print(" METRICS CSV:    ", metrics_csv)
    print(" DAY LOG CSV:    ", daylog_csv)
    print(" FLAGGED TXT:    ", flagged_txt)
    print(" BIGDAYS CSV:    ", bigdays_csv)
    print("=" * 120)
    print("DONE.")


if __name__ == "__main__":
    main()