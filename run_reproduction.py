#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cross-platform SCORCH repository-level figure driver (Windows has no make).

This driver reproduces the REPOSITORY-LEVEL publication figures and tables
and therefore requires a clone of the repository (its scripts/ tree). It is
NOT part of the installable analysis package: the connected
processed-field -> catalog reconstruction lives in the installed package and
is run with `scorch reproduce --base-dir <deposit-root> --route fast`.

Mirrors the Makefile targets:

    python run_reproduction.py smoke [--data-dir DIR] [--out-dir DIR]
    python run_reproduction.py fast  [--data-dir DIR] [--out-dir DIR]
                                     [--pub-dir DIR]
                                     [--nboot N] [--skip NAME ...]
                                     [--only NAME ...]
    python run_reproduction.py guide

Tiers
-----
smoke : small verification subset -- scorch-package catalog validation,
        Table 1, Figure 12 and Figure 2, all regenerated from the processed
        data deposit (default: <release>/scorch_data).
fast  : everything reproducible from the deposit alone: statistics +
        power-law tables, manuscript tables, and every deposit-reproducible
        publication figure (2, 3, 5-12, A-D, S.1) plus the k-fold
        CV validation chain and the GHCN station check. Figures 1 and 4 are
        frozen author-created assets with no producer and are NOT generated.
        The figS2-component-* stages regenerate the two INTERNAL component
        figures whose content is merged into the published Fig. D (Appendix
        D); they are not manuscript figures themselves. The "figS2"/"figS3"/
        "figS4" stage and directory names are LEGACY INTERNAL names kept for
        provenance, not current publication labels. Figure 11 (canonical
        5000-replicate Clauset bootstrap) and Figure 10 (pure-Python
        Mann-Kendall loops) are the slow stages.
        fast never writes to the deposit or to the source tree, and never
        regenerates a frozen asset; ALL REPRODUCTION outputs land under
        --out-dir (default <release>/reproduced).
        The final stage, publication-outputs, is an ASSEMBLY step rather
        than a reproduction step: it copies already-verified artifacts into
        the clean publication tree at --pub-dir (default
        <release>/publication_outputs), which is a separate declared
        destination so the --out-dir contract above stays literally true.
        It reads reproduced/, assets/frozen_figures/ and
        assets/manuscript_final/, selects every source BY SHA-256 and never
        by filename, and needs no manuscript and no private repository. It
        is NOT part of the smoke tier.
guide : PRINTS the provider-level ERA5 -> processed-field reconstruction
        guide and exits. It executes nothing, verifies nothing, and is not
        a reproduction run. Those steps are structurally validated only.

Bootstrap replicates: --nboot defaults to the CANONICAL 5000. A smaller
value is a QUICK, NONCANONICAL run and is announced as such.

Every stage is a subprocess of the current Python interpreter with
SCORCH_DATA_DIR / SCORCH_OUT_DIR exported, so individual scripts can also be
run by hand with the same environment.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))

# Canonical power-law bootstrap replicate count (the published runs).
CANONICAL_NBOOT = 5000


def _script(*parts: str) -> str:
    return os.path.join(ROOT, "scripts", *parts)


def _validate_catalog(env: dict) -> int:
    """Canonical catalog validation through the installable scorch package."""
    code = (
        "import os, sys, pandas as pd\n"
        "sys.path.insert(0, os.path.join(r'%s', 'src'))\n"
        "sys.path.insert(0, os.path.join(r'%s', 'scripts', 'figures', 'common'))\n"
        "from scorch.catalog import validate_master\n"
        "from _clean_paths import MASTER_CSV\n"
        "df = pd.read_csv(MASTER_CSV)\n"
        "summary = validate_master(df, expect_canonical_counts=True)\n"
        "print('[validate-catalog] PASS:', summary)\n" % (ROOT, ROOT)
    )
    return subprocess.call([sys.executable, "-c", code], env=env, cwd=ROOT)


