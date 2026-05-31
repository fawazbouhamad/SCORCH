
import os
import math
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

warnings.filterwarnings("ignore", category=RuntimeWarning)

# =============================================================================
# PATHS
# =============================================================================
OUT_DIR = r"ENTER_OUTPUT_DIRECTORY"

METRICS_CSV = os.path.join(
    OUT_DIR,
    "SHWE_spatial_PCA_metrics_blobfirst_clean_p60_merge_revert.csv"
)

OUT_FIG_PNG = os.path.join(
    OUT_DIR,
    "figure5_type_AGU_hist_boxplot_orientation_area_ratio.png"
)

OUT_FIG_PDF = os.path.join(
    OUT_DIR,
    "figure5_type_AGU_hist_boxplot_orientation_area_ratio.pdf"
)

OUT_SUMMARY_CSV = os.path.join(
    OUT_DIR,
    "figure5_type_AGU_hist_boxplot_summary.csv"
)

OUT_DEEP_ANALYSIS_TXT = os.path.join(
    OUT_DIR,
    "figure5_deep_type_geometry_analysis.txt"
)

# =============================================================================
# TYPE SETTINGS
# =============================================================================
TYPE_ORDER = ["Type 1", "Type 2", "Type 3", "Type 4"]

TYPE_DISPLAY = {
    "Type 1": "Type 1",
    "Type 2": "Type 2",
    "Type 3": "Type 3",
    "Type 4": "Type 4",
}

TYPE_FULL_NAMES = {
    "Type 1": "Independent",
    "Type 2": "Spatially clustered",
    "Type 3": "Temporally clustered",
    "Type 4": "Mixed multi-type",
}

TYPE_COLORS = {
    "Type 1": "#d7191c",
    "Type 2": "#f57c00",
    "Type 3": "#d9a300",
    "Type 4": "#6a3d9a",
}

# =============================================================================
# FIGURE SETTINGS
# =============================================================================
FIG_W = 12.2
FIG_H = 9.8
DPI = 500

LABEL_FS = 9.5
TICK_FS = 7.5
TITLE_FS = 11
ANNOT_FS = 6.8

HIST_ALPHA = 0.90
EDGE_LW = 0.35

BOX_FACE = "#E6E6E6"
BOX_EDGE = "#404040"
MEDIAN_COLOR = "#8B1E1E"

ORIENTATION_BINS = np.arange(-90, 90 + 15, 15)
RATIO_BINS = np.arange(0.0, 1.0001, 0.05)
AREA_BIN_COUNT = 12

USE_AREA_PERCENTILE_CLIP_FOR_PLOT = False
AREA_CLIP_LOW = 1
AREA_CLIP_HIGH = 99

