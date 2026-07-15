"""Typed configuration loading.

Configuration lives in config/settings.yaml. The file path can be overridden
with the CLAIMS_MINER_CONFIG environment variable, and any individual value
can be overridden with CLAIMS_MINER__SECTION__KEY (double underscore nesting),
e.g. CLAIMS_MINER__GENERATOR__N_CLAIMS=500000.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ENV_CONFIG_PATH = "CLAIMS_MINER_CONFIG"
ENV_PREFIX = "CLAIMS_MINER__"


@dataclass(frozen=True)
class GeneratorConfig:
    seed: int = 42
    n_claims: int = 10_000
    start_date: str = "2025-01-01"
    end_date: str = "2025-06-30"
    preventable_error_rate: float = 0.12
    background_denial_rate: float = 0.04

    def __post_init__(self) -> None:
        if not 0.0 <= self.preventable_error_rate <= 1.0:
            raise ValueError("preventable_error_rate must be within [0, 1]")
        if not 0.0 <= self.background_denial_rate <= 1.0:
            raise ValueError("background_denial_rate must be within [0, 1]")
        if self.n_claims <= 0:
            raise ValueError("n_claims must be positive")


@dataclass(frozen=True)
class PathsConfig:
    data_dir: str = "data"
    claims_file: str = "data/claims.parquet"
    remits_file: str = "data/remits.parquet"
    labels_file: str = "data/ground_truth_labels.parquet"
    duckdb_file: str = "data/claims_miner.duckdb"
    export_dir: str = "powerbi/export"


@dataclass(frozen=True)
class PipelineConfig:
    model_order: tuple[str, ...] = (
        "stg_claims",
        "stg_remits",
        "fct_denials",
        "fct_leakage",
        "mart_rcm_kpis",
    )


@dataclass(frozen=True)
class DetectionConfig:
    min_pattern_dollars: float = 500.0
    min_pattern_claims: int = 3


@dataclass(frozen=True)
class Settings:
    generator: GeneratorConfig = field(default_factory=GeneratorConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    detection: DetectionConfig = field(default_factory=DetectionConfig)


def _coerce(raw: str, template: object) -> object:
    """Coerce an env var string to the type of the value it overrides."""
    if isinstance(template, bool):
        return raw.lower() in {"1", "true", "yes"}
    if isinstance(template, int):
        return int(raw)
    if isinstance(template, float):
        return float(raw)
    return raw


def _apply_env_overrides(data: dict) -> dict:
    for key, value in os.environ.items():
        if not key.startswith(ENV_PREFIX):
            continue
        path = key[len(ENV_PREFIX):].lower().split("__")
        if len(path) != 2:
            continue
        section, leaf = path
        if section in data and leaf in data[section]:
            data[section][leaf] = _coerce(value, data[section][leaf])
    return data


def load_settings(config_path: str | Path | None = None) -> Settings:
    """Load settings from YAML with environment overrides applied."""
    path = Path(config_path or os.environ.get(ENV_CONFIG_PATH, "config/settings.yaml"))
    data: dict = {}
    if path.exists():
        with path.open() as fh:
            data = yaml.safe_load(fh) or {}
    data.setdefault("generator", {})
    data.setdefault("paths", {})
    data.setdefault("pipeline", {})
    data.setdefault("detection", {})
    data = _apply_env_overrides(data)

    pipeline_raw = dict(data["pipeline"])
    if "model_order" in pipeline_raw:
        pipeline_raw["model_order"] = tuple(pipeline_raw["model_order"])

    return Settings(
        generator=GeneratorConfig(**data["generator"]),
        paths=PathsConfig(**data["paths"]),
        pipeline=PipelineConfig(**pipeline_raw),
        detection=DetectionConfig(**data["detection"]),
    )
