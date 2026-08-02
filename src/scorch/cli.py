"""SCORCH command-line interface.

Subcommands:
  scorch fetch-data       download + safely extract the processed-data
                          deposit (Zenodo) and verify its checksums;
                          requires --doi / --url / SCORCH_DATA_DOI
  scorch reproduce        run the paper-reproduction stages from a
                          machine-readable YAML stage list; any required
                          stage that cannot run FAILS the command
  scorch validate-sources check an ERA5 daily-Tmax directory
  scorch validate-deposit structure + checksum + row-count check of an
                          extracted deposit
  scorch version          print the package version

The installable ``scorch`` package is the SCORCH ANALYSIS LIBRARY (canonical
kernels + catalog tools + these reconstruction stages). Full repository-level
paper reproduction (all figures/tables) additionally uses the ``scripts/``
tree and ``run_reproduction.py`` at the repository root -- see README.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__


class StageError(RuntimeError):
    """A reproduction stage is missing or failed."""


# ---------------------------------------------------------------------------
# builtin stages
# ---------------------------------------------------------------------------
def _builtin_validate_catalog(stage, base_dir, out_dir=None, config=None):
    """Builtin stage: validate the master catalog + event parameters files.

    The expected totals (rows/ellipses, events, dates/selected days, type
    counts) are the ``expected_counts:`` of the loaded YAML config -- the
    single source of truth of the configured route. The config is validated
    against the complete schema first, so every expected count is present;
    a config that omits one fails loudly before the stage runs.
    Deliberately wrong configured counts FAIL.
    """
    from . import catalog as cat
    from .pipeline import _cfg_params_expected
    _, expected = _cfg_params_expected(config)
    master_path = Path(base_dir) / stage["inputs"]["master_csv"]
    if not master_path.exists():
        raise StageError(f"master catalog not found: {master_path}")
    df = cat.load_master(master_path)
    summary = cat.validate_master(
        df, expect_canonical_counts=bool(stage.get("params", {})
                                         .get("expect_canonical_counts", True)),
        expected_counts=expected)
    print(f"  [ok] master catalog valid: {summary}")
    params_rel = stage.get("inputs", {}).get("parameters_csv")
    if params_rel:
        params_path = Path(base_dir) / params_rel
        if not params_path.exists():
            raise StageError(f"parameters file not found: {params_path}")
        psum = cat.validate_event_parameters(
            cat.load_event_parameters(params_path),
            expected_events=int(expected["events"]))
        print(f"  [ok] event parameters valid: {psum}")
    return "ok"


def _builtin_classify_events(stage, base_dir, out_dir=None, config=None):
    """Builtin stage: recompute the typology and compare to the catalog."""
    from . import catalog as cat
    from .typology import classify_events
    master_path = Path(base_dir) / stage["inputs"]["master_csv"]
    if not master_path.exists():
        raise StageError(f"master catalog not found: {master_path}")
    df = cat.load_master(master_path)
    derived = classify_events(df)
    stored = df.groupby("new_event_id")["v3_type"].first()
    merged = derived.set_index("new_event_id")["derived_type"]
    n_match = int((stored.reindex(merged.index) == merged).sum())
    print(f"  [ok] typology recomputed: {n_match}/{len(merged)} events match "
          "the stored v3_type")
    if n_match != len(merged):
        raise StageError("typology mismatch against the stored catalog")
    return "ok"


def _builtin_registry():
    from .pipeline import PIPELINE_STAGES
    reg = {
        "validate_catalog": _builtin_validate_catalog,
        "classify_events": _builtin_classify_events,
    }
    reg.update(PIPELINE_STAGES)
    return reg


# ---------------------------------------------------------------------------
# reproduce: stage runner
# ---------------------------------------------------------------------------
def _find_rscript():
    """Locate the Rscript executable (env override, PATH, common installs)."""
    env = os.environ.get("SCORCH_RSCRIPT")
    if env:
        if Path(env).exists():
            return env
        raise StageError(f"SCORCH_RSCRIPT points to a missing file: {env}")
    found = shutil.which("Rscript")
    if found:
        return found
    candidates = []
    for root in (r"C:\Program Files\R", r"C:\Program Files (x86)\R"):
        rp = Path(root)
        if rp.exists():
            candidates += sorted(rp.glob(r"R-*/bin/Rscript.exe"), reverse=True)
    if candidates:
        return str(candidates[0])
    raise StageError(
        "Rscript not found. Install R (with the spatstat packages, see "
        "docs/R_WORKFLOW.md) and either add Rscript to PATH or set "
        "SCORCH_RSCRIPT to its full path.")


def bundled_config_path():
    """Path to the canonical FAST config shipped as package data.

    Ships inside the wheel, so ``scorch reproduce --base-dir <deposit-root>
    --route fast`` works after ``pip install`` with no repository checkout.
    """
    path = Path(__file__).resolve().parent / "configs" / "reproduction_fast.yaml"
    if not path.exists():                                     # pragma: no cover
        raise StageError(
            "the bundled reconstruction config is missing from the installed "
            f"package ({path}). Reinstall scorch-heatwaves, or pass an "
            "explicit --config.")
    return path


def run_reproduction(config_path=None, base_dir=None, only=None, route="fast",
                     out_dir=None):
    """Execute the ordered stage list of a reconstruction YAML config.

    Each stage is a mapping with:
      name   : short identifier
      kind   : "builtin" (registered stage), "script" (Python file) or
               "rscript" (R file, run with Rscript)
      route  : "fast" (deposit-only) or "all" (default; runs in every route)
      script : (script/rscript kinds) path, resolved against the RELEASE root
               (the config file's parent directory's parent) first, then
               base_dir
      args   : optional extra command-line arguments
      inputs / outputs / comparison_targets / params : documentation +
               builtin arguments

    ``config_path`` defaults to the bundled canonical fast config.
    ``out_dir`` receives every newly generated intermediate (default: the
    ``SCORCH_OUT_DIR`` environment variable, else ``./reproduced``); the
    deposit is never written to.

    A stage selected by the route/--only filters that is missing or fails
    RAISES StageError -- required stages are never silently skipped.
    Unknown ``--only`` names RAISE StageError before anything runs.
    Returns the list of (name, status) pairs.
    """
    import yaml

    from .pipeline import validate_reconstruction_config
    config_path = Path(config_path or bundled_config_path()).resolve()
    release_root = config_path.parent.parent
    with open(config_path, "r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    # Reject unsupported parameters, non-canonical fixed rules and unknown
    # sections BEFORE any stage runs -- nothing is silently ignored.
    validate_reconstruction_config(config)
    if base_dir is None:
        base_dir = config.get("base_dir", ".")
    base_dir = Path(base_dir)
    if out_dir is None:
        out_dir = os.environ.get("SCORCH_OUT_DIR") or "reproduced"
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    builtins = _builtin_registry()

    stages = config.get("stages", [])
    known = [s.get("name") for s in stages]
    if only:
        unknown = [n for n in only if n not in known]
        if unknown:
            raise StageError(
                f"unknown stage name(s) in --only: {sorted(unknown)}. "
                f"Available stages: {', '.join(str(n) for n in known)}")
    selected = []
    for stage in stages:
        name = stage.get("name", "?")
        stage_route = stage.get("route", "all")
        if only:
            if name in only:
                selected.append(stage)
        elif stage_route in ("all", route):
            selected.append(stage)

    print(f"[reproduce] {config.get('name', config_path.name)}: "
          f"route={route}; {len(selected)}/{len(stages)} stages "
          f"(base_dir={base_dir}; out_dir={out_dir})")
    results = []
    for stage in selected:
        name = stage.get("name", "?")
        kind = stage.get("kind", "script")
        print(f"[stage] {name} ({kind})")
        if kind == "builtin":
            fn = builtins.get(stage.get("builtin"))
            if fn is None:
                raise StageError(
                    f"stage '{name}': unknown builtin "
                    f"'{stage.get('builtin')}'")
            # The FULL loaded config is handed to every builtin stage so the
            # top-level parameters: and expected_counts: mappings of the YAML
            # are the operative values of the configured reconstruction.
            results.append((name, fn(stage, base_dir, out_dir,
                                     config=config)))
        elif kind in ("script", "rscript"):
            rel = stage.get("script", "")
            script = release_root / rel
            if not script.exists():
                script = base_dir / rel
            if not script.exists():
                raise StageError(
                    f"stage '{name}': required script not found: {rel} "
                    f"(searched {release_root} and {base_dir})")
            if kind == "rscript":
                cmd = [_find_rscript(), str(script)]
            else:
                cmd = [sys.executable, str(script)]
            cmd += [str(a) for a in stage.get("args", [])]
            env = dict(os.environ)
            env.setdefault("SCORCH_DATA_DIR", str(base_dir.resolve()))
            proc = subprocess.run(cmd, cwd=str(release_root), env=env)
            if proc.returncode != 0:
                raise StageError(
                    f"stage '{name}' failed (exit {proc.returncode})")
            results.append((name, "ok"))
        else:
            raise StageError(f"stage '{name}': unknown stage kind '{kind}'")
    print("[reproduce] summary: " +
          ", ".join(f"{n}={s}" for n, s in results))
    return results


# ---------------------------------------------------------------------------
# provider-level reconstruction guide (documentation only)
# ---------------------------------------------------------------------------
PROVIDER_RECONSTRUCTION_GUIDE = """\
PROVIDER-LEVEL RECONSTRUCTION GUIDE -- DOCUMENTATION ONLY, NOTHING IS RUN
========================================================================
This text describes how a provider-scale user would rebuild the PROCESSED
DAILY FIELD from raw ERA5. It is a GUIDE. Printing it reconstructs nothing,
verifies nothing, and is not a reproduction run. The steps below are
STRUCTURALLY VALIDATED (the scripts ship, import, and expose the documented
arguments) but have NOT been rerun end to end in this release: they need a
multi-hour provider download, local working storage exceeding 10 GB (about
8.4 GB of yearly NetCDF files plus a roughly 2 GB derived long table and
intermediates; total network transfer is larger still), and R with the
spatstat packages.

