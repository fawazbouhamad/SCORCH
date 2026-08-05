"""Repository-level output isolation guards (V7).

The documented contract of ``run_reproduction.py`` is that EVERY generated
read and write of a reproduction run lands under the requested output
directory (``--out-dir`` / ``SCORCH_OUT_DIR``) and that the source tree —
including the repository-level ``reproduced/`` default — is never modified
when a different output directory is requested.

These tests fail on any FUTURE script that reintroduces a hardcoded
repository-root ``reproduced/`` path instead of routing through the central
helper (``scripts/figures/common/_clean_paths.py``) or the sanctioned
``SCORCH_OUT_DIR`` environment fallback:

* a static source scan over every shipped script and the driver;
* a live check that the central helper honours ``SCORCH_OUT_DIR``;
* a bootstrap-block check that every ``_SCORCH_REPRO`` consumer aliases the
  central helper's ``GENERATED_DIR`` (never a repository-root join);
* a functional stage run (deposit required, else skipped) proving writes
  land ONLY under the requested external output directory.
"""
import ast
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

RELEASE_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = RELEASE_ROOT / "scripts"
COMMON_DIR = SCRIPTS_DIR / "figures" / "common"
CENTRAL_HELPER = COMMON_DIR / "_clean_paths.py"

# The one sanctioned *definition* form outside the helper: an environment
# fallback that only uses the repository default when SCORCH_OUT_DIR (or the
# legacy alias) is absent.
_SANCTION_TOKENS = ("SCORCH_OUT_DIR", "SCORCH_CLEAN_OUT")

# Never allowed anywhere: a repository-root join that bypasses the
# environment override entirely.
_FORBIDDEN = re.compile(
    r"join\s*\(\s*_?SCORCH_ROOT\s*,\s*['\"]reproduced['\"]")


def _python_sources():
    yield RELEASE_ROOT / "run_reproduction.py"
    for path in sorted(SCRIPTS_DIR.rglob("*.py")):
        yield path
    for path in sorted((RELEASE_ROOT / "src").rglob("*.py")):
        if "egg-info" not in str(path):
            yield path


def _docstring_positions(tree):
    """Line spans of module/class/function docstrings (exempt from scan)."""
    spans = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                spans.append((body[0].lineno, body[0].end_lineno))
    return spans


def test_no_hardcoded_repo_reproduced_paths():
    """No script may join a root path to 'reproduced' outside the sanctioned
    environment-fallback form or the central helper itself."""
    violations = []
    for path in _python_sources():
        text = path.read_text(encoding="utf-8", errors="replace")
        if path.resolve() == CENTRAL_HELPER.resolve():
            continue  # the central helper is the single sanctioned home
        for m in _FORBIDDEN.finditer(text):
            line_no = text.count("\n", 0, m.start()) + 1
            violations.append(f"{path}:{line_no}: forbidden repository-root "
                              f"'reproduced' join: {m.group(0)!r}")
        # Every bare "reproduced" string constant must sit inside a
        # statement that carries the environment override.
        try:
            tree = ast.parse(text)
        except SyntaxError:  # pragma: no cover - shipped sources parse
            violations.append(f"{path}: not parseable")
            continue
        doc_spans = _docstring_positions(tree)
        lines = text.splitlines()
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant)
                    and node.value == "reproduced"):
                if any(a <= node.lineno <= b for a, b in doc_spans):
                    continue
                lo = max(0, node.lineno - 2)
                hi = min(len(lines), (node.end_lineno or node.lineno) + 1)
                window = "\n".join(lines[lo:hi])
                if not any(tok in window for tok in _SANCTION_TOKENS):
                    violations.append(
                        f"{path}:{node.lineno}: 'reproduced' path constant "
                        "without a SCORCH_OUT_DIR environment fallback")
    assert not violations, (
        "Scripts bypass the requested output directory "
        "(SCORCH_OUT_DIR):\n" + "\n".join(violations))


def test_clean_paths_honours_scorch_out_dir(tmp_path):
    """The central helper resolves GENERATED_DIR from SCORCH_OUT_DIR."""
    out_dir = tmp_path / "external_out"
    env = dict(os.environ)
    env["SCORCH_OUT_DIR"] = str(out_dir)
    env.pop("SCORCH_CLEAN_OUT", None)
    code = ("import sys; sys.path.insert(0, r'%s'); "
            "import _clean_paths as cp; print(cp.GENERATED_DIR)"
            % str(COMMON_DIR))
    got = subprocess.check_output([sys.executable, "-c", code], env=env,
                                  text=True).strip()
    assert Path(got) == out_dir, (
        f"GENERATED_DIR resolved to {got!r}, expected {out_dir}")


