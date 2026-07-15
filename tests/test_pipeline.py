from __future__ import annotations


def test_fct_denials_only_contains_denied_claims(warehouse):
    n = warehouse.execute(
        """
        SELECT count(*)
        FROM fct_denials d
        JOIN stg_remits r USING (claim_id)
        WHERE NOT r.denial_flag
        """
    ).fetchone()[0]
    assert n == 0


def test_no_ground_truth_columns_in_warehouse(warehouse):
    """The labels file must never leak into the warehouse the detector
    reads. If a table ever gains an is_preventable or injected_error
    column, detection metrics become meaningless."""
    cols = warehouse.execute(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE column_name IN ('is_preventable', 'injected_error')
        """
    ).fetchall()
    assert cols == []


def test_leakage_dollars_reconcile_to_denials(warehouse):
    a = warehouse.execute("SELECT ROUND(SUM(denied_dollars), 2) FROM fct_leakage").fetchone()[0]
    b = warehouse.execute("SELECT ROUND(SUM(denied_amount), 2) FROM fct_denials").fetchone()[0]
    assert a == b


def test_kpi_mart_claim_counts_reconcile(warehouse):
    total = warehouse.execute("SELECT SUM(total_claims) FROM mart_rcm_kpis").fetchone()[0]
    raw = warehouse.execute("SELECT count(*) FROM raw_claims").fetchone()[0]
    assert total == raw


def test_first_pass_yield_complements_denial_rate(warehouse):
    rows = warehouse.execute(
        "SELECT denial_rate, first_pass_yield FROM mart_rcm_kpis"
    ).fetchall()
    for denial_rate, fpy in rows:
        assert abs((denial_rate + fpy) - 1.0) < 1e-9
