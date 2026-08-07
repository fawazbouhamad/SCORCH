#!/usr/bin/env python3
"""Rebuild the processed-data deposit manifests (FILE_MANIFEST.csv + SHA256SUMS).

Standalone, standard library only. Intended for the v1.0.1 corrected overlay
(and any deposit sharing the v1.0.0 manifest conventions):

* FILE_MANIFEST.csv — CRLF CSV `file,bytes,sha256,n_rows,description`,
  covering every payload file EXCEPT itself and SHA256SUMS. The existing
  manifest is the authority for path order and descriptions; this tool only
  recomputes `bytes`, `sha256` and `n_rows` (true CSV data-row count via the
  csv module, so quoted embedded newlines are counted correctly; blank for
  non-CSV payloads).
* SHA256SUMS — LF text, `<hex>  <posix-path>`, covering every file EXCEPT
  itself, INCLUDING the final (rebuilt) FILE_MANIFEST.csv hash. Existing
  entry order is preserved.

Coverage is strict: a manifest path missing on disk, a disk file absent from
the manifest, or a duplicated manifest path is a hard failure (exit 1) and
nothing is written.

Usage:
    python rebuild_processed_deposit_manifests.py --root <deposit-root> [--verify]

With --verify the tool additionally re-reads what it wrote and re-checks
every hash, byte count and row count from disk (belt and braces).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import sys
from pathlib import Path

MANIFEST_NAME = "FILE_MANIFEST.csv"
SUMS_NAME = "SHA256SUMS"
FIELDS = ["file", "bytes", "sha256", "n_rows", "description"]


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def csv_data_rows(path: Path) -> int:
    """True CSV data-row count (records after the header, csv-module parsed)."""
    with open(path, "r", encoding="utf-8", newline="") as f:
        n = sum(1 for _ in csv.reader(f))
    return max(n - 1, 0)


def disk_files(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*")
                  if p.is_file())


def load_manifest(root: Path) -> list[dict]:
    with open(root / MANIFEST_NAME, "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows or list(rows[0].keys()) != FIELDS:
        sys.exit(f"FATAL: unexpected {MANIFEST_NAME} header "
                 f"(want {FIELDS}, got {list(rows[0].keys()) if rows else None})")
    return rows


def check_coverage(root: Path, manifest_paths: list[str]) -> None:
    dupes = sorted({p for p in manifest_paths if manifest_paths.count(p) > 1})
    on_disk = set(disk_files(root)) - {MANIFEST_NAME, SUMS_NAME}
    missing = sorted(set(manifest_paths) - set(disk_files(root)))
    extra = sorted(on_disk - set(manifest_paths))
    problems = []
    if dupes:
        problems.append(f"duplicate manifest paths: {dupes}")
    if missing:
        problems.append(f"manifest paths missing on disk: {missing}")
    if extra:
        problems.append(f"disk files absent from the manifest: {extra}")
    if problems:
        sys.exit("FATAL coverage failure:\n  " + "\n  ".join(problems))


def rebuild(root: Path) -> None:
    manifest = load_manifest(root)
    paths = [r["file"] for r in manifest]
    check_coverage(root, paths)

    # 1. FILE_MANIFEST.csv: keep order + descriptions, recompute the rest.
    for r in manifest:
        p = root / r["file"]
        r["bytes"] = str(p.stat().st_size)
        r["sha256"] = sha256_of(p)
        r["n_rows"] = (str(csv_data_rows(p))
                       if p.suffix.lower() == ".csv" else "")
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\r\n")
    w.writeheader()
    w.writerows(manifest)
    (root / MANIFEST_NAME).write_bytes(buf.getvalue().encode("utf-8"))
    print(f"[rebuild] {MANIFEST_NAME}: {len(manifest)} rows rewritten")

    # 2. SHA256SUMS: every file except itself, preserving existing order;
    #    the FILE_MANIFEST.csv entry hashes the file just written above.
    sums_path = root / SUMS_NAME
    order = []
    if sums_path.is_file():
        for line in sums_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                order.append(line.split(maxsplit=1)[1].lstrip("*").strip())
    want = [p for p in disk_files(root) if p != SUMS_NAME]
    ordered = [p for p in order if p in set(want)]
    ordered += [p for p in want if p not in set(ordered)]
    if sorted(ordered) != sorted(want):  # pragma: no cover - defensive
        sys.exit("FATAL: SHA256SUMS ordering reconstruction lost entries")
    lines = [f"{sha256_of(root / p)}  {p}\n" for p in ordered]
    sums_path.write_bytes("".join(lines).encode("utf-8"))
    print(f"[rebuild] {SUMS_NAME}: {len(lines)} entries rewritten "
          f"(includes the final {MANIFEST_NAME} hash)")


def verify(root: Path) -> int:
    bad = 0
    manifest = load_manifest(root)
    check_coverage(root, [r["file"] for r in manifest])
    for r in manifest:
        p = root / r["file"]
        if p.stat().st_size != int(r["bytes"]):
            print(f"[verify] BYTES mismatch: {r['file']}")
            bad += 1
        if sha256_of(p) != r["sha256"].lower():
            print(f"[verify] SHA mismatch: {r['file']}")
            bad += 1
        if p.suffix.lower() == ".csv":
            if r["n_rows"] == "" or csv_data_rows(p) != int(r["n_rows"]):
                print(f"[verify] ROW-COUNT mismatch: {r['file']}")
                bad += 1
    listed = {}
    for line in (root / SUMS_NAME).read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, name = line.split(maxsplit=1)
            listed[name.lstrip("*").strip()] = digest.lower()
    want = set(p for p in disk_files(root) if p != SUMS_NAME)
    if set(listed) != want:
        print(f"[verify] SHA256SUMS coverage mismatch: "
              f"missing={sorted(want - set(listed))} "
              f"extra={sorted(set(listed) - want)}")
        bad += 1
    for name, digest in listed.items():
        if sha256_of(root / name) != digest:
            print(f"[verify] SHA256SUMS mismatch: {name}")
            bad += 1
    print(f"[verify] {'PASS: 0 mismatches' if bad == 0 else f'FAIL: {bad} mismatches'} "
          f"({len(manifest)} manifest rows, {len(listed)} checksum entries)")
    return bad


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", required=True, help="deposit root directory")
    ap.add_argument("--verify", action="store_true",
                    help="re-verify everything after rebuilding")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    if not (root / MANIFEST_NAME).is_file():
        sys.exit(f"FATAL: {root / MANIFEST_NAME} not found")
    rebuild(root)
    if args.verify and verify(root):
        sys.exit(1)


if __name__ == "__main__":
    main()
