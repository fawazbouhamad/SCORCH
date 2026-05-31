"""
Figure 1:
(a) Event centroids with PCA L1/L2 axes
(b) Event-frequency heatmap from full PCA ellipse footprints

Figure 2:
(a) Centroids colored by L2/L1 ratio
(b) Centroids colored by ellipse area
(c) Centroids colored by L1 orientation
"""

import os
import math
import warnings

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe

from matplotlib.lines import Line2D
from matplotlib.colors import Normalize, LinearSegmentedColormap
from matplotlib.colors import BoundaryNorm
warnings.filterwarnings("ignore", category=RuntimeWarning)

# =============================================================================
# OPTIONAL: Cartopy
# =============================================================================

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

OUT_DIR = r"ENTER_OUTPUT_DIRECTORY"

METRICS_CSV = os.path.join(
    OUT_DIR,
    "SHWE_spatial_PCA_metrics_blobfirst_clean_p60_merge_revert.csv"
)

OUT_AB_PNG = os.path.join(
    OUT_DIR,
    "Figure_AB_PCA_axes_and_event_frequency_Q1_FIXED_DOMAIN.png"
)
OUT_AB_PDF = os.path.join(
    OUT_DIR,
    "Figure_AB_PCA_axes_and_event_frequency_Q1_FIXED_DOMAIN.pdf"
)

OUT_ABC_PNG = os.path.join(
    OUT_DIR,
    "Figure_ABC_PCA_metrics_Q1_FIXED_DOMAIN.png"
)
OUT_ABC_PDF = os.path.join(
    OUT_DIR,
    "Figure_ABC_PCA_metrics_Q1_FIXED_DOMAIN.pdf"
)


# =============================================================================
# FIXED MAP DOMAIN
# =============================================================================

LON_MIN = 20.0
LON_MAX = 70.0
LAT_MIN = 10.0
LAT_MAX = 46.0


# =============================================================================
# STYLE SETTINGS
# =============================================================================

FIG_AB_W = 13.2
FIG_AB_H = 6.0

FIG_ABC_W = 14.4
FIG_ABC_H = 5.0

L1_COLOR = "red"
L2_COLOR = "darkorange"

AXIS_ALPHA = 0.18
POINT_ALPHA = 0.55
POINT_SIZE = 15

AXIS_LW_L1 = 0.75
AXIS_LW_L2 = 0.75

MAJOR_TICK_STEP_DEG = 10

RATIO_CMAP = "viridis_r"
AREA_CMAP = "plasma"
ORIENT_CMAP = "RdYlBu_r"

USE_RATIO_PERCENTILE_CLIP = True
USE_AREA_PERCENTILE_CLIP = True
LOW_PCTL = 2
HIGH_PCTL = 98

HEATMAP_RES_DEG = 0.25

HEAT_CMAP = LinearSegmentedColormap.from_list(
    "event_frequency_q1_muted",
    ["#2ca25f", "#f7fcb9", "#f03b20"]
)

CITY_LABEL_MIN_DISTANCE_DEG = 2.75
COUNTRY_LABEL_MIN_DISTANCE_DEG = 4.35
SEA_LABEL_MIN_DISTANCE_DEG = 5.00

LABEL_PAD_DEG = 0.45


# =============================================================================
# LABELS INSIDE 20–70E, 10–46N ONLY
# name, lon, lat, priority
# lower priority = more important
# =============================================================================

SEA_LABELS = [
    ("RED SEA", 38.5, 20.8, 1),
    ("GULF OF ADEN", 47.6, 12.6, 1),
    ("ARABIAN SEA", 60.5, 14.8, 1),
    ("GULF OF OMAN", 58.5, 25.0, 1),
    ("PERSIAN GULF\n(ARABIAN GULF)", 51.0, 27.2, 1),
    ("BLACK SEA", 34.5, 43.5, 1),
    ("MEDITERRANEAN SEA", 31.5, 35.4, 1),
    ("CASPIAN SEA", 51.8, 41.3, 1),
]

COUNTRY_LABELS = [
    ("EGYPT", 30.0, 26.6, 1),
    ("SUDAN", 31.0, 18.6, 1),
    ("ERITREA", 39.0, 16.8, 2),
    ("DJIBOUTI", 42.7, 11.8, 3),
    ("YEMEN", 45.5, 15.2, 1),
    ("OMAN", 57.2, 20.4, 1),
    ("SAUDI ARABIA", 44.2, 23.0, 1),
    ("UNITED ARAB EMIRATES", 54.3, 24.0, 2),
    ("IRAQ", 43.5, 32.1, 1),
    ("SYRIA", 38.4, 35.0, 1),
    ("JORDAN", 36.4, 30.8, 2),
    ("IRAN", 53.8, 32.2, 1),
    ("AFGHANISTAN", 65.2, 34.2, 1),
    ("PAKISTAN", 67.0, 28.7, 1),
    ("TURKMENISTAN", 58.4, 39.4, 1),
    ("UZBEKISTAN", 64.5, 42.1, 1),
    ("TÜRKIYE", 35.3, 39.2, 1),
    ("GEORGIA", 43.7, 42.4, 2),
    ("AZERBAIJAN", 48.6, 40.8, 2),
    ("ARMENIA", 44.7, 40.3, 3),
    ("GREECE", 22.8, 39.2, 1),
    ("BULGARIA", 25.1, 42.8, 1),
]

