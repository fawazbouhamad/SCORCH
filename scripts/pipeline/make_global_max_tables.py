#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Recreate two manuscript tables from the EVENT-GLOBAL-MAX master dataset.

Table A - Compound Heatwave Typologies summary
Table B - Trend Analysis (Sen's slope + Mann-Kendall p) for Type 3 / Type 4
          Frequency and Duration.

All values are computed directly from the global-max master (corrected types:
T1=3, T2=4, T3=20, T4=24; event 14 = Type 3). The Mann-Kendall and Sen's-slope
functions are the exact ones used in
scripts/figures/Figure_9_Trend_Analysis_With_Table_statistics.py.

Outputs -> reproduced/tables/
    Table_Compound_Heatwave_Typologies_global_max.{png,pdf,csv,xlsx}
    Table_Trend_Analysis_global_max.{png,pdf,csv,xlsx}
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from scipy.stats import norm

os.environ.setdefault("MPLBACKEND", "Agg")
import matplotlib.pyplot as plt  # noqa: E402

_THIS = os.path.abspath(__file__)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_THIS)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "figures", "common"))
from _clean_paths import (  # noqa: E402
    GENERATED_DIR, MASTER_CSV, enforce_source_date_epoch)

# Deterministic PDF metadata also when this script is run directly,
# not only through run_reproduction.py. matplotlib reads
# SOURCE_DATE_EPOCH at write time, so pinning it here is sufficient.
enforce_source_date_epoch()

# Default input: the deposit master (env SCORCH_MASTER_FILE overrides).
MASTER = os.environ.get("SCORCH_MASTER_FILE", MASTER_CSV)
OUT = os.environ.get("SCORCH_TABLES_OUT_DIR",
                     os.path.join(GENERATED_DIR, "tables"))

TYPE_LABEL = {1: "Type 1 (Independent)", 2: "Type 2 (Spatially clustered)",
              3: "Type 3 (Temporally clustered)", 4: "Type 4 (Mixed)"}
# Original Figure-10 type colours (for the table row tint).
FIG10_COLORS = {1: "#d7191c", 2: "#f57c00", 3: "#d9a300", 4: "#6a3d9a"}


# --- exact MK + Sen functions from Figure_9 -----------------------------------
def mann_kendall_test(y):
    y = np.asarray(y, dtype=float)
    n = len(y)
    s = 0
    for k in range(n - 1):
        for j in range(k + 1, n):
            s += np.sign(y[j] - y[k])
    unique_y, counts = np.unique(y, return_counts=True)
    var_s = n * (n - 1) * (2 * n + 5)
    tie_correction = np.sum(counts * (counts - 1) * (2 * counts + 5))
    var_s = (var_s - tie_correction) / 18.0
    if s > 0:
        z = (s - 1) / np.sqrt(var_s) if var_s > 0 else 0.0
    elif s < 0:
        z = (s + 1) / np.sqrt(var_s) if var_s > 0 else 0.0
    else:
        z = 0.0
    p = 2 * (1 - norm.cdf(abs(z)))
    return s, z, p


