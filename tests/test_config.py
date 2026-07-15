from __future__ import annotations

import pytest

from claims_miner.config import GeneratorConfig, load_settings


def test_defaults_when_file_missing(tmp_path):
    s = load_settings(tmp_path / "nope.yaml")
    assert s.generator.n_claims == 10_000
    assert s.pipeline.model_order[0] == "stg_claims"


def test_yaml_values_load(tmp_path):
    cfg = tmp_path / "settings.yaml"
    cfg.write_text("generator:\n  n_claims: 123\n  seed: 9\n")
    s = load_settings(cfg)
    assert s.generator.n_claims == 123
    assert s.generator.seed == 9


def test_env_override_wins(tmp_path, monkeypatch):
    cfg = tmp_path / "settings.yaml"
    cfg.write_text("generator:\n  n_claims: 123\n")
    monkeypatch.setenv("CLAIMS_MINER__GENERATOR__N_CLAIMS", "456")
    s = load_settings(cfg)
    assert s.generator.n_claims == 456


def test_invalid_rates_rejected():
    with pytest.raises(ValueError):
        GeneratorConfig(preventable_error_rate=1.5)
    with pytest.raises(ValueError):
        GeneratorConfig(n_claims=0)
