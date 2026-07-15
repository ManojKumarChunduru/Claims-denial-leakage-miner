# ADR-0001: DuckDB over PostgreSQL for the analytics warehouse

Status: accepted
Date: 2026-07-15

## Context

The pipeline is scan-heavy analytics: full-table aggregations over claims
and remits, window functions for duplicate detection, and multi-way joins
against reference dimensions. Volumes in scope are 10K to 500K claims per
run, single writer, batch cadence. Consumers are the detection layer and
a Power BI model fed by parquet exports.

## Options considered

1. PostgreSQL in Docker: a served, row-oriented OLTP database.
2. DuckDB: an in-process, columnar OLAP engine with a single-file store.
3. SQLite: in-process but row-oriented, weak window function performance
   at this scale.

## Decision

DuckDB. This is the boring choice for this workload and that is the point:

- Zero operational surface. No container, no port, no credentials, no
  healthcheck. `pip install` and the warehouse exists. The quickstart is
  three commands partly because of this decision.
- Columnar execution fits the access pattern. Every model is a scan or an
  aggregation; measured end to end, the five models plus detection run in
  1.2 seconds over 500K claims on 1 vCPU (benchmark/results/).
- The SQL surface (CTEs, window functions, DATE functions) is close
  enough to MS SQL Server and Snowflake that models port with minimal
  edits, which matters because the SQL layer is the part most likely to
  be lifted into a Clarity-style reporting environment.

## Consequences

- No concurrent writers and no served endpoint. Acceptable: the pipeline
  is single-writer batch, and consumers read parquet exports.
- Teams that need a SQL endpoint (an on-prem Power BI gateway, SSRS) get
  the optional docker-compose Postgres target loaded by
  scripts/load_postgres.py, at the cost of running one container.
- If the workload ever becomes concurrent, multi-writer, or served, the
  decision flips to Postgres; the trigger is the first consumer that
  cannot read files.
