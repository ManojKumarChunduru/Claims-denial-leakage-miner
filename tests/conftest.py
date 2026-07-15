"""Shared fixtures: a small, fully materialized world in a temp directory."""

from __future__ import annotations

import duckdb
import pytest

from claims_miner.config import (
    DetectionConfig,
    GeneratorConfig,
    PathsConfig,
    PipelineConfig,
    Settings,
)
from claims_miner.detection.rules import detect
from claims_miner.generator.claims_factory import generate_claims
from claims_miner.generator.denial_engine import adjudicate
from claims_miner.pipeline.ingest import ingest
from claims_miner.pipeline.runner import run_models


@pytest.fixture(scope="session")
def settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    root = tmp_path_factory.mktemp("world")
    return Settings(
        generator=GeneratorConfig(seed=7, n_claims=4000),
        paths=PathsConfig(
            data_dir=str(root),
            claims_file=str(root / "claims.parquet"),
            remits_file=str(root / "remits.parquet"),
            labels_file=str(root / "labels.parquet"),
            duckdb_file=str(root / "wh.duckdb"),
            export_dir=str(root / "export"),
        ),
        pipeline=PipelineConfig(),
        detection=DetectionConfig(),
    )


@pytest.fixture(scope="session")
def generated(settings: Settings):
    data = generate_claims(settings.generator)
    remits = adjudicate(data.claims, data.labels, settings.generator)
    data.claims.to_parquet(settings.paths.claims_file, index=False)
    remits.to_parquet(settings.paths.remits_file, index=False)
    data.labels.to_parquet(settings.paths.labels_file, index=False)
    return data, remits


@pytest.fixture(scope="session")
def warehouse(settings: Settings, generated) -> duckdb.DuckDBPyConnection:
    con = ingest(settings)
    run_models(settings, con)
    detect(settings, con)
    return con
