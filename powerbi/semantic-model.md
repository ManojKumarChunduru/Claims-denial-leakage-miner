# Power BI semantic model

The pipeline exports four parquet tables to `powerbi/export/` (run
`claims-miner all`). Load them with Get Data > Parquet, then apply the
model below.

## Star schema

Fact tables:

- `detected_leakage` (grain: one row per flagged denied claim)
- `fct_denials` (grain: one row per denied claim, flagged or not)
- `mart_rcm_kpis` (grain: one row per service month, pre-aggregated)

Dimensions (build in Power Query from the facts, or reimport the
reference tables from DuckDB):

- `dim_payer`: payer_id, payer_name
- `dim_department`: department_id, department_name
- `dim_cause`: detected_cause (six members)
- `dim_date`: standard date table marked as the model date table,
  related to service_date

Relationships: single-direction, many-to-one from each fact to each
dimension on the id columns. Do not relate the two claim-grain facts to
each other; they share dimensions instead.

## Report pages

1. Command center: cards for Denial Rate, First Pass Yield, Denied
   Dollars, Preventable Dollars; monthly trend from mart_rcm_kpis.
2. Leakage explorer: matrix of payer x detected_cause weighted by denied
   dollars, drill to department, top N table of worklist claims.
3. Root cause detail: decomposition tree from Preventable Dollars into
   cause > payer > department.

## Measures

See `measures.dax`. Paste each into a measure on the noted table.

## Screenshots

After the report is built, export page screenshots to
`powerbi/screenshots/` and link them from the README "Dashboard" section.
Until then the README Dashboard section points here instead of showing
placeholder images.
