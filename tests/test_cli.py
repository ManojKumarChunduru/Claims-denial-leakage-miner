from __future__ import annotations

import json
from pathlib import Path

from claims_miner.cli import main


def _write_config(tmp_path: Path) -> Path:
    root = tmp_path / "world"
    cfg = tmp_path / "settings.yaml"
    cfg.write_text(
        f"""
generator:
  seed: 3
  n_claims: 1500
paths:
  data_dir: "{root}"
  claims_file: "{root}/claims.parquet"
  remits_file: "{root}/remits.parquet"
  labels_file: "{root}/labels.parquet"
  duckdb_file: "{root}/wh.duckdb"
  export_dir: "{root}/export"
"""
    )
    return cfg


def test_cli_all_runs_end_to_end(tmp_path, capsys):
    cfg = _write_config(tmp_path)
    rc = main(["all", "--config", str(cfg), "--quiet"])
    assert rc == 0

    # score command prints a JSON report to stdout
    payload = json.loads(capsys.readouterr().out)
    assert payload["precision"] > 0.9
    assert payload["recall"] > 0.9

    # run step exported the Power BI feed tables
    export_dir = tmp_path / "world" / "export"
    exported = {p.name for p in export_dir.glob("*.parquet")}
    assert {
        "fct_denials.parquet",
        "fct_leakage.parquet",
        "mart_rcm_kpis.parquet",
        "detected_leakage.parquet",
    } <= exported


def test_cli_generate_only_writes_inputs(tmp_path):
    cfg = _write_config(tmp_path)
    rc = main(["generate", "--config", str(cfg), "--quiet"])
    assert rc == 0
    root = tmp_path / "world"
    assert (root / "claims.parquet").exists()
    assert (root / "remits.parquet").exists()
    assert (root / "labels.parquet").exists()
    assert not (root / "wh.duckdb").exists()
