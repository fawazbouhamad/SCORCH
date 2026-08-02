#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Power-law scaling - SECOND version: ONE LARGEST ellipse per event-day.

Dr. Najibi's sensitivity request: instead of all 760 global-max ellipses (which
include many moderate/small ones), keep only the single largest-area ellipse on
each event-day, so the sample size equals the number of event-days (~395). This
re-tests areal-extent power-law scaling on the dominant daily footprint, using the
SAME Clauset methodology as Task 6 (so results are directly comparable).

Does NOT overwrite the all-ellipse analysis.

Outputs -> reproduced/power_law/largest_daily_ellipse/
  largest_ellipse_per_event_day_global_max.csv / .xlsx
  power_law_results_table.csv  +  power_law_largest_daily_ellipse_summary.csv
  POWER_LAW_LARGEST_DAILY_ELLIPSE_REPORT.md
  largest_daily_ellipse_pooled_ccdf.png/.pdf  + by_type + diagnostics
  pooled / by_type bootstrap_alpha figures + CSVs
  old_vs_new_vs_largest_comparison.csv
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

os.environ.setdefault("MPLBACKEND", "Agg")
_THIS = os.path.abspath(__file__)
_COMMON = os.path.dirname(_THIS)                        # scripts/figures/common
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_COMMON)))
sys.path.insert(0, _COMMON)
import plot_style as S            # noqa: E402
import task6_powerlaw as PL       # noqa: E402  (reuse the validated power-law math)
import matplotlib.pyplot as plt   # noqa: E402
from _clean_paths import MASTER_CSV, GENERATED_DIR, data_file  # noqa: E402

GM = os.path.join(GENERATED_DIR, "power_law")
OUT = os.path.join(GM, "largest_daily_ellipse")
POOLED_DIR = os.path.join(OUT, "all_types_pooled")
BYTYPE_DIR = os.path.join(OUT, "by_type")
DIAG_DIR = os.path.join(OUT, "individual_type_diagnostics")
# Comparison-table input (repair documented in docs/SANITIZATION_NOTES.md):
#   T6_NEW -- global-max all-ellipse power-law table; the deposit ships it at
#             power_law/statistics/power_law_results_table.csv.
# (The legacy daily-adaptive all-ellipse comparison table is excluded from
# this release; its comparison row is not produced.)
T6_NEW = os.environ.get(
    "SCORCH_T6_NEW_TABLE",
    data_file("power_law_results_table.csv", "power_law", "statistics"))
N_BOOT = 5000
SEED = 20260617


# --- one-largest-ellipse-per-event-day selection ------------------------------
def build_largest():
    df = pd.read_csv(MASTER_CSV)
    df["date"] = df["date"].astype(str)
    idx = df.groupby(["new_event_id", "date"])["ellipse_area_km2"].idxmax()
    sel = df.loc[idx].sort_values(["new_event_id", "date"]).reset_index(drop=True)
    return sel


# --- CCDF helpers (same layout as task6_regen_ccdf: legend TR, details BL) -----
def _ccdf(a):
    a = np.sort(a)
    n = a.size
    return a, 1.0 - np.arange(n) / n


def _fit_tail(xmin, alpha, n, n_tail, xmax):
    x = np.logspace(np.log10(xmin), np.log10(xmax), 200)
    return x, (n_tail / n) * (x / xmin) ** (1.0 - alpha)


def pooled_ccdf(res):
    a = np.sort(res["_data"])
    fig, ax = plt.subplots(figsize=(7.6, 6.0))
    x, c = _ccdf(a)
    ax.loglog(x, c, ".", ms=3.5, color="0.35", label="Empirical CCDF")
    xt, ct = _fit_tail(res["xmin"], res["alpha"], res["n_total"], res["n_tail"],
                       a.max())
    ax.loglog(xt, ct, "-", color="#c2185b", lw=2.0,
              label=f"Power-law tail (alpha={res['alpha']:.2f})")
    ax.axvline(res["xmin_boot_median"], ls="--", color="#1565c0", lw=1.4,
               label="bootstrap median A_min")
    ax.set_xlabel("Largest-daily ellipse area A (km$^2$)")
    ax.set_ylabel("P(area >= A)")
    ax.set_title("Largest ellipse per event-day - pooled CCDF with power-law tail",
                 fontsize=12, fontweight="bold")
    ax.legend(loc="upper right", fontsize=9, framealpha=0.9).set_zorder(20)
    details = (f"n = {res['n_total']}\nn in tail = {res['n_tail']} "
               f"({res['pct_tail']:.1f}%)\nA_min = {res['xmin']:.3g} km$^2$\n"
               f"alpha = {res['alpha']:.3f}\np = {res['p_value']:.4f} -> "
               f"{'rejected' if res['rejected_at_0p10'] else 'not rejected'} (0.10)")
    ax.text(0.02, 0.02, details, transform=ax.transAxes, fontsize=9, va="bottom",
            ha="left", zorder=20,
            bbox=dict(boxstyle="round,pad=0.5", fc="white", ec="0.5", alpha=0.92))
    fig.tight_layout()
    return S.save(fig, os.path.join(OUT, "largest_daily_ellipse_pooled_ccdf"),
                 formats=("png", "pdf"))


