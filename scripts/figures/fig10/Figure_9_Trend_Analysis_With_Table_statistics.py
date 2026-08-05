# ============================================================
# Q1 / Najibi-style SCORCH Fig. 11 trend-analysis package
#
# Outputs:
# 1) Fig. 11A: stacked frequency + Type 3/4 duration with OLS trends
# 2) Fig. 11B: same figure + OLS vs Mann-Kendall/Sen comparison table
# 3) Residual diagnostics for OLS fits
# 4) CSV trend summary table
# ============================================================

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from pathlib import Path
from scipy.stats import linregress, norm

# =========================
# INPUT OUTPUT PATH HERE
# =========================

# Clean-package path repair: resolve via clean/scripts/_clean_paths.py
# (original committed script had OUT_DIR = Path(r"INPUT OUTPUT PATH HERE")).
import os
import sys

# Headless rendering (plt.show() below is a no-op under Agg; without this the
# script blocks on an interactive window when run outside the harness).
os.environ.setdefault("MPLBACKEND", "Agg")
# Phase 2C candidate copy: outputs into the candidate workspace; (a)/(b)
# moved from above the panels to the left/y-axis side (author revision).
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_FIGS = os.path.dirname(_THIS_DIR)                       # scripts/figures
_ROOT = os.path.dirname(os.path.dirname(_FIGS))          # release root
sys.path.insert(0, os.path.join(_FIGS, "common"))
from _clean_paths import MASTER_CSV

# Output-location repair: write ONLY under reproduced/ (the F3 copy wrote
# into the code tree; see docs/SANITIZATION_NOTES.md).
OUT_DIR = Path(os.environ.get(
    "SCORCH_OUT_DIR", os.path.join(_ROOT, "reproduced"))) / "fig10"

OUT_DIR.mkdir(parents=True, exist_ok=True)
# ------------------------------------------------------------
# EVENT CATALOGUE
# ------------------------------------------------------------
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

# Clean-package input repair: the hard-coded catalogue above carries the OLD
# (pre-v3-reclassification) typology, which does not reproduce the reference
# figure/CSV. The event table is therefore derived from the master dataset
# (single source of truth); the catalogue list is retained for reference but
# no longer used. year/duration are computed exactly as before.
_master = pd.read_csv(MASTER_CSV)
_master["date"] = pd.to_datetime(_master["date"])
df = (_master.groupby("new_event_id")
      .agg(event_type_original=("event_type_original", "first"),
           v3_type=("v3_type", "first"),
           start_date=("date", "min"),
           end_date=("date", "max"))
      .reset_index()
      .rename(columns={"new_event_id": "event_id"}))

df["year"] = df["start_date"].dt.year
df["duration_days"] = (df["end_date"] - df["start_date"]).dt.days + 1

# ------------------------------------------------------------
# TYPE MAPPING
# ------------------------------------------------------------
type_map = {
    "Independent": "Type 1",
    "Independent Simultaneous": "Type 2",
    "Back-to-Back": "Type 3",
    "Back-to-Back Simultaneous": "Type 3",
    "Mixed Multi-Day": "Type 4",
}

type_names = {
    "Type 1": "Independent",
    "Type 2": "Spatially clustered",
    "Type 3": "Temporally clustered",
    "Type 4": "Mixed",
}

# Clean-package input repair: type comes from the master's v3 reclassified
# typing (v3_type), not from the old name-based map above; type_names follow
# the v3 naming used by the reference figure, Table 1 and the manuscript.
df["type"] = "Type " + df["v3_type"].astype(int).astype(str)

type_order = ["Type 1", "Type 2", "Type 3", "Type 4"]
duration_types = ["Type 3", "Type 4"]

colors = {
    "Type 1": "#d7191c",
    "Type 2": "#f57c00",
    "Type 3": "#d9a300",
    "Type 4": "#6a3d9a",
}

# ------------------------------------------------------------
# STYLE
# ------------------------------------------------------------
plt.rcParams.update({
    "font.family": "Arial",
    "font.size": 9,
    "axes.linewidth": 0.75,
    "xtick.major.width": 0.75,
    "ytick.major.width": 0.75,
    "xtick.direction": "out",
    "ytick.direction": "out",
    "savefig.dpi": 600,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
})

# ------------------------------------------------------------
# MANN-KENDALL + SEN SLOPE FUNCTIONS
# ------------------------------------------------------------
def mann_kendall_test(y):
    """
    Basic two-sided Mann-Kendall trend test.
    Returns S, z, p-value, and trend direction.
    """
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
        z = (s - 1) / np.sqrt(var_s)
    elif s < 0:
        z = (s + 1) / np.sqrt(var_s)
    else:
        z = 0.0

    p = 2 * (1 - norm.cdf(abs(z)))

    if p < 0.05 and z > 0:
        trend = "increasing"
    elif p < 0.05 and z < 0:
        trend = "decreasing"
    else:
        trend = "no significant trend"

    return s, z, p, trend


