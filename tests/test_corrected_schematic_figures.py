"""Determinism guards for the corrected schematic Figures 1 and 4.

The 2026-08 author-directed figure correction round restored both
schematic figures to Dr. Najibi's original slide exports with the
smallest authorized deterministic edits (Figure 1: threshold wording
"greater than or equal to"; Figure 4: horizontal Type 4 two -> one ->
two progression). These tests regenerate each figure into a temporary
directory and require byte-identity with the shipped canonical asset in
``assets/frozen_figures/``, which is itself byte-identical to the
manuscript embed. They also re-verify each producer's locality
guarantee (pixel changes confined to the authorized regions).
"""
from __future__ import annotations

import hashlib
import os
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FROZEN = REPO / "assets" / "frozen_figures"
FIG01_SCRIPT = (REPO / "scripts" / "figures" / "fig01" /
                "restore_fig01_original_threshold.py")
FIG01_ORIGINAL = (REPO / "scripts" / "figures" / "fig01" / "original" /
                  "Figure_01_original.png")
# Resolved from the environment only; no workstation path is embedded.
_APTOS = os.environ.get("SCORCH_APTOS_FONT", "").strip()
FIG01_FONT = Path(_APTOS) if _APTOS else None
FIG04_SCRIPT = (REPO / "scripts" / "figures" / "fig04" /
                "correct_fig04_type4_horizontal.py")
FIG04_ORIGINAL = (REPO / "scripts" / "figures" / "fig04" / "original" /
                  "Figure_04_original.png")
# Since the 2026-08 symmetry round this stage no longer produces the SHIPPED
# Figure 4: it produces the immutable donor that the active canonical
# producer (make_fig04_symmetry_final.py) consumes. The determinism and
# locality guarantees below are unchanged and still asserted byte-for-byte,
# now against the artifact this stage actually emits. The shipped asset is
# guarded separately, and more strictly, by test_fig04_symmetry_final.py.
FIG04_DONOR = (REPO / "scripts" / "figures" / "fig04" / "donor" /
               "Figure_04_approved_horizontal.png")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.mark.skipif(not FIG01_SCRIPT.exists() or not FIG01_ORIGINAL.exists(),
                    reason="fig01 restorer or archived original missing")
def test_fig01_reproduces_byte_identical_and_local(tmp_path):
    if FIG01_FONT is None or not FIG01_FONT.exists():
        pytest.skip("pinned Aptos Regular font not available; set "
                    "SCORCH_APTOS_FONT (Microsoft 365 cloud font, "
                    "not redistributable)")
    subprocess.run([sys.executable, str(FIG01_SCRIPT), "--out", str(tmp_path)],
                   check=True, cwd=REPO)
    assert _sha(tmp_path / "Figure_01.png") == _sha(
        FROZEN / "fig01" / "Figure_01.png")
    report = json.loads((tmp_path / "fig01_diff_report.json").read_text())
    assert report["locality_ok"] is True
    assert report["changed_pixels_outside_band"] == 0
    assert report["new_line"] == (
        "than or equal to a regional P97.5th threshold")


@pytest.mark.skipif(not FIG04_SCRIPT.exists() or not FIG04_ORIGINAL.exists()
                    or not FIG04_DONOR.exists(),
                    reason="fig04 corrector, archived original or immutable "
                           "donor missing")
def test_fig04_horizontal_stage_reproduces_donor_byte_identical_and_local(
        tmp_path):
    subprocess.run([sys.executable, str(FIG04_SCRIPT),
                    "--src", str(FIG04_ORIGINAL), "--out", str(tmp_path)],
                   check=True, cwd=REPO)
    assert _sha(tmp_path / "Figure_04.png") == _sha(FIG04_DONOR)
    report = json.loads((tmp_path / "fig04_diff_report.json").read_text())
    assert report["locality_ok"] is True
    assert report["changed_pixels_outside_boxes"] == 0
    assert len(report["right_arrow_boxes_rotated_180"]) == 2
    assert len(report["left_arrow_boxes_untouched"]) == 2
