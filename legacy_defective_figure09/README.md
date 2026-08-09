# `legacy_defective_figure09/` - superseded pre-release Figure 9 artifacts

**HISTORICAL ONLY. These images are scientifically DEFECTIVE and are excluded
from all canonical publication outputs.** They are archived so that the
correction is auditable, exactly as referenced by
`docs/FIGURE_PROVENANCE.csv` and `docs/REPRODUCIBILITY_MATRIX.csv`.

**The two rasters were REMOVED FROM GIT** to keep the source tree small; this
file remains as the public pointer record. They were **staged** as members of
the **locally built, locally verified v1.0.0 data-archive candidate**
`scorch_processed_data_v1.0.0.zip`, which is intended for the reserved data DOI
[10.5281/zenodo.21717752](https://doi.org/10.5281/zenodo.21717752).

**That archive candidate has NOT been uploaded, deposited, or published**, and
the DOI is reserved on an unpublished Zenodo draft, so it does not resolve. The
verification behind the hashes below is **local archive verification only** and
is NOT evidence of public availability: at present these two rasters are not
retrievable from Zenodo or anywhere else public, and they exist only in this
repository's Git history and in that local candidate. Their exact archive member
paths and hashes are in the table below and in the machine-readable crosswalk
`docs/RELOCATED_ARTIFACTS.csv`, whose `archive_publication_state` column records
the same local-only status.

The superseded pre-release Figure 9 chain aggregated per-event ellipse
orientation with an ordinary arithmetic mean. Orientation is a
180-degree-periodic axial quantity, so the arithmetic mean is not
rotation-equivariant and is invalid; for Event 4 it produced -21.101 deg
where the correct doubled-angle axial mean is +68.98532754765856 deg
(north-referenced, clockwise, (-90, 90]).

| Former repository path | Archive member path in `scorch_processed_data_v1.0.0.zip` | SHA-256 | Bytes | Content |
|---|---|---|---|---|
| `legacy_defective_figure09/Figure9_assembled_LEGACY_ARITHMETIC_DEFECTIVE.png` | `provenance_evidence/legacy_defective_figure09/Figure9_assembled_LEGACY_ARITHMETIC_DEFECTIVE.png` | `4cb3b38a5d80db8b2a936ed9ddf8246e2007609cd9c6ae1e6984256f1d1ffa04` | 944,684 | Superseded full-resolution render (arithmetic mean) |
| `legacy_defective_figure09/Figure_09_LEGACY_ARITHMETIC_DEFECTIVE.png` | `provenance_evidence/legacy_defective_figure09/Figure_09_LEGACY_ARITHMETIC_DEFECTIVE.png` | `b023c6e55359b69d74dd1b93f7199c2f82f12d782cd76f3de5170a8f36460ad1` | 274,118 | Superseded manuscript embed (downscale of the above) |

Both are binary PNGs, so their historical Windows-worktree bytes and their
repository-normalized bytes are the same bytes; the archive members are those
exact bytes, added verbatim with no transformation. The archive itself is
SHA-256 `8d6ca0c5cd77d672a7c73924a1d243dab01d1a592c1730389aa0f1a864871383`.

The corrected chain (v1.0.0) uses the doubled-angle axial mean via
`scripts/figures/common/scorch_axial.py`; the canonical full-resolution
render is `f4dce68d...` and the canonical manuscript embed is
`7859acbd9ea69047d5a85bda65c4eed25d3592d52c4b0bfaad0a3068226a1431`
(1950x637). Panels 9(a) and 9(b), event areas and axis ratios are
byte-identical between the superseded and corrected renders; only the
orientation-derived panel (c) and the event-orientation column changed.
