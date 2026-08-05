# `legacy_defective_figure09/` - superseded pre-release Figure 9 artifacts

**HISTORICAL ONLY. These images are scientifically DEFECTIVE and are excluded
from all canonical publication outputs.** They are archived here so that the
correction is auditable, exactly as referenced by
`docs/FIGURE_PROVENANCE.csv` and `docs/REPRODUCIBILITY_MATRIX.csv`.

The superseded pre-release Figure 9 chain aggregated per-event ellipse
orientation with an ordinary arithmetic mean. Orientation is a
180-degree-periodic axial quantity, so the arithmetic mean is not
rotation-equivariant and is invalid; for Event 4 it produced -21.101 deg
where the correct doubled-angle axial mean is +68.98532754765856 deg
(north-referenced, clockwise, (-90, 90]).

| File | SHA-256 | Content |
|---|---|---|
| `Figure9_assembled_LEGACY_ARITHMETIC_DEFECTIVE.png` | `4cb3b38a5d80db8b2a936ed9ddf8246e2007609cd9c6ae1e6984256f1d1ffa04` | Superseded full-resolution render (arithmetic mean) |
| `Figure_09_LEGACY_ARITHMETIC_DEFECTIVE.png` | `b023c6e55359b69d74dd1b93f7199c2f82f12d782cd76f3de5170a8f36460ad1` | Superseded manuscript embed (downscale of the above) |

The corrected chain (v1.0.0) uses the doubled-angle axial mean via
`scripts/figures/common/scorch_axial.py`; the canonical full-resolution
render is `f4dce68d...` and the canonical manuscript embed is
`7859acbd9ea69047d5a85bda65c4eed25d3592d52c4b0bfaad0a3068226a1431`
(1950x637). Panels 9(a) and 9(b), event areas and axis ratios are
byte-identical between the superseded and corrected renders; only the
orientation-derived panel (c) and the event-orientation column changed.
