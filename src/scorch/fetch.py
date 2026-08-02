"""Download the SCORCH processed-data deposit (Zenodo) and verify checksums.

The processed-data DOI is reserved while the Zenodo draft is private and
becomes publicly resolvable when the record is published. It is supplied
via ``--doi``, the environment variable ``SCORCH_DATA_DOI``, or an explicit
``--url``. Uses only the Python standard library (urllib), so it works in a
minimal install.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

DOI_ENV_VAR = "SCORCH_DATA_DOI"
SUMS_FILENAME = "SHA256SUMS"


@dataclass
class FetchResult:
    """Outcome of :func:`fetch_deposit`."""
    downloaded: list = field(default_factory=list)   # downloaded file paths
    extracted: list = field(default_factory=list)    # extracted archive paths
    deposit_root: str | None = None                  # dir holding SHA256SUMS
    verified: bool = False                           # SHA256SUMS all verified

    # Backwards-compatible iteration over the downloaded file list.
    def __iter__(self):
        return iter(self.downloaded)

    def __len__(self):
        return len(self.downloaded)

_ZENODO_RECORD_RE = re.compile(
    r"(?:zenodo\.org/records?/|zenodo\.)(\d+)", re.IGNORECASE)


class FetchError(RuntimeError):
    pass


def resolve_doi(doi=None, url=None):
    """Resolve the deposit location from an explicit DOI/URL or the env var.

    Raises FetchError with a clear explanation when nothing is configured.
    """
    if url:
        return url
    doi = doi or os.environ.get(DOI_ENV_VAR)
    if not doi:
        raise FetchError(
            "No data DOI or URL configured. The SCORCH processed-data DOI "
            "is reserved on the private Zenodo draft and becomes publicly "
            "resolvable at publication; once it exists, either set the "
            f"environment variable {DOI_ENV_VAR} to the DOI (e.g. "
            "10.5281/zenodo.21717752) or pass an explicit --url to "
            "'scorch fetch-data'.")
    doi = doi.strip()
    if doi.lower().startswith("http"):
        return doi
    return "https://doi.org/" + doi


def _zenodo_record_id(url):
    m = _ZENODO_RECORD_RE.search(url)
    return m.group(1) if m else None


def _download(url, dest_path):
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "scorch-heatwaves"})
    with urllib.request.urlopen(req) as resp, open(dest_path, "wb") as fh:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
    return dest_path


def _resolve_redirect(url):
    req = urllib.request.Request(url, method="HEAD",
                                 headers={"User-Agent": "scorch-heatwaves"})
    with urllib.request.urlopen(req) as resp:
        return resp.url


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_sha256sums(directory, sums_file=SUMS_FILENAME):
    """Verify every entry of a SHA256SUMS file (``<hash>  <filename>`` lines).

    Returns a list of (filename, ok) tuples; raises FetchError if the sums
    file is missing or any file fails verification.
    """
    directory = Path(directory)
    sums_path = directory / sums_file
    if not sums_path.exists():
        raise FetchError(f"checksum file not found: {sums_path}")
    results = []
    failures = []
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        expected, name = parts[0].lower(), parts[1].strip().lstrip("*")
        target = directory / name
        if not target.exists():
            failures.append(f"missing file: {name}")
            results.append((name, False))
            continue
        actual = sha256_file(target)
        ok = actual == expected
        results.append((name, ok))
        if not ok:
            failures.append(
                f"checksum mismatch for {name}: expected {expected}, "
                f"got {actual}")
    if failures:
        raise FetchError("SHA256 verification failed:\n  - " +
                         "\n  - ".join(failures))
    return results


def safe_extract_zip(archive_path, dest_dir):
    """Extract a ZIP archive with a path-traversal guard.

    Every member is verified to resolve INSIDE ``dest_dir`` before anything is
    written; absolute paths, drive letters, symlink-style names and ``..``
    components are rejected with FetchError. Returns the list of top-level
    entries created.
    """
    archive_path = Path(archive_path)
    dest_dir = Path(dest_dir).resolve()
    tops = set()
    with zipfile.ZipFile(archive_path) as zf:
        for info in zf.infolist():
            name = info.filename
            target = (dest_dir / name).resolve()
            if not str(target).startswith(str(dest_dir) + os.sep) \
                    and target != dest_dir:
                raise FetchError(
                    f"unsafe path in archive {archive_path.name}: {name!r} "
                    "(resolves outside the destination directory)")
            if name.split("/", 1)[0]:
                tops.add(name.split("/", 1)[0])
        zf.extractall(dest_dir)
    return sorted(tops)


def locate_deposit_root(dest_dir):
    """Locate the deposit root (the directory holding SHA256SUMS).

    Searches ``dest_dir`` itself, then one and two directory levels below.
    Returns None when no root is found, raises FetchError when several
    candidate roots exist.
    """
    dest_dir = Path(dest_dir)
    if (dest_dir / SUMS_FILENAME).exists():
        return dest_dir
    hits = sorted({p.parent for pattern in ("*/" + SUMS_FILENAME,
                                            "*/*/" + SUMS_FILENAME)
                   for p in dest_dir.glob(pattern)})
    if len(hits) > 1:
        raise FetchError(
            "multiple candidate deposit roots under "
            f"{dest_dir}: " + ", ".join(str(h) for h in hits))
    return hits[0] if hits else None


def fetch_deposit(dest_dir="scorch_data", doi=None, url=None, verify=True):
    """Download the processed-data deposit, extract archives, verify checksums.

    Parameters
    ----------
    dest_dir : output directory (created if needed).
    doi, url : explicit DOI or URL; falls back to the SCORCH_DATA_DOI env var.
    verify : verify the deposit's SHA256SUMS after download + extraction
        (default True). Verification is MANDATORY unless explicitly disabled:
        a missing SHA256SUMS or any mismatch raises FetchError.

    Returns
    -------
    FetchResult with the downloaded files, extracted archives, the located
    deposit root, and the verification status.
    """
    location = resolve_doi(doi=doi, url=url)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Resolve DOI redirects to the landing page (e.g. a Zenodo record).
    if "doi.org" in location:
        location = _resolve_redirect(location)

    record_id = _zenodo_record_id(location)
    result = FetchResult()
    if record_id:
        api_url = f"https://zenodo.org/api/records/{record_id}"
        req = urllib.request.Request(
            api_url, headers={"User-Agent": "scorch-heatwaves"})
        with urllib.request.urlopen(req) as resp:
            record = json.load(resp)
        files = record.get("files", [])
        if not files:
            raise FetchError(f"Zenodo record {record_id} lists no files")
        for f in files:
            name = f.get("key") or f.get("filename")
            # Zenodo file-entry links: ``content`` is the binary download;
            # ``self`` returns the file's METADATA as JSON and must never be
            # used to fetch the archive itself.
            links = f.get("links", {}) or {}
            link = (links.get("content")
                    or f"https://zenodo.org/api/records/{record_id}"
                       f"/files/{name}/content")
            print(f"[fetch] downloading {name} ...")
            result.downloaded.append(str(_download(link, dest_dir / name)))
    else:
        # Direct URL (including a local file:// URL used by the tests).
        name = location.rstrip("/").split("/")[-1] or "scorch_deposit.bin"
        print(f"[fetch] downloading {name} ...")
        result.downloaded.append(str(_download(location, dest_dir / name)))

    # Safely extract any downloaded ZIP archives (the Zenodo data record is
    # published as a single scorch_processed_data_v*.zip).
    for path in list(result.downloaded):
        if path.lower().endswith(".zip"):
            print(f"[fetch] extracting {Path(path).name} ...")
            tops = safe_extract_zip(path, dest_dir)
            result.extracted.append(path)
            print(f"[fetch] extracted top-level entries: {', '.join(tops)}")

    root = locate_deposit_root(dest_dir)
    result.deposit_root = str(root) if root else None

    if verify:
        if root is None:
            raise FetchError(
                f"no {SUMS_FILENAME} found under {dest_dir} after download/"
                "extraction; cannot verify the deposit. Pass --no-verify "
                "only if you have independently verified the files.")
        verify_sha256sums(root)
        result.verified = True
        print(f"[fetch] SHA256SUMS verified OK in {root}")
    return result
