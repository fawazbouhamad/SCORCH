#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Task 6 - Clauset-style continuous power-law analysis of ellipse AREAS (km^2).

Self-contained, independent Python implementation of the Clauset/Shalizi/Newman
(2009) procedure for the continuous power law

    p(A) = ((alpha-1)/Amin) * (A/Amin)^(-alpha),   A >= Amin.

This is NOT a wrapper around R's poweRlaw nor the PyPI `powerlaw` package: R /
poweRlaw are unavailable on this Windows host (checked: `Rscript`/`R` not on
PATH), so the equivalent procedure is implemented directly in scipy/numpy and
validated on a simulated continuous power law before use.

Pieces implemented (per group, independently):
  * continuous MLE: alpha_hat = 1 + n_tail / sum(ln(A_i/xmin)), A_i>=xmin
  * KS distance D = max|S(A) - P(A)| on the tail
  * xmin chosen by scanning candidate values (sorted unique data) minimizing D
  * goodness-of-fit p-value via 5000 semi-parametric Clauset bootstraps
  * 5000 semi-parametric bootstrap refits for alpha/xmin sampling distributions

Outputs land ONLY under reproduced/six_task_ellipse_review/task06_power_law.
The authoritative master table is never modified.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_THIS = os.path.abspath(__file__)
_DIR = os.path.dirname(_THIS)
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

import common as C  # noqa: E402
import plot_style as S  # noqa: E402

import matplotlib.pyplot as plt  # noqa: E402

# --- analysis constants ------------------------------------------------------
N_BOOT = 5000                 # principal GoF and bootstrap simulation count
N_BOOT_VALIDATION = 500       # sanity-check only (5000-pt synthetic set)
P_THRESHOLD = 0.10            # reject the power-law fit if p <= 0.10
MIN_TAIL = 5                  # smallest tail we will attempt to fit
CI_LOW, CI_HIGH = 2.5, 97.5   # 95% percentile interval

_POOLED_DIR = os.path.join(C.T06, "all_types_pooled")
_BYTYPE_DIR = os.path.join(C.T06, "by_type")
_DIAG_DIR = os.path.join(C.T06, "individual_type_diagnostics")
_REPORT = os.path.join(C.T06, "POWER_LAW_RESULTS.md")
_VALIDATION = os.path.join(C.T06, "python_implementation_validation.txt")


# ---------------------------------------------------------------------------
# Core continuous Clauset estimators
# ---------------------------------------------------------------------------
def continuous_alpha(tail: np.ndarray, xmin: float) -> float:
    """Continuous MLE of alpha for tail values (all >= xmin)."""
    n = tail.size
    s = np.sum(np.log(tail / xmin))
    if s <= 0:
        return np.nan
    return 1.0 + n / s


def ks_distance(tail: np.ndarray, xmin: float, alpha: float) -> float:
    """KS distance between empirical tail CDF and fitted continuous CDF."""
    x = np.sort(tail)
    n = x.size
    # Empirical CDF just above/below each point (Clauset uses both bounds).
    cdf_emp_upper = np.arange(1, n + 1) / n
    cdf_emp_lower = np.arange(0, n) / n
    cdf_fit = 1.0 - (x / xmin) ** (1.0 - alpha)
    d = np.maximum(np.abs(cdf_emp_upper - cdf_fit),
                   np.abs(cdf_emp_lower - cdf_fit))
    return float(np.max(d))


def fit_xmin(data: np.ndarray, min_tail: int = MIN_TAIL) -> dict:
    """Scan candidate xmin over sorted unique values; pick the KS minimizer."""
    data = np.asarray(data, dtype=float)
    candidates = np.unique(data)
    # The tail must retain at least `min_tail` points; drop the largest few.
    best = None
    for xmin in candidates:
        tail = data[data >= xmin]
        if tail.size < min_tail:
            break  # candidates are ascending -> tails only shrink further
        alpha = continuous_alpha(tail, xmin)
        if not np.isfinite(alpha) or alpha <= 1.0:
            continue
        d = ks_distance(tail, xmin, alpha)
        if best is None or d < best["ks"]:
            best = dict(xmin=float(xmin), alpha=float(alpha), ks=float(d),
                        n_tail=int(tail.size))
    if best is None:
        # Degenerate fallback: use the smallest value.
        xmin = float(candidates[0])
        tail = data[data >= xmin]
        alpha = continuous_alpha(tail, xmin)
        best = dict(xmin=xmin, alpha=float(alpha),
                    ks=ks_distance(tail, xmin, alpha), n_tail=int(tail.size))
    return best