# =============================================================================
# EVENT CATALOGUE
# =============================================================================
def build_event_type_catalogue():
    events = [
        (12, "Independent", "2002-07-31", "2002-07-31"),
        (26, "Independent", "2016-07-17", "2016-07-17"),
        (27, "Independent", "2016-08-03", "2016-08-03"),
        (41, "Independent", "2021-08-28", "2021-08-28"),

        (1, "Independent Simultaneous", "1983-07-13", "1983-07-13"),
        (23, "Independent Simultaneous", "2015-07-16", "2015-07-16"),
        (43, "Independent Simultaneous", "2023-07-12", "2023-07-12"),

        (2, "Back-to-Back", "1987-07-23", "1987-07-27"),
        (6, "Back-to-Back", "1999-08-18", "1999-08-22"),
        (7, "Back-to-Back", "2000-07-07", "2000-07-09"),
        (8, "Back-to-Back", "2000-07-28", "2000-08-02"),
        (9, "Back-to-Back", "2001-07-28", "2001-07-30"),
        (10, "Back-to-Back", "2001-08-07", "2001-08-12"),
        (14, "Back-to-Back", "2006-08-20", "2006-08-23"),
        (15, "Back-to-Back", "2007-07-25", "2007-08-01"),
        (17, "Back-to-Back", "2010-07-08", "2010-07-13"),
        (18, "Back-to-Back", "2010-07-16", "2010-07-18"),
        (19, "Back-to-Back", "2010-08-01", "2010-08-03"),
        (20, "Back-to-Back", "2010-08-05", "2010-08-21"),
        (21, "Back-to-Back", "2011-07-26", "2011-08-05"),
        (25, "Back-to-Back", "2016-06-07", "2016-06-08"),
        (29, "Back-to-Back", "2017-07-17", "2017-07-18"),
        (31, "Back-to-Back", "2017-08-01", "2017-08-13"),
        (32, "Back-to-Back", "2018-07-09", "2018-07-15"),
        (33, "Back-to-Back", "2019-06-26", "2019-06-27"),
        (34, "Back-to-Back", "2019-07-18", "2019-07-20"),
        (35, "Back-to-Back", "2020-07-19", "2020-07-21"),
        (36, "Back-to-Back", "2020-07-29", "2020-07-31"),
        (38, "Back-to-Back", "2021-07-18", "2021-07-21"),
        (42, "Back-to-Back", "2022-07-19", "2022-07-23"),
        (45, "Back-to-Back", "2023-08-13", "2023-08-28"),
        (49, "Back-to-Back", "2025-06-14", "2025-06-15"),
        (51, "Back-to-Back", "2025-08-07", "2025-08-15"),

        (3, "Back-to-Back Simultaneous", "1991-06-04", "1991-06-05"),
        (4, "Back-to-Back Simultaneous", "1998-05-24", "1998-05-26"),
        (13, "Back-to-Back Simultaneous", "2002-08-06", "2002-08-07"),

        (5, "Mixed Multi-Day", "1998-08-01", "1998-08-11"),
        (11, "Mixed Multi-Day", "2002-07-16", "2002-07-20"),
        (16, "Mixed Multi-Day", "2010-06-18", "2010-06-22"),
        (22, "Mixed Multi-Day", "2012-07-13", "2012-07-29"),
        (24, "Mixed Multi-Day", "2015-07-28", "2015-08-20"),
        (28, "Mixed Multi-Day", "2017-06-30", "2017-07-06"),
        (30, "Mixed Multi-Day", "2017-07-22", "2017-07-30"),
        (37, "Mixed Multi-Day", "2021-06-28", "2021-07-08"),
        (39, "Mixed Multi-Day", "2021-07-26", "2021-07-28"),
        (40, "Mixed Multi-Day", "2021-07-31", "2021-08-09"),
        (44, "Mixed Multi-Day", "2023-07-15", "2023-08-11"),
        (46, "Mixed Multi-Day", "2024-05-20", "2024-06-28"),
        (47, "Mixed Multi-Day", "2024-07-08", "2024-07-29"),
        (48, "Mixed Multi-Day", "2024-08-05", "2024-08-23"),
        (50, "Mixed Multi-Day", "2025-07-14", "2025-08-01"),
    ]

    cat = pd.DataFrame(
        events,
        columns=["event_id", "event_type_original", "start_date", "end_date"]
    )

    cat["start_date"] = pd.to_datetime(cat["start_date"])
    cat["end_date"] = pd.to_datetime(cat["end_date"])

    type_map = {
        "Independent": "Type 1",
        "Independent Simultaneous": "Type 2",
        "Back-to-Back": "Type 3",
        "Back-to-Back Simultaneous": "Type 3",
        "Mixed Multi-Day": "Type 4",
    }

    cat["type"] = cat["event_type_original"].map(type_map)

    return cat


def assign_type_from_catalogue(date, cat):
    matches = cat[
        (cat["start_date"] <= date) &
        (cat["end_date"] >= date)
    ]

    if len(matches) == 0:
        return np.nan, np.nan, np.nan

    row = matches.iloc[0]

    return row["event_id"], row["event_type_original"], row["type"]

# =============================================================================
# HELPER FUNCTIONS
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


def summarise(values):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]

    if len(values) == 0:
        return {
            "n": 0,
            "mean": np.nan,
            "std": np.nan,
            "min": np.nan,
            "q1": np.nan,
            "median": np.nan,
            "q3": np.nan,
            "max": np.nan,
        }

    return {
        "n": len(values),
        "mean": np.mean(values),
        "std": np.std(values, ddof=1) if len(values) > 1 else np.nan,
        "min": np.min(values),
        "q1": np.percentile(values, 25),
        "median": np.median(values),
        "q3": np.percentile(values, 75),
        "max": np.max(values),
    }