def test_bootstrap_scripts_route_through_central_helper():
    """Every script that uses the auto-inserted release bootstrap's
    ``_SCORCH_REPRO`` name must alias the central helper's GENERATED_DIR."""
    required = "from _clean_paths import GENERATED_DIR as _SCORCH_REPRO"
    offenders = []
    for path in _python_sources():
        text = path.read_text(encoding="utf-8", errors="replace")
        if "_SCORCH_REPRO" in text and required not in text:
            offenders.append(str(path))
    assert not offenders, (
        "_SCORCH_REPRO must alias _clean_paths.GENERATED_DIR (honours "
        "SCORCH_OUT_DIR); offenders:\n" + "\n".join(offenders))


def _deposit_dir():
    env = os.environ.get("SCORCH_DATA_DIR")
    roots = [Path(env)] if env else []
    roots.append(RELEASE_ROOT / "scorch_data")
    for root in roots:
        if not root or not root.is_dir():
            continue
        for cand in [root] + [p for p in sorted(root.glob("*"))
                              if p.is_dir()]:
            if (cand / "lgcp"
                    / "grid_predicted_intensity_all_variants.csv").exists():
                return cand
    return None


DEPOSIT = _deposit_dir()


@pytest.mark.skipif(DEPOSIT is None,
                    reason="processed-data deposit not available "
                           "(set SCORCH_DATA_DIR to enable)")
def test_stage_writes_land_only_in_requested_out_dir(tmp_path):
    """Running a real stage with an external --out-dir writes there and
    leaves the repository-level reproduced/ tree untouched."""
    out_dir = tmp_path / "isolated_out"
    repo_repro = RELEASE_ROOT / "reproduced"

    def _snapshot(root):
        if not root.is_dir():
            return {}
        return {p.relative_to(root).as_posix():
                (p.stat().st_size, p.stat().st_mtime_ns)
                for p in root.rglob("*") if p.is_file()}

    before = _snapshot(repo_repro)
    env = dict(os.environ)
    env.pop("SCORCH_OUT_DIR", None)
    env.pop("SCORCH_CLEAN_OUT", None)
    env.pop("SCORCH_RELEASE_ROOT", None)
    rc = subprocess.call(
        [sys.executable, str(RELEASE_ROOT / "run_reproduction.py"), "fast",
         "--only", "extract-variant3",
         "--data-dir", str(DEPOSIT), "--out-dir", str(out_dir)],
        env=env, cwd=str(RELEASE_ROOT))
    assert rc == 0, "extract-variant3 stage failed"
    produced = out_dir / "lgcp" / "grid_predicted_intensity_variant3.csv"
    assert produced.exists(), (
        f"expected generated artifact under the requested --out-dir: "
        f"{produced}")
    after = _snapshot(repo_repro)
    assert before == after, (
        "repository-level reproduced/ changed although an external "
        "--out-dir was requested")


# ---------------------------------------------------------------------------
# Deterministic PDF metadata (reproducible builds).
# ---------------------------------------------------------------------------
# matplotlib stamps PDF /CreationDate from the wall clock unless
# SOURCE_DATE_EPOCH is set, so two builds of the same table on different days
# differed in exactly those bytes and the publication-output PDFs were not
# byte-reproducible. The release declares one canonical epoch in the central
# helper and pins it before any stage runs. These guards fail if that
# declaration is removed, changed, duplicated inconsistently, or silently
# overridden by a foreign environment value.

CANONICAL_EPOCH = 1785374765            # 2026-07-30T01:26:05Z
CANONICAL_PDF_DATE = b"D:20260730012605Z"
_TABLE_PDFS = ("Table_01_Compound_Heatwave_Typologies.pdf",
               "Table_Trend_Analysis.pdf")


def _helper():
    sys.path.insert(0, str(COMMON_DIR))
    import _clean_paths
    return _clean_paths


def test_canonical_epoch_declared_once_in_the_central_helper():
    """The epoch is declared in exactly one place, and it is the helper."""
    cp = _helper()
    assert cp.CANONICAL_SOURCE_DATE_EPOCH == CANONICAL_EPOCH
    hits = []
    for path in _python_sources():
        if path.resolve() == CENTRAL_HELPER.resolve():
            continue
        if str(CANONICAL_EPOCH) in path.read_text(encoding="utf-8",
                                                  errors="replace"):
            hits.append(str(path))
    assert not hits, (
        "the canonical epoch must be declared ONCE in the central helper; "
        f"a duplicate literal appears in: {hits}")


