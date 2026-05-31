#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Generate compound heatwave typology summary table.

Uses:
SHWE_spatial_PCA_metrics_blobfirst_clean_p60_merge_revert.csv

Outputs:
1) compound_heatwave_typology_summary_table.csv
2) compound_heatwave_typology_summary_table.png
3) compound_heatwave_event_diagnostics.csv
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# =============================================================================
# USER SETTINGS
# =============================================================================

OUT_DIR = r"ENTER_OUTPUT_DIRECTORY"

# =============================================================================


METRICS_CSV = os.path.join(
    OUT_DIR,
    "SHWE_spatial_PCA_metrics_blobfirst_clean_p60_merge_revert.csv"
)

OUT_TABLE_CSV = os.path.join(
    OUT_DIR,
    "compound_heatwave_typology_summary_table.csv"
)

OUT_TABLE_PNG = os.path.join(
    OUT_DIR,
    "compound_heatwave_typology_summary_table.png"
)

OUT_DIAGNOSTICS_CSV = os.path.join(
    OUT_DIR,
    "compound_heatwave_event_diagnostics.csv"
)


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

        # Important: these are Type 3, not Type 4
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

    cat["type_name"] = cat["type"].map(
        {
            "Type 1": "Independent",
            "Type 2": "Spatially clustered",
            "Type 3": "Temporally clustered",
            "Type 4": "Mixed",
        }
    )

    cat["duration_days"] = (
        cat["end_date"] - cat["start_date"]
    ).dt.days + 1

    return cat


def assign_event_to_metric_date(date, cat):
    matches = cat[
        (cat["start_date"] <= date) &
        (cat["end_date"] >= date)
    ]

    if len(matches) == 0:
        return np.nan, np.nan, np.nan, np.nan

    if len(matches) > 1:
        raise RuntimeError(
            f"Date {date.strftime('%Y-%m-%d')} matched multiple events. "
            "Check catalogue overlap."
        )

    row = matches.iloc[0]

    return (
        row["event_id"],
        row["event_type_original"],
        row["type"],
        row["type_name"],
    )


def make_table_figure(summary):
    fig, ax = plt.subplots(figsize=(14.5, 5.4))
    ax.axis("off")

    table = ax.table(
        cellText=summary.values,
        colLabels=summary.columns,
        cellLoc="center",
        colLoc="center",
        loc="center",
    )

    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1.0, 2.25)

    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("black")
        cell.set_linewidth(0.8)

        if row == 0:
            cell.set_text_props(weight="bold")
            cell.set_height(0.16)
        else:
            cell.set_height(0.16)

        if col == 0 and row > 0:
            cell.set_text_props(weight="bold")

    plt.tight_layout()
    fig.savefig(OUT_TABLE_PNG, dpi=500, bbox_inches="tight")
    plt.close(fig)


def main():
    if OUT_DIR == r"ENTER_OUTPUT_DIRECTORY":
        raise ValueError("Please edit OUT_DIR before running the script.")

    if not os.path.exists(METRICS_CSV):
        raise FileNotFoundError(f"Metrics CSV not found:\n{METRICS_CSV}")

    os.makedirs(OUT_DIR, exist_ok=True)

    cat = build_event_type_catalogue()

    metrics = pd.read_csv(METRICS_CSV)

    if "date" not in metrics.columns:
        raise ValueError("Metrics CSV must contain a date column.")

    metrics["date"] = pd.to_datetime(metrics["date"], errors="coerce")
    metrics = metrics.dropna(subset=["date"]).copy()

    assigned = metrics["date"].apply(
        lambda d: assign_event_to_metric_date(d, cat)
    )

    metrics["event_id"] = assigned.apply(lambda x: x[0])
    metrics["event_type_original"] = assigned.apply(lambda x: x[1])
    metrics["type"] = assigned.apply(lambda x: x[2])
    metrics["type_name"] = assigned.apply(lambda x: x[3])

    unmatched = metrics["type"].isna().sum()

    if unmatched > 0:
        print(f"[WARNING] {unmatched} metrics rows did not match any catalogue event and were removed.")

    metrics = metrics[metrics["type"].isin(["Type 1", "Type 2", "Type 3", "Type 4"])].copy()
    metrics["event_id"] = metrics["event_id"].astype(int)

    ellipse_counts = (
        metrics.groupby("event_id")
        .size()
        .reset_index(name="ellipse_count")
    )

    diagnostics = cat.merge(ellipse_counts, on="event_id", how="left")
    diagnostics["ellipse_count"] = diagnostics["ellipse_count"].fillna(0).astype(int)

    diagnostics = diagnostics.sort_values(["type", "start_date", "event_id"]).copy()
    diagnostics.to_csv(OUT_DIAGNOSTICS_CSV, index=False)

    summary = (
        diagnostics
        .groupby(["type", "type_name"], as_index=False)
        .agg(
            number_of_events=("event_id", "nunique"),
            duration_days=("duration_days", "sum"),
            average_duration_days=("duration_days", "mean"),
            longest_event_days=("duration_days", "max"),
            min_ellipses_event=("ellipse_count", "min"),
            max_ellipses_event=("ellipse_count", "max"),
            avg_ellipses_event=("ellipse_count", "mean"),
        )
    )

    type_label = {
        "Type 1": "Type 1\n(Independent)",
        "Type 2": "Type 2\n(Spatially\nclustered)",
        "Type 3": "Type 3\n(Temporally\nclustered)",
        "Type 4": "Type 4 (Mixed)",
    }

    summary["Compound Heatwave Typologies"] = summary["type"].map(type_label)

    summary = summary[
        [
            "Compound Heatwave Typologies",
            "number_of_events",
            "duration_days",
            "average_duration_days",
            "longest_event_days",
            "min_ellipses_event",
            "max_ellipses_event",
            "avg_ellipses_event",
        ]
    ]

    summary = summary.rename(
        columns={
            "number_of_events": "Number of\nEvents",
            "duration_days": "Duration\n(days)",
            "average_duration_days": "Average\nDuration\n(days/event)",
            "longest_event_days": "Longest Event\n(days)",
            "min_ellipses_event": "Min\nEllipses/Event",
            "max_ellipses_event": "Max\nEllipses/Event",
            "avg_ellipses_event": "Avg\nEllipses/Event",
        }
    )

    summary["Average\nDuration\n(days/event)"] = (
        summary["Average\nDuration\n(days/event)"].round(1)
    )

    summary["Avg\nEllipses/Event"] = (
        summary["Avg\nEllipses/Event"].round(2)
    )

    summary.to_csv(OUT_TABLE_CSV, index=False)
    make_table_figure(summary)

    print("\n" + "=" * 120)
    print("COMPOUND HEATWAVE TYPOLOGY SUMMARY TABLE")
    print("=" * 120)
    print(summary.to_string(index=False))
    print("=" * 120)

    print("\nSaved:")
    print(OUT_TABLE_CSV)
    print(OUT_TABLE_PNG)
    print(OUT_DIAGNOSTICS_CSV)


if __name__ == "__main__":
    main()