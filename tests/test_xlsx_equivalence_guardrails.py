"""Adversarial guards on the CSV/XLSX semantic-equivalence evidence.

The equivalence run is the reproducible evidence behind an ``approved_removal``
record: it is what licenses deleting a shipped artifact. Evidence that can be
talked into agreeing is not evidence, so this file attacks the comparison with
mutations that a plausible-looking workbook could carry, and requires each one
to turn the verdict FAIL.

Four bypasses are covered, each independently:

A. **Fractional integer.** The old rule classified a column as integer-valued
   only when BOTH sides looked integral. Perturbing an XLSX integer to
   ``1.0000000000005`` demoted the column to "float", where its relative
   difference of 5e-13 slid under the 1e-12 tolerance and the run said PASS.
   Semantic type now comes from the canonical CSV alone.
B. **Signed infinity.** ``np.isinf`` is sign-blind, so ``+inf`` against
   ``-inf`` at the same cell produced identical masks and passed.
C. **External relationships** planted in a ``.rels`` part other than
   ``xl/_rels/workbook.xml.rels``, which was the only one ever read.
D. **Raw pivot parts** that openpyxl's object model does not expose.

A, C and D drive the real program end to end through a subprocess. B cannot:
the XLSX format cannot carry an infinity at all - openpyxl writes one and
pandas reads back ``NaN`` - so that predicate is exercised against the real
``compare()`` function with the workbook read monkeypatched. That is a genuine
limitation of the format, asserted explicitly below rather than papered over.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

openpyxl = pytest.importorskip("openpyxl")
np = pytest.importorskip("numpy")
pd = pytest.importorskip("pandas")

REPO = Path(__file__).resolve().parents[1]
PROGRAM = REPO / "remediation" / "xlsx_equivalence" / "compare_master_csv_xlsx.py"

STEM = "scorch_new_algorithm_master_cluster_ellipse_event_global_max"
CSV_NAME = f"{STEM}.csv"
XLSX_NAME = f"{STEM}.xlsx"
SHEET = "master_cluster_ellipse"

# Windows MAX_PATH is 260; pytest tmp dirs nest deeply and the production
# filenames are long, so synthetic data roots live under a short external root.
_SHORT_ROOT = Path(os.environ.get("TEMP") or "/tmp") / "sgxx"

_EXT_REL = (
    '<Relationship Id="rIdExternal99" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
    'relationships/hyperlink" '
    'Target="https://example.invalid/planted-external-target.xlsx" '
    'TargetMode="External"/>')
_SHEET_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
    'relationships">' + _EXT_REL + '</Relationships>')
_PIVOT_CACHE_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<pivotCacheDefinition xmlns="http://schemas.openxmlformats.org/'
    'spreadsheetml/2006/main" recordCount="0"/>')
_PIVOT_TABLE_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<pivotTableDefinition xmlns="http://schemas.openxmlformats.org/'
    'spreadsheetml/2006/main" name="PlantedPivot" cacheId="1"/>')


def _program():
    """The real comparison module, imported by path."""
    spec = importlib.util.spec_from_file_location("_scorch_xlsx_cmp", PROGRAM)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


INTEGER_COLUMNS = _program().INTEGER_SCHEMA_COLUMNS
FLOAT_COLUMNS = ("area_km2", "shape_ratio", "orientation_deg")
N_ROWS = 6


def _rows():
    """A small frame that honours the real schema: 20 integers, floats, keys."""
    out = []
    for i in range(N_ROWS):
        row = {c: i + 1 for c in INTEGER_COLUMNS}
        row["new_event_id"] = i + 1          # keys distinct per row
        row["cluster_id"] = i + 1
        row["date"] = f"2003-08-{i + 1:02d}"
        row["type_label"] = f"Type {i % 4 + 1}"
        row["area_km2"] = 1234.5678 + i
        row["shape_ratio"] = 0.618033 + i / 100
        row["orientation_deg"] = -12.5 + i
        out.append(row)
    return out


def _columns():
    cols = ["new_event_id", "date", "cluster_id", "type_label"]
    cols += [c for c in INTEGER_COLUMNS if c not in cols]
    cols += list(FLOAT_COLUMNS)
    return cols


def _write_pair(root: Path, xlsx_overrides=None):
    """Write catalogs/<CSV> and catalogs/<XLSX>; return the data root.

    ``xlsx_overrides`` maps (row_index, column) -> value and is applied to the
    XLSX only, so the canonical CSV stays authoritative.
    """
    cat = root / "catalogs"
    cat.mkdir(parents=True, exist_ok=True)
    cols = _columns()
    rows = _rows()

    with open(cat / CSV_NAME, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: r[c] for c in cols})

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = SHEET
    ws.append(cols)
    for i, r in enumerate(rows):
        values = dict(r)
        for (ri, col), val in (xlsx_overrides or {}).items():
            if ri == i:
                values[col] = val
        ws.append([values[c] for c in cols])
    wb.save(cat / XLSX_NAME)
    wb.close()
    return root


def _rezip(src: Path, dest: Path, add=None, replace=None):
    """Rewrite a ZIP, replacing member bytes and/or adding new members."""
    add, replace = add or {}, replace or {}
    with zipfile.ZipFile(src) as zin:
        items = [(i.filename, zin.read(i.filename)) for i in zin.infolist()]
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in items:
            zout.writestr(name, replace.get(name, data))
        for name, data in add.items():
            zout.writestr(name, data)
    return dest


def _run(root: Path):
    """Invoke the REAL comparison program in a subprocess."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("SCORCH_")}
    env["SCORCH_DATA_DIR"] = str(root)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run([sys.executable, str(PROGRAM)],
                          cwd=REPO, env=env, capture_output=True, text=True,
                          timeout=900)
    out = (proc.stdout or "") + (proc.stderr or "")
    report = None
    if "{" in out:
        try:
            report = json.loads(out[out.index("{"):out.rindex("}") + 1])
        except ValueError:
            report = None
    return proc.returncode, out, report


