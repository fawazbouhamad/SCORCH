#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Q1 / Elsevier-style CDF plots for SHWE event-average geometry.

Creates 2 separate CDF figures:
1) Event-mean area
2) Event-mean L2/L1 ratio

Each catalogue event contributes ONE value only.
"""

import os
import math
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore", category=RuntimeWarning)

# =============================================================================
# PATHS
# =============================================================================
OUT_DIR = r"C:\Users\fawaw\OneDrive - University of Florida\Coding\Outputs\najibi_hw_blobfirst_clean_merge_revert"

METRICS_CSV = os.path.join(
    OUT_DIR,
    "SHWE_spatial_PCA_metrics_blobfirst_clean_p60_merge_revert.csv"
)

OUT_EVENT_AVG_CSV = os.path.join(
    OUT_DIR,
    "figure_CDF_event_average_geometry_values.csv"
)

OUT_SUMMARY_CSV = os.path.join(
    OUT_DIR,
    "figure_CDF_event_average_summary.csv"
)

OUT_AREA_PNG = os.path.join(OUT_DIR, "figure_CDF_event_mean_area_by_type.png")
OUT_AREA_PDF = os.path.join(OUT_DIR, "figure_CDF_event_mean_area_by_type.pdf")

OUT_RATIO_PNG = os.path.join(OUT_DIR, "figure_CDF_event_mean_ratio_by_type.png")
OUT_RATIO_PDF = os.path.join(OUT_DIR, "figure_CDF_event_mean_ratio_by_type.pdf")

# =============================================================================
# TYPE SETTINGS
# =============================================================================
TYPE_ORDER = ["Type 1", "Type 2", "Type 3", "Type 4"]

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
FIG_W = 6.7
FIG_H = 4.8
DPI = 500

LABEL_FS = 10.5
TICK_FS = 8.5
LEGEND_FS = 8.7
TITLE_FS = 11.5

LINE_WIDTH = 2.15

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
# HELPERS
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


def nice_spines(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_linewidth(0.7)
    ax.spines["bottom"].set_linewidth(0.7)


def summarise(values):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]

    if len(values) == 0:
        return dict(
            n=0, mean=np.nan, std=np.nan, min=np.nan,
            q1=np.nan, median=np.nan, q3=np.nan, max=np.nan
        )

    return dict(
        n=len(values),
        mean=np.mean(values),
        std=np.std(values, ddof=1) if len(values) > 1 else np.nan,
        min=np.min(values),
        q1=np.percentile(values, 25),
        median=np.median(values),
        q3=np.percentile(values, 75),
        max=np.max(values),
    )


def prepare_ellipse_dataframe(metrics_csv):
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
        raise ValueError("Missing required columns: " + ", ".join(missing))

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
        print(f"[WARNING] {unmatched} ellipse rows did not match any catalogue event and were removed.")

    df = df[df["type"].isin(TYPE_ORDER)].copy()

    df["orientation_deg"] = df.apply(
        lambda r: orientation_from_north_deg(r["pc1_vec_x"], r["pc1_vec_y"]),
        axis=1
    )

    df["ellipse_area_km2"] = (
        np.pi * (df["axis1_len_km"] / 2.0) *
        (df["axis2_len_km"] / 2.0)
    )

    df["ellipse_area_million_km2"] = df["ellipse_area_km2"] / 1e6
    df["ratio_L2_L1"] = df["axis2_len_km"] / df["axis1_len_km"]

    df = df[
        np.isfinite(df["orientation_deg"]) &
        np.isfinite(df["ellipse_area_million_km2"]) &
        np.isfinite(df["ratio_L2_L1"])
    ].copy()

    return df


def convert_to_event_average_dataframe(df):
    event_df = (
        df.groupby(["event_id", "event_type_original", "type"], as_index=False)
        .agg(
            start_date=("date", "min"),
            end_date=("date", "max"),
            n_ellipse_rows=("date", "size"),
            n_active_dates=("date", "nunique"),
            orientation_deg=("orientation_deg", "mean"),
            ellipse_area_million_km2=("ellipse_area_million_km2", "mean"),
            ratio_L2_L1=("ratio_L2_L1", "mean"),
        )
    )

    event_df["event_id"] = event_df["event_id"].astype(int)
    return event_df


def smooth_empirical_cdf(values, x_min, x_max, n_grid=700):
    vals = np.asarray(values, dtype=float)
    vals = vals[np.isfinite(vals)]
    vals = np.sort(vals)

    if len(vals) == 0:
        return None, None

    y_emp = np.arange(1, len(vals) + 1) / len(vals)

    x_anchor = np.concatenate(([x_min], vals, [x_max]))
    y_anchor = np.concatenate(([0.0], y_emp, [1.0]))

    x_grid = np.linspace(x_min, x_max, n_grid)
    y_grid = np.interp(x_grid, x_anchor, y_anchor)

    return x_grid, y_grid


def get_dynamic_xlim(event_df, metric_col):
    vals = event_df[metric_col].replace([np.inf, -np.inf], np.nan).dropna().values

    xmin = np.nanmin(vals)
    xmax = np.nanmax(vals)

    if not np.isfinite(xmin) or not np.isfinite(xmax):
        raise ValueError(f"No finite values found for {metric_col}")

    if xmin == xmax:
        pad = 0.05 if xmin == 0 else abs(xmin) * 0.05
    else:
        pad = 0.035 * (xmax - xmin)

    return xmin - pad, xmax + pad


def make_cdf_figure(event_df, metric_col, xlabel, title, out_png, out_pdf):
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), dpi=300)

    x_min, x_max = get_dynamic_xlim(event_df, metric_col)

    for typ in TYPE_ORDER:
        sub = event_df[event_df["type"] == typ].copy()
        values = sub[metric_col].replace([np.inf, -np.inf], np.nan).dropna().values

        if len(values) == 0:
            continue

        x_curve, y_curve = smooth_empirical_cdf(values, x_min, x_max)

        ax.plot(
            x_curve,
            y_curve,
            color=TYPE_COLORS[typ],
            linewidth=LINE_WIDTH,
            label=typ,
            solid_capstyle="round",
            solid_joinstyle="round",
        )

    ax.set_xlabel(xlabel, fontsize=LABEL_FS)
    ax.set_ylabel("Cumulative probability", fontsize=LABEL_FS)
    ax.set_title(title, fontsize=TITLE_FS, fontweight="bold", pad=8)

    ax.set_xlim(x_min, x_max)
    ax.set_ylim(0, 1.02)

    ax.grid(True, alpha=0.22, linewidth=0.45)
    nice_spines(ax)

    ax.tick_params(axis="both", labelsize=TICK_FS, length=3)

    leg = ax.legend(
        frameon=True,
        fontsize=LEGEND_FS,
        loc="lower right",
        handlelength=2.6,
        borderpad=0.6,
        labelspacing=0.45,
    )

    leg.get_frame().set_edgecolor("0.75")
    leg.get_frame().set_linewidth(0.6)
    leg.get_frame().set_alpha(0.96)

    fig.tight_layout()
    fig.savefig(out_png, dpi=DPI, bbox_inches="tight")
    fig.savefig(out_pdf, dpi=DPI, bbox_inches="tight")
    plt.close(fig)


def make_summary_csv(event_df, out_csv):
    rows = []

    metrics = {
        "ellipse_area_million_km2": "Event-mean area (10^6 km2)",
        "ratio_L2_L1": "Event-mean ratio (L2/L1)",
    }

    for typ in TYPE_ORDER:
        sub = event_df[event_df["type"] == typ].copy()

        for col, label in metrics.items():
            s = summarise(sub[col].values)

            rows.append({
                "HW Type": typ,
                "Metric": label,
                "n_events": s["n"],
                "mean": s["mean"],
                "std": s["std"],
                "min": s["min"],
                "q1": s["q1"],
                "median": s["median"],
                "q3": s["q3"],
                "max": s["max"],
            })

    pd.DataFrame(rows).to_csv(out_csv, index=False)


def print_type_summary(event_df):
    print("\n" + "=" * 110)
    print("EVENT-AVERAGE CDF GEOMETRY SUMMARY")
    print("=" * 110)

    for typ in TYPE_ORDER:
        sub = event_df[event_df["type"] == typ].copy()

        print("\n" + "-" * 110)
        print(f"{typ} | {TYPE_FULL_NAMES[typ]} | n = {len(sub)}")
        print("-" * 110)

        for col, label in [
            ("ellipse_area_million_km2", "Area (10^6 km²)"),
            ("ratio_L2_L1", "Ratio (L2/L1)"),
        ]:
            vals = sub[col].dropna()

            print(f"\n{label}")
            print(f"Mean   = {vals.mean():8.3f}")
            print(f"Median = {vals.median():8.3f}")
            print(f"Std    = {vals.std():8.3f}")
            print(f"IQR    = ({vals.quantile(0.25):.3f}, {vals.quantile(0.75):.3f})")
            print(f"Range  = ({vals.min():.3f}, {vals.max():.3f})")

    print("\n" + "=" * 110)


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

    df_ellipse = prepare_ellipse_dataframe(METRICS_CSV)
    event_df = convert_to_event_average_dataframe(df_ellipse)

    event_df.to_csv(OUT_EVENT_AVG_CSV, index=False)
    make_summary_csv(event_df, OUT_SUMMARY_CSV)

    expected_counts = {
        "Type 1": 4,
        "Type 2": 3,
        "Type 3": 29,
        "Type 4": 15,
    }

    actual_counts = (
        event_df["type"]
        .value_counts()
        .reindex(TYPE_ORDER)
        .fillna(0)
        .astype(int)
    )

    print("\nEvent counts by type:")
    for typ in TYPE_ORDER:
        print(f"{typ}: {actual_counts[typ]} expected {expected_counts[typ]}")

    print(f"\nTotal events used: {len(event_df)} expected 51")

    if len(event_df) != 51:
        print("[WARNING] Total event count is not 51. Check unmatched dates or catalogue mapping.")

    for typ in TYPE_ORDER:
        if actual_counts[typ] != expected_counts[typ]:
            print(f"[WARNING] {typ} count mismatch.")

    make_cdf_figure(
        event_df=event_df,
        metric_col="ellipse_area_million_km2",
        xlabel="Area (km² × 10⁶)",
        title="CDF of Area",
        out_png=OUT_AREA_PNG,
        out_pdf=OUT_AREA_PDF,
    )

    make_cdf_figure(
        event_df=event_df,
        metric_col="ratio_L2_L1",
        xlabel="Ratio (L2/L1)",
        title="CDF of Ratio",
        out_png=OUT_RATIO_PNG,
        out_pdf=OUT_RATIO_PDF,
    )

    print_type_summary(event_df)

    print("\n" + "=" * 100)
    print("Q1 / Elsevier event-average CDF figures complete")
    print("[SAVED]", OUT_AREA_PNG)
    print("[SAVED]", OUT_AREA_PDF)
    print("[SAVED]", OUT_RATIO_PNG)
    print("[SAVED]", OUT_RATIO_PDF)
    print("[SAVED EVENT AVERAGE CSV]", OUT_EVENT_AVG_CSV)
    print("[SAVED SUMMARY CSV]", OUT_SUMMARY_CSV)
    print("=" * 100)


if __name__ == "__main__":
    main()