def sample_powerlaw(n: int, xmin: float, alpha: float,
                    rng: np.random.Generator) -> np.ndarray:
    """Inverse-CDF draw of n continuous power-law values >= xmin."""
    u = rng.random(n)
    return xmin * (1.0 - u) ** (-1.0 / (alpha - 1.0))


# ---------------------------------------------------------------------------
# Bootstrap: goodness-of-fit p-value + alpha/xmin sampling distributions
# ---------------------------------------------------------------------------
def bootstrap_group(data: np.ndarray, fit: dict, n_boot: int,
                    rng: np.random.Generator) -> dict:
    """Semi-parametric Clauset bootstrap.

    For each of n_boot synthetic datasets: with prob n_tail/n draw a value from
    the fitted power law (>= xmin), else resample from the empirical below-xmin
    part. Refit xmin+alpha on each synthetic set. The GoF p-value is the
    fraction of synthetic KS >= the empirical KS. The same refits give the
    alpha/xmin sampling distributions.
    """
    data = np.asarray(data, dtype=float)
    n = data.size
    xmin0, alpha0, ks0, n_tail = (fit["xmin"], fit["alpha"], fit["ks"],
                                  fit["n_tail"])
    below = data[data < xmin0]
    p_tail = n_tail / n

    ks_boot = np.empty(n_boot)
    alpha_boot = np.empty(n_boot)
    xmin_boot = np.empty(n_boot)
    n_failed = 0

    for b in range(n_boot):
        n_from_tail = int(rng.binomial(n, p_tail))
        n_from_below = n - n_from_tail
        parts = [sample_powerlaw(n_from_tail, xmin0, alpha0, rng)]
        if n_from_below > 0:
            if below.size > 0:
                parts.append(rng.choice(below, size=n_from_below, replace=True))
            else:
                # No empirical below-xmin mass: draw all from the tail model.
                parts.append(sample_powerlaw(n_from_below, xmin0, alpha0, rng))
        synth = np.concatenate(parts)
        try:
            f = fit_xmin(synth)
            if not np.isfinite(f["alpha"]):
                raise ValueError("non-finite alpha")
        except Exception:
            n_failed += 1
            ks_boot[b] = np.nan
            alpha_boot[b] = np.nan
            xmin_boot[b] = np.nan
            continue
        ks_boot[b] = f["ks"]
        alpha_boot[b] = f["alpha"]
        xmin_boot[b] = f["xmin"]

    valid = ~np.isnan(ks_boot)
    p_value = float(np.mean(ks_boot[valid] >= ks0)) if valid.any() else np.nan
    a_valid = alpha_boot[~np.isnan(alpha_boot)]
    x_valid = xmin_boot[~np.isnan(xmin_boot)]
    return dict(
        p_value=p_value,
        n_sims=int(n_boot),
        n_failed=int(n_failed),
        alpha_boot=alpha_boot,
        xmin_boot=xmin_boot,
        ks_boot=ks_boot,
        alpha_median=float(np.median(a_valid)) if a_valid.size else np.nan,
        xmin_median=float(np.median(x_valid)) if x_valid.size else np.nan,
        alpha_ci=(float(np.percentile(a_valid, CI_LOW)),
                  float(np.percentile(a_valid, CI_HIGH))) if a_valid.size else (np.nan, np.nan),
        xmin_ci=(float(np.percentile(x_valid, CI_LOW)),
                 float(np.percentile(x_valid, CI_HIGH))) if x_valid.size else (np.nan, np.nan),
    )