CITY_LABELS = [
    ("Cairo", 31.2357, 30.0444, 1),
    ("Alexandria", 29.9187, 31.2001, 2),
    ("Khartoum", 32.5599, 15.5007, 1),
    ("Asmara", 38.9251, 15.3229, 2),
    ("Djibouti", 43.1456, 11.5721, 2),

    ("Jeddah", 39.1925, 21.4858, 1),
    ("Makkah", 39.8579, 21.3891, 2),
    ("Madinah", 39.5692, 24.5247, 2),
    ("Riyadh", 46.6753, 24.7136, 1),
    ("Kuwait City", 47.9774, 29.3759, 1),
    ("Manama", 50.5860, 26.2235, 2),
    ("Doha", 51.5310, 25.2854, 2),
    ("Dubai", 55.2708, 25.2048, 1),
    ("Muscat", 58.4059, 23.5880, 1),
    ("Sana'a", 44.1910, 15.3694, 1),
    ("Aden", 45.0187, 12.7855, 2),

    ("Amman", 35.9304, 31.9539, 1),
    ("Jerusalem", 35.2137, 31.7683, 2),
    ("Beirut", 35.5018, 33.8938, 2),
    ("Baghdad", 44.3661, 33.3152, 1),

    ("Tehran", 51.3890, 35.6892, 1),
    ("Mashhad", 59.6168, 36.2605, 1),
    ("Isfahan", 51.6675, 32.6546, 2),
    ("Shiraz", 52.5836, 29.5918, 2),
    ("Tabriz", 46.2919, 38.0962, 2),
    ("Kabul", 69.2075, 34.5553, 1),
    ("Karachi", 67.0011, 24.8607, 1),
    ("Ashgabat", 58.3838, 37.9601, 1),
    ("Tashkent", 69.2401, 41.2995, 1),

    ("Istanbul", 28.9784, 41.0082, 1),
    ("Ankara", 32.8597, 39.9334, 1),
    ("Baku", 49.8671, 40.4093, 1),
    ("Yerevan", 44.5152, 40.1872, 2),
    ("Athens", 23.7275, 37.9838, 1),
    ("Damascus", 36.2765, 33.5138, 1),
    ("Bucharest", 26.1025, 44.4268, 1),
]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_extent(df=None):
    return LON_MIN, LON_MAX, LAT_MIN, LAT_MAX


def km_to_deg_offsets(dx_km, dy_km, lat_deg):
    km_per_deg_lon = 111.320 * math.cos(math.radians(lat_deg))
    km_per_deg_lat = 110.574

    if abs(km_per_deg_lon) < 1e-12:
        km_per_deg_lon = 1e-12

    return dx_km / km_per_deg_lon, dy_km / km_per_deg_lat


def exact_axis_endpoints_from_vectors(
    lon0,
    lat0,
    l1_len_km,
    l2_len_km,
    pc1_vec_x,
    pc1_vec_y,
    pc2_vec_x,
    pc2_vec_y
):
    v1 = np.array([pc1_vec_x, pc1_vec_y], dtype=float)
    v2 = np.array([pc2_vec_x, pc2_vec_y], dtype=float)

    n1 = np.linalg.norm(v1)
    n2 = np.linalg.norm(v2)

    if not np.isfinite(n1) or n1 <= 0:
        v1 = np.array([1.0, 0.0])
        n1 = 1.0

    if not np.isfinite(n2) or n2 <= 0:
        v2 = np.array([0.0, 1.0])
        n2 = 1.0

    v1 = v1 / n1
    v2 = v2 / n2

    half1 = l1_len_km / 2.0
    half2 = l2_len_km / 2.0

    dx1a, dy1a = -half1 * v1[0], -half1 * v1[1]
    dx1b, dy1b = half1 * v1[0], half1 * v1[1]

    dx2a, dy2a = -half2 * v2[0], -half2 * v2[1]
    dx2b, dy2b = half2 * v2[0], half2 * v2[1]

    dlon1a, dlat1a = km_to_deg_offsets(dx1a, dy1a, lat0)
    dlon1b, dlat1b = km_to_deg_offsets(dx1b, dy1b, lat0)
    dlon2a, dlat2a = km_to_deg_offsets(dx2a, dy2a, lat0)
    dlon2b, dlat2b = km_to_deg_offsets(dx2b, dy2b, lat0)

    return (
        (lon0 + dlon1a, lat0 + dlat1a),
        (lon0 + dlon1b, lat0 + dlat1b),
        (lon0 + dlon2a, lat0 + dlat2a),
        (lon0 + dlon2b, lat0 + dlat2b),
    )


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


def robust_norm(values, use_clip=True):
    values = np.asarray(values, dtype=float)
    vals = values[np.isfinite(values)]

    if len(vals) == 0:
        return Normalize(vmin=0.0, vmax=1.0)

    if use_clip:
        vmin = np.percentile(vals, LOW_PCTL)
        vmax = np.percentile(vals, HIGH_PCTL)
    else:
        vmin = np.nanmin(vals)
        vmax = np.nanmax(vals)

    if not np.isfinite(vmin) or not np.isfinite(vmax) or abs(vmax - vmin) < 1e-12:
        vmax = vmin + 1.0

    return Normalize(vmin=vmin, vmax=vmax)