@pytest.fixture
def data_root(request):
    """A short external data root, isolated per test."""
    name = "".join(ch if ch.isalnum() else "_"
                   for ch in request.node.name)[:24]
    root = _SHORT_ROOT / name
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _assert_cells_equivalent(report):
    """Every cell-level check passed, so only the STRUCTURAL condition failed.

    Without this the mutant would prove nothing: a run that failed because the
    values also diverged would not show the new structural guard doing any work.
    """
    c = report["comparison"]
    assert c["cell_equivalence_ok"] is True, c["failures"]
    assert c["structural_failures"], (
        "the run failed, but not for a structural reason")
    assert c["string_differing_cells"] == 0
    assert c["integer_differing_cells"] == 0
    assert c["integer_non_integral_cells"] == 0
    assert c["numeric_differing_cells"] == 0
    assert c["nan_mask_identical"] is True
    assert c["signed_inf_mask_identical"] is True


def _plant(data_root, add=None, replace=None):
    """Rewrite the synthetic workbook in place with planted parts."""
    xlsx = data_root / "catalogs" / XLSX_NAME
    staged = xlsx.with_name("staged.xlsx")
    shutil.move(str(xlsx), str(staged))
    _rezip(staged, xlsx, add=add, replace=replace)
    staged.unlink()
    return xlsx


# ---------------------------------------------------------------------------
# 0. Positive control - an unmodified synthetic pair must PASS.
# ---------------------------------------------------------------------------
def test_valid_synthetic_pair_passes(data_root):
    _write_pair(data_root)
    code, out, report = _run(data_root)
    assert code == 0, f"valid pair did not PASS:\n{out[-3000:]}"
    assert report["verdict"] == "PASS", out[-2000:]
    assert report["comparison"]["failures"] == []
    assert report["comparison"]["integer_valued_columns"] >= 20
    assert report["comparison"]["integer_schema_columns_missing"] == []
    assert report["workbook_structure"]["inert"] is True
    assert report["workbook_structure"]["pivot_zip_parts"] == []


def test_schema_is_pinned_at_twenty_columns():
    assert len(INTEGER_COLUMNS) == 20
    assert len(set(INTEGER_COLUMNS)) == 20


# ---------------------------------------------------------------------------
# A. Fractional integer that hides under the relative tolerance.
# ---------------------------------------------------------------------------
def test_fractional_integer_below_rel_tol_fails(data_root):
    """The exact bypass: 1 -> 1.0000000000005 in a non-key integer column."""
    perturbed = 1.0000000000005
    rel = abs(perturbed - 1.0) / max(abs(perturbed), 1.0)
    assert rel < 1e-12, (
        f"the mutation must hide UNDER the tolerance to be a real bypass; "
        f"relative difference was {rel!r}")

    _write_pair(data_root, xlsx_overrides={(0, "duration_days"): perturbed})
    code, out, report = _run(data_root)

    assert code == 1, f"fractional integer was accepted:\n{out[-3000:]}"
    assert report["verdict"] == "FAIL"
    c = report["comparison"]
    assert "duration_days" in c["integer_non_integral_columns"], c
    assert c["integer_non_integral_cells"] >= 1
    assert any("fractional" in f for f in c["failures"]), c["failures"]
    # and the column must still be CLASSIFIED as an integer column
    assert "duration_days" in c["integer_valued_column_names"]


