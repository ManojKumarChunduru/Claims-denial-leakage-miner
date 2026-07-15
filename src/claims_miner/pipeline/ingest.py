"""Load raw claim and remit files plus reference tables into DuckDB.

The warehouse layout mirrors a Clarity-style reporting database in
miniature: raw landing tables, reference dimensions, then layered models
built by runner.py. Ground-truth labels are deliberately NOT loaded here;
they only touch the scorer, never the warehouse the detector reads.
"""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb
import pandas as pd

from claims_miner.config import Settings
from claims_miner.generator import reference_data as ref

log = logging.getLogger(__name__)


def _reference_frames() -> dict[str, pd.DataFrame]:
    payers = pd.DataFrame(
        [
            {
                "payer_id": pid,
                "payer_name": meta["name"],
                "filing_limit_days": meta["filing_limit_days"],
            }
            for pid, meta in ref.PAYERS.items()
        ]
    )
    departments = pd.DataFrame(
        [
            {
                "department_id": did,
                "department_name": meta["name"],
                "auth_required": meta["auth_required"],
            }
            for did, meta in ref.DEPARTMENTS.items()
        ]
    )
    procedures = pd.DataFrame(
        [
            {
                "cpt_code": cpt,
                "cpt_desc": meta["desc"],
                "modifier_required": meta["modifier_required"],
            }
            for cpt, meta in ref.PROCEDURES.items()
        ]
    )
    valid_dx_pairs = pd.DataFrame(
        [
            {"cpt_code": cpt, "icd10_code": dx}
            for cpt, meta in ref.PROCEDURES.items()
            for dx in meta["valid_dx"]
        ]
    )
    carc = pd.DataFrame(
        [{"carc_code": code, "carc_desc": desc} for code, desc in ref.CARC_DESCRIPTIONS.items()]
    )
    return {
        "ref_payers": payers,
        "ref_departments": departments,
        "ref_procedures": procedures,
        "ref_valid_dx_pairs": valid_dx_pairs,
        "ref_carc": carc,
    }


def ingest(
    settings: Settings, con: duckdb.DuckDBPyConnection | None = None
) -> duckdb.DuckDBPyConnection:
    """Create/refresh raw and reference tables. Returns an open connection."""
    paths = settings.paths
    if con is None:
        Path(paths.duckdb_file).parent.mkdir(parents=True, exist_ok=True)
        con = duckdb.connect(paths.duckdb_file)

    for name, path in [("raw_claims", paths.claims_file), ("raw_remits", paths.remits_file)]:
        if not Path(path).exists():
            raise FileNotFoundError(
                f"{path} not found. Run the generator first: claims-miner generate"
            )
        con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM read_parquet('{path}')")
        rows = con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
        log.info("ingested table", extra={"table": name, "rows": rows})

    for name, frame in _reference_frames().items():
        con.register(f"_{name}_df", frame)
        con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _{name}_df")
        con.unregister(f"_{name}_df")
        log.info("loaded reference table", extra={"table": name, "rows": len(frame)})

    return con