def sens_slope(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    slopes = []
    for i in range(len(x) - 1):
        for j in range(i + 1, len(x)):
            if x[j] != x[i]:
                slopes.append((y[j] - y[i]) / (x[j] - x[i]))
    return float(np.median(slopes)) if slopes else float("nan")


# --- event-level table from the global-max master ----------------------------
def event_table(df):
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    g = df.groupby("new_event_id")
    ev = g.agg(v3_type=("v3_type", "first"),
              duration_days=("duration_days", "first"),
              start_date=("date", "min"),
              n_ellipses=("cluster_id", "size")).reset_index()
    ev["year"] = ev["start_date"].dt.year
    return ev


# --- Table A ------------------------------------------------------------------
def event_days_by_type(df):
    """Number of distinct (event, calendar day) occurrence days per type."""
    ed = df.drop_duplicates(["new_event_id", "date"])
    return ed["v3_type"].value_counts().to_dict()


def table_a(ev, df):
    """Frequency of Occurrence = total occurrence/event-DAYS (matches the original
    table: T3 19x3.7~71, T4 25x12.7~317 -> here T3 20x3.75=75, T4 24x13.04=313).
    Number of Compound Events = the actual number of events (3/4/20/24).
    """
    eday = event_days_by_type(df)
    rows = []
    for t in (1, 2, 3, 4):
        sub = ev[ev["v3_type"] == t]
        rows.append({
            "Compound Heatwave Typologies": TYPE_LABEL[t],
            "Frequency of Occurrence (Number of Events)": int(eday.get(t, 0)),
            "Number of Compound Events": int(sub.shape[0]),
            "Average Duration (days/event)": round(float(sub["duration_days"].mean()), 2),
            "Average Number of Ellipses per Compound Event":
                round(float(sub["n_ellipses"].mean()), 2),
            "Longest Compound Event (days)": int(sub["duration_days"].max()),
            "Min Ellipses per Compound Event": int(sub["n_ellipses"].min()),
            "Max Ellipses per Compound Event": int(sub["n_ellipses"].max()),
        })
    return pd.DataFrame(rows)


def per_type_calculation(ev, df):
    """Transparent intermediate calculation table behind Table A."""
    eday = event_days_by_type(df)
    rows = []
    for t in (1, 2, 3, 4):
        sub = ev[ev["v3_type"] == t]
        n_ev = int(sub.shape[0])
        tot_ell = int(sub["n_ellipses"].sum())
        rows.append(dict(
            v3_type=t, type_name=TYPE_LABEL[t],
            total_event_days=int(eday.get(t, 0)),
            number_of_events=n_ev,
            average_duration_days_per_event=round(float(sub["duration_days"].mean()), 4),
            total_ellipses=tot_ell,
            average_ellipses_per_event=round(tot_ell / n_ev, 4) if n_ev else 0.0))
    return pd.DataFrame(rows)


# --- Table B ------------------------------------------------------------------
def table_b(ev):
    rows = []
    series_rows = []
    year_min, year_max = int(ev["year"].min()), int(ev["year"].max())
    full_years = np.arange(year_min, year_max + 1)
    for t in (3, 4):
        sub = ev[ev["v3_type"] == t]
        # Frequency: events per year over the FULL period (zeros filled).
        counts = (sub.groupby("year").size()
                     .reindex(full_years, fill_value=0))
        sen_f = sens_slope(full_years, counts.to_numpy(float))
        _, _, p_f = mann_kendall_test(counts.to_numpy(float))
        # Duration: mean event duration per OBSERVED year (years with events).
        dur = sub.groupby("year")["duration_days"].mean().sort_index()
        sen_d = sens_slope(dur.index.to_numpy(float), dur.to_numpy(float))
        _, _, p_d = mann_kendall_test(dur.to_numpy(float))
        rows.append({"Heatwave Type": TYPE_LABEL[t], "Metric": "Frequency",
                     "Sen's Slope": round(sen_f, 4),
                     "Mann-Kendall p-value": round(float(p_f), 4)})
        rows.append({"Heatwave Type": TYPE_LABEL[t], "Metric": "Duration",
                     "Sen's Slope": round(sen_d, 4),
                     "Mann-Kendall p-value": round(float(p_d), 4)})
        for yr, val in counts.items():
            series_rows.append(dict(v3_type=t, type_name=TYPE_LABEL[t],
                                    metric="Frequency", year=int(yr),
                                    value=float(val)))
        for yr, val in dur.items():
            series_rows.append(dict(v3_type=t, type_name=TYPE_LABEL[t],
                                    metric="Duration", year=int(yr),
                                    value=float(val)))
    return pd.DataFrame(rows), pd.DataFrame(series_rows)


# --- rendering ----------------------------------------------------------------
def render_table(df, title, out_noext, type_col=None, colw=None, figsize=None):
    n_rows, n_cols = df.shape
    fig, ax = plt.subplots(figsize=figsize or (1.7 * n_cols, 0.7 * n_rows + 1.4))
    ax.axis("off")
    ax.set_title(title, fontweight="bold", fontsize=13, pad=14)
    cell_text = [[str(v) for v in row] for row in df.to_numpy()]
    tbl = ax.table(cellText=cell_text, colLabels=list(df.columns),
                   cellLoc="center", loc="center")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9)
    tbl.scale(1, 1.6)
    # header styling
    for j in range(n_cols):
        c = tbl[0, j]
        c.set_facecolor("#2f3b52")
        c.set_text_props(color="white", fontweight="bold")
        c.set_height(c.get_height() * 1.7)
    # row tint by type colour (first column), light alternating otherwise
    for i in range(n_rows):
        type_int = None
        if type_col is not None:
            label = str(df.iloc[i][type_col])
            for k, v in TYPE_LABEL.items():
                if v == label:
                    type_int = k
        for j in range(n_cols):
            cell = tbl[i + 1, j]
            if j == 0 and type_int is not None:
                cell.set_facecolor(FIG10_COLORS[type_int])
                cell.set_text_props(color="white", fontweight="bold")
            else:
                cell.set_facecolor("#f5f7fa" if i % 2 == 0 else "white")
            cell.set_edgecolor("#c8ccd4")
    if colw:
        for (r, c), w in colw.items():
            pass  # placeholder; auto width used
    tbl.auto_set_column_width(col=list(range(n_cols)))
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(f"{out_noext}.{ext}", dpi=300, bbox_inches="tight")
    plt.close(fig)


