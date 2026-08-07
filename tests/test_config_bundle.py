"""The canonical fast config must ship as package data, be usable without a
repository checkout, and stay identical to the repository copy."""
from pathlib import Path

import pytest
import yaml

from scorch import cli

REPO_CONFIG = Path(__file__).resolve().parents[1] / "configs" / \
    "reproduction_fast.yaml"


def test_bundled_config_ships_with_the_package():
    path = cli.bundled_config_path()
    assert path.exists()
    # Inside the installed package tree, NOT a repository-relative path.
    assert path.parent.name == "configs"
    assert path.parent.parent.name == "scorch"


def test_bundled_config_declares_the_connected_fast_route():
    config = yaml.safe_load(cli.bundled_config_path().read_text(
        encoding="utf-8"))
    names = [s["name"] for s in config["stages"]]
    assert names[:8] == [
        "field-products", "relabel-heatwaves", "select-days-events",
        "daily-dbscan-params", "event-global-params", "rebuild-catalog",
        "weighted-centroids", "classify-reconstructed",
    ]
    assert all(s.get("route") == "fast" for s in config["stages"])
    # Each stage that reads an intermediate must read one produced upstream.
    produced = set()
    for stage in config["stages"]:
        for got in (stage.get("inputs") or {}).values():
            if str(got).startswith("reconstruction/"):
                assert got in produced, \
                    f"{stage['name']} reads unproduced {got}"
        produced.update(stage.get("outputs") or [])
    assert config["expected_counts"]["ellipses"] == 760


@pytest.mark.skipif(not REPO_CONFIG.exists(),
                    reason="repository configs/ copy not present "
                           "(installed-package-only checkout)")
def test_repository_and_bundled_configs_are_identical():
    assert REPO_CONFIG.read_bytes() == cli.bundled_config_path().read_bytes()


def test_run_reproduction_defaults_to_the_bundled_config(tmp_path):
    """Without --config the runner loads the bundled config; the first stage
    then fails loudly on the missing deposit rather than skipping."""
    from scorch.pipeline import PipelineError
    with pytest.raises((cli.StageError, PipelineError)) as exc:
        cli.run_reproduction(base_dir=tmp_path, out_dir=tmp_path / "out",
                             only=["field-products"])
    assert "required input missing" in str(exc.value)


def test_unknown_only_stage_names_fail_clearly(tmp_path):
    with pytest.raises(cli.StageError, match="unknown stage name"):
        cli.run_reproduction(base_dir=tmp_path, out_dir=tmp_path / "out",
                             only=["field-products", "no-such-stage"])