def test_integer_classification_ignores_the_xlsx(data_root):
    """Even a whole column of fractions must not demote the schema type."""
    _write_pair(data_root, xlsx_overrides={
        (i, "day_n_noise_cells"): i + 1.5 for i in range(N_ROWS)})
    code, out, report = _run(data_root)
    assert code == 1, out[-3000:]
    c = report["comparison"]
    assert "day_n_noise_cells" in c["integer_valued_column_names"], (
        "the XLSX was allowed to influence semantic classification")
    assert "day_n_noise_cells" in c["integer_non_integral_columns"]


def test_canonical_csv_must_satisfy_its_own_schema(data_root):
    """If the CSV itself breaks the schema, the schema is wrong - say so."""
    _write_pair(data_root)
    csv_path = data_root / "catalogs" / CSV_NAME
    lines = csv_path.read_text(encoding="utf-8").splitlines()
    idx = _columns().index("union_cells")
    parts = lines[1].split(",")
    parts[idx] = "3.5"
    lines[1] = ",".join(parts)
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    code, out, report = _run(data_root)
    assert code == 1, out[-3000:]
    c = report["comparison"]
    assert "union_cells" in c["canonical_csv_schema_violations"], c
    assert any("violates its own integer schema" in f for f in c["failures"])


# ---------------------------------------------------------------------------
# B. Signed infinity, against the real compare() function.
#
# The XLSX format cannot carry an infinity: openpyxl writes one and pandas
# reads back NaN (asserted below, so this justification stays honest). The
# predicate is therefore exercised on the real comparison function with the
# workbook read replaced.
# ---------------------------------------------------------------------------
def test_xlsx_format_cannot_carry_infinity(data_root):
    """Documents WHY test B cannot go through a real workbook."""
    cat = data_root / "catalogs"
    cat.mkdir(parents=True, exist_ok=True)
    p = cat / "probe.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = SHEET
    ws.append(["v"])
    ws.append([float("inf")])
    wb.save(p)
    wb.close()
    back = pd.read_excel(p, sheet_name=SHEET)["v"].to_numpy(dtype=np.float64,
                                                            na_value=np.nan)
    assert not np.isinf(back).any(), (
        "the XLSX round-trip preserved an infinity after all - test B should "
        "be promoted to a full subprocess run")


@pytest.mark.parametrize("csv_val,xlsx_val,expect", [
    (np.inf, -np.inf, "posinf"),
    (-np.inf, np.inf, "neginf"),
])
def test_signed_infinity_mismatch_fails(data_root, monkeypatch,
                                        csv_val, xlsx_val, expect):
    """+inf vs -inf at the same cell must FAIL, though |isinf| masks agree."""
    _write_pair(data_root)
    cat = data_root / "catalogs"
    mod = _program()

    csv_df = pd.read_csv(cat / CSV_NAME)
    csv_df.loc[0, "area_km2"] = csv_val
    xlsx_df = csv_df.copy()
    xlsx_df.loc[0, "area_km2"] = xlsx_val

    a = csv_df["area_km2"].to_numpy(dtype=np.float64)
    b = xlsx_df["area_km2"].to_numpy(dtype=np.float64)
    assert np.array_equal(np.isinf(a), np.isinf(b)), (
        "the UNSIGNED infinity masks must be identical, otherwise this proves "
        "nothing about sign handling")

    monkeypatch.setattr(pd, "read_csv", lambda *a, **k: csv_df.copy())
    monkeypatch.setattr(pd, "read_excel", lambda *a, **k: xlsx_df.copy())
    result = mod.compare(cat / CSV_NAME, cat / XLSX_NAME)

    assert result["signed_inf_mask_identical"] is False, result
    assert result["inf_mask_identical"] is True, (
        "sanity: the sign-blind mask still agrees, which is the whole point")
    if expect == "posinf":
        assert "area_km2" in result["posinf_mask_mismatch_columns"]
    else:
        assert "area_km2" in result["neginf_mask_mismatch_columns"]
    assert any("infinity masks differ" in f for f in result["failures"]), (
        result["failures"])


