"""Benchmark the pipeline at increasing claim volumes.

Measures, per volume step:
- generate: synthetic data creation and parquet write (reported but
  excluded from pipeline throughput, since production data arrives from
  the billing system, not a generator)
- ingest: parquet -> DuckDB raw plus reference tables
- models: the five layered SQL models
- detect: rule engine materializing detected_leakage
- score: ground-truth evaluation

Throughput (claims/sec) is computed over ingest + models + detect, the
stages a production run would execute.

Usage:
    python benchmark/run_benchmark.py [--volumes 10000 100000 500000]

Results are written to benchmark/results/benchmark_<timestamp>.json and a
markdown summary is printed to stdout. Machine context (CPU count, RAM,
platform, versions) is captured with every run because throughput numbers
without hardware context are noise.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from claims_miner.config import (  # noqa: E402
    DetectionConfig,
    GeneratorConfig,
    PathsConfig,
    PipelineConfig,
    Settings,
)
from claims_miner.detection.rules import detect  # noqa: E402
from claims_miner.detection.scorer import score  # noqa: E402
from claims_miner.generator.claims_factory import generate_claims  # noqa: E402
from claims_miner.generator.denial_engine import adjudicate  # noqa: E402
from claims_miner.pipeline.ingest import ingest  # noqa: E402
from claims_miner.pipeline.runner import run_models  # noqa: E402


def _machine_context() -> dict:
    mem_gb = None
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        mem_gb = round(pages * page_size / 1024**3, 1)
    except (ValueError, OSError):
        pass
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "duckdb": duckdb.__version__,
        "cpu_count": os.cpu_count(),
        "ram_gb": mem_gb,
    }


def bench_volume(n_claims: int, work_dir: Path) -> dict:
    work_dir.mkdir(parents=True, exist_ok=True)
    settings = Settings(
        generator=GeneratorConfig(seed=42, n_claims=n_claims),
        paths=PathsConfig(
            data_dir=str(work_dir),
            claims_file=str(work_dir / "claims.parquet"),
            remits_file=str(work_dir / "remits.parquet"),
            labels_file=str(work_dir / "labels.parquet"),
            duckdb_file=str(work_dir / "wh.duckdb"),
            export_dir=str(work_dir / "export"),
        ),
        pipeline=PipelineConfig(),
        detection=DetectionConfig(),
    )

    timings: dict[str, float] = {}

    t0 = time.perf_counter()
    data = generate_claims(settings.generator)
    remits = adjudicate(data.claims, data.labels, settings.generator)
    data.claims.to_parquet(settings.paths.claims_file, index=False)
    remits.to_parquet(settings.paths.remits_file, index=False)
    data.labels.to_parquet(settings.paths.labels_file, index=False)
    timings["generate"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    con = ingest(settings)
    timings["ingest"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    model_timings = run_models(settings, con)
    timings["models"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    detect(settings, con)
    timings["detect"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    metrics = score(settings, con)
    timings["score"] = time.perf_counter() - t0

    con.close()

    pipeline_seconds = timings["ingest"] + timings["models"] + timings["detect"]
    return {
        "n_claims": n_claims,
        "timings_seconds": {k: round(v, 3) for k, v in timings.items()},
        "model_timings_seconds": {k: round(v, 3) for k, v in model_timings.items()},
        "pipeline_seconds": round(pipeline_seconds, 3),
        "claims_per_second": round(n_claims / pipeline_seconds),
        "detection_metrics": metrics.as_dict(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--volumes", nargs="+", type=int, default=[10_000, 100_000, 500_000]
    )
    args = parser.parse_args()

    results = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "machine": _machine_context(),
        "note": (
            "Throughput covers ingest + models + detect. Generation is "
            "excluded: production claims arrive from the billing system."
        ),
        "steps": [],
    }

    import tempfile

    for n in args.volumes:
        with tempfile.TemporaryDirectory() as tmp:
            print(f"benchmarking {n:,} claims ...", file=sys.stderr)
            results["steps"].append(bench_volume(n, Path(tmp)))

    out_dir = REPO_ROOT / "benchmark" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"benchmark_{stamp}.json"
    out_path.write_text(json.dumps(results, indent=2))

    print(f"\nresults written to {out_path}\n")
    print("| claims | pipeline s | claims/s | precision | recall | cause acc |")
    print("|-------:|-----------:|---------:|----------:|-------:|----------:|")
    for s in results["steps"]:
        m = s["detection_metrics"]
        print(
            f"| {s['n_claims']:,} | {s['pipeline_seconds']} "
            f"| {s['claims_per_second']:,} | {m['precision']} "
            f"| {m['recall']} | {m['cause_accuracy']} |"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