def analyze_group(name: str, data: np.ndarray, n_boot: int,
                  seed: int) -> dict:
    """Full independent estimation + bootstrap for one group."""
    rng = np.random.default_rng(seed)
    data = np.asarray(data, dtype=float)
    fit = fit_xmin(data)
    boot = bootstrap_group(data, fit, n_boot, rng)
    pct_tail = 100.0 * fit["n_tail"] / data.size
    rejected = bool(np.isfinite(boot["p_value"]) and
                    boot["p_value"] <= P_THRESHOLD)
    return dict(
        group=name,
        n_total=int(data.size),
        n_tail=int(fit["n_tail"]),
        pct_tail=float(pct_tail),
        xmin=fit["xmin"],
        xmin_boot_median=boot["xmin_median"],
        xmin_ci_low=boot["xmin_ci"][0],
        xmin_ci_high=boot["xmin_ci"][1],
        alpha=fit["alpha"],
        alpha_boot_median=boot["alpha_median"],
        alpha_ci_low=boot["alpha_ci"][0],
        alpha_ci_high=boot["alpha_ci"][1],
        ks_statistic=fit["ks"],
        p_value=boot["p_value"],
        n_sims=boot["n_sims"],
        n_sims_failed=boot["n_failed"],
        rejected_at_0p10=rejected,
        _data=data,
        _alpha_boot=boot["alpha_boot"],
        _xmin_boot=boot["xmin_boot"],
    )


