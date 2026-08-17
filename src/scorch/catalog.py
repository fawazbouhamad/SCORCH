"""Load / validate / export the SCORCH master ellipse catalog.

Schema mirrors the frozen canonical files:

  * ``scorch_new_algorithm_master_cluster_ellipse_event_global_max.csv``
    (760 ellipse rows for the canonical catalog), and
  * ``event_global_max_parameters.csv`` (51 events).

Expected canonical totals (canonical catalog): 1800 valid 1-degree cells,
15,738 warm-season days, Theta = 371, 395 selected days, 51 events,
760 ellipses; event type counts T1=3, T2=4, T3=20, T4=24.
"""
from __future__ import annotations

import pandas as pd

# Exact column order of the canonical master CSV header.
MASTER_COLUMNS = [
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
    "H_component_cells", "E_ellipse_cells", "interH_intersection_cells",
    "union_cells", "target_component_purity", "same_day_hw_purity",
    "containment", "iou_jaccard",
    "centroid_lon", "centroid_lat", "major_axis_km", "minor_axis_km",
    "ellipse_area_km2", "orientation_deg", "axis_ratio", "eccentricity",
    "pc1_vec_x", "pc1_vec_y", "pc2_vec_x", "pc2_vec_y",
    "centroid_x", "centroid_y", "x", "y", "lon", "lat",
    "area", "axis1_len_km", "axis2_len_km",
    "ratio", "L2_L1_ratio", "ratio_L2_L1", "orientation",
    "eigval_major", "eigval_minor", "pc1_explained_var",
]

# Remediation (fix/tmax-weighted-centroids): explicit coordinate definitions.
# Generic aliases above carry the Tmax-weighted location in post-remediation
# catalogs; the unweighted PCA origin is preserved separately. A catalog is
# valid with either NONE of these columns (pre-remediation baseline /
# fixtures) or ALL of them; a partial block is a schema violation.
MASTER_COLUMNS_REMEDIATION = [
    "pca_origin_lon_unweighted", "pca_origin_lat_unweighted",
    "centroid_lon_unweighted", "centroid_lat_unweighted",
    "centroid_lon_tmax_weighted", "centroid_lat_tmax_weighted",
    "tmax_weight_sum_c", "tmax_min_c", "tmax_max_c", "tmax_mean_c",
    "tmax_sd_c", "centroid_displacement_km",
    "centroid_displacement_bearing_deg",
    "E_ellipse_cells_translated", "interH_intersection_cells_translated",
    "union_cells_translated", "target_component_purity_translated",
    "same_day_hw_purity_translated", "containment_translated",
    "iou_jaccard_translated",
]

# Columns that must parse as integers / floats for the schema to be valid.
MASTER_INT_COLUMNS = [
    "new_event_id", "event_id", "v3_type", "duration_days",
    "day_index_in_event", "canonical_daily_minpts_used",
    "event_global_minpts_max_rounded", "event_global_minpts_used",
    "dbscan_rounded_minpts", "day_final_n_clusters", "day_n_noise_cells",
    "day_n_clustered_cells", "cluster_id",
]
MASTER_FLOAT_COLUMNS = [
    "canonical_daily_eps", "canonical_daily_minpts_raw",
    "event_global_eps_max", "event_global_minpts_max_raw",
    "dbscan_avg_eps", "dbscan_raw_avg_minpts", "sigma",
    "centroid_lon", "centroid_lat", "major_axis_km", "minor_axis_km",
    "ellipse_area_km2", "orientation_deg", "axis_ratio",
    "eigval_major", "eigval_minor", "pc1_explained_var",
    "pca_origin_lon_unweighted", "pca_origin_lat_unweighted",
    "centroid_lon_unweighted", "centroid_lat_unweighted",
    "centroid_lon_tmax_weighted", "centroid_lat_tmax_weighted",
    "tmax_weight_sum_c", "tmax_min_c", "tmax_max_c", "tmax_mean_c",
    "tmax_sd_c", "centroid_displacement_km",
    "centroid_displacement_bearing_deg",
]

PARAMETERS_COLUMNS = [
    "new_event_id", "event_global_eps_max", "event_global_minpts_max_raw",
    "event_global_minpts_max_rounded", "n_days", "v3_type",
    "event_global_minpts_used", "event_global_minpts_ceil_raw",
]

# Canonical catalog expectations.
EXPECTED_ROWS = 760
EXPECTED_EVENTS = 51
EXPECTED_DATES = 395
EXPECTED_TYPE_COUNTS = {1: 3, 2: 4, 3: 20, 4: 24}


class CatalogValidationError(ValueError):
    """Raised when a catalog file fails schema validation."""


def load_master(path):
    """Load a master ellipse catalog CSV (dates kept as strings)."""
    df = pd.read_csv(path)
    if "date" in df.columns:
        df["date"] = df["date"].astype(str)
    return df


def load_event_parameters(path):
    """Load an event-global-max parameters CSV."""
    return pd.read_csv(path)