def sens_slope(x, y):
    """
    Sen's slope as the median of all pairwise slopes.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    slopes = []
    for i in range(len(x) - 1):
        for j in range(i + 1, len(x)):
            if x[j] != x[i]:
                slopes.append((y[j] - y[i]) / (x[j] - x[i]))

    return np.median(slopes)


def trend_summary_for_type(input_df, typ):
    """
    Compute OLS, Mann-Kendall, Sen slope, and residual diagnostics
    for one event type.
    """
    sub = (
        input_df[input_df["type"] == typ]
        .groupby("year")["duration_days"]
        .mean()
        .reset_index()
        .sort_values("year")
    )

    x = sub["year"].values.astype(float)
    y = sub["duration_days"].values.astype(float)

    ols = linregress(x, y)

    yhat = ols.intercept + ols.slope * x
    residuals = y - yhat

    mae = np.mean(np.abs(residuals))
    rmse = np.sqrt(np.mean(residuals ** 2))

    s, z, mk_p, mk_trend = mann_kendall_test(y)
    sen = sens_slope(x, y)

    out = {
        "type": typ,
        "event_name": type_names[typ],
        "n_years": len(sub),
        "ols_slope_days_per_year": ols.slope,
        "ols_slope_days_per_decade": ols.slope * 10,
        "ols_intercept": ols.intercept,
        "ols_p_value": ols.pvalue,
        "ols_r_value": ols.rvalue,
        "ols_r_squared": ols.rvalue ** 2,
        "sen_slope_days_per_year": sen,
        "sen_slope_days_per_decade": sen * 10,
        "mk_S": s,
        "mk_z": z,
        "mk_p_value": mk_p,
        "mk_trend": mk_trend,
        "residual_MAE_days": mae,
        "residual_RMSE_days": rmse,
    }

    sub["ols_fitted"] = yhat
    sub["ols_residual"] = residuals
    sub["type"] = typ

    return out, sub


# ------------------------------------------------------------
# PANEL A DATA
# ------------------------------------------------------------
years = np.arange(1983, 2026)

annual_counts = (
    df.groupby(["year", "type"])
    .size()
    .unstack(fill_value=0)
    .reindex(index=years, columns=type_order, fill_value=0)
)

nonzero_years = annual_counts.sum(axis=1)
plot_years = nonzero_years[nonzero_years > 0].index
annual_plot = annual_counts.loc[plot_years]

# ------------------------------------------------------------
# PANEL B DATA + TREND SUMMARY
# ------------------------------------------------------------
trend_rows = []
diagnostic_rows = []

for typ in duration_types:
    row, diag = trend_summary_for_type(df, typ)
    trend_rows.append(row)
    diagnostic_rows.append(diag)

trend_df = pd.DataFrame(trend_rows)
diagnostic_df = pd.concat(diagnostic_rows, ignore_index=True)

trend_csv = OUT_DIR / "Fig11_Type3_Type4_duration_trend_summary.csv"
trend_df.to_csv(trend_csv, index=False)

print("\nTrend summary:")
print(trend_df.round(4))
print(f"\n[SAVED] {trend_csv}")

duration_summary = (
    df[df["type"].isin(duration_types)]
    .groupby(["year", "type"])["duration_days"]
    .mean()
    .reset_index()
)

# ------------------------------------------------------------
# CREATE ONLY ONE TWO-PANEL FIGURE
# ------------------------------------------------------------
fig, (ax1, ax2) = plt.subplots(
    2,
    1,
    figsize=(9.4, 6.45),
    gridspec_kw={
        "height_ratios": [1.0, 1.15],
        "hspace": 0.33
    }
)

# ============================================================
# PANEL (a): STACKED ANNUAL BARPLOT
# ============================================================
bottom = np.zeros(len(annual_plot))

for typ in type_order:
    vals = annual_plot[typ].values

    ax1.bar(
        annual_plot.index,
        vals,
        bottom=bottom,
        width=0.72,
        color=colors[typ],
        edgecolor="white",
        linewidth=0.45,
        alpha=0.95,
        label=f"{typ}",
        zorder=3,
    )

    bottom += vals

ax1.set_xlim(1982.5, 2025.5)
ax1.set_ylim(0, annual_plot.sum(axis=1).max() + 1)
ax1.set_ylabel("Number of events")

ax1.set_xticks([
    1985, 1990, 1995, 2000,
    2005, 2010, 2015, 2020, 2025
])

ax1.set_yticks(np.arange(0, annual_plot.sum(axis=1).max() + 2, 1))

ax1.grid(axis="y", linestyle="--", linewidth=0.45, alpha=0.22)
ax1.set_axisbelow(True)

ax1.spines["top"].set_visible(False)
ax1.spines["right"].set_visible(False)

ax1.tick_params(axis="both", labelsize=8.5)

ax1.legend(
    loc="upper left",
    frameon=False,
    fontsize=7.5,
    ncol=2,
    handlelength=1.2,
    columnspacing=1.1,
    handletextpad=0.45,
)

# Phase 2C canonical label: left/y-axis side, vertically centered on the
# panel; identical offset for both panels (equal-size axes).
ax1.text(
    -0.135,
    0.5,
    "(a)",
    transform=ax1.transAxes,
    ha="right",
    va="center",
    fontsize=17,
    fontweight="bold",
    color="black",
    family="Arial",
)

# ============================================================
# PANEL (b): TYPE 3 AND TYPE 4 DURATION ONLY
# No trend lines, no top-right annotation
# ============================================================
for typ in duration_types:

    sub = duration_summary[
        duration_summary["type"] == typ
    ].sort_values("year")

    ax2.plot(
        sub["year"],
        sub["duration_days"],
        color=colors[typ],
        linewidth=2.0,
        marker="o",
        markersize=3.6,
        markeredgewidth=0.0,
        solid_capstyle="round",
        label=f"{typ}",
        zorder=3
    )

ax2.set_xlim(1983, 2025)

ax2.set_ylim(
    0,
    df.loc[df["type"].isin(duration_types), "duration_days"].max() + 4
)

ax2.set_ylabel("Mean duration (days)")
ax2.set_xlabel("Year")

ax2.set_xticks([
    1985, 1990, 1995, 2000,
    2005, 2010, 2015, 2020, 2025
])

ax2.set_yticks(np.arange(0, 51, 5))

ax2.grid(axis="y", linestyle="--", linewidth=0.40, alpha=0.18)
ax2.set_axisbelow(True)

ax2.spines["top"].set_visible(False)
ax2.spines["right"].set_visible(False)

ax2.tick_params(axis="both", labelsize=8.5, length=3.2, width=0.75)

ax2.legend(
    loc="upper left",
    frameon=False,
    fontsize=7.5,
    ncol=2,
    handlelength=2.0,
    columnspacing=1.2,
    handletextpad=0.45,
)

ax2.text(
    -0.135,
    0.5,
    "(b)",
    transform=ax2.transAxes,
    ha="right",
    va="center",
    fontsize=17,
    fontweight="bold",
    color="black",
    family="Arial",
)

fig.align_ylabels([ax1, ax2])

fig_png = OUT_DIR / "Fig11_SCORCH_event_frequency_duration_ONLY_two_panels.png"
fig_pdf = OUT_DIR / "Fig11_SCORCH_event_frequency_duration_ONLY_two_panels.pdf"

plt.savefig(fig_png, bbox_inches="tight")
plt.savefig(fig_pdf, bbox_inches="tight")
plt.show()

print(f"[SAVED] {fig_png}")
print(f"[SAVED] {fig_pdf}")

# ============================================================
# MANN-KENDALL + SEN SLOPE SUMMARY
# TYPE 3 & TYPE 4
# DURATION ONLY
#
# the v1.0.0 pre-release correction (docs/ALIGNMENT_DECISIONS.md Correction 2): the frequency Mann-Kendall and
# Sen's-slope block was REMOVED. Annual event counts are descriptive only and
# are not trend-tested anywhere in this workflow, matching the manuscript:
# "Annual event counts are reported descriptively and are not subjected to a
# trend test." The annual-count PANEL of this figure is unaffected -- only the
# inferential statistic was removed.
# ============================================================

print("\n" + "="*80)
print("MANN-KENDALL DURATION TREND RESULTS")
print("(annual event counts are descriptive only and are not trend-tested)")
print("="*80)

for typ in ["Type 3", "Type 4"]:

    # --------------------------------------------------------
    # DURATION
    # --------------------------------------------------------
    dur_df = (
        df[df["type"] == typ]
        .groupby("year")["duration_days"]
        .mean()
        .reset_index()
        .sort_values("year")
    )

    x_dur = dur_df["year"].values
    y_dur = dur_df["duration_days"].values

    sen_dur = sens_slope(x_dur, y_dur)
    _, _, mk_p_dur, _ = mann_kendall_test(y_dur)

    print(f"\n{typ} DURATION")
    print(f"Sen slope : {sen_dur:.4f} days/year")
    print(f"MK p-value: {mk_p_dur:.6f}")

print("\n" + "="*80)