def setup_panel_ax(ax, df=None):
    lon_min, lon_max, lat_min, lat_max = get_extent(df)

    if HAVE_CARTOPY:
        ax.set_extent([lon_min, lon_max, lat_min, lat_max], crs=ccrs.PlateCarree())

        ax.add_feature(
            cfeature.OCEAN.with_scale("50m"),
            facecolor="#dcecf2",
            zorder=0
        )
        ax.add_feature(
            cfeature.LAND.with_scale("50m"),
            facecolor="#f8f6ef",
            zorder=0
        )
        ax.add_feature(
            cfeature.LAKES.with_scale("50m"),
            facecolor="#eaf3f7",
            edgecolor="none",
            zorder=1
        )
        ax.add_feature(
            cfeature.RIVERS.with_scale("50m"),
            linewidth=0.22,
            edgecolor="#9fc9d8",
            alpha=0.45,
            zorder=6
        )
        ax.add_feature(
            cfeature.COASTLINE.with_scale("50m"),
            linewidth=0.45,
            edgecolor="0.35",
            alpha=0.65,
            zorder=7
        )
        ax.add_feature(
            cfeature.BORDERS.with_scale("50m"),
            linewidth=0.35,
            edgecolor="0.45",
            alpha=0.45,
            zorder=7
        )

        xticks = np.arange(20, 71, MAJOR_TICK_STEP_DEG)
        yticks = np.arange(10, 47, MAJOR_TICK_STEP_DEG)

        gl = ax.gridlines(
            crs=ccrs.PlateCarree(),
            draw_labels=True,
            linewidth=0.32,
            alpha=0.28,
            linestyle="-",
            xlocs=xticks,
            ylocs=yticks,
            x_inline=False,
            y_inline=False,
            zorder=6
        )

        gl.top_labels = False
        gl.right_labels = False
        gl.xlabel_style = {"size": 8}
        gl.ylabel_style = {"size": 8}

    else:
        ax.set_xlim(lon_min, lon_max)
        ax.set_ylim(lat_min, lat_max)
        ax.set_xlabel("Longitude (°)", fontsize=9)
        ax.set_ylabel("Latitude (°)", fontsize=9)
        ax.set_xticks(np.arange(20, 71, 10))
        ax.set_yticks(np.arange(10, 47, 10))
        ax.tick_params(labelsize=8)
        ax.grid(True, alpha=0.30, linewidth=0.45)


def plot_line(ax, x, y, color, lw=1.0, alpha=1.0, zorder=3):
    if HAVE_CARTOPY:
        ax.plot(
            x,
            y,
            color=color,
            linewidth=lw,
            alpha=alpha,
            zorder=zorder,
            transform=ccrs.PlateCarree()
        )
    else:
        ax.plot(
            x,
            y,
            color=color,
            linewidth=lw,
            alpha=alpha,
            zorder=zorder
        )


def plot_scatter(ax, x, y, c, s=20, alpha=0.5, zorder=4):
    if HAVE_CARTOPY:
        sc = ax.scatter(
            x,
            y,
            c=c,
            s=s,
            alpha=alpha,
            zorder=zorder,
            transform=ccrs.PlateCarree(),
            edgecolors="none"
        )
    else:
        sc = ax.scatter(
            x,
            y,
            c=c,
            s=s,
            alpha=alpha,
            zorder=zorder,
            edgecolors="none"
        )

    return sc


def panel_label(ax, label):
    ax.text(
        0.50,
        1.035,
        label,
        transform=ax.transAxes,
        ha="center",
        va="bottom",
        fontsize=12,
        fontweight="bold",
        zorder=40
    )


def label_box(lon, lat, text, fontsize, dx, dy):
    label_lon = lon + dx
    label_lat = lat + dy

    lines = text.split("\n")
    longest = max(len(line) for line in lines)

    width = max(1.05, 0.145 * longest * (fontsize / 6.0))
    height = max(0.62, 0.78 * len(lines) * (fontsize / 6.0))

    return (
        label_lon - width / 2,
        label_lon + width / 2,
        label_lat - height / 2,
        label_lat + height / 2
    )


def boxes_overlap(b1, b2, pad=0.28):
    return not (
        b1[1] + pad < b2[0] or
        b1[0] - pad > b2[1] or
        b1[3] + pad < b2[2] or
        b1[2] - pad > b2[3]
    )


def box_inside_domain(box):
    return (
        box[0] >= LON_MIN + LABEL_PAD_DEG and
        box[1] <= LON_MAX - LABEL_PAD_DEG and
        box[2] >= LAT_MIN + LABEL_PAD_DEG and
        box[3] <= LAT_MAX - LABEL_PAD_DEG
    )


def add_text(
    ax,
    lon,
    lat,
    text,
    fontsize,
    color,
    alpha,
    weight="normal",
    style="normal",
    zorder=15
):
    kwargs = dict(
        ha="center",
        va="center",
        fontsize=fontsize,
        color=color,
        alpha=alpha,
        fontweight=weight,
        fontstyle=style,
        zorder=zorder,
        path_effects=[
            pe.withStroke(linewidth=2.7, foreground="white", alpha=0.96)
        ]
    )

    if HAVE_CARTOPY:
        ax.text(lon, lat, text, transform=ccrs.PlateCarree(), **kwargs)
    else:
        ax.text(lon, lat, text, **kwargs)


