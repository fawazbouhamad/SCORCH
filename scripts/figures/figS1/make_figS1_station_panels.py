# ============================================================
# Q1 / Najibi-style ERA5 vs GHCNd validation
#
# SCORCH observational consistency check
#
# Event:
# Back-to-back heatwave
# 2016-06-07 to 2016-06-08
# South Egypt / North Sudan
#
# Station:
# GHCND:EG000062414
# ASSWAN, EG
#
# Method:
# - ERA5 daily Tmax vs GHCNd observed Tmax
# - Warm-season pooled P95 thresholds
# - April 1 -> September 30
# - Same philosophy as SCORCH framework
#
# Outputs:
# (1) Validation metrics CSV
# (2) Daily merged timeseries CSV
# (3) Q1-style timeseries figure
# (4) Q1-style scatter figure
# ============================================================

import os
import sys

# v1.0.0 pre-release correction: force a headless, deterministic backend. The recovered research
# script relied on an interactive backend and called plt.show(), which blocks
# forever in an automated reproduction run.
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from pathlib import Path


def _mse(y_true, y_pred):
    """Mean squared error -- same definition as sklearn.metrics."""
    a = np.asarray(y_true, dtype=float)
    b = np.asarray(y_pred, dtype=float)
    return float(np.mean((a - b) ** 2))


def _mae(y_true, y_pred):
    """Mean absolute error -- same definition as sklearn.metrics."""
    a = np.asarray(y_true, dtype=float)
    b = np.asarray(y_pred, dtype=float)
    return float(np.mean(np.abs(a - b)))


# ============================================================
# USER INPUTS
# ============================================================

# the v1.0.0 pre-release correction SANITIZATION -------------------------------------------------------
# The recovered original read a private Downloads CSV and an external ERA5
# netCDF via absolute Windows paths. Both are replaced by the deposited,
# redistributable series so this script runs from the processed-data deposit
# alone (honours SCORCH_DATA_DIR / SCORCH_OUT_DIR). No absolute path, temporary
# directory or private workspace is referenced.
_THIS = os.path.dirname(os.path.abspath(__file__))
_FIGS = os.path.dirname(_THIS)
sys.path.insert(0, os.path.join(_FIGS, "common"))
from _clean_paths import DATA_DIR, generated  # noqa: E402

_STATION_DIR = os.path.join(DATA_DIR, "validation_station")
GHCND_CSV = os.path.join(_STATION_DIR, "ghcnd_aswan_EG000062414.csv")
ERA5_CSV = os.path.join(_STATION_DIR, "era5_aswan_cell_2016.csv")

OUT_DIR = Path(generated("supplement_station_panels"))
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# EVENT SETTINGS
# ============================================================

EVENT_START = "2016-06-07"
EVENT_END   = "2016-06-08"

PLOT_START  = "2016-05-31"
PLOT_END    = "2016-06-12"

# X-axis control
X_TICK_INTERVAL_DAYS = 2
X_TICK_FORMAT = "%b %d"

# ============================================================
# STATION INFORMATION
# ============================================================

STATION_ID   = "EG000062414"
STATION_NAME = "ASSWAN, EG"

STATION_LAT = 23.97
STATION_LON = 32.78

# ============================================================
# MATPLOTLIB STYLE
# ============================================================

plt.rcParams.update({
    "font.family": "Arial",
    "font.size": 10,
    "axes.linewidth": 0.8,
    "axes.labelsize": 10,
    "axes.titlesize": 10,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "xtick.major.width": 0.8,
    "ytick.major.width": 0.8,
    "legend.fontsize": 8.8,
})

# ============================================================
# LOAD GHCNd
# ============================================================

obs = pd.read_csv(GHCND_CSV)

obs["DATE"] = pd.to_datetime(obs["DATE"])

obs = obs[
    obs["STATION"].astype(str) == STATION_ID
].copy()

# NOAA daily data are commonly stored in Fahrenheit in this file
obs["GHCNd_TMAX_C"] = (obs["TMAX"] - 32) * 5 / 9

obs = obs[
    ["DATE", "GHCNd_TMAX_C"]
].dropna()

obs = obs.sort_values("DATE")

# ============================================================
# LOAD ERA5
# ============================================================