What IS executed and verified is the connected reconstruction from the
deposited processed field onward:

    scorch reproduce --base-dir <deposit-root> --route fast

Steps (each must be run by hand, in order):

1. Download daily ERA5 Tmax (1940-2025, April-September, 10-46N / 20-70E):
     python scripts/download/download_era5_arco.py --outdir <ncdir>
   (or the CDS route: download_era5_cds.py + era5_hourly_to_daily_tmax.py)

2. Aggregate to the 1-degree grid, derive per-cell warm-season p95
   thresholds, apply the exceedance rule (tmax >= threshold) and the
   canonical heatwave labelling; writes master_exceed_heatwaves_long.csv:
     python scripts/pipeline/build_master_dataset.py --datadir <ncdir>
   NOTE: --datadir is REQUIRED. Without it the script exits with an error;
   it does not fall back to any default location.

3. Package the processed field as the deposited CF-1.10 NetCDF:
     python scripts/deposit/build_processed_field_netcdf.py \\
         --master-csv <step-2 CSV> \\
         --extent-csv <deposit gridded/fig02_daily_extent.csv> \\
         --out scorch_processed_daily_tmax_field_v1.0.0.nc
   The result is the input to the executable fast route above, which
   performs selection, daily DBSCAN parameter choice, event-global
   parameters, clustering, ellipse geometry and typology, and verifies each
   stage against the deposited catalogs.

