#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Power-law scaling - THIRD version: ONE LARGEST ellipse per EVENT (n=51).

Dr. Najibi: "select the 51 ellipses that are the largest among the days of the
compound event (3+4+20+24) and apply the power-law scaling; combine all types for
the main result." This keeps a single largest-area ellipse per ``new_event_id``,
so n = number of events = 51. Same Clauset methodology as Task 6, so it is
directly comparable to the n=760 (all) and n=395 (largest-per-day) versions.

MAIN result = pooled / all-types combined. By-type fits are produced only as
LOW-n diagnostics (Type 1 n=3, Type 2 n=4, Type 3 n=20, Type 4 n=24).

Does NOT overwrite the all-ellipse or largest-per-day analyses.

Outputs -> reproduced/power_law/largest_event_ellipse/
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
import task6_powerlaw as PL       # noqa: E402  (reuse validated power-law math)
import power_law_largest_daily_ellipse as LD  # noqa: E402  (reuse CCDF helpers)
import matplotlib.pyplot as plt   # noqa: E402
from _clean_paths import MASTER_CSV, GENERATED_DIR, data_file  # noqa: E402

GM = os.path.join(GENERATED_DIR, "power_law")
OUT = os.path.join(GM, "largest_event_ellipse")
POOLED_DIR = os.path.join(OUT, "all_types_pooled")
BYTYPE_DIR = os.path.join(OUT, "by_type")
DIAG_DIR = os.path.join(OUT, "individual_type_diagnostics")

# Comparison-table inputs (repair documented in docs/SANITIZATION_NOTES.md).
# (The legacy daily-adaptive all-ellipse comparison table is excluded from
# this release; its comparison row is not produced.)
B_ALL = os.environ.get(
    "SCORCH_T6_NEW_TABLE",
    data_file("power_law_results_table.csv", "power_law", "statistics"))
C_DAILY = os.path.join(GM, "largest_daily_ellipse",
                       "power_law_results_table.csv")
if not os.path.exists(C_DAILY):  # fall back to the deposit copy
    C_DAILY = data_file("power_law_results_table.csv",
                        "power_law", "largest_daily_ellipse")
N_BOOT = 5000
SEED = 20260617
LABEL = "Largest ellipse per event (n=51) - pooled CCDF with power-law tail"
XLABEL = "Largest-per-event ellipse area A (km$^2$)"


def build_largest_per_event():
    df = pd.read_csv(MASTER_CSV)
    df["date"] = df["date"].astype(str)
    idx = df.groupby("new_event_id")["ellipse_area_km2"].idxmax()
    return df.loc[idx].sort_values("new_event_id").reset_index(drop=True)


# CCDF using the largest-daily helpers but with this version's title/xlabel.
def pooled_ccdf(res):
    a = np.sort(res["_data"])
    fig, ax = plt.subplots(figsize=(7.6, 6.0))
    x, c = LD._ccdf(a)
    ax.loglog(x, c, ".", ms=4.0, color="0.35", label="Empirical CCDF")
    xt, ct = LD._fit_tail(res["xmin"], res["alpha"], res["n_total"],
                          res["n_tail"], a.max())
    ax.loglog(xt, ct, "-", color="#c2185b", lw=2.0,
              label=f"Power-law tail (alpha={res['alpha']:.2f})")
    ax.axvline(res["xmin_boot_median"], ls="--", color="#1565c0", lw=1.4,
               label="bootstrap median A_min")
    ax.set_xlabel(XLABEL)
    ax.set_ylabel("P(area >= A)")
    ax.set_title(LABEL, fontsize=12, fontweight="bold")
    ax.legend(loc="upper right", fontsize=9, framealpha=0.9).set_zorder(20)
    details = (f"n = {res['n_total']}\nn in tail = {res['n_tail']} "
               f"({res['pct_tail']:.1f}%)\nA_min = {res['xmin']:.3g} km$^2$\n"
               f"alpha = {res['alpha']:.3f}\np = {res['p_value']:.4f} -> "
               f"{'rejected' if res['rejected_at_0p10'] else 'not rejected'} (0.10)"
               "\n(n=51: small sample - low statistical power)")
    ax.text(0.02, 0.02, details, transform=ax.transAxes, fontsize=9, va="bottom",
            ha="left", zorder=20,
            bbox=dict(boxstyle="round,pad=0.5", fc="white", ec="0.5", alpha=0.92))
    fig.tight_layout()
    return S.save(fig, os.path.join(OUT, "largest_event_ellipse_pooled_ccdf"),
                 formats=("png", "pdf"))


