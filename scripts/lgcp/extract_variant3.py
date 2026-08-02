# --- SCORCH release bootstrap (auto-inserted; release-relative, no absolute paths) ---
import os as _os, sys as _sys
def _scorch_find_root(_p):
    while _p != _os.path.dirname(_p):
        if _os.path.isdir(_os.path.join(_p, "scripts")) and _os.path.isdir(_os.path.join(_p, "configs")):
            return _p
        _p = _os.path.dirname(_p)
    return _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_SCORCH_ROOT = _os.environ.get("SCORCH_RELEASE_ROOT") or _scorch_find_root(_os.path.dirname(_os.path.abspath(__file__)))
_os.environ["SCORCH_RELEASE_ROOT"] = _SCORCH_ROOT
_sys.path.insert(0, _os.path.join(_SCORCH_ROOT, "scripts", "figures", "common"))
from _clean_paths import GENERATED_DIR as _SCORCH_REPRO  # noqa: E402  central helper; honours SCORCH_OUT_DIR
# --- end SCORCH release bootstrap ---
"""Deterministic extraction of the Figure-12 Tier-A input from the full LGCP
variants table (Part 6 canonical chain step 3->4).

    grid_predicted_intensity_all_variants.csv   (R/spatstat diagnostics output)
        -> [lon, lat, pred_intensity_x1e6_variant3]
        -> grid_predicted_intensity_variant3.csv

No model fitting; pure column selection in stable row order. Reads from
data/processed/lgcp/ and writes to reproduced/lgcp/. Verifies byte/numeric
equality against the frozen data/processed/grid_predicted_intensity_variant3.csv.
"""
import os
import pandas as pd

from _clean_paths import data_file  # noqa: E402  (on sys.path via bootstrap)

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(_HERE))  # <root>/scripts/lgcp -> <root>
SRC = data_file("grid_predicted_intensity_all_variants.csv", "lgcp")
FROZEN = data_file("grid_predicted_intensity_variant3.csv", "catalogs")
OUT_DIR = os.path.join(os.environ.get(
    "SCORCH_OUT_DIR", os.path.join(ROOT, "reproduced")), "lgcp")
OUT = os.path.join(OUT_DIR, "grid_predicted_intensity_variant3.csv")

COLS = ["lon", "lat", "pred_intensity_x1e6_variant3"]


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    df = pd.read_csv(SRC)
    out = df[COLS].copy()
    out.to_csv(OUT, index=False)
    print(f"[extract] wrote {len(out)} rows -> {OUT}")

    frozen = pd.read_csv(FROZEN)
    same_shape = out.shape == frozen.shape
    # numeric equality within float tolerance
    import numpy as np
    max_abs = float(np.max(np.abs(out.values - frozen.values))) if same_shape else float("nan")
    ok = same_shape and max_abs < 1e-9
    print(f"[verify] shape match={same_shape} max_abs_diff={max_abs:.3e} EQUAL={ok}")
    if not ok:
        raise SystemExit("variant-3 extraction does NOT match frozen CSV")


if __name__ == "__main__":
    main()