def _stages(nboot: int, out_dir: str = "", pub_dir: str = ""):
    """(name, argv) stage table. argv None => handled specially.

    out_dir / pub_dir are the reproduction and publication destinations
    handed to the final publication-outputs stage. They are consulted for
    that stage only, so callers that merely need the stage NAMES may leave
    them empty.
    """
    py = sys.executable
    return [
        # ---- smoke subset -------------------------------------------------
        ("validate-catalog", None),
        ("table1", [py, _script("pipeline", "make_global_max_tables.py")]),
        ("fig12", [py, _script("figures", "fig12",
                               "make_q1_variant3_four_variable_centroid_map.py")]),
        ("fig02-panel-a", [py, _script("figures", "fig02",
                                       "fig02_panel_a_tmax_p95_map.py")]),
        ("fig02-panel-b", [py, _script("figures", "fig02",
                                       "fig02_panel_b_extent_hexbin.py")]),
        ("fig02-assemble", [py, _script("figures", "fig02",
                                        "assemble_figure2.py")]),
        # ---- remaining Tier A ---------------------------------------------
        ("statistics", [py, _script("pipeline",
                                    "regenerate_statistics_global_max.py"),
                        "--nboot", str(nboot)]),
        ("extract-variant3", [py, _script("lgcp", "extract_variant3.py")]),
        ("fig03-panels", [py, _script("figures", "fig03", "fig3_panels.py")]),
        ("fig03-assemble", [py, _script("figures", "fig03",
                                        "make_figure3_composite.py")]),
        ("fig08", [py, _script("figures", "fig08",
                               "Figure_10_Statistical_Analysis_of_Types_ORIGINAL.py")]),
        ("fig09", [py, _script("figures", "fig09",
                               "make_figure9_unified_ORIGINAL.py")]),
        ("fig05-06-07", [py, _script("figures", "fig05_06_07",
                                     "make_figs_5_6_7.py")]),
        ("fig06-r2", [py, _script("figures", "fig05_06_07",
                                  "make_fig6.py")]),
        ("figA1", [py, _script("figures", "figA1",
                               "make_figA1_sigma_sensitivity.py")]),
        ("figA2", [py, _script("figures", "figA2",
                               "make_new_figA2_event10_candidate.py")]),
        ("figA3", [py, _script("figures", "figA3",
                               "make_figA3_dbscan_params.py")]),
        ("figS1", [py, _script("figures", "figS1",
                               "make_figS1_type3_event25.py")]),
        # INTERNAL COMPONENT of the published Fig. D (superseded standalone
        # figure; content = panel (a) of Fig. D). Not a manuscript figure.
        # "figS2"/"figS3" here are legacy internal names, not publication labels.
        ("figS2-component-distance",
         [py, _script("figures", "figS3", "make_figS3_risk_zone_distance.py")]),
        ("kfold-cv", [py, _script("validation",
                                  "kfold_cv_four_variable_centroid_model.py")]),
        ("kfold-riskzone", [py, _script("validation",
                                        "kfold_cv_risk_zone_validation.py")]),
        ("kfold-plot", [py, _script("validation",
                                    "plot_kfold_cv_validation_figure.py")]),
        ("kfold-foldmaps", [py, _script("validation",
                                        "make_kfold_fold_maps.py")]),
        # INTERNAL COMPONENT of the published Fig. D (superseded standalone
        # figure; content = panels (b)-(f) of Fig. D). Not a manuscript figure.
        # "figS2"/"figS4" here are legacy internal names, not publication labels.
        ("figS2-component-foldmaps",
         [py, _script("figures", "figS4", "make_figS4_kfold_maps.py")]),
        ("figS2", [py, _script("figures", "figS2",
                               "make_new_figS2_candidate.py")]),
        # Published S.1 composite: merges the regenerated Type 3 Event 25
        # figure (figS1 stage output) with the frozen station artwork;
        # byte-identical to the deployed supplement embed.
        ("figS1-composite", [py, _script("figures", "figS1",
                                         "make_new_figS1_candidate.py")]),
        ("ghcn-validation", [py, _script("validation",
                                         "ghcn_era5_validation.py")]),
        # 5000-replicate Clauset bootstrap x2 -- slow; kept late.
        ("fig11", [py, _script("figures", "fig11",
                               "make_q1_power_law_2x2_panel.py")]),
        # Pure-Python O(n^2) Mann-Kendall loops (canonical, verbatim) make
        # this the slowest stage (~10-15 min); kept last.
        ("fig10", [py, _script("figures", "fig10",
                               "Figure_9_Trend_Analysis_With_Table_statistics.py")]),
        # ---- assembly, always last ----------------------------------------
        # Assembles the clean publication tree from artifacts the stages
        # above have already produced, so it must run after all of them.
        # Not a reproduction stage and NOT in SMOKE_STAGES: it regenerates
        # no science, it selects every source by SHA-256 (never by
        # filename) and copies it into --pub-dir, which is deliberately a
        # different destination from --out-dir.
        ("publication-outputs", [py, _script("publication",
                                             "build_publication_outputs.py"),
                                 "--root", ROOT,
                                 "--reproduced-dir", out_dir,
                                 "--out-dir", pub_dir]),
    ]