def bytype_ccdf(per_type):
    fig, ax = plt.subplots(figsize=(8.0, 6.2))
    detail = []
    for t in sorted(per_type):
        res = per_type[t]
        a = np.sort(res["_data"])
        col = S.type_color(t)
        x, c = _ccdf(a)
        ax.loglog(x, c, ".", ms=3.0, color=col, alpha=0.7,
                  label=f"{S.TYPE_LABELS[t]} ({S.TYPE_NAMES[t]})")
        xt, ct = _fit_tail(res["xmin"], res["alpha"], res["n_total"],
                           res["n_tail"], a.max())
        ax.loglog(xt, ct, "-", color=col, lw=1.8)
        ax.axvline(res["xmin_boot_median"], ls="--", color=col, lw=1.0, alpha=0.7)
        detail.append(f"{S.TYPE_LABELS[t]}: alpha={res['alpha']:.2f}, "
                      f"p={res['p_value']:.3f} "
                      f"({'rej' if res['rejected_at_0p10'] else 'not rej'})")
    ax.set_xlabel("Largest-daily ellipse area A (km$^2$)")
    ax.set_ylabel("P(area >= A)")
    ax.set_title("Largest ellipse per event-day - per-type CCDFs",
                 fontsize=12, fontweight="bold")
    ax.legend(loc="upper right", fontsize=8.5, framealpha=0.9).set_zorder(20)
    ax.text(0.02, 0.02, "\n".join(detail), transform=ax.transAxes, fontsize=8.5,
            va="bottom", ha="left", zorder=20,
            bbox=dict(boxstyle="round,pad=0.5", fc="white", ec="0.5", alpha=0.92))
    fig.tight_layout()
    return S.save(fig, os.path.join(OUT, "largest_daily_ellipse_by_type_ccdf"),
                 formats=("png", "pdf"))


def diag_ccdf(t, res):
    a = np.sort(res["_data"])
    col = S.type_color(t)
    fig, ax = plt.subplots(figsize=(7.0, 5.8))
    x, c = _ccdf(a)
    ax.loglog(x, c, ".", ms=4, color=col, label=f"{S.TYPE_LABELS[t]} empirical")
    xt, ct = _fit_tail(res["xmin"], res["alpha"], res["n_total"], res["n_tail"],
                       a.max())
    ax.loglog(xt, ct, "-", color="#222", lw=2.0,
              label=f"power-law tail (alpha={res['alpha']:.2f})")
    ax.axvline(res["xmin_boot_median"], ls="--", color="#1565c0", lw=1.3,
               label="bootstrap median A_min")
    ax.set_xlabel("Largest-daily ellipse area A (km$^2$)")
    ax.set_ylabel("P(area >= A)")
    ax.set_title(f"{S.TYPE_LABELS[t]} ({S.TYPE_NAMES[t]}) - largest-daily CCDF",
                 fontsize=12, fontweight="bold")
    ax.legend(loc="upper right", fontsize=9, framealpha=0.9).set_zorder(20)
    details = (f"n = {res['n_total']}\nn in tail = {res['n_tail']} "
               f"({res['pct_tail']:.1f}%)\nA_min = {res['xmin']:.3g} km$^2$\n"
               f"alpha = {res['alpha']:.3f}\np = {res['p_value']:.4f} -> "
               f"{'rejected' if res['rejected_at_0p10'] else 'not rejected'} (0.10)")
    if res["n_total"] < 20:
        details += "\n(small sample - low confidence)"
    ax.text(0.02, 0.02, details, transform=ax.transAxes, fontsize=8.5, va="bottom",
            ha="left", zorder=20,
            bbox=dict(boxstyle="round,pad=0.5", fc="white", ec="0.5", alpha=0.92))
    fig.tight_layout()
    return S.save(fig, os.path.join(DIAG_DIR, f"type{t}_ccdf_diagnostic"),
                 formats=("png", "pdf"))