era5 = pd.read_csv(ERA5_CSV)
era5["DATE"] = pd.to_datetime(era5["DATE"])

# The deposit stores the already-selected nearest ERA5 grid cell, so the
# nearest-neighbour lookup the original performed against the raw netCDF is
# baked in. Report it for provenance parity with the original console output.
nearest_lat = float(era5["cell_lat"].iloc[0])
nearest_lon = float(era5["cell_lon"].iloc[0])
print("")
print("Nearest ERA5 grid cell (from deposit):")
print("Latitude :", nearest_lat)
print("Longitude:", nearest_lon)

era5 = era5[["DATE", "ERA5_TMAX_C"]].dropna().sort_values("DATE")

# ============================================================
# MERGE
# Keep ALL ERA5 points.
# GHCNd is added only where observed data exists.
# ============================================================

df = pd.merge(
    era5,
    obs,
    on="DATE",
    how="left"
).sort_values("DATE")

# Plot window
df_plot = df[
    (df["DATE"] >= PLOT_START) &
    (df["DATE"] <= PLOT_END)
].copy()

if df_plot.empty:
    raise ValueError("No ERA5 dates found inside the plot window.")

# Metrics-only dataframe
# Only dates with BOTH ERA5 and GHCNd are used.
df_metrics = df_plot.dropna(
    subset=["GHCNd_TMAX_C", "ERA5_TMAX_C"]
).copy()

if df_metrics.empty:
    raise ValueError("No overlapping ERA5 and GHCNd dates found for metrics.")

# ============================================================
# WARM-SEASON P95 THRESHOLDS
# ============================================================

warm_months = [4, 5, 6, 7, 8, 9]

obs_warm = obs[
    obs["DATE"].dt.month.isin(warm_months)
].copy()

era5_warm = era5[
    era5["DATE"].dt.month.isin(warm_months)
].copy()

obs_p95 = np.percentile(
    obs_warm["GHCNd_TMAX_C"].dropna(),
    95
)

era5_p95 = np.percentile(
    era5_warm["ERA5_TMAX_C"].dropna(),
    95
)

print("\nWarm-season thresholds:")
print(f"GHCNd P95 = {obs_p95:.2f} °C")
print(f"ERA5  P95 = {era5_p95:.2f} °C")

# ============================================================
# EVENT EXCEEDANCE
# ============================================================

event_df = df_plot[
    (df_plot["DATE"] >= EVENT_START) &
    (df_plot["DATE"] <= EVENT_END)
].copy()

event_df["GHCNd_HW"] = (
    event_df["GHCNd_TMAX_C"] > obs_p95
)

event_df["ERA5_HW"] = (
    event_df["ERA5_TMAX_C"] > era5_p95
)

# ============================================================
# VALIDATION METRICS
# Only overlapping valid dates are used.
# ============================================================

rmse = np.sqrt(
    _mse(
        df_metrics["GHCNd_TMAX_C"],
        df_metrics["ERA5_TMAX_C"]
    )
)

mae = _mae(
    df_metrics["GHCNd_TMAX_C"],
    df_metrics["ERA5_TMAX_C"]
)

bias = np.mean(
    df_metrics["ERA5_TMAX_C"] -
    df_metrics["GHCNd_TMAX_C"]
)

corr = df_metrics["GHCNd_TMAX_C"].corr(
    df_metrics["ERA5_TMAX_C"]
)

ghcnd_hits = int(event_df["GHCNd_HW"].sum(skipna=True))
era5_hits  = int(event_df["ERA5_HW"].sum(skipna=True))

# ============================================================
# SAVE METRICS
# ============================================================

metrics = pd.DataFrame({
    "Metric": [
        "Station",
        "Event",
        "Nearest ERA5 latitude",
        "Nearest ERA5 longitude",
        "GHCNd warm-season P95 (°C)",
        "ERA5 warm-season P95 (°C)",
        "RMSE (°C)",
        "MAE (°C)",
        "Mean bias (ERA5 - GHCNd) (°C)",
        "Correlation (r)",
        "Observed exceedance days",
        "ERA5 exceedance days",
        "Number of overlapping validation days",
        "Number of ERA5 plot-window days",
        "Number of GHCNd observed plot-window days"
    ],
    "Value": [
        STATION_NAME,
        f"{EVENT_START} to {EVENT_END}",
        round(nearest_lat, 2),
        round(nearest_lon, 2),
        round(obs_p95, 2),
        round(era5_p95, 2),
        round(rmse, 2),
        round(mae, 2),
        round(bias, 2),
        round(corr, 2),
        ghcnd_hits,
        era5_hits,
        len(df_metrics),
        df_plot["ERA5_TMAX_C"].notna().sum(),
        df_plot["GHCNd_TMAX_C"].notna().sum()
    ]
})

