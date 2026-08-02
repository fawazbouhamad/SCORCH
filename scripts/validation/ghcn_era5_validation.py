"""ERA5 vs GHCNd station validation (Supplementary Fig. S.1 panels c-d).

Release-local, path-sanitized version. Reads the ARCHIVED station inputs from
the processed-data deposit's ``validation_station/`` directory (resolved via
``SCORCH_DATA_DIR``) and recomputes the reported metrics. Raw ERA5 is not
redistributed by this release; the archived `era5_aswan_cell_2016.csv` is the
extracted nearest-grid-cell daily Tmax series for the single Aswan cell only
(see docs/SOURCE_DATA_PROVENANCE.md).

Station EG000062414 (Aswan, Egypt); comparison window 2016-05-31..2016-06-12
(n = 9 overlapping days). Recomputes r = 0.9802, RMSE = 1.696 C,
bias(ERA5-GHCN) = -1.595 C (reported rounded: 0.98 / 1.70 / -1.60).
"""
import os
import numpy as np
import pandas as pd

import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.join(ROOT, "scripts", "figures", "common"))
from _clean_paths import DATA_DIR  # noqa: E402

STN = os.path.join(DATA_DIR, "validation_station")
OUT = os.path.join(os.environ.get(
    "SCORCH_OUT_DIR", os.path.join(ROOT, "reproduced")), "supplement")
os.makedirs(OUT, exist_ok=True)

PLOT_START, PLOT_END = "2016-05-31", "2016-06-12"


def main() -> None:
    ghcn = pd.read_csv(os.path.join(STN, "ghcnd_aswan_tmax_celsius.csv"))
    era5 = pd.read_csv(os.path.join(STN, "era5_aswan_cell_2016.csv"))
    ghcn["DATE"] = pd.to_datetime(ghcn["DATE"])
    era5["DATE"] = pd.to_datetime(era5["DATE"])

    df = pd.merge(era5[["DATE", "ERA5_TMAX_C"]],
                  ghcn[["DATE", "GHCNd_TMAX_C"]], on="DATE", how="left")
    win = df[(df["DATE"] >= PLOT_START) & (df["DATE"] <= PLOT_END)]
    m = win.dropna(subset=["GHCNd_TMAX_C", "ERA5_TMAX_C"]).copy()

    n = len(m)
    rmse = float(np.sqrt(np.mean((m["ERA5_TMAX_C"] - m["GHCNd_TMAX_C"]) ** 2)))
    bias = float(np.mean(m["ERA5_TMAX_C"] - m["GHCNd_TMAX_C"]))
    r = float(m["GHCNd_TMAX_C"].corr(m["ERA5_TMAX_C"]))

    out = win.copy()
    out["DATE"] = out["DATE"].dt.strftime("%Y-%m-%d")
    out.to_csv(os.path.join(OUT, "merged_station_validation.csv"), index=False)
    pd.DataFrame({"metric": ["n_overlap_days", "pearson_r", "rmse_C", "bias_C"],
                  "value": [n, round(r, 4), round(rmse, 4), round(bias, 4)]}
                 ).to_csv(os.path.join(OUT, "station_validation_metrics.csv"), index=False)

    print(f"n overlapping days = {n}")
    print(f"r    = {r:.4f}  (reported 0.98)")
    print(f"RMSE = {rmse:.4f} C  (reported 1.70)")
    print(f"bias = {bias:.4f} C  (reported -1.60)")


if __name__ == "__main__":
    main()