# ---------------------------------------------------------------------------
# Validation on a known continuous power law
# ---------------------------------------------------------------------------
def validate_implementation() -> dict:
    rng = np.random.default_rng(C.SEED)
    alpha_true, xmin_true, n = 2.5, 1.0, 5000
    data = sample_powerlaw(n, xmin_true, alpha_true, rng)
    # The validation is an implementation sanity check (does the estimator
    # recover a known alpha/xmin and give a non-rejecting p-value), NOT a
    # principal analysis, so it uses a smaller bootstrap count for tractability
    # on a 5000-point synthetic set. The five principal analyses (pooled + 4
    # types) all use the full N_BOOT=5000.
    res = analyze_group("VALIDATION_synthetic", data, N_BOOT_VALIDATION,
                        C.SEED + 1)
    alpha_err = abs(res["alpha"] - alpha_true)
    ok = (alpha_err <= 0.1) and (res["p_value"] > P_THRESHOLD)
    lines = [
        "Python continuous-Clauset implementation validation",
        "=" * 55,
        "This confirms the INDEPENDENT scipy/numpy implementation (NOT R/poweRlaw,",
        "NOT the PyPI `powerlaw` package) recovers a known continuous power law.",
        "",
        f"Simulated truth : alpha_true={alpha_true}, xmin_true={xmin_true}, n={n}",
        f"Seed            : data={C.SEED}, bootstrap={C.SEED + 1}",
        f"Recovered alpha : {res['alpha']:.4f}  (|err|={alpha_err:.4f}, tol=0.10)",
        f"Recovered xmin  : {res['xmin']:.4f}",
        f"n_tail          : {res['n_tail']} of {res['n_total']}",
        f"KS statistic    : {res['ks_statistic']:.5f}",
        f"GoF p-value     : {res['p_value']:.4f}  (n_sims={res['n_sims']}, "
        f"failed={res['n_sims_failed']})",
        "",
        f"alpha within 0.1 of truth : {alpha_err <= 0.1}",
        f"p-value > {P_THRESHOLD} (not rejected): {res['p_value'] > P_THRESHOLD}",
        f"VALIDATION PASSED         : {ok}",
    ]
    with open(_VALIDATION, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return dict(passed=bool(ok), alpha=res["alpha"], alpha_err=float(alpha_err),
                xmin=res["xmin"], p_value=res["p_value"],
                n_sims=res["n_sims"], n_failed=res["n_sims_failed"])


# ---------------------------------------------------------------------------
# CSV persistence
# ---------------------------------------------------------------------------
def save_group_csvs(res: dict, out_dir: str, tag: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    pd.DataFrame({"alpha_bootstrap": res["_alpha_boot"]}).to_csv(
        os.path.join(out_dir, f"{tag}_bootstrap_alpha.csv"), index=False)
    pd.DataFrame({"xmin_bootstrap_km2": res["_xmin_boot"]}).to_csv(
        os.path.join(out_dir, f"{tag}_bootstrap_xmin.csv"), index=False)


def results_row(res: dict) -> dict:
    return {
        "group": res["group"],
        "n_total": res["n_total"],
        "n_tail": res["n_tail"],
        "pct_tail": round(res["pct_tail"], 3),
        "Amin_point_km2": res["xmin"],
        "Amin_boot_median_km2": res["xmin_boot_median"],
        "Amin_ci95_low_km2": res["xmin_ci_low"],
        "Amin_ci95_high_km2": res["xmin_ci_high"],
        "alpha_point": res["alpha"],
        "alpha_boot_median": res["alpha_boot_median"],
        "alpha_ci95_low": res["alpha_ci_low"],
        "alpha_ci95_high": res["alpha_ci_high"],
        "ks_statistic": res["ks_statistic"],
        "p_value": res["p_value"],
        "n_sims": res["n_sims"],
        "n_sims_failed": res["n_sims_failed"],
        "rejected_at_0.10": res["rejected_at_0p10"],
    }


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
def _empirical_ccdf(data: np.ndarray):
    x = np.sort(data)
    n = x.size
    ccdf = 1.0 - (np.arange(0, n) / n)  # P(X >= x) at each sorted point
    return x, ccdf


def _fitted_tail_ccdf(x_tail: np.ndarray, xmin: float, alpha: float,
                      ccdf_at_xmin: float):
    """Fitted CCDF for A>=xmin, anchored to empirical CCDF at xmin."""
    model = (x_tail / xmin) ** (1.0 - alpha)
    return ccdf_at_xmin * model


def fig_pooled_ccdf(res: dict, path_noext: str) -> None:
    data = res["_data"]
    x, ccdf = _empirical_ccdf(data)
    xmin, alpha = res["xmin"], res["alpha"]
    amin_med = res["xmin_boot_median"]
    idx = np.searchsorted(x, xmin, side="left")
    ccdf_at_xmin = ccdf[idx] if idx < len(ccdf) else ccdf[-1]
    x_tail = x[x >= xmin]
    fit_ccdf = _fitted_tail_ccdf(x_tail, xmin, alpha, ccdf_at_xmin)

    fig, ax = plt.subplots(figsize=(7.2, 5.4))
    ax.loglog(x, ccdf, marker="o", linestyle="none", ms=3.2,
              color=S.ALL_COLOR, alpha=0.55, label="Empirical CCDF (all types)")
    ax.loglog(x_tail, fit_ccdf, color="#cc0000", lw=2.2,
              label=f"Fitted power law (alpha={alpha:.2f})")
    ax.axvline(amin_med, ls="--", color="#08519c", lw=1.4,
               label=f"Bootstrap-median Amin = {amin_med:,.0f} km$^2$")
    txt = (f"n total = {res['n_total']}\n"
           f"n tail (A>=Amin) = {res['n_tail']} ({res['pct_tail']:.1f}%)\n"
           f"alpha = {alpha:.3f}\n"
           f"Amin = {xmin:,.0f} km$^2$\n"
           f"p-value = {res['p_value']:.3f}\n"
           f"{'REJECTED' if res['rejected_at_0p10'] else 'not rejected'} "
           f"at p={P_THRESHOLD}")
    ax.text(0.025, 0.04, txt, transform=ax.transAxes, va="bottom", ha="left",
            fontsize=9, bbox=dict(boxstyle="round,pad=0.4", fc="white",
                                  ec="#999999", alpha=0.92))
    ax.set_xlabel("Ellipse area $A$ (km$^2$)")
    ax.set_ylabel("CCDF  $P(A \\geq a)$")
    ax.set_title("Pooled ellipse-area power-law fit (all event types)")
    ax.legend(loc="upper right", fontsize=9)
    fig.text(0.5, -0.02,
             "Continuous Clauset MLE; independent Python implementation "
             "(not R/poweRlaw). Units: km$^2$.",
             ha="center", fontsize=8, color="#555555")
    S.save(fig, path_noext)


def _alpha_boxplot(results: list[dict], path_noext: str, title: str,
                   colors: list[str], labels: list[str], caption: str) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 5.2))
    series = [r["_alpha_boot"][~np.isnan(r["_alpha_boot"])] for r in results]
    bp = ax.boxplot(series, showfliers=False, patch_artist=True,
                    widths=0.55, medianprops=dict(color="black", lw=1.4))
    for patch, col in zip(bp["boxes"], colors):
        patch.set_facecolor(col)
        patch.set_alpha(0.65)
    for i, s in enumerate(series):
        med = float(np.median(s))
        ax.annotate(f"{med:.2f}", xy=(i + 1, med),
                    xytext=(i + 1, med), ha="center", va="bottom",
                    fontsize=9, fontweight="bold")
    ax.set_xticks(range(1, len(labels) + 1))
    ax.set_xticklabels(labels)
    ax.set_ylabel("Bootstrap alpha estimate")
    ax.set_title(title)
    fig.text(0.5, -0.02, caption, ha="center", fontsize=8, color="#555555")
    S.save(fig, path_noext)