def add_dot(ax, lon, lat, size=8):
    if HAVE_CARTOPY:
        ax.scatter(
            lon,
            lat,
            s=size,
            color="black",
            alpha=0.80,
            transform=ccrs.PlateCarree(),
            zorder=16
        )
    else:
        ax.scatter(
            lon,
            lat,
            s=size,
            color="black",
            alpha=0.80,
            zorder=16
        )


def try_add_label(
    ax,
    occupied_boxes,
    text,
    lon,
    lat,
    fontsize,
    dx,
    dy,
    color,
    alpha,
    weight="normal",
    style="normal",
    zorder=15,
    pad=0.35,
    dot=False
):
    if not (LON_MIN <= lon <= LON_MAX and LAT_MIN <= lat <= LAT_MAX):
        return False

    box = label_box(lon, lat, text, fontsize, dx, dy)

    if not box_inside_domain(box):
        return False

    if any(boxes_overlap(box, old_box, pad=pad) for old_box in occupied_boxes):
        return False

    occupied_boxes.append(box)

    if dot:
        add_dot(ax, lon, lat, size=9 if fontsize >= 5.5 else 7)

    add_text(
        ax,
        lon + dx,
        lat + dy,
        text,
        fontsize=fontsize,
        color=color,
        alpha=alpha,
        weight=weight,
        style=style,
        zorder=zorder
    )

    return True


def add_google_style_labels(ax):
    occupied_boxes = []

    manual_offsets = {
        "MEDITERRANEAN SEA": (-1.55, -1.75),
        "BLACK SEA": (0.0, -0.15),
        "CASPIAN SEA": (-0.25, 0.65),
        "PERSIAN GULF\n(ARABIAN GULF)": (0.10, 0.10),
        "GULF OF OMAN": (0.20, -0.08),
        "ARABIAN SEA": (-0.20, 0.12),
        "GULF OF ADEN": (0.12, -0.45),
        "RED SEA": (-0.30, -0.3),

        "EGYPT": (0.0, 0.0),
        "SUDAN": (0.0, 0.0),
        "ERITREA": (0.0, 0.0),
        "DJIBOUTI": (0.0, 0.35),
        "YEMEN": (-0.20, 0.5),
        "OMAN": (-0.4, 0.0),
        "SAUDI ARABIA": (1.5, -0.5),
        "UNITED ARAB EMIRATES": (-0.35, -0.35),
        "IRAQ": (0.0, 0.0),
        "JORDAN": (0.0, 0.0),
        "IRAN": (0.0, 0.0),
        "AFGHANISTAN": (-0.35, -0.10),
        "PAKISTAN": (-0.30, -0.65),
        "SYRIA": (0.0, 0.0),
        "TURKMENISTAN": (0.0, 0.20),
        "UZBEKISTAN": (-0.20, -0.50),
        "TÜRKIYE": (0.0, 0.0),
        "GEORGIA": (-0.20, -0.15),
        "AZERBAIJAN": (0.10, -1.1),
        "ARMENIA": (-0.20, 0.10),
        "GREECE": (-0.30, 0.30),
        "BULGARIA": (0.20, -0.10),

        "Alexandria": (-0.45, 0.12),
        "Cairo": (0.35, 0.18),
        "Khartoum": (0.35, 0.15),
        "Asmara": (-0.40, 0.10),
        "Djibouti": (-0.35, 0.10),
        "Damascus": (0.42, 0.22),
        "Bucharest": (0.42, 0.22),

        "Jeddah": (-0.45, -0.10),
        "Makkah": (0.28, -0.05),
        "Madinah": (-0.35, 0.10),
        "Riyadh": (0.40, 0.12),
        "Kuwait City": (0.30, 0.15),
        "Manama": (0.18, 0.12),
        "Doha": (0.25, 0.12),
        "Dubai": (0.28, 0.10),
        "Abu Dhabi": (-0.40, -0.08),
        "Muscat": (0.35, -0.10),
        "Sana'a": (-0.35, 0.12),
        "Aden": (0.35, -0.10),

        "Amman": (0.25, 0.10),
        "Jerusalem": (0.30, -0.05),
        "Beirut": (0.20, 0.12),
        "Baghdad": (0.35, 0.15),
        "Basra": (0.30, -0.10),

        "Tehran": (0.40, 0.15),
        "Mashhad": (0.35, 0.15),
        "Isfahan": (0.35, -0.05),
        "Shiraz": (0.35, -0.08),
        "Tabriz": (-0.40, 0.12),
        "Kabul": (-0.50, 0.10),
        "Karachi": (-0.45, -0.10),
        "Ashgabat": (0.30, -0.05),
        "Tashkent": (-0.55, 0.10),

        "Istanbul": (0.30, 0.12),
        "Ankara": (0.35, 0.12),
        "Tbilisi": (0.25, 0.12),
        "Baku": (0.35, -3),
        "Yerevan": (0.25, -0.10),
        "Athens": (0.30, -0.10),
    }

    def candidate_offsets(name, default_dx=0.0, default_dy=0.0):
        return [manual_offsets.get(name, (default_dx, default_dy))]

    # -----------------------------
    # 1) Seas first, subtle and italic
    # -----------------------------
    for name, lon, lat, priority in sorted(SEA_LABELS, key=lambda x: x[3]):
        for dx, dy in candidate_offsets(name):
            if try_add_label(
                ax=ax,
                occupied_boxes=occupied_boxes,
                text=name,
                lon=lon,
                lat=lat,
                fontsize=5.45,
                dx=dx,
                dy=dy,
                color="#426f83",
                alpha=0.56,
                weight="normal",
                style="italic",
                zorder=11,
                pad=0.20,
                dot=False
            ):
                break

    # -----------------------------
    # 2) Countries
    # -----------------------------
    for name, lon, lat, priority in sorted(COUNTRY_LABELS, key=lambda x: x[3]):
        fontsize = 5.15 if priority == 1 else 4.75

        for dx, dy in candidate_offsets(name):
            if try_add_label(
                ax=ax,
                occupied_boxes=occupied_boxes,
                text=name,
                lon=lon,
                lat=lat,
                fontsize=fontsize,
                dx=dx,
                dy=dy,
                color="0.22",
                alpha=0.48,
                weight="bold",
                style="normal",
                zorder=12,
                pad=0.18,
                dot=False
            ):
                break

    # -----------------------------
    # 3) Cities
    # -----------------------------
    CITY_TEXT_DX = 0.55   # positive = right, negative = left
    CITY_TEXT_DY = 0.65   # positive = up, negative = down
    
    for name, lon, lat, priority in sorted(CITY_LABELS, key=lambda x: x[3]):
        try_add_label(
            ax=ax,
            occupied_boxes=occupied_boxes,
            text=name,
            lon=lon,
            lat=lat,
            fontsize=5.0,
            dx=CITY_TEXT_DX,
            dy=CITY_TEXT_DY,
            color="0.05",
            alpha=0.92,
            weight="normal",
            style="normal",
            zorder=20,
            pad=0.08,
            dot=True
        )