metrics.to_csv(
    OUT_DIR / "validation_metrics.csv",
    index=False
)

# ============================================================
# SAVE MERGED DAILY DATA
# ============================================================

df_save = df_plot.copy()
df_save["DATE"] = df_save["DATE"].dt.strftime("%Y-%m-%d")

df_save.to_csv(
    OUT_DIR / "merged_daily_validation.csv",
    index=False
)

# ============================================================
# FIGURE A
# Q1 TIMESERIES
# ============================================================

fig, ax = plt.subplots(
    figsize=(7.0, 3.9),
    dpi=300
)

# ============================================================
# SCORCH / Q1 COLORS
# ============================================================

COL_GHCND = "#1f1f1f"     # near-black
COL_ERA5  = "#c44e52"     # muted SCORCH warm red

# ============================================================
# GHCNd observed Tmax
# Continuous line but only real markers
# ============================================================

obs_line = df_plot.copy()

obs_line["GHCNd_TMAX_C_interp"] = (
    obs_line["GHCNd_TMAX_C"]
    .interpolate(method="linear")
)

# ------------------------------------------------------------
# Continuous observed line
# ------------------------------------------------------------

ax.plot(
    obs_line["DATE"],
    obs_line["GHCNd_TMAX_C_interp"],
    color=COL_GHCND,
    linewidth=2.2,
    linestyle="-",
    alpha=0.98,
    zorder=5
)

# ------------------------------------------------------------
# Real observed markers only
# ------------------------------------------------------------

obs_valid = obs_line.dropna(
    subset=["GHCNd_TMAX_C"]
)

ax.plot(
    obs_valid["DATE"],
    obs_valid["GHCNd_TMAX_C"],
    linestyle="None",
    marker="s",
    markersize=4.6,
    markerfacecolor=COL_GHCND,
    markeredgecolor="white",
    markeredgewidth=0.5,
    label="GHCNd Tmax",
    zorder=6
)

# ============================================================
# ERA5 Tmax
# ============================================================

ax.plot(
    df_plot["DATE"],
    df_plot["ERA5_TMAX_C"],
    color=COL_ERA5,
    linewidth=2.0,
    linestyle="-",
    marker="s",
    markersize=4.2,
    markerfacecolor=COL_ERA5,
    markeredgecolor="white",
    markeredgewidth=0.45,
    alpha=0.96,
    label="ERA5 Tmax",
    zorder=4
)
# ------------------------------------------------------------
# P95 thresholds
# ------------------------------------------------------------

ax.axhline(
    obs_p95,
    color=COL_GHCND,
    linestyle="--",
    linewidth=1.5,
    alpha=0.75,
    label="GHCNd P95"
)

ax.axhline(
    era5_p95,
    color=COL_ERA5,
    linestyle=":",
    linewidth=1.7,
    alpha=0.82,
    label="ERA5 P95"
)

# ------------------------------------------------------------
# Event shading
# Red highlight, June 7 to June 8 only.
# ------------------------------------------------------------

ax.axvspan(
    pd.to_datetime(EVENT_START),
    pd.to_datetime(EVENT_END),
    color="red",
    alpha=0.12,
    zorder=0
)

# ------------------------------------------------------------
# Labels
# ------------------------------------------------------------

ax.set_ylabel("Daily Tmax (°C)")
ax.set_xlabel("Date")

# ------------------------------------------------------------
# Grid
# ------------------------------------------------------------

ax.grid(
    True,
    linestyle="--",
    linewidth=0.5,
    alpha=0.32
)

# ------------------------------------------------------------
# Legend
# Bottom-left
# ------------------------------------------------------------