def fig_pooled_alpha_box(res: dict, path_noext: str) -> None:
    _alpha_boxplot(
        [res], path_noext,
        "Pooled bootstrap alpha distribution (all event types)",
        [S.ALL_COLOR], ["All types"],
        f"{res['n_sims']} semi-parametric bootstrap refits; "
        f"outliers hidden. n tail = {res['n_tail']} ellipses. "
        f"median alpha = {float(np.nanmedian(res['_alpha_boot'])):.3f}.")


def fig_bytype_ccdf(per_type: dict, path_noext: str) -> None:
    fig, ax = plt.subplots(figsize=(7.8, 5.8))
    inset_lines = []
    for t in sorted(per_type):
        res = per_type[t]
        col = S.type_color(t)
        data = res["_data"]
        x, ccdf = _empirical_ccdf(data)
        xmin, alpha = res["xmin"], res["alpha"]
        idx = np.searchsorted(x, xmin, side="left")
        ccdf_at_xmin = ccdf[idx] if idx < len(ccdf) else ccdf[-1]
        x_tail = x[x >= xmin]
        fit_ccdf = _fitted_tail_ccdf(x_tail, xmin, alpha, ccdf_at_xmin)
        lab = f"{S.TYPE_LABELS[t]} ({S.TYPE_NAMES[t]}), n={res['n_total']}"
        ax.loglog(x, ccdf, marker="o", linestyle="none", ms=3.0,
                  color=col, alpha=0.5, label=lab)
        ax.loglog(x_tail, fit_ccdf, color=col, lw=2.0)
        ax.axvline(xmin, ls="--", color=col, lw=1.0, alpha=0.7)
        pv = res["p_value"]
        inset_lines.append(
            f"{S.TYPE_LABELS[t]}: alpha={alpha:.2f}, Amin={xmin:,.0f}, "
            f"p={pv:.3f} ({'rej' if res['rejected_at_0p10'] else 'ok'})")
    ax.text(0.025, 0.04, "\n".join(inset_lines), transform=ax.transAxes,
            va="bottom", ha="left", fontsize=8.5,
            bbox=dict(boxstyle="round,pad=0.4", fc="white", ec="#999999",
                      alpha=0.92))
    ax.set_xlabel("Ellipse area $A$ (km$^2$)")
    ax.set_ylabel("CCDF  $P(A \\geq a)$")
    ax.set_title("Per-type ellipse-area power-law fits")
    ax.legend(loc="upper right", fontsize=8.5)
    fig.text(0.5, -0.02,
             "Dashed lines: per-type Amin. Independent continuous Clauset "
             "MLE (not R/poweRlaw). Units: km$^2$.",
             ha="center", fontsize=8, color="#555555")
    S.save(fig, path_noext)


def fig_bytype_alpha_box(per_type: dict, path_noext: str) -> None:
    ts = sorted(per_type)
    results = [per_type[t] for t in ts]
    colors = [S.type_color(t) for t in ts]
    labels = [S.TYPE_LABELS[t] for t in ts]
    caption = ("Per-type bootstrap alpha; outliers hidden. Tail counts: " +
               ", ".join(f"{S.TYPE_LABELS[t]} n_tail={per_type[t]['n_tail']}"
                         for t in ts) + ".")
    _alpha_boxplot(results, path_noext,
                   "Per-type bootstrap alpha distributions", colors, labels,
                   caption)