# =============================================================================
# DATA
# =============================================================================

def load_and_prepare_data():
    if not os.path.exists(METRICS_CSV):
        raise FileNotFoundError(f"Metrics CSV not found:\n{METRICS_CSV}")

    df = pd.read_csv(METRICS_CSV)

    required_cols = [
        "centroid_lon",
        "centroid_lat",
        "axis1_len_km",
        "axis2_len_km",
        "pc1_vec_x",
        "pc1_vec_y",
        "pc2_vec_x",
        "pc2_vec_y"
    ]

    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(
            "Missing required columns:\n"
            + ", ".join(missing)
            + "\n\nYour PCA metrics file must include exact PCA eigenvectors."
        )

    df = df.copy()

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

    df = df[
        (df["centroid_lon"] >= LON_MIN) &
        (df["centroid_lon"] <= LON_MAX) &
        (df["centroid_lat"] >= LAT_MIN) &
        (df["centroid_lat"] <= LAT_MAX)
    ].copy()

    df["L1_km"] = df["axis1_len_km"]
    df["L2_km"] = df["axis2_len_km"]

    df["L2_L1_ratio"] = df["L2_km"] / df["L1_km"]
    df["ellipse_area_km2"] = (
        np.pi * (df["L1_km"] / 2.0) * (df["L2_km"] / 2.0)
    )

    df["orientation_deg"] = df.apply(
        lambda r: orientation_from_north_deg(
            r["pc1_vec_x"],
            r["pc1_vec_y"]
        ),
        axis=1
    )

    return df


# =============================================================================
# PANEL PLOTTING
# =============================================================================

def plot_panel_a_axes(ax, df):
    for _, row in df.iterrows():
        lon0 = float(row["centroid_lon"])
        lat0 = float(row["centroid_lat"])

        p1a, p1b, p2a, p2b = exact_axis_endpoints_from_vectors(
            lon0=lon0,
            lat0=lat0,
            l1_len_km=float(row["L1_km"]),
            l2_len_km=float(row["L2_km"]),
            pc1_vec_x=float(row["pc1_vec_x"]),
            pc1_vec_y=float(row["pc1_vec_y"]),
            pc2_vec_x=float(row["pc2_vec_x"]),
            pc2_vec_y=float(row["pc2_vec_y"]),
        )

        plot_line(
            ax,
            [p1a[0], p1b[0]],
            [p1a[1], p1b[1]],
            color=L1_COLOR,
            lw=AXIS_LW_L1,
            alpha=AXIS_ALPHA,
            zorder=2
        )

        plot_line(
            ax,
            [p2a[0], p2b[0]],
            [p2a[1], p2b[1]],
            color=L2_COLOR,
            lw=AXIS_LW_L2,
            alpha=AXIS_ALPHA,
            zorder=2
        )

    plot_scatter(
        ax,
        df["centroid_lon"].values,
        df["centroid_lat"].values,
        c="black",
        s=POINT_SIZE,
        alpha=POINT_ALPHA,
        zorder=8
    )

    handles = [
        Line2D([0], [0], color=L1_COLOR, lw=2.0, label="L1"),
        Line2D([0], [0], color=L2_COLOR, lw=2.0, label="L2"),
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor="black",
            markeredgecolor="black",
            markersize=5,
            label="Centroid"
        )
    ]

    ax.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.045),
        ncol=3,
        fontsize=8.2,
        frameon=True,
        fancybox=False,
        framealpha=1.0,
        edgecolor="black",
        facecolor="white",
        handlelength=2.0,
        columnspacing=1.4,
        borderpad=0.65
    )

    panel_label(ax, "(a)")


