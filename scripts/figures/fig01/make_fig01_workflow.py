"""Deterministic, code-native source for manuscript Figure 1 (SCORCH workflow).

This replaces the earlier author slide export, whose second and third
description boxes misstated the workflow order (regional selection wording
and "spatial connectivity ... clustering into compound heatwaves"). The
corrected figure communicates the implemented order:

  1. ERA5 hourly 2-m temperature -> Apr-Sep daily Tmax, 1940-2025, 1-deg grid
  2. Local grid-cell heatwave episodes (grid-specific P95 Tmax + persistence)
  3. Retain regionally extensive days with N_HW(t) >= 371 (empirical regional
     97.5th-percentile grid-cell-count threshold)
  4. Maximal consecutive-day runs of retained days define the compound events
  5. Event-consistent DBSCAN delineates simultaneous daily heat structures
  6. Unweighted PCA geometry; completed ellipse rigidly translated to the
     raw-Celsius Tmax-weighted centroid
  7. Event-type classification and geometric/temporal/upper-tail/centroid-
     concentration analyses

Visual style, color family, canvas ratio (16:9, 4500x2531 px at 300 dpi) and
the two-column box/arrow layout follow the previous approved artwork.

Usage: python make_fig01_workflow.py [--out OUTDIR]   (default: reproduced/fig01)
Outputs: Figure_01.png (300 dpi) and Figure_01.pdf, deterministic
(no timestamps; PDF CreationDate suppressed).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle, FancyArrow

# Colors sampled from the previous approved artwork (kept in the same family).
ROWS = [
    {
        "border": "#000000", "label_color": "#000000",
        "label": "Maximum\nTemperature Data",
        "desc": ("Obtain daily maximum temperature (Tmax) for the\n"
                 "warm season (Apr–Sep: 1940–2025) from hourly ERA5\n"
                 "2-m temperature over the Eastern Mediterranean &\n"
                 "Middle East (EMME), aggregated to the 1° analysis grid"),
    },
    {
        "border": "#F87200", "label_color": "#7A3008",
        "label": "Identifying\nExtreme\nHeatwaves",
        "desc": ("Identify local heatwave episodes from grid-specific\n"
                 "P95th Tmax thresholds and the persistence rule;\n"
                 "retain regionally extensive days with "
                 r"$N_{\mathrm{HW}}(t) \geq 371$" "\n"
                 "heatwave-labeled cells (the empirical regional\n"
                 "P97.5th grid-cell-count threshold)"),
    },
    {
        "border": "#D868C8", "label_color": "#7030A0",
        "label": "Delineating\nCompound Events\n& Heat Structures",
        "desc": ("Group retained days into maximal consecutive-day\n"
                 "runs, which define the compound events; then\n"
                 "delineate the simultaneous daily heat structures\n"
                 "within each event using event-consistent DBSCAN"),
    },
    {
        "border": "#0870A0", "label_color": "#106080",
        "label": "Process-based\nCompound\nHeatwaves",
        "desc": ("Quantify unweighted PCA ellipse geometry, rigidly\n"
                 "translate each completed ellipse to its raw-Celsius\n"
                 "Tmax-weighted centroid, classify event types 1–4, and\n"
                 "analyze geometry, time, area tails, and centroid\n"
                 "concentration"),
    },
]

# Row vertical centers (axes fraction, from top) and box height, mirroring the
# previous artwork's spacing.
ROW_Y = [0.893, 0.631, 0.369, 0.100]
BOX_H = 0.175
LEFT_X, LEFT_W = 0.065, 0.30
RIGHT_X, RIGHT_W = 0.415, 0.55


def build(out_dir: Path) -> None:
    fig = plt.figure(figsize=(15.0, 8.4367), dpi=300)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    for i, row in enumerate(ROWS):
        y = ROW_Y[i]
        # Left rounded stage box
        ax.add_patch(FancyBboxPatch(
            (LEFT_X, y - BOX_H / 2), LEFT_W, BOX_H,
            boxstyle="round,pad=0,rounding_size=0.025",
            linewidth=2.2, edgecolor=row["border"], facecolor="white",
            mutation_aspect=15.0 / 8.4367))
        ax.text(LEFT_X + LEFT_W / 2, y, row["label"],
                ha="center", va="center", fontsize=15.5, fontweight="bold",
                color=row["label_color"], linespacing=1.35)
        # Right description box (sharp corners)
        ax.add_patch(Rectangle(
            (RIGHT_X, y - BOX_H / 2), RIGHT_W, BOX_H,
            linewidth=2.2, edgecolor=row["border"], facecolor="white"))
        ax.text(RIGHT_X + RIGHT_W / 2, y, row["desc"],
                ha="center", va="center", fontsize=13.2, color="black",
                linespacing=1.4)

    # Downward arrows between consecutive rows in both columns.
    for i in range(3):
        y0 = ROW_Y[i] - BOX_H / 2 - 0.008
        y1 = ROW_Y[i + 1] + BOX_H / 2 + 0.008
        # Left column: thick arrow
        ax.add_patch(FancyArrow(
            LEFT_X + LEFT_W / 2, y0, 0, y1 - y0,
            width=0.004, head_width=0.016, head_length=0.030,
            length_includes_head=True, color="black"))
        # Right column: thin arrow
        ax.add_patch(FancyArrow(
            RIGHT_X + RIGHT_W / 2, y0, 0, y1 - y0,
            width=0.0012, head_width=0.011, head_length=0.026,
            length_includes_head=True, color="black"))

    out_dir.mkdir(parents=True, exist_ok=True)
    png = out_dir / "Figure_01.png"
    pdf = out_dir / "Figure_01.pdf"
    fig.savefig(png, dpi=300, facecolor="white")
    fig.savefig(pdf, facecolor="white",
                metadata={"CreationDate": None, "Producer": None,
                          "Creator": "SCORCH make_fig01_workflow.py"})
    plt.close(fig)
    print(f"wrote {png} and {pdf}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reproduced/fig01")
    args = ap.parse_args()
    build(Path(args.out))