def prepare_dataframe(metrics_csv):
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
        raise ValueError("Missing required columns in metrics CSV: " + ", ".join(missing))

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

    cat = build_event_type_catalogue()

    assigned = df["date"].apply(lambda d: assign_type_from_catalogue(d, cat))

    df["event_id"] = assigned.apply(lambda x: x[0])
    df["event_type_original"] = assigned.apply(lambda x: x[1])
    df["type"] = assigned.apply(lambda x: x[2])

    unmatched = df["type"].isna().sum()
    if unmatched > 0:
        print(f"[WARNING] {unmatched} ellipse rows did not match any catalogue event date and were removed.")

    df = df[df["type"].isin(TYPE_ORDER)].copy()

    df["orientation_deg"] = df.apply(
        lambda r: orientation_from_north_deg(r["pc1_vec_x"], r["pc1_vec_y"]),
        axis=1
    )

    df["ellipse_area_km2"] = (
        np.pi * (df["axis1_len_km"] / 2.0) * (df["axis2_len_km"] / 2.0)
    )

    df["ellipse_area_million_km2"] = df["ellipse_area_km2"] / 1e6
    df["ratio_L2_L1"] = df["axis2_len_km"] / df["axis1_len_km"]

    df = df[
        np.isfinite(df["orientation_deg"]) &
        np.isfinite(df["ellipse_area_million_km2"]) &
        np.isfinite(df["ratio_L2_L1"])
    ].copy()

    return df


