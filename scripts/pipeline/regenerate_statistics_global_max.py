#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regenerate summary statistics + power-law scaling on the EVENT-GLOBAL-MAX
master dataset, reusing the validated kernels (no canonical code modified).

Outputs (reproduced/power_law/statistics/):
    * summary_by_type.csv          per-type & overall ellipse/area/geometry stats
    * event_type_summary.csv       per-event rollup (counts, mean area, duration)
    * power_law_results_table.csv  Clauset MLE alpha, xmin, GoF p (pooled+by type)
    * by_type/typeN_bootstrap_alpha.csv / _xmin.csv
    * all_types_pooled/pooled_bootstrap_alpha.csv / _xmin.csv
    * STATISTICS_SUMMARY.md

Usage:
    python scripts/pipeline/regenerate_statistics_global_max.py [--nboot N]
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

_THIS = os.path.abspath(__file__)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_THIS)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "figures", "common"))
import common as C            # noqa: E402
import task6_powerlaw as PL   # noqa: E402  (reuse validated power-law math)
from _clean_paths import GENERATED_DIR, MASTER_CSV  # noqa: E402

# Default input: the deposit master (env SCORCH_MASTER_FILE overrides).
NEW_CSV = os.environ.get("SCORCH_MASTER_FILE", MASTER_CSV)
# Output mirrors the deposit's power_law/statistics/ layout under reproduced/.
OUT = os.environ.get(
    "SCORCH_STATS_OUT_DIR",
    os.path.join(GENERATED_DIR, "power_law", "statistics"))

TYPE_NAMES = {1: "Type 1 (Independent)", 2: "Type 2 (Spatially clustered)",
              3: "Type 3 (Temporally clustered)", 4: "Type 4 (Mixed)"}


def summary_by_type(df):
    rows = []
    groups = [("ALL", df)] + [(f"Type {t}", df[df["v3_type"] == t])
                              for t in (1, 2, 3, 4)]
    for name, g in groups:
        if g.empty:
            continue
        area = g["ellipse_area_km2"].to_numpy(float)
        rows.append(dict(
            group=name,
            n_events=int(g["new_event_id"].nunique()),
            n_event_days=int(g.groupby(["new_event_id", "date"]).ngroups),
            n_ellipses=int(g.shape[0]),
            mean_area_km2=float(np.mean(area)),
            median_area_km2=float(np.median(area)),
            total_area_km2=float(np.sum(area)),
            mean_axis_ratio=float(g["axis_ratio"].mean()),
            mean_orientation_deg=float(g["orientation_deg"].mean()),
            mean_major_axis_km=float(g["major_axis_km"].mean()),
            mean_duration_days=float(
                g.groupby("new_event_id")["duration_days"].first().mean()),
        ))
    return pd.DataFrame(rows)


def event_summary(df):
    g = df.groupby("new_event_id")
    out = g.agg(
        event_id=("event_id", "first"), v3_type=("v3_type", "first"),
        duration_days=("duration_days", "first"),
        n_ellipses=("cluster_id", "size"),
        mean_area_km2=("ellipse_area_km2", "mean"),
        total_area_km2=("ellipse_area_km2", "sum"),
        event_global_eps_max=("event_global_eps_max", "first"),
        event_global_minpts_used=("event_global_minpts_used", "first"),
    ).reset_index()
    return out


def power_law(df, n_boot):
    os.makedirs(os.path.join(OUT, "by_type"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "all_types_pooled"), exist_ok=True)
    table = []
    pooled = PL.analyze_group("pooled", df["ellipse_area_km2"].to_numpy(float),
                              n_boot, C.SEED)
    PL.save_group_csvs(pooled, os.path.join(OUT, "all_types_pooled"), "pooled")
    table.append({"group": "ALL", **PL.results_row(pooled)})
    for t in (1, 2, 3, 4):
        sub = df.loc[df["v3_type"] == t, "ellipse_area_km2"].to_numpy(float)
        if sub.size == 0:
            continue
        res = PL.analyze_group(f"type{t}", sub, n_boot, C.SEED + t)
        PL.save_group_csvs(res, os.path.join(OUT, "by_type"), f"type{t}")
        table.append({"group": TYPE_NAMES[t], **PL.results_row(res)})
    tab = pd.DataFrame(table)
    tab.to_csv(os.path.join(OUT, "power_law_results_table.csv"), index=False)
    return tab


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nboot", type=int, default=2000,
                    help="power-law bootstrap count (canonical used 5000)")
    args = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)
    df = pd.read_csv(NEW_CSV)

    sbt = summary_by_type(df)
    sbt.to_csv(os.path.join(OUT, "summary_by_type.csv"), index=False)
    ev = event_summary(df)
    ev.to_csv(os.path.join(OUT, "event_type_summary.csv"), index=False)
    pl = power_law(df, args.nboot)

    lines = ["# Event-global-max statistics & power-law\n",
             f"Bootstrap replicates: {args.nboot} (canonical run used 5000).\n",
             "## Summary by type\n", sbt.round(3).to_markdown(index=False),
             "\n## Power-law (ellipse area km^2)\n",
             pl.round(4).to_markdown(index=False)]
    with open(os.path.join(OUT, "STATISTICS_SUMMARY.md"), "w",
              encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    print("[STATS] summary_by_type.csv, event_type_summary.csv,",
          "power_law_results_table.csv")
    print(sbt.to_string(index=False))
    print("\n[POWER-LAW]")
    print(pl.to_string(index=False))
    print(f"\n[STATS] outputs -> {os.path.relpath(OUT, REPO_ROOT)}")


if __name__ == "__main__":
    main()