def plot_panel_b_ellipse_frequency(ax, df, fig):
    lon_grid = np.arange(LON_MIN, LON_MAX + HEATMAP_RES_DEG, HEATMAP_RES_DEG)
    lat_grid = np.arange(LAT_MIN, LAT_MAX + HEATMAP_RES_DEG, HEATMAP_RES_DEG)

    Lon, Lat = np.meshgrid(lon_grid, lat_grid)
    freq = np.zeros_like(Lon, dtype=float)

    for _, row in df.iterrows():
        lon0 = float(row["centroid_lon"])
        lat0 = float(row["centroid_lat"])

        L1 = float(row["L1_km"])
        L2 = float(row["L2_km"])

        if not np.isfinite(L1) or not np.isfinite(L2) or L1 <= 0 or L2 <= 0:
            continue

        v1 = np.array([float(row["pc1_vec_x"]), float(row["pc1_vec_y"])], dtype=float)
        v2 = np.array([float(row["pc2_vec_x"]), float(row["pc2_vec_y"])], dtype=float)

        n1 = np.linalg.norm(v1)
        n2 = np.linalg.norm(v2)

        if not np.isfinite(n1) or not np.isfinite(n2) or n1 <= 0 or n2 <= 0:
            continue

        v1 = v1 / n1
        v2 = v2 / n2

        km_per_deg_lon = 111.320 * np.cos(np.radians(lat0))
        km_per_deg_lat = 110.574

        dx_km = (Lon - lon0) * km_per_deg_lon
        dy_km = (Lat - lat0) * km_per_deg_lat

        x1 = dx_km * v1[0] + dy_km * v1[1]
        x2 = dx_km * v2[0] + dy_km * v2[1]

        inside = (
            (x1 / (L1 / 2.0)) ** 2 +
            (x2 / (L2 / 2.0)) ** 2
        ) <= 1.0

        freq[inside] += 1.0

    freq_plot = freq
    positive = freq.flatten()
    positive = positive[np.isfinite(positive)]

    quantile_levels = np.concatenate((
        [0],
        np.percentile(
            positive,
            [20, 40, 60, 80, 90, 95, 98, 100]
        )
    ))
    
    quantile_levels = np.unique(quantile_levels)
    
    norm = BoundaryNorm(
        boundaries=quantile_levels,
        ncolors=HEAT_CMAP.N,
        clip=True
    )

    if HAVE_CARTOPY:
        im = ax.pcolormesh(
        lon_grid,
        lat_grid,
        freq_plot,
        cmap=HEAT_CMAP,
        norm=norm,
        shading="auto",
        alpha=0.78,
        transform=ccrs.PlateCarree(),
        zorder=3
    )
    else:
        im = ax.pcolormesh(
        lon_grid,
        lat_grid,
        freq_plot,
        cmap=HEAT_CMAP,
        norm=norm,
        shading="auto",
        alpha=0.78,
        transform=ccrs.PlateCarree(),
        zorder=3
    )

    add_google_style_labels(ax)
    panel_label(ax, "(b)")

    return im, quantile_levels



# =============================================================================
# FIGURES
# =============================================================================

def make_figure_ab(df):
    if HAVE_CARTOPY:
        fig, axes = plt.subplots(
            1,
            2,
            figsize=(FIG_AB_W, FIG_AB_H),
            subplot_kw={"projection": ccrs.PlateCarree()}
        )
    else:
        fig, axes = plt.subplots(
            1,
            2,
            figsize=(FIG_AB_W, FIG_AB_H)
        )

    ax_a, ax_b = axes

    setup_panel_ax(ax_a, df)
    setup_panel_ax(ax_b, df)

    plot_panel_a_axes(ax_a, df)
    im, quantile_levels = plot_panel_b_ellipse_frequency(ax_b, df, fig)

    plt.tight_layout(rect=[0, 0.04, 0.93, 0.98])
    # ==========================================
    # PERFECT COLORBAR TO THE RIGHT OF MAP (b)
    # Same vertical height as panel (b), not inside map
    # ==========================================
    
    pos = ax_b.get_position()
    
    cax = fig.add_axes([
        pos.x1 + 0.010,   # gap between map and colorbar
        pos.y0,           # exact same bottom as map
        0.018,            # colorbar width
        pos.height        # exact same height as map
    ])
    
    cbar = fig.colorbar(
        im,
        cax=cax,
        orientation="vertical",
        ticks=quantile_levels
    )
    
    cbar.set_label("Event Frequency", fontsize=9)
    cbar.ax.tick_params(labelsize=8, length=2.5, width=0.6)
    cbar.outline.set_linewidth(0.6)

    plt.savefig(OUT_AB_PNG, dpi=300, bbox_inches="tight")
    plt.savefig(OUT_AB_PDF, dpi=300, bbox_inches="tight")
    plt.close(fig)

    print("[SAVED]", OUT_AB_PNG)
    print("[SAVED]", OUT_AB_PDF)