def test_matching_signed_infinity_is_accepted(data_root, monkeypatch):
    """Identical signed infinities must NOT fail - the guard is not blanket."""
    _write_pair(data_root)
    cat = data_root / "catalogs"
    mod = _program()
    csv_df = pd.read_csv(cat / CSV_NAME)
    csv_df.loc[0, "area_km2"] = np.inf
    csv_df.loc[1, "area_km2"] = -np.inf
    xlsx_df = csv_df.copy()

    monkeypatch.setattr(pd, "read_csv", lambda *a, **k: csv_df.copy())
    monkeypatch.setattr(pd, "read_excel", lambda *a, **k: xlsx_df.copy())
    result = mod.compare(cat / CSV_NAME, cat / XLSX_NAME)
    assert result["signed_inf_mask_identical"] is True
    assert result["failures"] == [], result["failures"]


# ---------------------------------------------------------------------------
# C. External relationships in parts that were never scanned.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("part", [
    "_rels/.rels",
    "xl/worksheets/_rels/sheet1.xml.rels",
])
def test_external_relationship_in_any_rels_part_fails(data_root, part):
    _write_pair(data_root)
    xlsx = data_root / "catalogs" / XLSX_NAME
    with zipfile.ZipFile(xlsx) as zin:
        names = set(zin.namelist())
        existing = zin.read(part) if part in names else None

    if existing is not None:
        patched = existing.replace(
            b"</Relationships>", _EXT_REL.encode("utf-8") + b"</Relationships>")
        assert patched != existing, f"could not plant into {part}"
        _plant(data_root, replace={part: patched})
    else:
        _plant(data_root, add={part: _SHEET_RELS.encode("utf-8")})

    code, out, report = _run(data_root)
    assert code == 1, f"external relationship in {part} accepted:\n{out[-3000:]}"
    w = report["workbook_structure"]
    assert part in w["relationship_parts_scanned"], (
        f"{part} was never scanned; scanned={w['relationship_parts_scanned']}")
    assert w["relationship_parts_scanned_count"] >= 2
    assert w["external_rel_targets"] >= 1
    assert part in w["external_relationship_parts"], w
    assert any("planted-external-target" in t
               for t in w["external_relationship_targets_detail"]), w
    assert w["inert"] is False
    _assert_cells_equivalent(report)


def test_unparseable_rels_part_fails_closed(data_root):
    """A malformed relationship part is absence of evidence, not evidence."""
    _write_pair(data_root)
    _plant(data_root, add={"xl/worksheets/_rels/sheet1.xml.rels":
                           b"<Relationships><not-closed>"})
    code, out, report = _run(data_root)
    assert code == 1, f"malformed .rels accepted:\n{out[-3000:]}"
    assert report is not None, (
        f"the run must still emit a structured report, not a bare traceback:\n"
        f"{out[-3000:]}")
    w = report["workbook_structure"]
    assert w["relationship_parse_errors"], w
    assert "xl/worksheets/_rels/sheet1.xml.rels" in [
        e["part"] for e in w["relationship_parse_errors"]], w
    assert w["inert"] is False
    assert report["verdict"] == "FAIL"


# ---------------------------------------------------------------------------
# D. Raw pivot parts the object model does not expose.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("part,payload", [
    ("xl/pivotCache/pivotCacheDefinition1.xml", _PIVOT_CACHE_XML),
    ("xl/pivotTables/pivotTable1.xml", _PIVOT_TABLE_XML),
])
def test_raw_pivot_part_fails_even_with_zero_pivot_objects(data_root, part,
                                                           payload):
    _write_pair(data_root)
    _plant(data_root, add={part: payload.encode("utf-8")})

    code, out, report = _run(data_root)
    assert code == 1, f"raw pivot part accepted:\n{out[-3000:]}"
    w = report["workbook_structure"]
    assert part in w["pivot_zip_parts"], w["pivot_zip_parts"]
    assert w["inert"] is False
    # The point of the guard: the object model saw nothing.
    assert w["pivot_caches"] == 0 and w["worksheet_pivots"] == 0, (
        "openpyxl exposed a pivot object, so this does not prove the RAW scan "
        "is what caught it")
    _assert_cells_equivalent(report)