def nice_spines(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_linewidth(0.6)
    ax.spines["bottom"].set_linewidth(0.6)


def draw_hist_box(ax_hist, ax_box, values, bins, color, xlim=None):
    vals = np.asarray(values, dtype=float)
    vals = vals[np.isfinite(vals)]

    if len(vals) == 0:
        ax_hist.text(
            0.5, 0.5, "No data",
            transform=ax_hist.transAxes,
            ha="center",
            va="center",
            fontsize=8,
        )
        ax_box.axis("off")
        return

    ax_hist.hist(
        vals,
        bins=bins,
        color=color,
        alpha=HIST_ALPHA,
        edgecolor="black",
        linewidth=EDGE_LW,
    )

    ax_hist.grid(axis="y", alpha=0.22, linewidth=0.45)
    ax_hist.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax_hist.tick_params(axis="both", labelsize=TICK_FS, length=2.5)
    nice_spines(ax_hist)

    s = summarise(vals)
    txt = f"n={s['n']}\nMed={s['median']:.2f}"

    ax_hist.text(
        0.96,
        0.92,
        txt,
        transform=ax_hist.transAxes,
        ha="right",
        va="top",
        fontsize=ANNOT_FS,
        bbox=dict(
            boxstyle="round,pad=0.20",
            facecolor="white",
            edgecolor="0.75",
            alpha=0.95,
        ),
    )

    ax_box.boxplot(
        vals,
        vert=False,
        widths=0.55,
        patch_artist=True,
        boxprops=dict(facecolor=BOX_FACE, edgecolor=BOX_EDGE, linewidth=0.75),
        medianprops=dict(color=MEDIAN_COLOR, linewidth=1.25),
        whiskerprops=dict(color=BOX_EDGE, linewidth=0.75),
        capprops=dict(color=BOX_EDGE, linewidth=0.75),
        flierprops=dict(
            marker="o",
            markerfacecolor="white",
            markeredgecolor=BOX_EDGE,
            markersize=2.2,
            alpha=0.85,
        ),
    )

    ax_box.set_yticks([])
    ax_box.grid(axis="x", alpha=0.18, linewidth=0.45)
    ax_box.tick_params(axis="x", labelsize=TICK_FS, length=2.5)
    nice_spines(ax_box)

    if xlim is not None:
        ax_hist.set_xlim(*xlim)
        ax_box.set_xlim(*xlim)

    plt.setp(ax_hist.get_xticklabels(), visible=False)


def make_summary_csv(df, out_csv):
    rows = []

    metrics = {
        "orientation_deg": "Orientation (degrees)",
        "ellipse_area_million_km2": "Area (10^6 km2)",
        "ratio_L2_L1": "Ratio (L2/L1)",
    }

    for typ in TYPE_ORDER:
        sub = df[df["type"] == typ].copy()

        for col, label in metrics.items():
            s = summarise(sub[col].values)

            rows.append({
                "type": typ,
                "type_name": TYPE_FULL_NAMES[typ],
                "metric": label,
                "n": s["n"],
                "mean": s["mean"],
                "std": s["std"],
                "min": s["min"],
                "q1": s["q1"],
                "median": s["median"],
                "q3": s["q3"],
                "max": s["max"],
            })

    pd.DataFrame(rows).to_csv(out_csv, index=False)


def print_type_summary(df):
    print("\n" + "=" * 120)
    print("TYPE-BASED GEOMETRIC SUMMARY OF MAJOR COMPOUND HEATWAVE ELLIPSES")
    print("=" * 120)

    for typ in TYPE_ORDER:
        sub = df[df["type"] == typ].copy()

        if len(sub) == 0:
            print(f"\n{typ} | No data")
            continue

        o = sub["orientation_deg"].dropna()
        a = sub["ellipse_area_million_km2"].dropna()
        r = sub["ratio_L2_L1"].dropna()

        print("\n" + "-" * 120)
        print(f"{typ} | {TYPE_FULL_NAMES[typ]}")
        print("-" * 120)

        print(f"Total fitted ellipses : {len(sub)}")
        print(f"Unique event dates    : {sub['date'].nunique()}")
        print(f"Unique catalogue IDs  : {sub['event_id'].nunique()}")

        print("\nOrientation (°)")
        print(f"Mean   = {o.mean():8.2f}")
        print(f"Median = {o.median():8.2f}")
        print(f"Std    = {o.std():8.2f}")
        print(f"IQR    = ({o.quantile(0.25):.2f}, {o.quantile(0.75):.2f})")
        print(f"Range  = ({o.min():.2f}, {o.max():.2f})")

        print("\nArea (10^6 km²)")
        print(f"Mean   = {a.mean():8.2f}")
        print(f"Median = {a.median():8.2f}")
        print(f"Std    = {a.std():8.2f}")
        print(f"IQR    = ({a.quantile(0.25):.2f}, {a.quantile(0.75):.2f})")
        print(f"Range  = ({a.min():.2f}, {a.max():.2f})")

        print("\nRatio (L2/L1)")
        print(f"Mean   = {r.mean():8.2f}")
        print(f"Median = {r.median():8.2f}")
        print(f"Std    = {r.std():8.2f}")
        print(f"IQR    = ({r.quantile(0.25):.2f}, {r.quantile(0.75):.2f})")
        print(f"Range  = ({r.min():.2f}, {r.max():.2f})")

    print("\n" + "=" * 120)
    print("END OF TYPE SUMMARY")
    print("=" * 120)


def write_deep_type_analysis_txt(df, out_txt):
    lines = []

    lines.append("DEEP TYPE-BASED ANALYSIS OF PCA-DERIVED HEATWAVE ELLIPSE GEOMETRY")
    lines.append("=" * 100)
    lines.append("")
    lines.append("This file summarizes the geometry of major compound heatwave ellipse structures by event type.")
    lines.append("Metrics include orientation, spatial area, and shape ratio (L2/L1).")
    lines.append("Area is reported in 10^6 km².")
    lines.append("Lower L2/L1 values indicate more elongated structures; values closer to 1 indicate more compact structures.")
    lines.append("Orientation is measured relative to geographic north, where 0° indicates north–south alignment.")
    lines.append("Positive values indicate clockwise tilt from north; negative values indicate counter-clockwise tilt from north.")
    lines.append("")
    lines.append("Important interpretation note:")
    lines.append("Each row represents one fitted ellipse object. Therefore, the counts below refer to fitted ellipses, not necessarily unique catalogue events.")
    lines.append("Multiple ellipses may occur on the same date when spatially separated heatwave structures are detected.")
    lines.append("")

    for typ in TYPE_ORDER:
        sub = df[df["type"] == typ].copy()

        if len(sub) == 0:
            continue

        o = sub["orientation_deg"].dropna()
        a = sub["ellipse_area_million_km2"].dropna()
        r = sub["ratio_L2_L1"].dropna()

        med_o = o.median()
        med_a = a.median()
        med_r = r.median()

        if abs(med_o) <= 15:
            orientation_note = "The median orientation is close to 0°, suggesting a dominant north–south geometric alignment."
        elif med_o > 15:
            orientation_note = "The positive median orientation indicates a clockwise tilt from geographic north."
        else:
            orientation_note = "The negative median orientation indicates a counter-clockwise tilt from geographic north."

        if med_a < 0.30:
            area_note = "The median area indicates relatively small heatwave footprints."
        elif med_a < 0.70:
            area_note = "The median area indicates moderate heatwave footprints."
        else:
            area_note = "The median area indicates large regional-scale heatwave footprints."

        if med_r < 0.35:
            ratio_note = "The median L2/L1 ratio indicates strongly elongated ellipse geometries."
        elif med_r < 0.60:
            ratio_note = "The median L2/L1 ratio indicates moderately elongated ellipse geometries."
        else:
            ratio_note = "The median L2/L1 ratio indicates relatively compact or rounded ellipse geometries."

        lines.append("-" * 100)
        lines.append(f"{typ} | {TYPE_FULL_NAMES[typ]}")
        lines.append("-" * 100)
        lines.append(f"Total fitted ellipses: {len(sub)}")
        lines.append(f"Unique heatwave dates: {sub['date'].nunique()}")
        lines.append(f"Unique catalogue IDs : {sub['event_id'].nunique()}")
        lines.append("")

        lines.append("Orientation summary:")
        lines.append(f"  Mean orientation   : {o.mean():.2f}°")
        lines.append(f"  Median orientation : {o.median():.2f}°")
        lines.append(f"  Standard deviation : {o.std():.2f}°")
        lines.append(f"  IQR                : {o.quantile(0.25):.2f}° to {o.quantile(0.75):.2f}°")
        lines.append(f"  Range              : {o.min():.2f}° to {o.max():.2f}°")
        lines.append("")

        lines.append("Area summary:")
        lines.append(f"  Mean area   : {a.mean():.3f} ×10^6 km²")
        lines.append(f"  Median area : {a.median():.3f} ×10^6 km²")
        lines.append(f"  Std area    : {a.std():.3f} ×10^6 km²")
        lines.append(f"  IQR         : {a.quantile(0.25):.3f} to {a.quantile(0.75):.3f} ×10^6 km²")
        lines.append(f"  Range       : {a.min():.3f} to {a.max():.3f} ×10^6 km²")
        lines.append("")

        lines.append("Shape ratio summary:")
        lines.append(f"  Mean L2/L1   : {r.mean():.3f}")
        lines.append(f"  Median L2/L1 : {r.median():.3f}")
        lines.append(f"  Std L2/L1    : {r.std():.3f}")
        lines.append(f"  IQR          : {r.quantile(0.25):.3f} to {r.quantile(0.75):.3f}")
        lines.append(f"  Range        : {r.min():.3f} to {r.max():.3f}")
        lines.append("")

        lines.append("Interpretation:")
        lines.append(f"  {orientation_note}")
        lines.append(f"  {area_note}")
        lines.append(f"  {ratio_note}")
        lines.append("")
        lines.append("")

    lines.append("=" * 100)
    lines.append("END OF DEEP TYPE ANALYSIS")
    lines.append("=" * 100)

    with open(out_txt, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

# =============================================================================
# MAIN
# =============================================================================
def main():
    plt.rcParams.update({
        "font.family": "serif",
        "font.size": 9,
        "axes.labelsize": LABEL_FS,
        "axes.titlesize": TITLE_FS,
        "xtick.labelsize": TICK_FS,
        "ytick.labelsize": TICK_FS,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })

    df = prepare_dataframe(METRICS_CSV)

    n_ellipses = len(df)
    n_dates = df["date"].nunique()
    n_events = df["event_id"].nunique()

    if USE_AREA_PERCENTILE_CLIP_FOR_PLOT:
        lo = np.percentile(df["ellipse_area_million_km2"], AREA_CLIP_LOW)
        hi = np.percentile(df["ellipse_area_million_km2"], AREA_CLIP_HIGH)
        df_plot = df[
            (df["ellipse_area_million_km2"] >= lo) &
            (df["ellipse_area_million_km2"] <= hi)
        ].copy()
    else:
        df_plot = df.copy()

    area_min = np.nanmin(df_plot["ellipse_area_million_km2"])
    area_max = np.nanmax(df_plot["ellipse_area_million_km2"])

    if area_min == area_max:
        area_bins = np.linspace(area_min - 0.1, area_max + 0.1, AREA_BIN_COUNT + 1)
    else:
        area_bins = np.linspace(area_min, area_max, AREA_BIN_COUNT + 1)

    fig = plt.figure(figsize=(FIG_W, FIG_H), dpi=300)

    outer = fig.add_gridspec(
        3, 4,
        hspace=0.46,
        wspace=0.28,
        left=0.075,
        right=0.995,
        bottom=0.075,
        top=0.965
    )

    row_info = [
        {
            "metric": "orientation_deg",
            "xlabel": "Orientation (°)",
            "bins": ORIENTATION_BINS,
            "xlim": (-90, 90),
        },
        {
            "metric": "ellipse_area_million_km2",
            "xlabel": "Area (km² × 10⁶)",
            "bins": area_bins,
            "xlim": None,
        },
        {
            "metric": "ratio_L2_L1",
            "xlabel": "Ratio (L2/L1)",
            "bins": RATIO_BINS,
            "xlim": (0, 1),
        },
    ]

    for r, info in enumerate(row_info):
        for c, typ in enumerate(TYPE_ORDER):
            subgs = outer[r, c].subgridspec(
                2, 1,
                height_ratios=[4.1, 1.0],
                hspace=0.03
            )

            ax_hist = fig.add_subplot(subgs[0, 0])
            ax_box = fig.add_subplot(subgs[1, 0], sharex=ax_hist)

            sub = df_plot[df_plot["type"] == typ]
            values = sub[info["metric"]].values

            draw_hist_box(
                ax_hist=ax_hist,
                ax_box=ax_box,
                values=values,
                bins=info["bins"],
                color=TYPE_COLORS[typ],
                xlim=info["xlim"],
            )
            ax_box.set_xlabel(
            info["xlabel"],
            fontsize=LABEL_FS,
            labelpad=4
        )

            if r == 0:
                ax_hist.set_title(
                    TYPE_DISPLAY[typ],
                    fontsize=TITLE_FS,
                    fontweight="bold",
                    pad=7,
                    color=TYPE_COLORS[typ],
                )

            if c == 0:
                ax_hist.set_ylabel("Number of ellipses", fontsize=LABEL_FS)
            else:
                ax_hist.set_ylabel("")
            
            # Keep y-axis tick numbers visible for every panel
            ax_hist.tick_params(axis="y", labelleft=True)

    fig.text(
        0.025, 0.870, "(a)",
        rotation=90,
        ha="center",
        va="center",
        fontsize=14,
        fontweight="bold",
    )

    fig.text(
        0.025, 0.550, "(b)",
        rotation=90,
        ha="center",
        va="center",
        fontsize=14,
        fontweight="bold",
    )

    fig.text(
        0.025, 0.210, "(c)",
        rotation=90,
        ha="center",
        va="center",
        fontsize=14,
        fontweight="bold",
    )

    fig.savefig(OUT_FIG_PNG, dpi=DPI, bbox_inches="tight")
    fig.savefig(OUT_FIG_PDF, dpi=DPI, bbox_inches="tight")
    plt.close(fig)

    make_summary_csv(df, OUT_SUMMARY_CSV)
    write_deep_type_analysis_txt(df, OUT_DEEP_ANALYSIS_TXT)
    print_type_summary(df)

    print("\n" + "=" * 100)
    print("Type-based AGU/Q1 histogram + boxplot figure complete")
    print("Loaded fitted ellipses:", n_ellipses)
    print("Unique heatwave dates:", n_dates)
    print("Unique catalogue events:", n_events)
    print("[SAVED PNG]", OUT_FIG_PNG)
    print("[SAVED PDF]", OUT_FIG_PDF)
    print("[SAVED SUMMARY CSV]", OUT_SUMMARY_CSV)
    print("[SAVED DEEP ANALYSIS TXT]", OUT_DEEP_ANALYSIS_TXT)
    print("=" * 100)


if __name__ == "__main__":
    main()