def make_figure_abc(df):
    if HAVE_CARTOPY:
        fig, axes = plt.subplots(
            1,
            3,
            figsize=(FIG_ABC_W, FIG_ABC_H),
            subplot_kw={"projection": ccrs.PlateCarree()}
        )
    else:
        fig, axes = plt.subplots(
            1,
            3,
            figsize=(FIG_ABC_W, FIG_ABC_H)
        )

    ax_a, ax_b, ax_c = axes

    for ax in axes:
        setup_panel_ax(ax, df)

    ratio_norm = robust_norm(
        df["L2_L1_ratio"].values,
        use_clip=USE_RATIO_PERCENTILE_CLIP
    )

    sc_a = plot_scatter(
        ax_a,
        df["centroid_lon"].values,
        df["centroid_lat"].values,
        c=df["L2_L1_ratio"].values,
        s=POINT_SIZE + 12,
        alpha=0.72,
        zorder=8
    )

    sc_a.set_cmap(RATIO_CMAP)
    sc_a.set_norm(ratio_norm)



    panel_label(ax_a, "(a)")

    area_norm = robust_norm(
        df["ellipse_area_km2"].values,
        use_clip=USE_AREA_PERCENTILE_CLIP
    )

    sc_b = plot_scatter(
        ax_b,
        df["centroid_lon"].values,
        df["centroid_lat"].values,
        c=df["ellipse_area_km2"].values,
        s=POINT_SIZE + 12,
        alpha=0.72,
        zorder=8
    )

    sc_b.set_cmap(AREA_CMAP)
    sc_b.set_norm(area_norm)



    panel_label(ax_b, "(b)")

    sc_c = plot_scatter(
        ax_c,
        df["centroid_lon"].values,
        df["centroid_lat"].values,
        c=df["orientation_deg"].values,
        s=POINT_SIZE + 12,
        alpha=0.75,
        zorder=8
    )

    sc_c.set_cmap(ORIENT_CMAP)
    sc_c.set_clim(-90, 90)



    panel_label(ax_c, "(c)")

    plt.tight_layout(rect=[0, 0.02, 0.84, 0.98])
    # =========================================================
    # PERFECT EXTERNAL COLORBARS FOR ABC PANELS
    # =========================================================
    
    # -------------------------
    # (a) L2/L1 ratio
    # -------------------------
    pos_a = ax_a.get_position()
    
    cax_a = fig.add_axes([
        pos_a.x1 + 0.020,
        pos_a.y0,
        0.012,
        pos_a.height
    ])
    
    cbar_a = fig.colorbar(
        sc_a,
        cax=cax_a,
        orientation="vertical"
    )
    
    cbar_a.set_label("L2 / L1", fontsize=9)
    cbar_a.ax.tick_params(labelsize=8)
    cbar_a.outline.set_linewidth(0.6)
    
    
    # -------------------------
    # (b) Ellipse area
    # -------------------------
    pos_b = ax_b.get_position()
    
    cax_b = fig.add_axes([
        pos_b.x1 + 0.020,
        pos_b.y0,
        0.012,
        pos_b.height
    ])
    
    cbar_b = fig.colorbar(
        sc_b,
        cax=cax_b,
        orientation="vertical"
    )
    
    cbar_b.set_label("Area (km²)", fontsize=9)
    cbar_b.ax.tick_params(labelsize=8)
    cbar_b.outline.set_linewidth(0.6)
    
    
    # -------------------------
    # (c) Orientation
    # -------------------------
    pos_c = ax_c.get_position()
    
    cax_c = fig.add_axes([
        pos_c.x1 + 0.020,
        pos_c.y0,
        0.012,
        pos_c.height
    ])
    
    cbar_c = fig.colorbar(
        sc_c,
        cax=cax_c,
        orientation="vertical"
    )
    
    cbar_c.set_label("L1 orientation (°)", fontsize=9)
    cbar_c.ax.tick_params(labelsize=8)
    cbar_c.outline.set_linewidth(0.6)

    plt.savefig(OUT_ABC_PNG, dpi=300, bbox_inches="tight")
    plt.savefig(OUT_ABC_PDF, dpi=300, bbox_inches="tight")
    plt.close(fig)

    print("[SAVED]", OUT_ABC_PNG)
    print("[SAVED]", OUT_ABC_PDF)


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 100)
    print("Loading PCA metrics...")
    print(METRICS_CSV)

    df = load_and_prepare_data()

    print("Loaded rows inside fixed domain:", len(df))
    print("Fixed domain: 20–70°E, 10–46°N")
    print("Cartopy available:", HAVE_CARTOPY)
    print("Output directory:", OUT_DIR)

    make_figure_ab(df)
    make_figure_abc(df)
    make_individual_panels(df)
def save_single_panel_with_colorbar(fig, ax, mappable, out_png, out_pdf, label):
    plt.tight_layout(rect=[0, 0.02, 0.88, 0.98])

    pos = ax.get_position()

    cax = fig.add_axes([
        pos.x1 + 0.025,
        pos.y0,
        0.020,
        pos.height
    ])

    cbar = fig.colorbar(
        mappable,
        cax=cax,
        orientation="vertical"
    )

    cbar.set_label(label, fontsize=10)
    cbar.ax.tick_params(labelsize=9, length=2.5, width=0.6)
    cbar.outline.set_linewidth(0.6)

    plt.savefig(out_png, dpi=600, bbox_inches="tight")
    plt.savefig(out_pdf, dpi=600, bbox_inches="tight")
    plt.close(fig)
