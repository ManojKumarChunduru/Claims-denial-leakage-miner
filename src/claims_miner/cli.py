"""Command line interface.

    claims-miner generate   Generate synthetic claims, remits, and labels
    claims-miner run        Ingest, build SQL models, run detection, export
    claims-miner score      Score detection output against ground truth
    claims-miner all        generate + run + score
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from claims_miner.config import Settings, load_settings
from claims_miner.detection.rules import detect
from claims_miner.detection.scorer import score
from claims_miner.generator.claims_factory import generate_claims
from claims_miner.generator.denial_engine import adjudicate
from claims_miner.logging_conf import configure_logging
from claims_miner.pipeline.ingest import ingest
from claims_miner.pipeline.runner import export_marts, run_models

log = logging.getLogger(__name__)


def cmd_generate(settings: Settings) -> None:
    data = generate_claims(settings.generator)
    remits = adjudicate(data.claims, data.labels, settings.generator)
    Path(settings.paths.data_dir).mkdir(parents=True, exist_ok=True)
    data.claims.to_parquet(settings.paths.claims_file, index=False)
    remits.to_parquet(settings.paths.remits_file, index=False)
    data.labels.to_parquet(settings.paths.labels_file, index=False)
    log.info(
        "generation complete",
        extra={
            "claims": len(data.claims),
            "denials": int(remits["denial_flag"].sum()),
            "preventable_labels": int(data.labels["is_preventable"].sum()),
        },
    )


def cmd_run(settings: Settings) -> None:
    con = ingest(settings)
    run_models(settings, con)
    patterns = detect(settings, con)
    export_marts(settings, con)
    if not patterns.empty:
        log.info("top leakage patterns", extra={"patterns": patterns.head(10).to_dict("records")})


def cmd_score(settings: Settings) -> None:
    result = score(settings)
    print(json.dumps(result.as_dict(), indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="claims-miner")
    parser.add_argument(
        "command", choices=["generate", "run", "score", "all"], help="workflow step to execute"
    )
    parser.add_argument("--config", default=None, help="path to settings.yaml")
    parser.add_argument("--quiet", action="store_true", help="log warnings and above only")
    args = parser.parse_args(argv)

    configure_logging(logging.WARNING if args.quiet else logging.INFO)
    settings = load_settings(args.config)

    steps = {
        "generate": [cmd_generate],
        "run": [cmd_run],
        "score": [cmd_score],
        "all": [cmd_generate, cmd_run, cmd_score],
    }[args.command]
    for step in steps:
        step(settings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