SMOKE_STAGES = ("validate-catalog", "table1", "fig12",
                "fig02-panel-a", "fig02-panel-b", "fig02-assemble")

PROVIDER_GUIDE = """\
PROVIDER-LEVEL RECONSTRUCTION GUIDE -- DOCUMENTATION ONLY, NOTHING IS RUN
========================================================================
This command PRINTS instructions. It does not reconstruct anything, does
not verify anything, and is not a reproduction run. The steps below are
STRUCTURALLY VALIDATED ONLY (the scripts ship, import, and expose the
documented arguments); they were NOT rerun end to end for this release,
because they need a multi-hour provider-scale download (a possible network
transfer of hourly source data of order 100 GB), local working storage
exceeding 10 GB of NetCDF files and derived intermediates, and R with the
spatstat packages.

Requires: python with the [download] extra (xarray/zarr/gcsfs or cdsapi),
R 4.5+ with spatstat.model for step 4.

1. Download daily ERA5 Tmax (1940-2025, Apr-Sep, 10-46N / 20-70E):
     python scripts/download/download_era5_arco.py --outdir <ncdir>
   (or the CDS route: download_era5_cds.py + era5_hourly_to_daily_tmax.py)

2. Aggregate to 1 degree, derive per-cell warm-season p95 thresholds, apply
   the exceedance rule (tmax >= threshold) and the canonical heatwave
   labelling; writes master_exceed_heatwaves_long.csv:
     python scripts/pipeline/build_master_dataset.py --datadir <ncdir>
   --datadir is REQUIRED; without it the script exits with an error.

3. Package the processed field as the deposited CF-1.10 NetCDF:
     python scripts/deposit/build_processed_field_netcdf.py \\
         --master-csv <step-2 CSV> \\
         --extent-csv <deposit gridded/fig02_daily_extent.csv> \\
         --out scorch_processed_daily_tmax_field_v1.0.0.nc

   Everything downstream of this file IS executed and verified, by the
   installed package's connected reconstruction:
     scorch reproduce --base-dir <deposit-root> --route fast
   (selection, 395 daily Method-A parameter selections, 51 event-global
   parameter pairs, clustering, PCA ellipses, typology).

4. Centroid-concentration (LGCP) chain, needing the step-2 long table:
     set SCORCH_ERA5_TMAX_LONG_CSV=<step-2 CSV>
     python scripts/lgcp/build_inputs.py
     Rscript scripts/lgcp/spatial_risk_lgcp_model_diagnostics.R \\
         reproduced/lgcp_inputs reproduced/lgcp/model_diagnostics_and_variants
     python scripts/lgcp/extract_variant3.py
   The R fit itself HAS been executed against the deposited lgcp/ inputs
   and matched; only the step-2 covariate construction needs this chain.

The processed-data deposit contains the verified outputs of steps 2-4, so
the 'fast' tier reproduces every downstream number without executing them.
"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("tier", choices=("smoke", "fast", "guide"))
    ap.add_argument("--data-dir",
                    default=os.environ.get("SCORCH_DATA_DIR",
                                           os.path.join(ROOT, "scorch_data")),
                    help="processed-data deposit root")
    ap.add_argument("--out-dir",
                    default=os.environ.get("SCORCH_OUT_DIR",
                                           os.path.join(ROOT, "reproduced")),
                    help="output root (never the deposit)")
    ap.add_argument("--pub-dir",
                    default=os.environ.get(
                        "SCORCH_PUB_DIR",
                        os.path.join(ROOT, "publication_outputs")),
                    help="publication-output root for the final "
                         "publication-outputs assembly stage (never the "
                         "deposit and never --out-dir)")
    ap.add_argument("--nboot", type=int, default=CANONICAL_NBOOT,
                    help=f"power-law bootstrap replicates (default and "
                         f"CANONICAL: {CANONICAL_NBOOT}). Any smaller value "
                         "produces a QUICK, NONCANONICAL run whose power-law "
                         "numbers do not reproduce the published values.")
    ap.add_argument("--only", nargs="*", default=None,
                    help="run only these stage names")
    ap.add_argument("--skip", nargs="*", default=(),
                    help="skip these stage names")
    args = ap.parse_args(argv)

    if args.tier == "guide":
        print(PROVIDER_GUIDE)
        return 0

    all_names = [n for n, _ in _stages(args.nboot)]
    unknown = sorted({n for n in (args.only or ()) if n not in all_names}
                     | {n for n in args.skip if n not in all_names})
    if unknown:
        print(f"[ERROR] unknown stage name(s): {', '.join(unknown)}\n"
              f"        available stages: {', '.join(all_names)}")
        return 2

    if args.nboot != CANONICAL_NBOOT:
        print(f"[WARNING] QUICK / NONCANONICAL MODE: --nboot {args.nboot} "
              f"instead of the canonical {CANONICAL_NBOOT}. The power-law "
              "outputs of this run are NOT the published canonical values "
              "and must not be reported as reproductions of them.")

    if not os.path.isdir(args.data_dir):
        print(f"[ERROR] data dir not found: {args.data_dir}\n"
              "        Download the processed-data deposit first "
              "(scorch fetch-data --doi 10.5281/zenodo.21717752 --dest "
              "scorch_data) or pass --data-dir.")
        return 2

    # The publication tree is a SEPARATE declared destination: keeping it
    # distinct from both the deposit and the reproduction output root is
    # what makes the "all reproduction outputs land under --out-dir"
    # contract literally true.
    abs_data = os.path.abspath(args.data_dir)
    abs_out = os.path.abspath(args.out_dir)
    abs_pub = os.path.abspath(args.pub_dir)
    for label, other in (("--data-dir", abs_data), ("--out-dir", abs_out)):
        if abs_pub == other:
            print(f"[ERROR] --pub-dir must differ from {label}: {abs_pub}")
            return 2

    # Pin the reproducible-build epoch BEFORE any stage runs, and do it on
    # os.environ so the child env built below inherits it. Without this the
    # PDF writers stamp wall-clock /CreationDate and the published tables
    # stop being byte-reproducible. A conflicting or malformed pre-set value
    # is refused rather than silently honoured.
    sys.path.insert(0, os.path.join(ROOT, "scripts", "figures", "common"))
    from _clean_paths import (SourceDateEpochError,  # noqa: E402
                              enforce_source_date_epoch)
    try:
        epoch = enforce_source_date_epoch()
    except SourceDateEpochError as exc:
        print(f"[ERROR] {exc}")
        return 2
    print(f"[ok  ] SOURCE_DATE_EPOCH pinned to {epoch} "
          f"(2026-07-30T01:26:05Z) for deterministic PDF metadata")

    env = dict(os.environ)
    env["SCORCH_DATA_DIR"] = abs_data
    env["SCORCH_OUT_DIR"] = abs_out
    env["SCORCH_PUB_DIR"] = abs_pub
    env.setdefault("MPLBACKEND", "Agg")
    # The documented contract is that a run NEVER modifies the source tree:
    # suppress interpreter bytecode caches (__pycache__/*.pyc) that stage
    # imports would otherwise write next to the shipped scripts.
    env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    os.makedirs(args.out_dir, exist_ok=True)

    stages = _stages(args.nboot, abs_out, abs_pub)
    wanted = [n for n, _ in stages]
    if args.tier == "smoke":
        wanted = list(SMOKE_STAGES)
    if args.only:
        wanted = [n for n in wanted if n in set(args.only)]
    wanted = [n for n in wanted if n not in set(args.skip)]

    results = []
    for name, cmd in stages:
        if name not in wanted:
            continue
        print(f"\n=== [{args.tier}] stage: {name} ===")
        t0 = time.time()
        if cmd is None:
            rc = _validate_catalog(env)
        else:
            rc = subprocess.call(cmd, env=env, cwd=ROOT)
        dt = time.time() - t0
        results.append((name, rc, dt))
        print(f"=== [{args.tier}] stage {name}: "
              f"{'OK' if rc == 0 else f'FAILED (rc={rc})'} in {dt:.1f}s ===")
        if rc != 0:
            break

    print("\n===== SUMMARY =====")
    for name, rc, dt in results:
        print(f"{'PASS' if rc == 0 else 'FAIL':4s}  {name:18s}  {dt:8.1f}s")
    return 0 if all(rc == 0 for _, rc, _ in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
