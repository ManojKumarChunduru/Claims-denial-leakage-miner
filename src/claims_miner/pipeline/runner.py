"""Execute the layered SQL models in dependency order.

Each model is a plain .sql file under pipeline/models/. The runner reads
config.pipeline.model_order and executes each file against the warehouse,
timing every step. Keeping models as plain SQL (rather than string
constants in Python) means they can be reviewed, diffed, and ported to
MS SQL Server or Snowflake with minimal friction.
"""

from __future__ import annotations

import logging
import time
from importlib import resources
from pathlib import Path

import duckdb

from claims_miner.config import Settings

log = logging.getLogger(__name__)


def _model_sql(name: str) -> str:
    pkg = resources.files("claims_miner.pipeline") / "models" / f"{name}.sql"
    if not pkg.is_file():
        raise FileNotFoundError(f"SQL model not found: {name}.sql")
    return pkg.read_text()


def run_models(
    settings: Settings, con: duckdb.DuckDBPyConnection | None = None
) -> dict[str, float]:
    """Run all models in order. Returns model name -> elapsed seconds."""
    if con is None:
        con = duckdb.connect(settings.paths.duckdb_file)

    timings: dict[str, float] = {}
    for name in settings.pipeline.model_order:
        sql = _model_sql(name)
        t0 = time.perf_counter()
        con.execute(sql)
        elapsed = time.perf_counter() - t0
        timings[name] = elapsed
        log.info("model built", extra={"model": name, "seconds": round(elapsed, 3)})
    return timings


def export_marts(settings: Settings, con: duckdb.DuckDBPyConnection | None = None) -> list[str]:
    """Export the mart and fact tables to parquet for Power BI ingestion."""
    if con is None:
        con = duckdb.connect(settings.paths.duckdb_file)
    export_dir = Path(settings.paths.export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    exported: list[str] = []
    for table in ["fct_denials", "fct_leakage", "mart_rcm_kpis", "detected_leakage"]:
        exists = con.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [table]
        ).fetchone()[0]
        if not exists:
            log.warning("skipping export, table missing", extra={"table": table})
            continue
        out = export_dir / f"{table}.parquet"
        con.execute(f"COPY {table} TO '{out}' (FORMAT PARQUET)")
        exported.append(str(out))
        log.info("exported", extra={"table": table, "path": str(out)})
    return exported