def main():
    os.makedirs(OUT, exist_ok=True)
    df = pd.read_csv(MASTER)
    ev = event_table(df)
    assert ev["v3_type"].value_counts().to_dict().get(3) == 20, "Type3 != 20"
    assert int(ev.loc[ev["new_event_id"] == 14, "v3_type"].iloc[0]) == 3, \
        "event 14 must be Type 3"

    A = table_a(ev, df)
    A.to_csv(os.path.join(OUT, "Table_Compound_Heatwave_Typologies_global_max.csv"),
             index=False)
    calc = per_type_calculation(ev, df)
    calc.to_csv(os.path.join(
        OUT, "Table_Compound_Heatwave_Typologies_calculation_global_max.csv"),
        index=False)
    B, series = table_b(ev)
    B.to_csv(os.path.join(OUT, "Table_Trend_Analysis_global_max.csv"), index=False)
    series.to_csv(os.path.join(
        OUT, "Table_Trend_Analysis_yearly_series_global_max.csv"), index=False)
    with pd.ExcelWriter(os.path.join(OUT, "global_max_tables.xlsx"),
                        engine="openpyxl") as xw:
        A.to_excel(xw, sheet_name="Compound_Typologies", index=False)
        calc.to_excel(xw, sheet_name="Typologies_calculation", index=False)
        B.to_excel(xw, sheet_name="Trend_Analysis", index=False)
        series.to_excel(xw, sheet_name="Trend_yearly_series", index=False)

    render_table(A, "Compound Heatwave Typologies (event-global-max)",
                 os.path.join(OUT, "Table_Compound_Heatwave_Typologies_global_max"),
                 type_col="Compound Heatwave Typologies",
                 figsize=(15.5, 3.4))
    render_table(B, "Trend Analysis - Sen's Slope & Mann-Kendall (event-global-max)",
                 os.path.join(OUT, "Table_Trend_Analysis_global_max"),
                 type_col="Heatwave Type", figsize=(9.5, 3.4))

    print("=== TABLE A: Compound Heatwave Typologies (global-max) ===")
    print(A.to_string(index=False))
    print("\n=== TABLE B: Trend Analysis (global-max) ===")
    print(B.to_string(index=False))
    print(f"\n[TABLES] event 14 type = "
          f"{int(ev.loc[ev['new_event_id'] == 14, 'v3_type'].iloc[0])}; "
          f"type counts = {ev['v3_type'].value_counts().sort_index().to_dict()}")
    print(f"[TABLES] outputs -> {os.path.relpath(OUT, REPO_ROOT)}")


if __name__ == "__main__":
    main()
