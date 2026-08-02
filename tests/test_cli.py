"""CLI behaviour tests: safe fetch/extract, deposit-root location,
mandatory checksum verification, deposit validation, and loud stage
failures in `scorch reproduce`."""
import hashlib
import zipfile
from pathlib import Path

import pytest
import yaml
from conftest import complete_config

from scorch import cli, fetch


def _write_stage_cfg(tmp_path: Path, stages) -> Path:
    """A schema-complete config (V6: every key required) carrying the given
    stage list, written under <tmp>/configs/c.yaml."""
    cfg = tmp_path / "configs" / "c.yaml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(yaml.safe_dump(complete_config(name="t", stages=stages)),
                   encoding="utf-8")
    return cfg


def _make_mock_deposit_zip(tmp_path: Path) -> Path:
    """A minimal Zenodo-style ZIP: one top-level dir with SHA256SUMS."""
    root = tmp_path / "build" / "scorch_processed_data_v9.9.9"
    (root / "catalogs").mkdir(parents=True)
    master = root / "catalogs" / "master.csv"
    master.write_text("a,b\n1,2\n", encoding="utf-8")
    readme = root / "DATA_README.md"
    readme.write_text("mock deposit\n", encoding="utf-8")
    sums = []
    for rel in ("catalogs/master.csv", "DATA_README.md"):
        digest = hashlib.sha256((root / rel).read_bytes()).hexdigest()
        sums.append(f"{digest}  {rel}")
    (root / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    zpath = tmp_path / "scorch_processed_data_v9.9.9.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        for p in sorted(root.rglob("*")):
            if p.is_file():
                zf.write(p, f"{root.name}/{p.relative_to(root).as_posix()}")
    return zpath


def test_safe_extract_and_locate_root(tmp_path):
    zpath = _make_mock_deposit_zip(tmp_path)
    dest = tmp_path / "dest"
    tops = fetch.safe_extract_zip(zpath, dest)
    assert tops == ["scorch_processed_data_v9.9.9"]
    root = fetch.locate_deposit_root(dest)
    assert root is not None and root.name == "scorch_processed_data_v9.9.9"
    fetch.verify_sha256sums(root)  # must not raise


def test_extract_rejects_path_traversal(tmp_path):
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("../outside.txt", "pwned")
    with pytest.raises(fetch.FetchError, match="unsafe path"):
        fetch.safe_extract_zip(evil, tmp_path / "dest")
    assert not (tmp_path / "outside.txt").exists()


def test_fetch_deposit_local_zip_end_to_end(tmp_path):
    """fetch-data from a local mock Zenodo ZIP: download (file://), safe
    extract, root location, mandatory checksum verification."""
    zpath = _make_mock_deposit_zip(tmp_path)
    dest = tmp_path / "fetched"
    result = fetch.fetch_deposit(dest_dir=dest,
                                 url=zpath.resolve().as_uri(), verify=True)
    assert result.verified
    assert result.deposit_root and Path(result.deposit_root).exists()
    assert any(p.endswith(".zip") for p in result.downloaded)
    assert result.extracted


def test_fetch_deposit_fails_without_sums(tmp_path):
    plain = tmp_path / "file.bin"
    plain.write_bytes(b"data")
    with pytest.raises(fetch.FetchError, match="cannot verify"):
        fetch.fetch_deposit(dest_dir=tmp_path / "d2",
                            url=plain.resolve().as_uri(), verify=True)


def test_fetch_verify_detects_corruption(tmp_path):
    zpath = _make_mock_deposit_zip(tmp_path)
    dest = tmp_path / "dest"
    fetch.safe_extract_zip(zpath, dest)
    root = fetch.locate_deposit_root(dest)
    (root / "DATA_README.md").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(fetch.FetchError, match="mismatch"):
        fetch.verify_sha256sums(root)


class _FakeResponse:
    """Minimal urlopen response: context manager + chunked/full read()."""

    def __init__(self, payload: bytes, url: str):
        self._payload = payload
        self._pos = 0
        self.url = url

    def read(self, size=-1):
        if size is None or size < 0:
            chunk, self._pos = self._payload[self._pos:], len(self._payload)
        else:
            chunk = self._payload[self._pos:self._pos + size]
            self._pos += len(chunk)
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_fetch_deposit_zenodo_record_api_uses_links_content(
        tmp_path, monkeypatch):
    """Mocked Zenodo record API: the file entry's links.content URL (binary)
    must be selected for download -- links.self returns metadata JSON and
    must never be fetched. The downloaded archive is then safely extracted,
    the root located, and SHA256SUMS verified."""
    import json as _json
    import urllib.request as _ur

    zpath = _make_mock_deposit_zip(tmp_path)
    zip_bytes = zpath.read_bytes()
    record_id = "1234567"
    api_url = f"https://zenodo.org/api/records/{record_id}"
    self_url = (f"https://zenodo.org/api/records/{record_id}/files/"
                "scorch_processed_data_v9.9.9.zip")
    content_url = self_url + "/content"
    record_json = {
        "files": [{
            "key": "scorch_processed_data_v9.9.9.zip",
            "links": {"self": self_url, "content": content_url},
        }],
    }
    file_metadata_json = {"key": "scorch_processed_data_v9.9.9.zip",
                          "mimetype": "application/zip"}
    requested = []

    def fake_urlopen(req, *args, **kwargs):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        requested.append(url)
        if url == api_url:
            return _FakeResponse(
                _json.dumps(record_json).encode("utf-8"), url)
        if url == content_url:
            return _FakeResponse(zip_bytes, url)
        if url == self_url:
            # links.self is METADATA JSON, not the archive; downloading it
            # would produce an unusable "zip" and must not happen.
            return _FakeResponse(
                _json.dumps(file_metadata_json).encode("utf-8"), url)
        raise AssertionError(f"unexpected URL requested: {url}")

    monkeypatch.setattr(_ur, "urlopen", fake_urlopen)

    dest = tmp_path / "fetched_api"
    result = fetch.fetch_deposit(
        dest_dir=dest, url=f"https://zenodo.org/records/{record_id}",
        verify=True)

    # links.content was downloaded; links.self was never fetched.
    assert content_url in requested
    assert self_url not in requested
    # Downloaded archive is byte-identical to the real ZIP, was extracted
    # safely, the deposit root located, and every checksum verified.
    downloaded = [p for p in result.downloaded if p.endswith(".zip")]
    assert len(downloaded) == 1
    assert Path(downloaded[0]).read_bytes() == zip_bytes
    assert result.extracted == downloaded
    assert result.deposit_root is not None
    assert Path(result.deposit_root).name == "scorch_processed_data_v9.9.9"
    assert result.verified


def test_validate_deposit_fails_on_incomplete(tmp_path, capsys):
    (tmp_path / "SHA256SUMS").write_text("", encoding="utf-8")
    ok = cli.validate_deposit(tmp_path)
    out = capsys.readouterr().out
    assert not ok
    assert "RESULT: FAIL" in out
    assert "catalogs/" in out  # the real layout is what is checked


def test_reproduce_missing_script_fails_loudly(tmp_path):
    cfg = _write_stage_cfg(tmp_path, [
        {"name": "gone", "kind": "script", "script": "scripts/nope.py"}])
    with pytest.raises(cli.StageError, match="required script not found"):
        cli.run_reproduction(cfg, base_dir=tmp_path)


def test_reproduce_unknown_builtin_fails_loudly(tmp_path):
    cfg = _write_stage_cfg(tmp_path, [
        {"name": "b", "kind": "builtin", "builtin": "does_not_exist"}])
    with pytest.raises(cli.StageError, match="unknown builtin"):
        cli.run_reproduction(cfg, base_dir=tmp_path)


def test_reproduce_builtin_missing_input_fails_loudly(tmp_path):
    cfg = _write_stage_cfg(tmp_path, [
        {"name": "v", "kind": "builtin", "builtin": "validate_catalog",
         "inputs": {"master_csv": "catalogs/missing.csv"}}])
    with pytest.raises(cli.StageError, match="master catalog not found"):
        cli.run_reproduction(cfg, base_dir=tmp_path)


def test_reproduce_route_filtering(tmp_path):
    cfg = _write_stage_cfg(tmp_path, [
        {"name": "full-only", "kind": "script", "script": "scripts/nope.py",
         "route": "full"}])
    # fast route selects nothing -> empty run, no error
    results = cli.run_reproduction(cfg, base_dir=tmp_path, route="fast")
    assert results == []
    with pytest.raises(cli.StageError):
        cli.run_reproduction(cfg, base_dir=tmp_path, route="full")


def test_cli_reproduce_exit_code(tmp_path):
    cfg = _write_stage_cfg(tmp_path, [
        {"name": "gone", "kind": "script", "script": "scripts/nope.py"}])
    rc = cli.main(["reproduce", "--config", str(cfg),
                   "--base-dir", str(tmp_path)])
    assert rc == 1