def make_individual_panels(df):
    outputs = {
        "A_axes": (
            os.path.join(OUT_DIR, "Panel_A_PCA_axes_centroids.png"),
            os.path.join(OUT_DIR, "Panel_A_PCA_axes_centroids.pdf")
        ),
        "B_frequency": (
            os.path.join(OUT_DIR, "Panel_B_ellipse_frequency.png"),
            os.path.join(OUT_DIR, "Panel_B_ellipse_frequency.pdf")
        ),
        "C_ratio": (
            os.path.join(OUT_DIR, "Panel_C_L2_L1_ratio.png"),
            os.path.join(OUT_DIR, "Panel_C_L2_L1_ratio.pdf")
        ),
        "D_area": (
            os.path.join(OUT_DIR, "Panel_D_ellipse_area.png"),
            os.path.join(OUT_DIR, "Panel_D_ellipse_area.pdf")
        ),
        "E_orientation": (
            os.path.join(OUT_DIR, "Panel_E_L1_orientation.png"),
            os.path.join(OUT_DIR, "Panel_E_L1_orientation.pdf")
        ),
    }

    # -------------------------
    # Panel A: PCA axes + centroids
    # -------------------------
    if HAVE_CARTOPY:
        fig, ax = plt.subplots(
            1, 1, figsize=(7.2, 5.6),
            subplot_kw={"projection": ccrs.PlateCarree()}
        )
    else:
        fig, ax = plt.subplots(1, 1, figsize=(7.2, 5.6))

    setup_panel_ax(ax, df)
    plot_panel_a_axes(ax, df)
    plt.tight_layout(rect=[0, 0.04, 1, 0.98])
    plt.savefig(outputs["A_axes"][0], dpi=600, bbox_inches="tight")
    plt.savefig(outputs["A_axes"][1], dpi=600, bbox_inches="tight")
    plt.close(fig)

    # -------------------------
    # Panel B: ellipse-frequency heatmap
    # -------------------------
    if HAVE_CARTOPY:
        fig, ax = plt.subplots(
            1, 1, figsize=(7.2, 5.6),
            subplot_kw={"projection": ccrs.PlateCarree()}
        )
    else:
        fig, ax = plt.subplots(1, 1, figsize=(7.2, 5.6))

    setup_panel_ax(ax, df)
    im, quantile_levels = plot_panel_b_ellipse_frequency(ax, df, fig)
    save_single_panel_with_colorbar(
        fig, ax, im,
        outputs["B_frequency"][0],
        outputs["B_frequency"][1],
        "Event frequency"
    )

    # -------------------------
    # Panel C: L2/L1 ratio
    # -------------------------
    if HAVE_CARTOPY:
        fig, ax = plt.subplots(
            1, 1, figsize=(7.2, 5.6),
            subplot_kw={"projection": ccrs.PlateCarree()}
        )
    else:
        fig, ax = plt.subplots(1, 1, figsize=(7.2, 5.6))

    setup_panel_ax(ax, df)

    ratio_norm = robust_norm(
        df["L2_L1_ratio"].values,
        use_clip=USE_RATIO_PERCENTILE_CLIP
    )

    sc = plot_scatter(
        ax,
        df["centroid_lon"].values,
        df["centroid_lat"].values,
        c=df["L2_L1_ratio"].values,
        s=POINT_SIZE + 12,
        alpha=0.72,
        zorder=8
    )

    sc.set_cmap(RATIO_CMAP)
    sc.set_norm(ratio_norm)

    save_single_panel_with_colorbar(
        fig, ax, sc,
        outputs["C_ratio"][0],
        outputs["C_ratio"][1],
        "L2 / L1"
    )

    # -------------------------
    # Panel D: ellipse area
    # -------------------------
    if HAVE_CARTOPY:
        fig, ax = plt.subplots(
            1, 1, figsize=(7.2, 5.6),
            subplot_kw={"projection": ccrs.PlateCarree()}
        )
    else:
        fig, ax = plt.subplots(1, 1, figsize=(7.2, 5.6))

    setup_panel_ax(ax, df)

    area_norm = robust_norm(
        df["ellipse_area_km2"].values,
        use_clip=USE_AREA_PERCENTILE_CLIP
    )

    sc = plot_scatter(
        ax,
        df["centroid_lon"].values,
        df["centroid_lat"].values,
        c=df["ellipse_area_km2"].values,
        s=POINT_SIZE + 12,
        alpha=0.72,
        zorder=8
    )

    sc.set_cmap(AREA_CMAP)
    sc.set_norm(area_norm)

    save_single_panel_with_colorbar(
        fig, ax, sc,
        outputs["D_area"][0],
        outputs["D_area"][1],
        "Area (km²)"
    )

    # -------------------------
    # Panel E: orientation
    # -------------------------
    if HAVE_CARTOPY:
        fig, ax = plt.subplots(
            1, 1, figsize=(7.2, 5.6),
            subplot_kw={"projection": ccrs.PlateCarree()}
        )
    else:
        fig, ax = plt.subplots(1, 1, figsize=(7.2, 5.6))

    setup_panel_ax(ax, df)

    sc = plot_scatter(
        ax,
        df["centroid_lon"].values,
        df["centroid_lat"].values,
        c=df["orientation_deg"].values,
        s=POINT_SIZE + 12,
        alpha=0.75,
        zorder=8
    )

    sc.set_cmap(ORIENT_CMAP)
    sc.set_clim(-90, 90)

    save_single_panel_with_colorbar(
        fig, ax, sc,
        outputs["E_orientation"][0],
        outputs["E_orientation"][1],
        "L1 orientation (°)"
    )

    print("[SAVED] Individual high-quality panel PNG/PDF files")
    print("=" * 100)
    print("DONE.")


if __name__ == "__main__":
    main()