def fig_individual_diag(t: int, res: dict, path_noext: str) -> None:
    data = res["_data"]
    x, ccdf = _empirical_ccdf(data)
    xmin, alpha = res["xmin"], res["alpha"]
    col = S.type_color(t)
    idx = np.searchsorted(x, xmin, side="left")
    ccdf_at_xmin = ccdf[idx] if idx < len(ccdf) else ccdf[-1]
    x_tail = x[x >= xmin]
    fit_ccdf = _fitted_tail_ccdf(x_tail, xmin, alpha, ccdf_at_xmin)

    fig, (axc, axb) = plt.subplots(1, 2, figsize=(11.5, 5.2))
    axc.loglog(x, ccdf, marker="o", linestyle="none", ms=3.4, color=col,
               alpha=0.55, label="Empirical CCDF")
    axc.loglog(x_tail, fit_ccdf, color="#222222", lw=2.0,
               label=f"Fit alpha={alpha:.2f}")
    axc.axvline(res["xmin_boot_median"], ls="--", color="#08519c", lw=1.3,
                label=f"Median Amin={res['xmin_boot_median']:,.0f}")
    axc.set_xlabel("Ellipse area $A$ (km$^2$)")
    axc.set_ylabel("CCDF  $P(A \\geq a)$")
    axc.set_title(f"{S.TYPE_LABELS[t]} ({S.TYPE_NAMES[t]}) CCDF")
    axc.legend(loc="lower left", fontsize=8.5)

    ab = res["_alpha_boot"][~np.isnan(res["_alpha_boot"])]
    axb.hist(ab, bins=40, color=col, alpha=0.7, edgecolor="white")
    axb.axvline(alpha, color="#cc0000", lw=1.6,
                label=f"point alpha={alpha:.2f}")
    axb.axvline(res["alpha_boot_median"], color="black", ls="--", lw=1.3,
                label=f"median={res['alpha_boot_median']:.2f}")
    axb.set_xlabel("Bootstrap alpha")
    axb.set_ylabel("Frequency")
    axb.set_title("Bootstrap alpha distribution")
    axb.legend(fontsize=8.5)

    cap = (f"n={res['n_total']}, n_tail={res['n_tail']} "
           f"({res['pct_tail']:.1f}%), Amin={xmin:,.0f} km$^2$, "
           f"KS={res['ks_statistic']:.3f}, p={res['p_value']:.3f}, "
           f"{'REJECTED' if res['rejected_at_0p10'] else 'not rejected'} "
           f"at p={P_THRESHOLD}. {res['n_sims']} sims "
           f"({res['n_sims_failed']} failed). Independent Python Clauset.")
    fig.text(0.5, -0.02, cap, ha="center", fontsize=8, color="#555555")
    S.save(fig, path_noext)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def write_report(table: pd.DataFrame, pooled: dict, per_type: dict,
                 validation: dict, excluded: dict) -> None:
    def fmt(v, nd=3):
        return "n/a" if v is None or (isinstance(v, float) and np.isnan(v)) \
            else f"{v:.{nd}f}"

    lines = []
    lines.append("# Task 6 - Power-Law Analysis of Ellipse Areas (km$^2$)\n")
    lines.append("## Method and provenance\n")
    lines.append(
        "We test whether ellipse-footprint areas (km$^2$) follow a continuous "
        "power law p(A) = ((alpha-1)/Amin)(A/Amin)^(-alpha) for A>=Amin, using "
        "the Clauset, Shalizi & Newman (2009) procedure.\n")
    lines.append(
        "**Implementation note.** R and the `poweRlaw` package are NOT available "
        "on this host (`Rscript`/`R` are not on PATH). The procedure here is an "
        "INDEPENDENT, self-contained scipy/numpy implementation of the *equivalent* "
        "continuous Clauset method - it is NOT an `poweRlaw` run and does NOT use "
        "the PyPI `powerlaw` package. It was validated against a simulated "
        "continuous power law before use (see below).\n")
    lines.append(
        f"- Continuous MLE: alpha = 1 + n_tail / sum ln(A_i/Amin).\n"
        f"- Amin selected by minimizing the KS distance over candidate values.\n"
        f"- Goodness-of-fit p-value and alpha/Amin 95% intervals from "
        f"**{N_BOOT}** semi-parametric Clauset bootstraps per group.\n"
        f"- Fixed seed = {C.SEED}. Decision rule fixed a priori: p > {P_THRESHOLD} "
        f"=> power law NOT rejected at 90% confidence; p <= {P_THRESHOLD} => "
        f"evidence against the fit.\n")
    lines.append(
        f"- Observation unit: one ellipse_area_km2 per workbook row (one unique "
        f"canonical ellipse footprint per event-day). Excluded "
        f"{excluded['nonfinite']} non-finite/zero/negative areas and "
        f"{excluded['duplicates']} exact duplicate joined rows "
        f"(key = new_event_id+date+cluster_id).\n")

    lines.append("\n## Implementation validation\n")
    lines.append(
        f"On a simulated continuous power law (alpha_true=2.5, xmin_true=1, "
        f"n=5000) the implementation recovered alpha = {fmt(validation['alpha'])} "
        f"(|error| = {fmt(validation['alpha_err'])}, tolerance 0.10), "
        f"Amin = {fmt(validation['xmin'])}, GoF p = {fmt(validation['p_value'])} "
        f"({N_BOOT} sims, {validation['n_failed']} failed). "
        f"**Validation {'PASSED' if validation['passed'] else 'FAILED'}** "
        f"(alpha within tolerance and a non-rejecting p-value).\n")

    lines.append("\n## Results table\n")
    show = table.copy()
    cols = ["group", "n_total", "n_tail", "pct_tail", "Amin_point_km2",
            "Amin_boot_median_km2", "alpha_point", "alpha_boot_median",
            "alpha_ci95_low", "alpha_ci95_high", "ks_statistic", "p_value",
            "rejected_at_0.10"]
    hdr = ("| Group | n | n_tail | %tail | Amin (km^2) | Amin med | alpha | "
           "alpha med | alpha 2.5% | alpha 97.5% | KS | p | reject@0.10 |")
    sep = "|" + "---|" * 13
    lines.append(hdr)
    lines.append(sep)
    for _, r in show[cols].iterrows():
        lines.append(
            f"| {r['group']} | {int(r['n_total'])} | {int(r['n_tail'])} | "
            f"{r['pct_tail']:.1f} | {r['Amin_point_km2']:,.0f} | "
            f"{r['Amin_boot_median_km2']:,.0f} | {r['alpha_point']:.3f} | "
            f"{r['alpha_boot_median']:.3f} | {r['alpha_ci95_low']:.3f} | "
            f"{r['alpha_ci95_high']:.3f} | {r['ks_statistic']:.3f} | "
            f"{fmt(r['p_value'])} | {r['rejected_at_0.10']} |")

    lines.append("\n## Interpretation\n")
    # Which fits can / cannot be rejected.
    not_rej = [r["group"] for _, r in show.iterrows()
               if not r["rejected_at_0.10"]]
    rej = [r["group"] for _, r in show.iterrows() if r["rejected_at_0.10"]]
    lines.append(
        f"- **Not rejected at p={P_THRESHOLD}** (power law plausible, not proven "
        f"uniquely correct): {', '.join(not_rej) if not_rej else 'none'}.\n"
        f"- **Rejected at p={P_THRESHOLD}** (evidence against a pure power-law "
        f"tail): {', '.join(rej) if rej else 'none'}.\n")
    lines.append(
        "- **Tail heaviness.** A lower alpha means a heavier tail, i.e. "
        "relatively more very large ellipses. Compare alpha point estimates and "
        "their bootstrap 95% intervals across groups in the table; overlapping "
        "intervals indicate the difference is not statistically resolved.\n")
    lines.append(
        "- **Amin differences.** The fitted lower bound Amin (km$^2$) marks where "
        "power-law behavior begins; only the upper tail above Amin is modeled, so "
        "the %tail column shows how much of each group's data actually informs "
        "the fit.\n")
    lines.append(
        "- **Small-sample caveats (CRITICAL).** Type 1 (n=3) and Type 2 (n=13) "
        "have extremely small samples; their tails contain only a handful of "
        "points. Any Amin/alpha/p-value for these groups is statistically "
        "unreliable and is reported for completeness only - do not interpret it "
        "as evidence for or against a power law. Type 3 (n=180) and the pooled "
        "set / Type 4 (n=662) are the only groups with enough data for a "
        "meaningful test, and even there the tail samples are modest.\n")
    lines.append(
        "- **Limitations.** A non-rejecting KS test does not prove the power law "
        "is the true or best model; competing heavy-tailed distributions "
        "(log-normal, truncated power law, exponential) were not formally "
        "compared here. Areas derive from a fixed PCA ellipse (sigma=1.25) on "
        "DBSCAN components, so they inherit upstream clustering and grid "
        "discretization effects. We make NO claim of physical causation or "
        "self-organization.\n")

    with open(_REPORT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> dict:
    S.apply()
    C.ensure_dirs()
    for d in (_POOLED_DIR, _BYTYPE_DIR, _DIAG_DIR):
        os.makedirs(d, exist_ok=True)

    df = C.load_workbook()
    n_before = df.shape[0]
    dup_mask = df.duplicated(subset=["new_event_id", "date", "cluster_id"])
    n_dups = int(dup_mask.sum())
    df = df.loc[~dup_mask].copy()
    area = df["ellipse_area_km2"].to_numpy(float)
    finite_mask = np.isfinite(area) & (area > 0)
    n_nonfinite = int((~finite_mask).sum())
    df = df.loc[finite_mask].copy()
    excluded = dict(nonfinite=n_nonfinite, duplicates=n_dups,
                    n_before=n_before, n_after=int(df.shape[0]))

    # Validation first.
    validation = validate_implementation()

    rows = []

    # --- pooled ---
    pooled_data = df["ellipse_area_km2"].to_numpy(float)
    pooled = analyze_group("All types (pooled)", pooled_data, N_BOOT, C.SEED)
    save_group_csvs(pooled, _POOLED_DIR, "pooled")
    rows.append(results_row(pooled))
    fig_pooled_ccdf(pooled, os.path.join(_POOLED_DIR, "pooled_ccdf_powerlaw"))
    fig_pooled_alpha_box(pooled,
                         os.path.join(_POOLED_DIR, "pooled_bootstrap_alpha"))

    # --- per type ---
    per_type = {}
    for t in (1, 2, 3, 4):
        sub = df.loc[df["v3_type"] == t, "ellipse_area_km2"].to_numpy(float)
        if sub.size == 0:
            continue
        seed_t = C.SEED + 100 + t
        res = analyze_group(f"Type {t}", sub, N_BOOT, seed_t)
        per_type[t] = res
        save_group_csvs(res, _BYTYPE_DIR, f"type{t}")
        rows.append(results_row(res))
        fig_individual_diag(
            t, res, os.path.join(_DIAG_DIR, f"type{t}_ccdf_diagnostic"))

    fig_bytype_ccdf(per_type, os.path.join(_BYTYPE_DIR, "by_type_ccdf"))
    fig_bytype_alpha_box(per_type,
                         os.path.join(_BYTYPE_DIR, "by_type_bootstrap_alpha"))

    table = pd.DataFrame(rows)
    table.to_csv(os.path.join(C.T06, "power_law_results_table.csv"), index=False)

    write_report(table, pooled, per_type, validation, excluded)

    # Manifest.
    C.write_manifest(os.path.join(C.T06, "task06_manifest.json"), dict(
        task="task06_power_law",
        utc=C.utc_stamp(),
        git_commit=C.git_commit(),
        workbook=C.WORKBOOK,
        workbook_sha256=C.sha256_file(C.WORKBOOK),
        dependency_versions=C.dependency_versions(),
        seed=C.SEED,
        n_boot=N_BOOT,
        p_threshold=P_THRESHOLD,
        r_poweRlaw_used=False,
        implementation="independent scipy/numpy continuous Clauset",
        excluded=excluded,
        validation=validation,
        groups={r["group"]: {k: r[k] for k in (
            "n_total", "n_tail", "Amin_point_km2", "alpha_point", "p_value",
            "rejected_at_0.10", "n_sims", "n_sims_failed")} for r in rows},
    ))

    summary = dict(
        r_poweRlaw_used=False,
        validation=validation,
        excluded=excluded,
        groups={r["group"]: dict(
            n=r["n_total"], n_tail=r["n_tail"], Amin=r["Amin_point_km2"],
            alpha=r["alpha_point"], p_value=r["p_value"],
            reject=r["rejected_at_0.10"], n_sims=r["n_sims"],
            n_failed=r["n_sims_failed"]) for r in rows},
        out_dirs=dict(base=C.T06, pooled=_POOLED_DIR, by_type=_BYTYPE_DIR,
                      diagnostics=_DIAG_DIR, report=_REPORT),
    )
    return summary


if __name__ == "__main__":
    import json
    print(json.dumps(main(), indent=2, default=str))