def validate_master(df, expect_canonical_counts=False, expected_counts=None):
    """Validate a master catalog DataFrame against the canonical schema.

    Parameters
    ----------
    df : DataFrame (as returned by :func:`load_master`).
    expect_canonical_counts : bool
        If True, additionally require the expected totals (rows/ellipses,
        events, unique dates, type counts).
    expected_counts : optional mapping overriding the module-constant
        totals -- the loaded YAML ``expected_counts:`` of the configured
        route (keys ``ellipses``, ``events``, ``selected_days``,
        ``type_counts``). Without it the canonical-catalog constants
        (760 rows, 51 events, 395 unique dates, 3/4/20/24) apply.

    Returns
    -------
    dict summary (n_rows, n_events, n_dates, type_counts) on success.

    Raises
    ------
    CatalogValidationError on any schema violation.
    """
    problems = []

    missing = [c for c in MASTER_COLUMNS if c not in df.columns]
    if missing:
        problems.append(f"missing required columns: {missing}")
    rem_present = [c for c in MASTER_COLUMNS_REMEDIATION if c in df.columns]
    if rem_present and len(rem_present) != len(MASTER_COLUMNS_REMEDIATION):
        rem_missing = [c for c in MASTER_COLUMNS_REMEDIATION
                       if c not in df.columns]
        problems.append(
            f"partial Tmax-weighted-centroid column block: missing "
            f"{rem_missing}")

    for col in MASTER_INT_COLUMNS:
        if col in df.columns:
            try:
                vals = pd.to_numeric(df[col], errors="raise")
                if not (vals == vals.round()).all():
                    problems.append(f"column '{col}' has non-integer values")
            except (ValueError, TypeError):
                problems.append(f"column '{col}' is not numeric")
    for col in MASTER_FLOAT_COLUMNS:
        if col in df.columns:
            try:
                pd.to_numeric(df[col], errors="raise")
            except (ValueError, TypeError):
                problems.append(f"column '{col}' is not numeric")

    if "date" in df.columns:
        parsed = pd.to_datetime(df["date"], errors="coerce")
        if parsed.isna().any():
            problems.append("column 'date' has unparseable dates")

    summary = {}
    if not problems:
        summary["n_rows"] = int(df.shape[0])
        summary["n_events"] = int(df["new_event_id"].nunique())
        summary["n_dates"] = int(df["date"].nunique())
        per_event_type = df.groupby("new_event_id")["v3_type"].first()
        summary["type_counts"] = {
            int(k): int(v)
            for k, v in per_event_type.value_counts().sort_index().items()}

        if expect_canonical_counts:
            exp = expected_counts or {}
            exp_rows = int(exp.get("ellipses", EXPECTED_ROWS))
            exp_events = int(exp.get("events", EXPECTED_EVENTS))
            exp_dates = int(exp.get("selected_days", EXPECTED_DATES))
            exp_types = {int(k): int(v)
                         for k, v in (exp.get("type_counts")
                                      or EXPECTED_TYPE_COUNTS).items()}
            if summary["n_rows"] != exp_rows:
                problems.append(
                    f"expected {exp_rows} rows, found {summary['n_rows']}")
            if summary["n_events"] != exp_events:
                problems.append(
                    f"expected {exp_events} events, "
                    f"found {summary['n_events']}")
            if summary["n_dates"] != exp_dates:
                problems.append(
                    f"expected {exp_dates} unique dates, "
                    f"found {summary['n_dates']}")
            if summary["type_counts"] != exp_types:
                problems.append(
                    f"expected type counts {exp_types}, "
                    f"found {summary['type_counts']}")

    if problems:
        raise CatalogValidationError(
            "master catalog validation failed:\n  - " + "\n  - ".join(problems))
    return summary


def validate_event_parameters(df, expected_events=None):
    """Validate an event-parameters DataFrame; returns a small summary dict.

    ``expected_events`` (e.g. the YAML ``expected_counts.events``) makes the
    row count an additional hard requirement.
    """
    problems = []
    missing = [c for c in PARAMETERS_COLUMNS if c not in df.columns]
    if missing:
        problems.append(f"missing required columns: {missing}")
    if not problems:
        if df["new_event_id"].duplicated().any():
            problems.append("duplicated new_event_id rows")
        if expected_events is not None and df.shape[0] != int(expected_events):
            problems.append(
                f"expected {int(expected_events)} events, "
                f"found {int(df.shape[0])}")
    if problems:
        raise CatalogValidationError(
            "event parameters validation failed:\n  - " + "\n  - ".join(problems))
    return {"n_events": int(df.shape[0])}


def export_master(df, path):
    """Export a master catalog to CSV (or XLSX when path ends with .xlsx)."""
    path = str(path)
    if path.lower().endswith(".xlsx"):
        with pd.ExcelWriter(path, engine="openpyxl") as xw:
            df.to_excel(xw, sheet_name="master_cluster_ellipse", index=False)
    else:
        df.to_csv(path, index=False)
    return path
