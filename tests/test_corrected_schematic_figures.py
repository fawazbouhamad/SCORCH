"""Determinism guards for the corrected schematic Figures 1 and 4.

The 2026-08 correction round gave both schematic figures runnable
producers. These tests regenerate each figure into a temporary directory
and require byte-identity with the shipped canonical asset in
``assets/frozen_figures/``, which is itself byte-identical to the
manuscript embed. They also re-verify the Figure 4 locality guarantee
(pixel changes confined to the two lower Type 4 arrow boxes).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FROZEN = REPO / "assets" / "frozen_figures"
FIG01_SCRIPT = REPO / "scripts" / "figures" / "fig01" / "make_fig01_workflow.py"
FIG04_SCRIPT = REPO / "scripts" / "figures" / "fig04" / "correct_fig04_type4_arrows.py"
FIG04_ORIGINAL = REPO / "scripts" / "figures" / "fig04" / "original" / "Figure_04_original.png"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.mark.skipif(not FIG01_SCRIPT.exists(), reason="fig01 producer missing")
def test_fig01_reproduces_byte_identical(tmp_path):
    subprocess.run([sys.executable, str(FIG01_SCRIPT), "--out", str(tmp_path)],
                   check=True, cwd=REPO)
    assert _sha(tmp_path / "Figure_01.png") == _sha(FROZEN / "fig01" / "Figure_01.png")


@pytest.mark.skipif(not FIG04_SCRIPT.exists() or not FIG04_ORIGINAL.exists(),
                    reason="fig04 corrector or archived original missing")
def test_fig04_reproduces_byte_identical_and_local(tmp_path):
    subprocess.run([sys.executable, str(FIG04_SCRIPT),
                    "--src", str(FIG04_ORIGINAL), "--out", str(tmp_path)],
                   check=True, cwd=REPO)
    assert _sha(tmp_path / "Figure_04.png") == _sha(FROZEN / "fig04" / "Figure_04.png")
    report = json.loads((tmp_path / "fig04_diff_report.json").read_text())
    assert report["locality_ok"] is True
    assert report["changed_pixels_outside_boxes"] == 0
    assert len(report["lower_arrow_boxes_rotated_180"]) == 2
    assert len(report["upper_arrow_boxes_untouched"]) == 2