def bytype_ccdf(per_type):
    fig, ax = plt.subplots(figsize=(8.0, 6.2))
    detail = []
    for t in sorted(per_type):
        res = per_type[t]
        a = np.sort(res["_data"])
        col = S.type_color(t)
        x, c = LD._ccdf(a)
        ax.loglog(x, c, ".", ms=4.0, color=col, alpha=0.75,
                  label=f"{S.TYPE_LABELS[t]} ({S.TYPE_NAMES[t]}), n={res['n_total']}")
        xt, ct = LD._fit_tail(res["xmin"], res["alpha"], res["n_total"],
                              res["n_tail"], a.max())
        ax.loglog(xt, ct, "-", color=col, lw=1.6)
        detail.append(f"{S.TYPE_LABELS[t]}: a={res['alpha']:.2f}, "
                      f"p={res['p_value']:.3f}")
    ax.set_xlabel(XLABEL)
    ax.set_ylabel("P(area >= A)")
    ax.set_title("Largest ellipse per event - per-type CCDFs (LOW-n diagnostics)",
                 fontsize=12, fontweight="bold")
    ax.legend(loc="upper right", fontsize=8.5, framealpha=0.9).set_zorder(20)
    ax.text(0.02, 0.02, "\n".join(detail) + "\n(low n per type - diagnostic only)",
            transform=ax.transAxes, fontsize=8.5, va="bottom", ha="left", zorder=20,
            bbox=dict(boxstyle="round,pad=0.5", fc="white", ec="0.5", alpha=0.92))
    fig.tight_layout()
    return S.save(fig, os.path.join(OUT, "largest_event_ellipse_by_type_ccdf"),
                 formats=("png", "pdf"))


def diag_ccdf(t, res):
    a = np.sort(res["_data"])
    col = S.type_color(t)
    fig, ax = plt.subplots(figsize=(7.0, 5.8))
    x, c = LD._ccdf(a)
    ax.loglog(x, c, ".", ms=5, color=col, label=f"{S.TYPE_LABELS[t]} empirical")
    xt, ct = LD._fit_tail(res["xmin"], res["alpha"], res["n_total"],
                          res["n_tail"], a.max())
    ax.loglog(xt, ct, "-", color="#222", lw=2.0,
              label=f"power-law tail (alpha={res['alpha']:.2f})")
    ax.set_xlabel(XLABEL)
    ax.set_ylabel("P(area >= A)")
    ax.set_title(f"{S.TYPE_LABELS[t]} ({S.TYPE_NAMES[t]}) - largest-per-event CCDF "
                 f"(n={res['n_total']}, diagnostic)", fontsize=11, fontweight="bold")
    ax.legend(loc="upper right", fontsize=9, framealpha=0.9).set_zorder(20)
    details = (f"n = {res['n_total']}\nA_min = {res['xmin']:.3g} km$^2$\n"
               f"alpha = {res['alpha']:.3f}\np = {res['p_value']:.4f}\n"
               "(low n - diagnostic only)")
    ax.text(0.02, 0.02, details, transform=ax.transAxes, fontsize=8.5, va="bottom",
            ha="left", zorder=20,
            bbox=dict(boxstyle="round,pad=0.5", fc="white", ec="0.5", alpha=0.92))
    fig.tight_layout()
    return S.save(fig, os.path.join(DIAG_DIR, f"type{t}_ccdf_diagnostic"),
                 formats=("png", "pdf"))


def _pooled(path, label):
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    r = df[df["group"] == "All types (pooled)"]
    if r.empty:
        return None
    r = r.iloc[0]
    return dict(version=label, n=int(r["n_total"]), n_tail=int(r["n_tail"]),
                pct_tail=round(float(r["pct_tail"]), 1),
                Amin_km2=round(float(r["Amin_point_km2"]), 0),
                alpha=round(float(r["alpha_point"]), 3),
                p_value=round(float(r["p_value"]), 4),
                decision="REJECTED" if bool(r["rejected_at_0.10"]) else "not rejected")