ax.legend(
    frameon=False,
    loc="lower left",
    bbox_to_anchor=(0.08, 0.02)
)

# ------------------------------------------------------------
# Limits
# ------------------------------------------------------------

ax.set_xlim(
    pd.to_datetime(PLOT_START),
    pd.to_datetime(PLOT_END)
)

# ------------------------------------------------------------
# X-axis tick control
# ------------------------------------------------------------

ax.xaxis.set_major_locator(
    mdates.DayLocator(interval=X_TICK_INTERVAL_DAYS)
)

ax.xaxis.set_major_formatter(
    mdates.DateFormatter(X_TICK_FORMAT)
)

plt.setp(
    ax.get_xticklabels(),
    rotation=0,
    ha="center"
)

# ------------------------------------------------------------
# Clean layout
# ------------------------------------------------------------

fig.tight_layout()

# ------------------------------------------------------------
# Save
# ------------------------------------------------------------

fig.savefig(
    OUT_DIR / "validation_timeseries_Q1.png",
    dpi=600,
    bbox_inches="tight"
)

fig.savefig(
    OUT_DIR / "validation_timeseries_Q1.pdf",
    bbox_inches="tight"
)

plt.close(fig)

# ============================================================
# FIGURE B
# Q1 SCATTER
# Uses only overlapping valid ERA5-GHCNd dates.
# ============================================================

fig, ax = plt.subplots(
    figsize=(4.3, 4.1),
    dpi=300
)

ax.scatter(
    df_metrics["GHCNd_TMAX_C"],
    df_metrics["ERA5_TMAX_C"],
    s=42,
    linewidth=0.55,
    edgecolor="black",
    alpha=0.88
)

min_val = min(
    df_metrics["GHCNd_TMAX_C"].min(),
    df_metrics["ERA5_TMAX_C"].min()
) - 1

max_val = max(
    df_metrics["GHCNd_TMAX_C"].max(),
    df_metrics["ERA5_TMAX_C"].max()
) + 1

ax.plot(
    [min_val, max_val],
    [min_val, max_val],
    linestyle="--",
    linewidth=1.4
)

ax.set_xlim(min_val, max_val)
ax.set_ylim(min_val, max_val)

ax.set_xlabel("GHCNd Tmax (°C)")
ax.set_ylabel("ERA5 Tmax (°C)")

metrics_text = (
    f"r = {corr:.2f}\n"
    f"RMSE = {rmse:.2f} °C\n"
    f"Bias = {bias:.2f} °C"
)

ax.text(
    0.05,
    0.95,
    metrics_text,
    transform=ax.transAxes,
    ha="left",
    va="top",
    fontsize=9,
    bbox=dict(
        facecolor="white",
        edgecolor="none",
        alpha=0.88
    )
)

ax.grid(
    True,
    linestyle="--",
    linewidth=0.5,
    alpha=0.32
)

fig.tight_layout()

fig.savefig(
    OUT_DIR / "validation_scatter_Q1.png",
    dpi=600,
    bbox_inches="tight"
)

fig.savefig(
    OUT_DIR / "validation_scatter_Q1.pdf",
    bbox_inches="tight"
)

plt.close(fig)

# ============================================================
# PRINT SUMMARY
# ============================================================

print("\n================================================")
print("VALIDATION SUMMARY")
print("================================================")

print(f"\nStation: {STATION_NAME}")
print(f"Event  : {EVENT_START} to {EVENT_END}")

print(f"\nObserved P95 : {obs_p95:.2f} °C")
print(f"ERA5 P95     : {era5_p95:.2f} °C")

print(f"\nRMSE : {rmse:.2f} °C")
print(f"MAE  : {mae:.2f} °C")
print(f"Bias : {bias:.2f} °C")
print(f"r    : {corr:.2f}")

print(f"\nObserved exceedance days : {ghcnd_hits}")
print(f"ERA5 exceedance days     : {era5_hits}")

print(f"\nOverlapping validation days : {len(df_metrics)}")
print(f"ERA5 plot-window days       : {df_plot['ERA5_TMAX_C'].notna().sum()}")
print(f"GHCNd plot-window days      : {df_plot['GHCNd_TMAX_C'].notna().sum()}")

print("\nSaved outputs to:")
print(OUT_DIR)
print("================================================")