def test_absent_source_date_epoch_is_pinned_automatically():
    """A public build is deterministic with no operator action."""
    cp = _helper()
    for start in ({}, {"SOURCE_DATE_EPOCH": ""}):
        env = dict(start)
        assert cp.enforce_source_date_epoch(env) == CANONICAL_EPOCH
        assert env["SOURCE_DATE_EPOCH"] == str(CANONICAL_EPOCH)


@pytest.mark.parametrize("bad", ["1700000000", "0", "-1", "not-a-number",
                                 "1785374765.0", " 1785374765 "])
def test_conflicting_or_malformed_epoch_is_refused(bad):
    """Silently honouring a foreign epoch would change every emitted PDF."""
    cp = _helper()
    with pytest.raises(cp.SourceDateEpochError):
        cp.enforce_source_date_epoch({"SOURCE_DATE_EPOCH": bad})


def test_matching_epoch_is_accepted():
    cp = _helper()
    env = {"SOURCE_DATE_EPOCH": str(CANONICAL_EPOCH)}
    assert cp.enforce_source_date_epoch(env) == CANONICAL_EPOCH


def test_pdf_creation_date_is_wall_clock_and_timezone_independent(tmp_path):
    """Two PDFs written at different wall-clock times must be identical.

    This is the regression the fix exists for: it fails if the epoch is not
    pinned, if it is pinned to a naive datetime (machine timezone leaks in),
    or if a later matplotlib changes the rendering.
    """
    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Agg")
    import time
    from matplotlib import pyplot as plt
    cp = _helper()
    made = []
    for i, tz in enumerate(("UTC", "Asia/Tokyo")):
        env_backup = dict(os.environ)
        try:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
            os.environ["TZ"] = tz
            cp.enforce_source_date_epoch()
            fig, ax = plt.subplots(figsize=(2, 1))
            ax.plot([0, 1], [0, 1])
            out = tmp_path / f"probe{i}.pdf"
            fig.savefig(out)
            plt.close(fig)
            made.append(out.read_bytes())
        finally:
            os.environ.clear()
            os.environ.update(env_backup)
        time.sleep(1.1)          # guarantee a different wall-clock second
    assert made[0] == made[1], (
        "two PDFs written at different wall-clock times and timezones "
        "differ; SOURCE_DATE_EPOCH is not being honoured")
    assert CANONICAL_PDF_DATE in made[0], (
        f"emitted PDF does not carry {CANONICAL_PDF_DATE!r}")


def _pub_tables():
    d = RELEASE_ROOT / "publication_outputs" / "tables"
    if not d.is_dir():
        pytest.skip("publication_outputs/ not materialized in this checkout")
    return d


def test_shipped_table_pdfs_carry_the_canonical_date():
    """The publication-output PDFs must carry the declared stamp, not a build date."""
    d = _pub_tables()
    for name in _TABLE_PDFS:
        raw = (d / name).read_bytes()
        found = re.search(rb"/CreationDate \(([^)]*)\)", raw)
        assert found, f"{name}: no /CreationDate"
        assert found.group(1) == CANONICAL_PDF_DATE, (
            f"{name}: /CreationDate is {found.group(1)!r}, expected "
            f"{CANONICAL_PDF_DATE!r} -- a wall-clock stamp has returned")


def test_manifest_and_sha256sums_inherit_the_stable_pdf_hashes():
    """The two digest listings must agree with the actual PDF bytes."""
    import csv
    import hashlib
    d = _pub_tables()
    root = d.parent
    manifest = {r["path"]: r["sha256"] for r in csv.DictReader(
        open(root / "PUBLICATION_OUTPUTS_MANIFEST.csv", encoding="utf-8",
             newline=""))}
    sums = {}
    for line in (root / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, _, name = line.partition("  ")
        sums[name.lstrip("*")] = digest
    for name in _TABLE_PDFS:
        rel = f"tables/{name}"
        actual = hashlib.sha256((d / name).read_bytes()).hexdigest()
        assert manifest.get(rel) == actual, f"{rel}: manifest digest stale"
        assert sums.get(rel) == actual, f"{rel}: SHA256SUMS digest stale"
