#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mechanically RE-DERIVE event type from the new event-global-max daily ellipse
counts, compare to the original/manual labels, and (if anything changed) UPDATE
the type columns of the global-max master dataset in place.

Per Dr. Najibi, the global-max type is defined purely from the daily ellipse
counts (NOT preserved from the old manual labels):

  Type 1: single-day event with exactly 1 ellipse.
  Type 2: single-day event with multiple (>1) ellipses.
  Type 3: multi-day event (>=2 days) whose days are CONSISTENT --
          every day has exactly 1 ellipse, OR every day has >1 ellipse.
  Type 4: multi-day event with MIXED structure -- at least one day with exactly
          1 ellipse AND at least one other day with >1 ellipse.

(No event-day has 0 ellipses under either method, so every day is 1 or >1.)

Outputs (reproduced/event_global_max_algorithm/comparison/):
  * event_type_reclassification_global_max.csv / .xlsx
  * type3_type4_transition_check.csv
  * TYPE_RECLASSIFICATION_SUMMARY.md

Side effect: rewrites the type columns (v3_type, type, event_type,
event_type_name, event_type_original) of the global-max master CSV + XLSX so they
carry the new mechanically-derived global-max type. The canonical workbook is
NEVER modified.
"""
from __future__ import annotations

import os
import sys

import pandas as pd

_THIS = os.path.abspath(__file__)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_THIS)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "figures", "common"))
import common as C  # noqa: E402
from _clean_paths import GENERATED_DIR  # noqa: E402

# Tier-B stage: operates in place on the master freshly built by
# build_event_global_max_master.py (env SCORCH_MASTER_FILE overrides).
NEW_DIR = os.environ.get(
    "SCORCH_GM_OUT_DIR",
    os.path.join(GENERATED_DIR, "event_global_max_algorithm"))
MASTER_CSV = os.environ.get("SCORCH_MASTER_FILE", os.path.join(
    NEW_DIR, "scorch_new_algorithm_master_cluster_ellipse_event_global_max.csv"))
MASTER_XLSX = os.path.join(
    NEW_DIR, "scorch_new_algorithm_master_cluster_ellipse_event_global_max.xlsx")
OUT = os.path.join(NEW_DIR, "comparison")
SHEET = "master_cluster_ellipse"

# Canonical formatting of each type label (mirrors the canonical workbook).
TYPE_FIELDS = {
    1: dict(type="Type 1", event_type="Type 1", event_type_name="Independent",
            event_type_original="Independent"),
    2: dict(type="Type 2", event_type="Type 2",
            event_type_name="Spatially clustered",
            event_type_original="Independent Simultaneous"),
    3: dict(type="Type 3", event_type="Type 3",
            event_type_name="Temporally clustered",
            event_type_original="Back-to-Back"),
    4: dict(type="Type 4", event_type="Type 4", event_type_name="Mixed",
            event_type_original="Mixed Multi-Day"),
}
TYPE_NAME = {1: "Type 1", 2: "Type 2", 3: "Type 3", 4: "Type 4"}


def derive_type(daily_counts) -> int:
    """Mechanical type from an ordered list of per-day ellipse counts."""
    counts = list(daily_counts)
    n_days = len(counts)
    if n_days <= 1:
        return 1 if counts and counts[0] == 1 else 2
    all_one = all(c == 1 for c in counts)
    all_multi = all(c > 1 for c in counts)
    return 3 if (all_one or all_multi) else 4


def _explain(old_seq, new_seq, old_t, new_t):
    nd = len(new_seq)
    if nd <= 1:
        struct = "single-day"
    elif all(c == 1 for c in new_seq):
        struct = "multi-day, every day has 1 ellipse (consistent)"
    elif all(c > 1 for c in new_seq):
        struct = "multi-day, every day has >1 ellipse (consistent)"
    else:
        struct = ("multi-day, mixed: at least one day with 1 ellipse and at "
                  "least one day with >1")
    if old_t == new_t:
        return f"No change. Global-max structure: {struct}."
    return (f"{TYPE_NAME[old_t]} -> {TYPE_NAME[new_t]}: global-max daily counts "
            f"{old_seq} -> {new_seq}; new structure is {struct}.")


def main() -> dict:
    os.makedirs(OUT, exist_ok=True)
    wb = C.load_workbook()
    wb["date"] = wb["date"].dt.strftime("%Y-%m-%d")
    master = pd.read_csv(MASTER_CSV)
    master["date"] = master["date"].astype(str)

    # full event-day universe (canonical) + old/new per-day ellipse counts
    ed = (wb.groupby(["new_event_id", "date"])
            .agg(event_id=("event_id", "first"),
                 old_label=("v3_type", "first"),
                 duration_days=("duration_days", "first"),
                 old_n=("day_final_n_clusters", "first")).reset_index())
    new_counts = master.groupby(["new_event_id", "date"]).size().rename("new_n")
    ed = ed.merge(new_counts, on=["new_event_id", "date"], how="left")
    ed["new_n"] = ed["new_n"].fillna(0).astype(int)
    ed = ed.sort_values(["new_event_id", "date"]).reset_index(drop=True)

    rows = []
    for eid, g in ed.groupby("new_event_id"):
        old_seq = g["old_n"].tolist()
        new_seq = g["new_n"].tolist()
        old_label = int(g["old_label"].iloc[0])
        old_mech = derive_type(old_seq)
        new_mech = derive_type(new_seq)
        rows.append(dict(
            new_event_id=int(eid), event_id=int(g["event_id"].iloc[0]),
            start_date=g["date"].iloc[0], end_date=g["date"].iloc[-1],
            duration_days=int(g["duration_days"].iloc[0]),
            n_days=int(g.shape[0]),
            old_type=TYPE_NAME[old_label],
            old_mechanical_type=TYPE_NAME[old_mech],
            new_global_max_type=TYPE_NAME[new_mech],
            daily_sequence_before_global_max="-".join(map(str, old_seq)),
            daily_sequence_after_global_max="-".join(map(str, new_seq)),
            changed_type=bool(old_label != new_mech),
            changed_due_to_algorithm=bool(old_mech != new_mech),
            original_label_matches_mechanical=bool(old_label == old_mech),
            old_type_int=old_label, new_global_max_type_int=new_mech,
            explanation=_explain(old_seq, new_seq, old_label, new_mech)))
    diag = pd.DataFrame(rows).sort_values("new_event_id").reset_index(drop=True)

    diag_cols = [
        "new_event_id", "event_id", "start_date", "end_date", "duration_days",
        "n_days", "old_type", "old_mechanical_type", "new_global_max_type",
        "daily_sequence_before_global_max", "daily_sequence_after_global_max",
        "changed_type", "changed_due_to_algorithm",
        "original_label_matches_mechanical", "explanation"]
    diag_out = diag[diag_cols]
    diag_out.to_csv(
        os.path.join(OUT, "event_type_reclassification_global_max.csv"),
        index=False)
    with pd.ExcelWriter(
            os.path.join(OUT, "event_type_reclassification_global_max.xlsx"),
            engine="openpyxl") as xw:
        diag_out.to_excel(xw, sheet_name="reclassification", index=False)

    # Type 3 <-> Type 4 transition check
    t34 = diag[(diag["old_type_int"].isin([3, 4])) &
               (diag["new_global_max_type_int"].isin([3, 4])) &
               (diag["old_type_int"] != diag["new_global_max_type_int"])]
    t34[diag_cols].to_csv(
        os.path.join(OUT, "type3_type4_transition_check.csv"), index=False)
    n_3to4 = int(((diag["old_type_int"] == 3) &
                  (diag["new_global_max_type_int"] == 4)).sum())
    n_4to3 = int(((diag["old_type_int"] == 4) &
                  (diag["new_global_max_type_int"] == 3)).sum())

    # ---- update master type columns to the new global-max mechanical type ----
    new_type_by_event = dict(zip(diag["new_event_id"],
                                 diag["new_global_max_type_int"]))
    changed_events = diag.loc[diag["changed_type"], "new_event_id"].tolist()
    master["v3_type"] = master["new_event_id"].map(new_type_by_event).astype(int)
    for fld in ("type", "event_type", "event_type_name", "event_type_original"):
        master[fld] = master["v3_type"].map(lambda t: TYPE_FIELDS[t][fld])
    master.to_csv(MASTER_CSV, index=False)
    with pd.ExcelWriter(MASTER_XLSX, engine="openpyxl") as xw:
        master.to_excel(xw, sheet_name=SHEET, index=False)

    # ---- markdown summary ----
    n_changed = int(diag["changed_type"].sum())
    lines = ["# Event-type reclassification under event-global-max\n",
             "Types are mechanically derived from the new global-max daily "
             "ellipse counts (definitions in the script header / "
             "`docs/EVENT_GLOBAL_MAX_ALGORITHM.md`).\n",
             f"- Original manual labels matching the mechanical definition under "
             f"the OLD daily counts: "
             f"**{int(diag['original_label_matches_mechanical'].sum())}/51** "
             f"(validates the definitions).",
             f"- Events whose type changed vs the original label: "
             f"**{n_changed}**.",
             f"- **Type 3 -> Type 4: {n_3to4}**.  **Type 4 -> Type 3: {n_4to3}**.",
             f"- Changed event IDs: "
             f"**{changed_events if changed_events else 'none'}**.",
             "- The global-max master CSV/XLSX type columns now carry the "
             "mechanically-derived global-max type.\n",
             "## Events that changed type\n"]
    chg = diag[diag["changed_type"]]
    if chg.empty:
        lines.append("_No events changed type._")
    else:
        lines.append(chg[["new_event_id", "start_date", "end_date",
                          "old_type", "new_global_max_type",
                          "daily_sequence_before_global_max",
                          "daily_sequence_after_global_max",
                          "explanation"]].to_markdown(index=False))
    with open(os.path.join(OUT, "TYPE_RECLASSIFICATION_SUMMARY.md"), "w",
              encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    print(f"[RECLASSIFY] changed vs original: {n_changed}  "
          f"(3->4: {n_3to4}, 4->3: {n_4to3})  changed IDs: {changed_events}")
    print(f"[RECLASSIFY] master type columns updated -> "
          f"{os.path.relpath(MASTER_CSV, REPO_ROOT)} (+ .xlsx)")
    if not chg.empty:
        print(chg[["new_event_id", "old_type", "new_global_max_type",
                   "daily_sequence_before_global_max",
                   "daily_sequence_after_global_max"]].to_string(index=False))
    return dict(n_changed=n_changed, n_3to4=n_3to4, n_4to3=n_4to3,
                changed_events=changed_events)


if __name__ == "__main__":
    main()
