"""Load exported mart parquet files into the compose Postgres instance.

Usage:
    docker compose up -d
    claims-miner all
    python scripts/load_postgres.py

Connection settings come from environment variables with sane local
defaults matching docker-compose.yml. DuckDB's postgres extension does the
transfer, so pandas never materializes the tables in memory.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import duckdb

from claims_miner.config import load_settings
from claims_miner.logging_conf import configure_logging

log = logging.getLogger(__name__)

PG_DSN = (
    f"host={os.environ.get('PGHOST', 'localhost')} "
    f"port={os.environ.get('PGPORT', '5432')} "
    f"user={os.environ.get('PGUSER', 'claims')} "
    f"password={os.environ.get('PGPASSWORD', 'claims_local_only')} "
    f"dbname={os.environ.get('PGDATABASE', 'claims_marts')}"
)


def main() -> int:
    configure_logging()
    settings = load_settings()
    export_dir = Path(settings.paths.export_dir)
    files = sorted(export_dir.glob("*.parquet"))
    if not files:
        log.error("no exports found, run 'claims-miner all' first",
                  extra={"export_dir": str(export_dir)})
        return 1

    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{PG_DSN}' AS pg (TYPE POSTGRES)")
    for path in files:
        table = path.stem
        con.execute(f"CREATE OR REPLACE TABLE pg.public.{table} AS "
                    f"SELECT * FROM read_parquet('{path}')")
        rows = con.execute(f"SELECT count(*) FROM pg.public.{table}").fetchone()[0]
        log.info("loaded to postgres", extra={"table": table, "rows": rows})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
