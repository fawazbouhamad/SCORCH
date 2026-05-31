
import os
import math
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.stats import gaussian_kde

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
    "figure_density_event_average_orientation_by_type_Q1_clean.png"
)

OUT_FIG_PDF = os.path.join(
    OUT_DIR,
    "figure_density_event_average_orientation_by_type_Q1_clean.pdf"
)

OUT_EVENT_AVERAGE_CSV = os.path.join(
    OUT_DIR,
    "figure_density_event_average_orientation_values.csv"
)

OUT_SUMMARY_CSV = os.path.join(
    OUT_DIR,
    "figure_density_event_average_orientation_summary.csv"
)

# =============================================================================
# TYPE SETTINGS
# =============================================================================
TYPE_ORDER = ["Type 1", "Type 2", "Type 3", "Type 4"]

TYPE_COLORS = {
    "Type 1": "#d7191c",
    "Type 2": "#f57c00",
    "Type 3": "#d9a300",
    "Type 4": "#6a3d9a",
}

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
    matches = cat[(cat["start_date"] <= date) & (cat["end_date"] >= date)]

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

    df = df[df["type"].isin(TYPE_ORDER)].copy()

    df["orientation_deg"] = df.apply(
        lambda r: orientation_from_north_deg(r["pc1_vec_x"], r["pc1_vec_y"]),
        axis=1
    )

    df = df[np.isfinite(df["orientation_deg"])].copy()
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
        )
    )

    event_df["event_id"] = event_df["event_id"].astype(int)
    return event_df


def kde_curve(values, x_grid):
    vals = np.asarray(values, dtype=float)
    vals = vals[np.isfinite(vals)]

    if len(vals) < 2 or np.nanstd(vals) == 0:
        return None

    kde = gaussian_kde(vals)
    return kde(x_grid)


def make_summary_csv(event_df, out_csv):
    rows = []

    for typ in TYPE_ORDER:
        vals = event_df.loc[event_df["type"] == typ, "orientation_deg"].dropna().values

        rows.append({
            "type": typ,
            "n_events": len(vals),
            "mean_orientation_deg": np.mean(vals) if len(vals) else np.nan,
            "median_orientation_deg": np.median(vals) if len(vals) else np.nan,
            "std_orientation_deg": np.std(vals, ddof=1) if len(vals) > 1 else np.nan,
            "min_orientation_deg": np.min(vals) if len(vals) else np.nan,
            "max_orientation_deg": np.max(vals) if len(vals) else np.nan,
        })

    pd.DataFrame(rows).to_csv(out_csv, index=False)


# =============================================================================
# MAIN
# =============================================================================
def main():
    plt.rcParams.update({
        "font.family": "Arial",
        "font.size": 9,
        "axes.labelsize": 9.5,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "axes.linewidth": 0.75,
        "xtick.major.width": 0.75,
        "ytick.major.width": 0.75,
        "xtick.direction": "out",
        "ytick.direction": "out",
        "savefig.dpi": 600,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })

    df_ellipse = prepare_ellipse_dataframe(METRICS_CSV)
    event_df = convert_to_event_average_dataframe(df_ellipse)

    event_df.to_csv(OUT_EVENT_AVERAGE_CSV, index=False)
    make_summary_csv(event_df, OUT_SUMMARY_CSV)

    x_grid = np.linspace(-90, 90, 600)

    fig, ax = plt.subplots(figsize=(6.8, 4.35))

    for typ in TYPE_ORDER:
        vals = event_df.loc[event_df["type"] == typ, "orientation_deg"].dropna().values
        density = kde_curve(vals, x_grid)

        if density is None:
            ax.scatter(
                vals,
                np.zeros_like(vals),
                color=TYPE_COLORS[typ],
                s=18,
                edgecolor="white",
                linewidth=0.35,
                label=typ,
                zorder=4,
            )
            continue

        ax.plot(
            x_grid,
            density,
            color=TYPE_COLORS[typ],
            linewidth=2.15,
            label=typ,
            zorder=3,
        )

    ax.axvline(
        0,
        color="0.35",
        linewidth=0.75,
        linestyle="--",
        zorder=1,
    )

    ax.set_xlim(-90, 90)
    ax.set_xticks(np.arange(-90, 91, 30))

    ax.set_xlabel("Orientation (°)")
    ax.set_ylabel("Probability Density")

    ax.grid(
        axis="y",
        linestyle="--",
        linewidth=0.40,
        alpha=0.20,
        zorder=0,
    )

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.legend(
        loc="upper right",
        frameon=False,
        fontsize=8.0,
        handlelength=2.4,
    )

    fig.savefig(OUT_FIG_PNG, bbox_inches="tight")
    fig.savefig(OUT_FIG_PDF, bbox_inches="tight")
    plt.show()

    print("\nSaved:")
    print(OUT_FIG_PNG)
    print(OUT_FIG_PDF)
    print(OUT_EVENT_AVERAGE_CSV)
    print(OUT_SUMMARY_CSV)
    print("\nDONE.")


if __name__ == "__main__":
    main()