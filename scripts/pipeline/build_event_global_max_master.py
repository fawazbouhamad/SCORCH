#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regenerate the SCORCH master cluster/ellipse dataset using EVENT-GLOBAL
MAXIMUM DBSCAN hyperparameters (Dr. Najibi's methodological decision).

WHAT CHANGES
------------
The canonical pipeline selects DBSCAN parameters *per event-day* (daily adaptive
``dbscan_avg_eps`` + ``dbscan_rounded_minpts``).  Dr. Najibi now wants a single,
consistent, *event-global maximum* threshold applied to every day of the same
compound event, so adjacent small ellipses / noise are suppressed and the
threshold is constant across the days of one event.

For each event (``new_event_id``):
    event_global_eps_max        = max(canonical daily eps over the event's days)
    event_global_minpts_max_raw = max(canonical daily RAW mean minPts over days)
    event_global_minpts_used    = max(canonical daily ROUNDED minPts over days)
                                  (the max of the true per-day integer
                                  ``dbscan_rounded_minpts``; see the minPts
                                  INTEGER RULE below -- ceil(max_raw) is
                                  recorded for audit only)

Every day of the event is then re-clustered with
``DBSCAN(eps=event_global_eps_max, min_samples=event_global_minpts_used)`` and
one PCA ellipse (sigma=1.25) is fitted per resulting component, exactly as in the
canonical kernel.

minPts INTEGER RULE (documented choice)
---------------------------------------
DBSCAN ``min_samples`` must be an integer.  The canonical algorithm DOES expose a
true, per-day integer min_samples: ``dbscan_rounded_minpts`` is the value actually
fed to the final per-day DBSCAN run (the decimal ``dbscan_raw_avg_minpts`` is the
pre-rounding mean over the tied modal grid cells).  Because a true selected
integer per day exists, Dr. Najibi's PRIMARY rule applies -- "use the maximum of
those integer values":

    event_global_minpts_used = max(per-day dbscan_rounded_minpts)

This is the maximum integer threshold actually applied on any day of the event
(a genuine event-global maximum), and it guarantees that one-day events
(Types 1 and 2) reproduce the canonical daily result EXACTLY (max over one day ==
that day's own value), so the workflow applies uniformly to all 51 events.

For full auditability we ALSO record the decimal ``event_global_minpts_max_raw``
= max(per-day raw mean minPts) and ``event_global_minpts_ceil_raw`` =
ceil(max_raw) (the alternative "decimals-only" rule).  Where ceil(max_raw)
differs from max(rounded) the difference is visible in the parameter table; we
deliberately use max(rounded) because it preserves canonical daily equivalence
for one-day events, which ceil(max_raw) would break.

WHAT IS PRESERVED (NOT changed)
-------------------------------
* Raw heatwave-labelled grid cells (re-used verbatim from the canonical
  Method-A label file -- the same cells the canonical workbook was built from).
* Event identity, dates, duration, day index -- copied from the canonical
  workbook, never recomputed.
* Event TYPE labels (``v3_type`` / ``type`` / ``event_type_name`` ...).  The
  typology is a fixed, manually-curated classification keyed to event dates and
  structure; it is carried over unchanged.  A separate diagnostic
  (``compare_event_global_max.py``) reports how per-day ellipse structure changed
  and which events *would* shift type if the typology were mechanically
  re-derived -- for Dr. Najibi's review -- without overwriting the labels.

OUTPUTS  (reproduced/event_global_max_algorithm/)
----------------------------------------------
* scorch_new_algorithm_master_cluster_ellipse_event_global_max.csv
* scorch_new_algorithm_master_cluster_ellipse_event_global_max.xlsx
* event_global_max_parameters.csv      (per-event chosen global-max params)
* kernel_selfcheck_daily_canonical.csv (re-run canonical params vs workbook)
* build_manifest.json

The authoritative canonical workbook is opened READ-ONLY and never modified.
"""
from __future__ import annotations

import json
import math
import os
import sys

import numpy as np
import pandas as pd

# --- release wiring (release-relative; Windows-safe) -------------------------
_THIS = os.path.abspath(__file__)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_THIS)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "figures", "common"))

import common as C        # noqa: E402  (release copy of six_task_review/common.py)
import clustering as cl   # noqa: E402  (canonical scripts/common/clustering.py)
import ellipse_pca as ep  # noqa: E402  (canonical scripts/common/ellipse_pca.py)
import tmax_weighted_centroid as twc  # noqa: E402  (post-PCA stages 2+3)
from sklearn.cluster import DBSCAN  # noqa: E402
import _clean_paths as _cp  # noqa: E402
from _clean_paths import GENERATED_DIR  # noqa: E402

# Tier-B stage: requires the canonical daily-adaptive workbook and the
# Method-A label file (env SCORCH_WORKBOOK / SCORCH_LABELS_A; see common.py).
OUT_DIR = os.environ.get(
    "SCORCH_GM_OUT_DIR",
    os.path.join(GENERATED_DIR, "event_global_max_algorithm"))
MASTER_CSV = os.path.join(
    OUT_DIR, "scorch_new_algorithm_master_cluster_ellipse_event_global_max.csv")
MASTER_XLSX = os.path.join(
    OUT_DIR, "scorch_new_algorithm_master_cluster_ellipse_event_global_max.xlsx")
WORKBOOK_SHEET = "master_cluster_ellipse"

# Metadata columns carried over UNCHANGED, one value per event-day.
META_COLS = [
    "new_event_id", "event_id", "v3_type", "type", "event_type",
    "event_type_name", "event_type_original", "duration_days",
    "day_index_in_event",
]


# -----------------------------------------------------------------------------
# DBSCAN + ellipse kernel (identical formulas to the canonical pipeline)
# -----------------------------------------------------------------------------
def dbscan_labels(lon, lat, eps, min_samples):
    """Canonical DBSCAN on the precomputed grid-cell Euclidean distance."""
    D = cl.pairwise_distance_cells(lon, lat, grid_step=C.GRID_STEP,
                                   chebyshev=False)
    return DBSCAN(eps=float(eps), min_samples=int(min_samples),
                  metric="precomputed").fit_predict(D)


# -----------------------------------------------------------------------------
# Canonical per-cell daily Tmax (degC) for the weighted-centroid stage.
# Source: the processed-data deposit's CF NetCDF field (units checked).
# The join is by exact date + exact 1-degree cell-centre coordinates (stable
# cell identifiers); missing / duplicated / non-finite values raise.
# -----------------------------------------------------------------------------
TMAX_NC = os.environ.get(
    "SCORCH_TMAX_NC",
    _cp.data_file("scorch_processed_daily_tmax_field_v1.0.0.nc", "gridded"))

# Counter: the weighted stage must run exactly once per retained structure.
WEIGHTED_CALLS = {"n": 0}


def load_tmax_by_date(dates):
    """{date_str: {(lon, lat): tmax_degC}} for the requested dates (strict)."""
    import xarray as xr
    ds = xr.open_dataset(TMAX_NC)
    units = str(ds["tmax"].attrs.get("units", "")).lower()
    if units not in ("degc", "celsius", "degrees_celsius", "deg_c"):
        raise twc.WeightedCentroidError(
            f"Tmax field units are '{units}', not degrees Celsius; "
            f"refusing to weight ({TMAX_NC})")
    want = np.array(sorted(set(str(d) for d in dates)),
                    dtype="datetime64[ns]")
    sub = ds["tmax"].sel(time=want).load()
    out = {}
    lons = [float(v) for v in sub["lon"].values]
    lats = [float(v) for v in sub["lat"].values]
    for i, d in enumerate(np.datetime_as_string(want, unit="D")):
        arr = sub.values[i]
        day = {}
        for yi, la in enumerate(lats):
            for xi, lo in enumerate(lons):
                v = float(arr[yi, xi])
                if math.isfinite(v):
                    day[(lo, la)] = v
        out[str(d)] = day
    ds.close()
    return out


def member_tmax_weights(lon, lat, date, tmax_day):
    """Exactly one finite raw-Celsius Tmax per member cell, else raise."""
    w = np.empty(lon.size, dtype=float)
    missing = []
    for i, (lo, la) in enumerate(zip(lon.tolist(), lat.tolist())):
        key = (float(lo), float(la))
        if key not in tmax_day:
            missing.append(key)
        else:
            w[i] = tmax_day[key]
    if missing:
        raise twc.WeightedCentroidError(
            f"{len(missing)} member cell(s) have no Tmax on {date}: "
            f"{missing[:5]} ...")
    return w


def _pc_vectors(orientation_deg):
    """Reproduce workbook pc1_vec/pc2_vec from the major-axis orientation.

    Verified against the canonical workbook: pc1 = (cos t, sin t),
    pc2 = (-sin t, cos t), with t = orientation_deg in [0, 180).
    """
    t = math.radians(float(orientation_deg))
    return (math.cos(t), math.sin(t), -math.sin(t), math.cos(t))


def day_ellipse_rows(lon, lat, labels, date, tmax_day):
    """One metrics dict per DBSCAN component (noise excluded).

    Also computes the heatwave/ellipse footprint purity family against the
    *same-day* heatwave-labelled grid cells (lon/lat are exactly those cells), matching the
    canonical purity definitions closely enough for the optional diagnostics.

    Remediation: after the COMPLETE unweighted PCA ellipse is calculated,
    the raw-Celsius Tmax-weighted centroid (stage 2) is computed for the
    component's member cells only, and the finished ellipse is rigidly
    translated to it (stage 3). PCA geometry is never refit or altered.
    """
    rows = []
    comp_labels = sorted(set(labels.tolist()) - {C.NOISE})
    for cid, lab in enumerate(comp_labels):
        m = labels == lab
        clon, clat = lon[m], lat[m]
        e = ep.evaluate_cluster_ellipse(clon, clat, C.SIGMA)
        if not e:
            continue
        a, b = e["major_axis_km"], e["minor_axis_km"]
        ratio = e["axis_ratio"]
        ecc = math.sqrt(max(0.0, 1.0 - ratio * ratio))
        p1x, p1y, p2x, p2y = _pc_vectors(e["orientation_deg"])

        # Purity family: ellipse footprint over the same-day heatwave cells.
        center_xy, eigvecs, eigvals = ep.fit_pca(
            ep.project_lonlat_to_km(clon, clat, e["centroid_lon"],
                                    e["centroid_lat"]))
        inside_day = ep.ellipse_mask(lon, lat, e["centroid_lon"],
                                     e["centroid_lat"], center_xy, eigvecs,
                                     eigvals, C.SIGMA)
        H = int(m.sum())                       # component (heatwave) cells
        E = int(inside_day.sum())              # same-day HW cells in ellipse
        inter = int((m & inside_day).sum())    # intersection
        union = int((m | inside_day).sum())
        target_purity = 100.0 * inter / H if H else float("nan")
        hw_purity = 100.0 * inter / E if E else float("nan")
        containment = 100.0 * inter / union if union else float("nan")
        iou = 100.0 * inter / union if union else float("nan")

        # --- Stage 2 (post-PCA): raw-Celsius Tmax-weighted centroid --------
        w_c = member_tmax_weights(clon, clat, date, tmax_day)
        wc = twc.tmax_weighted_centroid(
            clon, clat, w_c, context=f"{date} cluster {cid}")
        WEIGHTED_CALLS["n"] += 1
        # --- Stage 3: rigid translation; footprint of the translated ellipse
        inside_w = twc.translated_ellipse_mask(
            lon, lat, wc["lon_w"], wc["lat_w"], eigvecs, eigvals, C.SIGMA)
        E_w = int(inside_w.sum())
        inter_w = int((m & inside_w).sum())
        union_w = int((m | inside_w).sum())
        disp_km, disp_bearing = twc.geodesic_displacement_km(
            e["centroid_lon"], e["centroid_lat"], wc["lon_w"], wc["lat_w"])

        rows.append(dict(
            cluster_id=cid, sigma=C.SIGMA,
            H_component_cells=H, E_ellipse_cells=E,
            interH_intersection_cells=inter, union_cells=union,
            target_component_purity=target_purity,
            same_day_hw_purity=hw_purity, containment=containment,
            iou_jaccard=iou,
            # Generic centroid aliases now report the AUTHORITATIVE
            # Tmax-weighted location (all downstream location analyses).
            centroid_lon=wc["lon_w"], centroid_lat=wc["lat_w"],
            major_axis_km=a, minor_axis_km=b,
            ellipse_area_km2=e["ellipse_area_km2"],
            orientation_deg=e["orientation_deg"], axis_ratio=ratio,
            eccentricity=ecc,
            pc1_vec_x=p1x, pc1_vec_y=p1y, pc2_vec_x=p2x, pc2_vec_y=p2y,
            centroid_x=wc["lon_w"], centroid_y=wc["lat_w"],
            x=wc["lon_w"], y=wc["lat_w"],
            lon=wc["lon_w"], lat=wc["lat_w"],
            area=e["ellipse_area_km2"], axis1_len_km=a, axis2_len_km=b,
            ratio=ratio, L2_L1_ratio=ratio, ratio_L2_L1=ratio,
            orientation=e["orientation_deg"],
            eigval_major=e["eigval_major"], eigval_minor=e["eigval_minor"],
            pc1_explained_var=e["pc1_explained_var"],
            # Explicit coordinate definitions (remediation; full precision).
            pca_origin_lon_unweighted=e["centroid_lon"],
            pca_origin_lat_unweighted=e["centroid_lat"],
            centroid_lon_unweighted=e["centroid_lon"],
            centroid_lat_unweighted=e["centroid_lat"],
            centroid_lon_tmax_weighted=wc["lon_w"],
            centroid_lat_tmax_weighted=wc["lat_w"],
            tmax_weight_sum_c=wc["weight_sum_c"],
            tmax_min_c=wc["tmax_min_c"], tmax_max_c=wc["tmax_max_c"],
            tmax_mean_c=wc["tmax_mean_c"], tmax_sd_c=wc["tmax_sd_c"],
            centroid_displacement_km=disp_km,
            centroid_displacement_bearing_deg=disp_bearing,
            # Footprint of the rigidly translated ellipse (location product).
            E_ellipse_cells_translated=E_w,
            interH_intersection_cells_translated=inter_w,
            union_cells_translated=union_w,
            target_component_purity_translated=(
                100.0 * inter_w / H if H else float("nan")),
            same_day_hw_purity_translated=(
                100.0 * inter_w / E_w if E_w else float("nan")),
            containment_translated=(
                100.0 * inter_w / union_w if union_w else float("nan")),
            iou_jaccard_translated=(
                100.0 * inter_w / union_w if union_w else float("nan")),
        ))
    return rows


# -----------------------------------------------------------------------------
# Build
# -----------------------------------------------------------------------------
def build():
    os.makedirs(OUT_DIR, exist_ok=True)
    wb = C.load_workbook()                 # read-only
    wb["date_str"] = wb["date"].dt.strftime("%Y-%m-%d")
    if "dbscan_modal_count" not in wb.columns:
        # Deposit rebuild: the research workbook's modal-count audit string is
        # not shipped. It feeds only the event-day table's audit-only fields
        # (modal_count / modal_count_max / is_modal_tie), none of which are
        # consumed by this builder or written to the master catalog.
        wb["dbscan_modal_count"] = "1"
    labels_A = C.load_labels_A()           # same-day heatwave-labelled cells + labels

    # 1) per event-day canonical parameters (one row per new_event_id/date)
    ed = C.build_event_day_table(wb)       # has eps_selected, min_samples_raw/selected
    ed = ed.sort_values(["new_event_id", "date"]).reset_index(drop=True)

    # 2) event-global MAX parameters
    grp = ed.groupby("new_event_id")
    ev = grp.agg(
        event_global_eps_max=("eps_selected", "max"),
        event_global_minpts_max_raw=("min_samples_raw", "max"),
        event_global_minpts_max_rounded=("min_samples_selected", "max"),
        n_days=("date", "nunique"),
        v3_type=("v3_type", "first"),
    ).reset_index()
    # PRIMARY rule: max of the true per-day integer min_samples actually applied.
    ev["event_global_minpts_used"] = ev["event_global_minpts_max_rounded"].astype(int)
    # Audit-only alternative (decimals-only rule); NOT used for clustering.
    ev["event_global_minpts_ceil_raw"] = ev["event_global_minpts_max_raw"].apply(
        lambda r: max(1, int(math.ceil(float(r)))))
    ev.to_csv(os.path.join(OUT_DIR, "event_global_max_parameters.csv"),
              index=False)
    g_eps = dict(zip(ev["new_event_id"], ev["event_global_eps_max"]))
    g_mp = dict(zip(ev["new_event_id"], ev["event_global_minpts_used"]))
    g_mp_raw = dict(zip(ev["new_event_id"], ev["event_global_minpts_max_raw"]))
    g_mp_rnd = dict(zip(ev["new_event_id"], ev["event_global_minpts_max_rounded"]))

    # Canonical per-cell daily Tmax for every event day (strict join source).
    tmax_by_date = load_tmax_by_date(ed["date"].unique())

    # Frozen audit passthrough: the true canonical DAILY-adaptive parameters
    # (canonical_daily_*) come from the Tier-B research workbook and cannot be
    # recomputed from a deposit master whose dbscan_* aliases already carry the
    # event-global values. When the source workbook ships them, carry them
    # over VERBATIM (keyed by event + day); never derive them here.
    daily_cols = ("canonical_daily_eps", "canonical_daily_minpts_raw",
                  "canonical_daily_minpts_used")
    daily_carry = {}
    if all(c in wb.columns for c in daily_cols):
        for (eid_c, dstr), g in wb.groupby(["new_event_id", "date_str"]):
            daily_carry[(int(eid_c), dstr)] = tuple(
                g[c].iloc[0] for c in daily_cols)

    # day-level metadata lookup (carried over unchanged)
    meta_value_cols = [c for c in META_COLS if c != "new_event_id"]
    meta = (wb.sort_values(["new_event_id", "date"])
              .groupby(["new_event_id", "date_str"])[meta_value_cols]
              .first().reset_index())
    meta_lookup = {(int(r.new_event_id), r.date_str): r for r in meta.itertuples()}

    # 3) self-check + 4) global-max clustering, per event-day
    selfcheck, master_rows, gmax_label_rows = [], [], []
    for row in ed.itertuples():
        eid, date = int(row.new_event_id), row.date
        lon, lat = C.day_cells(labels_A, date)
        # --- self-check: reproduce canonical day count with daily params ---
        lab_can = dbscan_labels(lon, lat, row.eps_selected,
                                row.min_samples_selected)
        n_can = len(set(lab_can.tolist()) - {C.NOISE})
        selfcheck.append(dict(
            new_event_id=eid, date=date,
            daily_eps=row.eps_selected,
            daily_minpts=row.min_samples_selected,
            workbook_n_clusters=int(row.day_final_n_clusters),
            reproduced_n_clusters=int(n_can),
            match=int(n_can == int(row.day_final_n_clusters))))

        # --- new method: event-global MAX params ---
        eps_g, mp_g = g_eps[eid], int(g_mp[eid])
        lab_g = dbscan_labels(lon, lat, eps_g, mp_g)
        # per-cell global-max labels (for snapshot/GIF regeneration)
        for lo, la, lb in zip(lon.tolist(), lat.tolist(), lab_g.tolist()):
            gmax_label_rows.append(dict(date=date, lon=lo, lat=la, label=int(lb)))
        ell_rows = day_ellipse_rows(lon, lat, lab_g, date, tmax_by_date[date])
        m = meta_lookup[(eid, date)]
        carried = daily_carry.get((eid, date))
        n_clustered = int((lab_g != C.NOISE).sum())
        n_noise = int((lab_g == C.NOISE).sum())
        for er in ell_rows:
            rec = dict(
                new_event_id=eid, event_id=int(m.event_id), date=date,
                v3_type=int(m.v3_type), type=m.type,
                event_type=m.event_type, event_type_name=m.event_type_name,
                event_type_original=m.event_type_original,
                duration_days=int(m.duration_days),
                day_index_in_event=int(m.day_index_in_event),
                # event-global-max parameters actually applied
                canonical_daily_eps=float(
                    carried[0] if carried else row.eps_selected),
                canonical_daily_minpts_raw=float(
                    carried[1] if carried else row.min_samples_raw),
                canonical_daily_minpts_used=int(
                    carried[2] if carried else row.min_samples_selected),
                event_global_eps_max=float(eps_g),
                event_global_minpts_max_raw=float(g_mp_raw[eid]),
                event_global_minpts_max_rounded=int(g_mp_rnd[eid]),
                event_global_minpts_used=int(mp_g),
                # canonical alias columns (so downstream scripts read params)
                dbscan_avg_eps=float(eps_g),
                dbscan_raw_avg_minpts=float(g_mp_raw[eid]),
                dbscan_rounded_minpts=int(mp_g),
                day_final_n_clusters=len(ell_rows),
                day_n_noise_cells=n_noise,
                day_n_clustered_cells=n_clustered,
            )
            rec.update(er)
            master_rows.append(rec)

    # global-max per-cell labels (mirrors the schema of final_labels_method_A.csv
    # so the six-task snapshot/GIF harness can render global-max clusters).
    gmax_labels_csv = os.path.join(OUT_DIR, "final_labels_event_global_max.csv")
    pd.DataFrame(gmax_label_rows).to_csv(gmax_labels_csv, index=False)
    print(f"[LABELS] {os.path.relpath(gmax_labels_csv, REPO_ROOT)} "
          f"({len(gmax_label_rows)} cell-rows)")

    sc = pd.DataFrame(selfcheck)
    sc.to_csv(os.path.join(OUT_DIR, "kernel_selfcheck_daily_canonical.csv"),
              index=False)
    match_rate = float(sc["match"].mean()) if len(sc) else float("nan")
    print(f"[SELF-CHECK] canonical params reproduce workbook day counts: "
          f"{int(sc['match'].sum())}/{len(sc)} event-days "
          f"({100*match_rate:.1f}%)")

    master = pd.DataFrame(master_rows)
    # stable column order: canonical workbook columns first, then extras
    front = [
        "new_event_id", "event_id", "date", "v3_type", "type", "event_type",
        "event_type_name", "event_type_original", "duration_days",
        "day_index_in_event",
        "canonical_daily_eps", "canonical_daily_minpts_raw",
        "canonical_daily_minpts_used",
        "event_global_eps_max", "event_global_minpts_max_raw",
        "event_global_minpts_max_rounded", "event_global_minpts_used",
        "dbscan_avg_eps", "dbscan_raw_avg_minpts", "dbscan_rounded_minpts",
        "day_final_n_clusters", "day_n_noise_cells", "day_n_clustered_cells",
        "cluster_id", "sigma",
    ]
    rest = [c for c in master.columns if c not in front]
    master = master[front + rest]
    master.to_csv(MASTER_CSV, index=False)
    with pd.ExcelWriter(MASTER_XLSX, engine="openpyxl") as xw:
        master.to_excel(xw, sheet_name=WORKBOOK_SHEET, index=False)

    if WEIGHTED_CALLS["n"] != master.shape[0]:
        raise twc.WeightedCentroidError(
            f"weighted-centroid stage ran {WEIGHTED_CALLS['n']} times for "
            f"{master.shape[0]} catalog rows; must be exactly once per "
            f"retained structure")

    manifest = dict(
        method="event_global_maximum_dbscan_hyperparameters",
        tmax_weighted_centroids=dict(
            weights="raw processed daily Tmax values (absolute observed "
                    "level, not anomaly/exceedance; no abs())",
            units="degrees_Celsius",
            weighting_scope="structure-specific (member cells only; DBSCAN "
                            "noise and other structures excluded)",
            clustering_unweighted=True,
            pca_unweighted=True,
            appendix_a_and_sigma_unchanged=True,
            sigma_ellipse_scale=C.SIGMA,
            weighting_applied_only_after_complete_pca_ellipse=True,
            translation_rigid_geometry_unchanged=True,
            authoritative_location_fields=[
                "centroid_lon_tmax_weighted", "centroid_lat_tmax_weighted"],
            generic_aliases_map_to="tmax_weighted",
            unweighted_fields_preserved=[
                "pca_origin_lon_unweighted", "pca_origin_lat_unweighted",
                "centroid_lon_unweighted", "centroid_lat_unweighted"],
            tmax_source=TMAX_NC,
            tmax_source_sha256=C.sha256_file(TMAX_NC),
            weighted_stage_calls=WEIGHTED_CALLS["n"],
        ),
        minpts_integer_rule=("max(per-day dbscan_rounded_minpts) per event "
                             "(true per-day integer; one-day events match "
                             "canonical exactly). ceil(max_raw) recorded for audit."),
        eps_rule="max(daily_avg_eps) per event (kept continuous)",
        sigma=C.SIGMA, grid_step=C.GRID_STEP,
        source_workbook=os.path.relpath(C.WORKBOOK, REPO_ROOT),
        source_workbook_sha256=C.sha256_file(C.WORKBOOK),
        source_labels=os.path.relpath(C.LABELS_A_CSV, REPO_ROOT),
        n_events=int(ev.shape[0]), n_event_days=int(ed.shape[0]),
        n_ellipse_rows=int(master.shape[0]),
        selfcheck_match_event_days=int(sc["match"].sum()),
        selfcheck_total_event_days=int(len(sc)),
        master_csv=os.path.relpath(MASTER_CSV, REPO_ROOT),
        master_xlsx=os.path.relpath(MASTER_XLSX, REPO_ROOT),
        dependency_versions=C.dependency_versions(),
        git_commit=C.git_commit(), timestamp_utc=C.utc_stamp(),
    )
    with open(os.path.join(OUT_DIR, "build_manifest.json"), "w",
              encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, default=str)

    print(f"[MASTER] {os.path.relpath(MASTER_CSV, REPO_ROOT)}  "
          f"rows={master.shape[0]} cols={master.shape[1]}")
    print(f"[MASTER] {os.path.relpath(MASTER_XLSX, REPO_ROOT)}")
    print(f"[PARAMS] events={ev.shape[0]}  event-days={ed.shape[0]}  "
          f"ellipses={master.shape[0]}")
    return manifest


if __name__ == "__main__":
    np.random.seed(C.SEED)
    build()