def main():
    for d in (OUT, POOLED_DIR, BYTYPE_DIR, DIAG_DIR):
        os.makedirs(d, exist_ok=True)
    S.apply()

    # 1) dataset
    sel = build_largest()
    assert sel.shape[0] == 395, f"expected 395 rows, got {sel.shape[0]}"
    ed_counts = sel["v3_type"].value_counts().sort_index().to_dict()
    assert ed_counts == {1: 3, 2: 4, 3: 75, 4: 313}, ed_counts
    assert int(sel.loc[sel["new_event_id"] == 14, "v3_type"].iloc[0]) == 3
    sel.to_csv(os.path.join(OUT, "largest_ellipse_per_event_day_global_max.csv"),
               index=False)
    with pd.ExcelWriter(
            os.path.join(OUT, "largest_ellipse_per_event_day_global_max.xlsx"),
            engine="openpyxl") as xw:
        sel.to_excel(xw, sheet_name="largest_per_event_day", index=False)

    # 2) power-law (same methodology as Task 6)
    pooled = PL.analyze_group("All types (pooled)",
                              sel["ellipse_area_km2"].to_numpy(float), N_BOOT, SEED)
    PL.save_group_csvs(pooled, POOLED_DIR, "pooled")
    per_type, table = {}, [PL.results_row(pooled)]
    for t in (1, 2, 3, 4):
        a = sel.loc[sel["v3_type"] == t, "ellipse_area_km2"].to_numpy(float)
        res = PL.analyze_group(f"Type {t}", a, N_BOOT, SEED + t)
        per_type[t] = res
        PL.save_group_csvs(res, BYTYPE_DIR, f"type{t}")
        table.append(PL.results_row(res))
    tab = pd.DataFrame(table)
    tab.to_csv(os.path.join(OUT, "power_law_results_table.csv"), index=False)

    # figures
    pooled_ccdf(pooled)
    bytype_ccdf(per_type)
    for t in (1, 2, 3, 4):
        diag_ccdf(t, per_type[t])
    PL.fig_pooled_alpha_box(pooled, os.path.join(POOLED_DIR, "pooled_bootstrap_alpha"))
    PL.fig_bytype_alpha_box(per_type, os.path.join(BYTYPE_DIR, "by_type_bootstrap_alpha"))

    # clean summary CSV
    def rj(v):
        return "REJECT power-law plausibility" if bool(v) else "retain (not rejected)"
    summ = pd.DataFrame([dict(
        dataset_group=r["group"], n_ellipses=int(r["n_total"]),
        n_tail=int(r["n_tail"]), pct_tail=round(float(r["pct_tail"]), 1),
        xmin_Amin_km2=round(float(r["Amin_point_km2"]), 0),
        alpha_exponent=round(float(r["alpha_point"]), 3),
        gof_p_value=round(float(r["p_value"]), 4),
        decision_at_0p10=rj(r["rejected_at_0.10"])) for r in table])
    summ.to_csv(os.path.join(OUT, "power_law_largest_daily_ellipse_summary.csv"),
                index=False)

    # 3-way comparison (pooled)
    comp = build_comparison(pooled)
    comp.to_csv(os.path.join(OUT, "old_vs_new_vs_largest_comparison.csv"),
                index=False)

    write_report(sel, tab, summ, pooled, per_type, comp)

    print(f"[LARGEST-DAILY] n={sel.shape[0]} type-day counts={ed_counts} "
          f"event14=Type {int(sel.loc[sel['new_event_id']==14,'v3_type'].iloc[0])}")
    print(f"[LARGEST-DAILY] pooled: alpha={pooled['alpha']:.2f} "
          f"Amin={pooled['xmin']:,.0f} p={pooled['p_value']:.4f} "
          f"reject={pooled['rejected_at_0p10']}")
    print(f"[LARGEST-DAILY] outputs -> {os.path.relpath(OUT, REPO_ROOT)}")
    return dict(summary=summ, pooled=pooled)


def _pooled_row(path):
    if not path or not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    r = df[df["group"] == "All types (pooled)"]
    return r.iloc[0] if not r.empty else None


def build_comparison(pooled_new):
    B = _pooled_row(T6_NEW)        # new global-max, all ellipses
    rows = []
    if B is not None:
        rows.append(dict(version="B: global-max (all ellipses)",
                         n=int(B["n_total"]), Amin_km2=round(float(B["Amin_point_km2"]), 0),
                         alpha=round(float(B["alpha_point"]), 3),
                         p_value=round(float(B["p_value"]), 4),
                         decision="REJECTED" if bool(B["rejected_at_0.10"]) else "not rejected"))
    rows.append(dict(version="C: global-max (largest ellipse per event-day)",
                     n=int(pooled_new["n_total"]),
                     Amin_km2=round(float(pooled_new["xmin"]), 0),
                     alpha=round(float(pooled_new["alpha"]), 3),
                     p_value=round(float(pooled_new["p_value"]), 4),
                     decision="REJECTED" if pooled_new["rejected_at_0p10"] else "not rejected"))
    return pd.DataFrame(rows)