def main():
    for d in (OUT, POOLED_DIR, BYTYPE_DIR, DIAG_DIR):
        os.makedirs(d, exist_ok=True)
    S.apply()

    sel = build_largest_per_event()
    assert sel.shape[0] == 51, f"expected 51 rows, got {sel.shape[0]}"
    assert sel["new_event_id"].is_unique, "new_event_id must be unique"
    counts = sel["v3_type"].value_counts().sort_index().to_dict()
    assert counts == {1: 3, 2: 4, 3: 20, 4: 24}, counts
    assert int(sel.loc[sel["new_event_id"] == 14, "v3_type"].iloc[0]) == 3
    sel.to_csv(os.path.join(OUT, "largest_ellipse_per_event_global_max.csv"),
               index=False)
    with pd.ExcelWriter(
            os.path.join(OUT, "largest_ellipse_per_event_global_max.xlsx"),
            engine="openpyxl") as xw:
        sel.to_excel(xw, sheet_name="largest_per_event", index=False)

    # MAIN: pooled, all types combined
    pooled = PL.analyze_group("All types (pooled)",
                              sel["ellipse_area_km2"].to_numpy(float), N_BOOT, SEED)
    PL.save_group_csvs(pooled, POOLED_DIR, "pooled")
    table = [PL.results_row(pooled)]
    per_type = {}
    for t in (1, 2, 3, 4):
        a = sel.loc[sel["v3_type"] == t, "ellipse_area_km2"].to_numpy(float)
        res = PL.analyze_group(f"Type {t}", a, N_BOOT, SEED + t)
        per_type[t] = res
        PL.save_group_csvs(res, BYTYPE_DIR, f"type{t}")
        table.append(PL.results_row(res))
    tab = pd.DataFrame(table)
    tab.to_csv(os.path.join(OUT, "power_law_results_table.csv"), index=False)

    pooled_ccdf(pooled)
    bytype_ccdf(per_type)
    for t in (1, 2, 3, 4):
        diag_ccdf(t, per_type[t])
    PL.fig_pooled_alpha_box(pooled, os.path.join(POOLED_DIR, "pooled_bootstrap_alpha"))

    def rj(v):
        return "REJECT power-law plausibility" if bool(v) else "retain (not rejected)"
    summ = pd.DataFrame([dict(
        dataset_group=r["group"], n_ellipses=int(r["n_total"]),
        n_tail=int(r["n_tail"]), pct_tail=round(float(r["pct_tail"]), 1),
        xmin_Amin_km2=round(float(r["Amin_point_km2"]), 0),
        alpha_exponent=round(float(r["alpha_point"]), 3),
        gof_p_value=round(float(r["p_value"]), 4),
        decision_at_0p10=rj(r["rejected_at_0.10"]),
        note=("MAIN result" if r["group"] == "All types (pooled)"
              else "low-n diagnostic only")) for r in table])
    summ.to_csv(os.path.join(OUT, "power_law_largest_event_ellipse_summary.csv"),
                index=False)

    # 4-way comparison (pooled)
    rows = []
    for path, lab in [(B_ALL, "B: global-max (all ellipses)"),
                      (C_DAILY, "C: global-max (largest per event-day)")]:
        r = _pooled(path, lab)
        if r is not None:
            rows.append(r)
    rows.append(dict(version="D: global-max (largest per event)",
                     n=int(pooled["n_total"]), n_tail=int(pooled["n_tail"]),
                     pct_tail=round(float(pooled["pct_tail"]), 1),
                     Amin_km2=round(float(pooled["xmin"]), 0),
                     alpha=round(float(pooled["alpha"]), 3),
                     p_value=round(float(pooled["p_value"]), 4),
                     decision="REJECTED" if pooled["rejected_at_0p10"]
                     else "not rejected"))
    comp = pd.DataFrame(rows)[["version", "n", "n_tail", "pct_tail", "Amin_km2",
                               "alpha", "p_value", "decision"]]
    comp.to_csv(os.path.join(
        OUT, "power_law_old_vs_globalmax_vs_largestdaily_vs_largestevent_comparison.csv"),
        index=False)

    write_report(sel, summ, comp, pooled)

    print(f"[LARGEST-EVENT] n={sel.shape[0]} type counts={counts} "
          f"event14=Type {int(sel.loc[sel['new_event_id']==14,'v3_type'].iloc[0])}")
    print(f"[LARGEST-EVENT] pooled: alpha={pooled['alpha']:.2f} "
          f"Amin={pooled['xmin']:,.0f} tail={pooled['n_tail']} "
          f"({pooled['pct_tail']:.1f}%) p={pooled['p_value']:.4f} "
          f"reject={pooled['rejected_at_0p10']}")
    print(comp.to_string(index=False))
    print(f"[LARGEST-EVENT] outputs -> {os.path.relpath(OUT, REPO_ROOT)}")