4. Centroid-concentration (LGCP) chain, needing the step-2 long table:
     set SCORCH_ERA5_TMAX_LONG_CSV=<step-2 CSV>
     python scripts/lgcp/build_inputs.py
     Rscript scripts/lgcp/spatial_risk_lgcp_model_diagnostics.R \\
         reproduced/lgcp_inputs reproduced/lgcp/model_diagnostics_and_variants
     python scripts/lgcp/extract_variant3.py
   (The fit itself HAS been executed against the deposited lgcp/ inputs;
   only the step-2 covariate construction needs this provider chain.)

The processed-data deposit already contains the verified outputs of steps
2-4, so nothing downstream requires this guide to be executed.
"""


# ---------------------------------------------------------------------------
# validate-deposit
# ---------------------------------------------------------------------------
REQUIRED_DEPOSIT_DIRS = [
    "catalogs", "gridded", "lgcp", "power_law", "selected_days",
    "validation_kfold", "validation_station", "figure_table_source_data",
]
REQUIRED_DEPOSIT_FILES = [
    "DATA_README.md", "DATA_DICTIONARY.csv", "FILE_MANIFEST.csv",
    "PROVENANCE.md", "SHA256SUMS", "LICENSE.txt",
    "catalogs/scorch_new_algorithm_master_cluster_ellipse_event_global_max.csv",
    "catalogs/final_labels_event_global_max.csv",
    "catalogs/event_global_max_parameters.csv",
    "catalogs/grid_predicted_intensity_variant3.csv",
    "gridded/scorch_processed_daily_tmax_field_v1.0.0.nc",
    "gridded/fig02_daily_extent.csv",
    "gridded/fig02_box_p95.csv",
    "gridded/analysis_grid.csv",
    "selected_days/selected_days_395.csv",
    "selected_days/event_catalog_51.csv",
    "lgcp/lgcp_model_parameters.csv",
    "validation_kfold/per_centroid_risk_zone_validation.csv",
]
ROW_COUNT_INVARIANTS = [
    ("catalogs/scorch_new_algorithm_master_cluster_ellipse_event_global_max.csv", 760),
    ("catalogs/final_labels_event_global_max.csv", 191098),
    ("catalogs/event_global_max_parameters.csv", 51),
    ("catalogs/grid_predicted_intensity_variant3.csv", 1800),
    ("gridded/fig02_daily_extent.csv", 15738),
    ("gridded/fig02_box_p95.csv", 1800),
    ("gridded/analysis_grid.csv", 1800),
    ("selected_days/selected_days_395.csv", 395),
    ("selected_days/event_catalog_51.csv", 51),
    ("validation_kfold/per_centroid_risk_zone_validation.csv", 760),
]
EXPECTED_TYPE_COUNTS = {1: 3, 2: 4, 3: 20, 4: 24}


def locate_deposit_root(directory):
    """Find the deposit root at or below ``directory``.

    The root is the directory holding SHA256SUMS. Accepts the root itself, a
    parent (e.g. the fetch destination) containing one extracted deposit, or a
    single-subdirectory wrapper. Raises StageError when no unique root exists.
    """
    directory = Path(directory)
    if (directory / "SHA256SUMS").exists():
        return directory
    hits = [p.parent for p in directory.glob("*/SHA256SUMS")]
    hits += [p.parent for p in directory.glob("*/*/SHA256SUMS")]
    hits = sorted(set(hits))
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise StageError(
            f"no deposit found under {directory}: no SHA256SUMS file at the "
            "top level or one/two levels below. Run 'scorch fetch-data "
            "--doi 10.5281/zenodo.21717752' first, or pass the extracted "
            "deposit directory.")
    raise StageError(
        f"multiple candidate deposits under {directory}: "
        + ", ".join(str(h) for h in hits))


def _count_csv_rows(path):
    import csv
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return sum(1 for _ in csv.reader(fh)) - 1


def validate_deposit(directory):
    """Structure + checksum + row-count + type-count check of a deposit."""
    from .fetch import verify_sha256sums, FetchError
    try:
        root = locate_deposit_root(directory)
    except StageError as exc:
        print(f"[FAIL] {exc}")
        print("RESULT: FAIL")
        return False
    print(f"[deposit] root: {root}")
    ok = True

    for name in REQUIRED_DEPOSIT_DIRS:
        present = (root / name).is_dir()
        print(f"[{'OK  ' if present else 'FAIL'}] directory present: {name}/")
        ok = ok and present
    for name in REQUIRED_DEPOSIT_FILES:
        present = (root / name).exists()
        print(f"[{'OK  ' if present else 'FAIL'}] file present: {name}")
        ok = ok and present

    try:
        results = verify_sha256sums(root)
        print(f"[OK  ] SHA256SUMS verified ({len(results)} files)")
    except FetchError as exc:
        print(f"[FAIL] {exc}")
        ok = False

    # completeness: no unlisted files (SHA256SUMS exempts itself)
    try:
        listed = set()
        for line in (root / "SHA256SUMS").read_text(
                encoding="utf-8").splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) == 2:
                listed.add(parts[1].strip().lstrip("*"))
        on_disk = {p.relative_to(root).as_posix()
                   for p in root.rglob("*")
                   if p.is_file() and p.name != "SHA256SUMS"}
        unlisted = sorted(on_disk - listed)
        if unlisted:
            print(f"[FAIL] {len(unlisted)} unlisted file(s): "
                  + ", ".join(unlisted[:5])
                  + (" ..." if len(unlisted) > 5 else ""))
            ok = False
        else:
            print("[OK  ] no unlisted files")
    except OSError as exc:
        print(f"[FAIL] completeness check: {exc}")
        ok = False

    for rel, expected in ROW_COUNT_INVARIANTS:
        path = root / rel
        if not path.exists():
            continue  # already reported as missing above
        n = _count_csv_rows(path)
        good = n == expected
        print(f"[{'OK  ' if good else 'FAIL'}] rows {rel}: {n} "
              f"(expected {expected})")
        ok = ok and good

    master = root / REQUIRED_DEPOSIT_FILES[6]
    if master.exists():
        try:
            import pandas as pd
            df = pd.read_csv(master, usecols=["new_event_id", "v3_type"])
            counts = df.groupby("new_event_id")["v3_type"].first() \
                       .value_counts().to_dict()
            counts = {int(k): int(v) for k, v in counts.items()}
            good = counts == EXPECTED_TYPE_COUNTS
            print(f"[{'OK  ' if good else 'FAIL'}] event type counts "
                  f"T1..T4: {counts} (expected {EXPECTED_TYPE_COUNTS})")
            ok = ok and good
        except Exception as exc:                              # noqa: BLE001
            print(f"[FAIL] type-count check: {exc}")
            ok = False

    print("RESULT: " + ("PASS" if ok else "FAIL"))
    return ok


# ---------------------------------------------------------------------------
# argparse wiring
# ---------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(
        prog="scorch",
        description="SCORCH heatwave framework: catalog tools, validation, "
                    "and paper reproduction.")
    sub = p.add_subparsers(dest="command")

    f = sub.add_parser("fetch-data",
                       help="download + extract the processed-data deposit")
    f.add_argument("--doi", default=None,
                   help="deposit DOI (default: SCORCH_DATA_DOI env var)")
    f.add_argument("--url", default=None, help="direct deposit/record URL")
    f.add_argument("--dest", default="scorch_data", help="output directory")
    f.add_argument("--no-verify", action="store_true",
                   help="skip SHA256SUMS verification (NOT recommended)")

    r = sub.add_parser(
        "reproduce",
        help="run the connected processed-field -> catalog reconstruction")
    r.add_argument("--config", default=None,
                   help="stage-list YAML (default: the canonical fast config "
                        "bundled with the installed package)")
    r.add_argument("--base-dir", default=None,
                   help="processed-data deposit root (default: config's "
                        "base_dir or cwd)")
    r.add_argument("--out-dir", default=None,
                   help="output root for newly generated intermediates "
                        "(default: SCORCH_OUT_DIR env var, else "
                        "./reproduced; never the deposit)")
    r.add_argument("--route", choices=["fast"], default="fast",
                   help="fast: the complete connected reconstruction from "
                        "the deposited processed field (the only executable "
                        "route; reconstructing the field itself from "
                        "provider ERA5 is a guide: see "
                        "'scorch reconstruction-guide')")
    r.add_argument("--only", nargs="*", default=None,
                   help="run only the named stages (overrides --route); "
                        "unknown names are an error")

    sub.add_parser(
        "reconstruction-guide",
        help="print the provider-level ERA5 -> processed-field "
             "reconstruction guide (documentation only; nothing is run)")

    v = sub.add_parser("validate-sources",
                       help="check an ERA5 daily-Tmax directory")
    v.add_argument("--dir", required=True, help="ERA5 daily NetCDF directory")
    v.add_argument("--expected-files", type=int, default=86)
    v.add_argument("--sample", type=int, default=None,
                   help="validate only the first N files")

    d = sub.add_parser("validate-deposit",
                       help="structure + checksum + row-count check of a "
                            "deposit")
    d.add_argument("--dir", required=True,
                   help="deposit directory (root, or the fetch destination "
                        "containing it)")

    sub.add_parser("version", help="print the package version")
    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "version":
        print(f"scorch-heatwaves {__version__}")
        return 0
    if args.command == "fetch-data":
        from .fetch import fetch_deposit, FetchError
        try:
            result = fetch_deposit(dest_dir=args.dest, doi=args.doi,
                                   url=args.url, verify=not args.no_verify)
        except FetchError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(f"[fetch] downloaded {len(result.downloaded)} file(s); "
              f"deposit root: {result.deposit_root}")
        return 0
    if args.command == "reproduce":
        try:
            run_reproduction(args.config, base_dir=args.base_dir,
                             only=args.only, route=args.route,
                             out_dir=args.out_dir)
        except (StageError, RuntimeError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        return 0
    if args.command == "reconstruction-guide":
        print(PROVIDER_RECONSTRUCTION_GUIDE)
        return 0
    if args.command == "validate-sources":
        from .validation import validate_era5_dir, format_report
        report = validate_era5_dir(args.dir,
                                   expected_files=args.expected_files,
                                   sample=args.sample)
        print(format_report(report))
        return 0 if report["ok"] else 1
    if args.command == "validate-deposit":
        return 0 if validate_deposit(args.dir) else 1
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