def write_report(sel, tab, summ, pooled, per_type, comp):
    areas = sel["ellipse_area_km2"].to_numpy(float)
    p = pooled
    L = []
    L.append("# Power-law scaling - LARGEST ellipse per event-day (global-max)\n")
    L.append("_Dr. Najibi's second/sensitivity version: keep only the single "
             "largest-area ellipse on each event-day, so n = number of event-days "
             "(395) rather than all 760 ellipses. Same Clauset methodology as "
             "Task 6 (5000 bootstraps, seed 20260617)._\n")
    L.append("## Dataset\n")
    L.append(f"- Rows = **{sel.shape[0]}** (one largest ellipse per event-day).")
    L.append("- Event-day counts by type: " +
             ", ".join(f"Type {t}={int((sel['v3_type']==t).sum())}"
                       for t in (1, 2, 3, 4)) + " (= 3/4/75/313).")
    L.append("- Event 14 = Type 3. Selection: max `ellipse_area_km2` within each "
             "(new_event_id, date).\n")
    L.append("## Power-law results (largest-daily)\n")
    L.append(summ.to_markdown(index=False))
    L.append("\n## A vs B vs C (pooled)\n")
    L.append(comp.to_markdown(index=False))
    L.append("")
    L.append(f"- Median largest-daily area = **{np.median(areas)/1e6:.2f}M km^2** "
             f"(vs 1.31M km^2 across all 760 ellipses): keeping the daily maximum "
             "lifts the typical area and removes the small/moderate pile-up.\n")
    L.append("## Interpretation for Dr. Najibi\n")
    pooled_B = _pooled_row(T6_NEW)
    pB = float(pooled_B["p_value"]) if pooled_B is not None else float("nan")
    aB = float(pooled_B["alpha_point"]) if pooled_B is not None else float("nan")
    xminB = float(pooled_B["Amin_point_km2"]) if pooled_B is not None else float("nan")
    L.append(f"- **p-value:** largest-daily pooled p = **{p['p_value']:.3f}** "
             f"(all-ellipse global-max p = {pB:.3f}). "
             f"{'Higher -> even less reason to reject' if p['p_value']>=pB else 'Lower'}; "
             "in both cases a pure power law is **"
             f"{'not rejected' if not p['rejected_at_0p10'] else 'rejected'}** at 0.10.")
    L.append(f"- **Amin:** largest-daily Amin = **{p['xmin']/1e6:.2f}M km^2** "
             f"(all-ellipse {xminB/1e6:.2f}M). "
             f"{'Moves down' if p['xmin']<xminB else 'Moves up/similar'} - more of "
             "the (now larger) ellipses inform the fit.")
    L.append(f"- **alpha:** largest-daily alpha = **{p['alpha']:.2f}** "
             f"(all-ellipse {aB:.2f}).")
    L.append(f"- **Tail fraction:** {p['pct_tail']:.1f}% of the 395 daily maxima "
             f"are in the fitted tail ({p['n_tail']} points) - "
             "less extreme truncation than the 5.7% of the all-ellipse version, so "
             "this estimate is **less power-limited**.")
    L.append("- **Imbalance:** YES, this reduces the moderate/small-ellipse imbalance "
             "by construction - each event-day contributes exactly one (its largest) "
             "footprint, so adjacent/secondary small ellipses no longer flood the body.")
    L.append("- **Stronger or weaker evidence?** It is a **cleaner, better-balanced** "
             "test (one dominant footprint per day, larger informative tail). If it "
             "also does not reject the power law, that is **more credible "
             "non-rejection** than the all-ellipse version - but a steep alpha and "
             "modest tail still mean this is **'power law not excluded', NOT positive "
             "proof of scale-free / self-organized-critical behavior.** Use cautious "
             "wording.\n")
    L.append("## Files\n")
    L.append("- Dataset: `largest_ellipse_per_event_day_global_max.csv/.xlsx`")
    L.append("- Results: `power_law_results_table.csv`, "
             "`power_law_largest_daily_ellipse_summary.csv`")
    L.append("- Comparison: `old_vs_new_vs_largest_comparison.csv`")
    L.append("- Figures: `largest_daily_ellipse_pooled_ccdf.*`, "
             "`largest_daily_ellipse_by_type_ccdf.*`, "
             "`individual_type_diagnostics/`, bootstrap-alpha figures.\n")
    with open(os.path.join(OUT, "POWER_LAW_LARGEST_DAILY_ELLIPSE_REPORT.md"),
              "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