def write_report(sel, summ, comp, pooled):
    areas = sel["ellipse_area_km2"].to_numpy(float)
    p = pooled
    B = _pooled(B_ALL, "B")
    C = _pooled(C_DAILY, "C")
    L = []
    L.append("# Power-law scaling - LARGEST ellipse per EVENT (n=51, global-max)\n")
    L.append("_Dr. Najibi: select the 51 ellipses that are the largest among the "
             "days of each compound event (3+4+20+24) and run the scaling, combining "
             "all types. Same Clauset methodology as Task 6 (5000 bootstraps, seed "
             "20260617). The MAIN result is the pooled all-types fit; per-type fits "
             "are low-n diagnostics only._\n")
    L.append("## 1. Dataset\n")
    L.append(f"- Rows = **{sel.shape[0]}** (one largest-area ellipse per event; "
             "`new_event_id` unique).")
    L.append("- Type counts: Type 1=3, Type 2=4, Type 3=20, Type 4=24 (=51). "
             "Event 14 = Type 3.")
    L.append(f"- Median selected area = **{np.median(areas)/1e6:.2f}M km^2**; "
             f"min={areas.min()/1e6:.2f}M, max={areas.max()/1e6:.2f}M km^2.\n")
    L.append("## 2. MAIN result - pooled / all types combined\n")
    L.append(f"- **n = {p['n_total']}**, fitted **alpha = {p['alpha']:.2f}**, "
             f"**A_min = {p['xmin']:,.0f} km^2**, tail = **{p['n_tail']} "
             f"({p['pct_tail']:.1f}%)**, GoF **p = {p['p_value']:.3f}** -> "
             f"**{'REJECTED' if p['rejected_at_0p10'] else 'NOT rejected'}** at 0.10.\n")
    L.append("## 3. Results table (incl. low-n per-type diagnostics)\n")
    L.append(summ.to_markdown(index=False))
    L.append("\n## 4. A vs B vs C vs D (pooled, all types)\n")
    L.append(comp.to_markdown(index=False))
    L.append("")
    L.append("## 5. Interpretation for Dr. Najibi\n")
    pB = B["p_value"] if B else float("nan")
    pC = C["p_value"] if C else float("nan")
    L.append(f"1. **Ellipses used:** {p['n_total']} (one largest per event).")
    L.append("2. **Type counts:** 3 / 4 / 20 / 24 (event 14 = Type 3).")
    L.append(f"3. **alpha = {p['alpha']:.2f}, A_min = {p['xmin']/1e6:.2f}M km^2, "
             f"p = {p['p_value']:.3f} -> "
             f"{'rejected' if p['rejected_at_0p10'] else 'not rejected'}.**")
    L.append(f"4. **Vs n=760 (all, p={pB:.3f}) and n=395 (largest-daily, p={pC:.3f}):** "
             f"the decision is the same family of outcome "
             f"({'not rejected' if not p['rejected_at_0p10'] else 'rejected'}); "
             "the fit is anchored by the same handful of very large ellipses, so "
             "alpha/A_min stay in the same regime.")
    L.append("5. **Imbalance:** YES - this is the strongest reduction of the "
             "moderate/small-ellipse imbalance: every event contributes exactly one "
             "(its single largest) footprint, so adjacent/secondary small ellipses "
             "are entirely removed.")
    L.append(f"6. **Stronger or weaker evidence?** **Weaker in statistical power.** "
             f"With only {p['n_total']} points (tail = {p['n_tail']}), the "
             "goodness-of-fit test has very little power to reject ANY model, so a "
             "non-rejecting p-value here is largely uninformative - it is NOT stronger "
             "evidence for a power law than the n=760 / n=395 versions.")
    L.append("7. **Safe to claim power-law / scale-free / SOC?** **No.** "
             "Non-rejection is not proof; the sample (51) and tail are small and the "
             f"exponent is steep (alpha~{p['alpha']:.1f}, vs SOC's ~1.5-3). This "
             "version cleans the imbalance but does not provide positive evidence for "
             "scale-free / self-organized-critical behavior.\n")
    L.append("## 6. Files\n")
    L.append("- Dataset: `largest_ellipse_per_event_global_max.csv/.xlsx`")
    L.append("- Results: `power_law_results_table.csv`, "
             "`power_law_largest_event_ellipse_summary.csv`")
    L.append("- Comparison: "
             "`power_law_old_vs_globalmax_vs_largestdaily_vs_largestevent_comparison.csv`")
    L.append("- Figures: `largest_event_ellipse_pooled_ccdf.*` (MAIN), "
             "`largest_event_ellipse_by_type_ccdf.*` (low-n), "
             "`individual_type_diagnostics/`, pooled bootstrap-alpha.\n")
    with open(os.path.join(OUT, "POWER_LAW_LARGEST_EVENT_ELLIPSE_REPORT.md"),
              "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
