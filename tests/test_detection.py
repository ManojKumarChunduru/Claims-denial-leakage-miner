from __future__ import annotations

from claims_miner.detection.scorer import score


def test_detected_causes_are_known_rules(warehouse):
    causes = {
        r[0]
        for r in warehouse.execute(
            "SELECT DISTINCT detected_cause FROM detected_leakage"
        ).fetchall()
    }
    known = {
        "missing_auth",
        "timely_filing",
        "duplicate_claim",
        "invalid_dx_pair",
        "missing_modifier",
        "coverage_termed",
    }
    assert causes <= known
    assert len(causes) >= 5


def test_original_of_duplicate_pair_is_not_flagged(warehouse):
    """For attribute-identical groups, only later submissions may be
    flagged as duplicates; the earliest is the payable original."""
    n = warehouse.execute(
        """
        WITH ranked AS (
            SELECT claim_id,
                   ROW_NUMBER() OVER (
                       PARTITION BY patient_id, payer_id, cpt_code, service_date
                       ORDER BY submission_date, claim_id
                   ) AS rn
            FROM stg_claims
        )
        SELECT count(*)
        FROM detected_leakage d
        JOIN ranked r USING (claim_id)
        WHERE d.detected_cause = 'duplicate_claim'
          AND r.rn = 1
          AND d.carc_code <> '18'
        """
    ).fetchone()[0]
    assert n == 0


def test_scorer_metrics_are_strong_and_bounded(settings, warehouse):
    s = score(settings, warehouse)
    assert 0.95 <= s.precision <= 1.0
    assert 0.95 <= s.recall <= 1.0
    assert 0.95 <= s.cause_accuracy <= 1.0
    assert s.false_negatives + s.true_positives > 0


def test_scorer_counts_reconcile(settings, warehouse):
    s = score(settings, warehouse)
    flagged = warehouse.execute("SELECT count(*) FROM detected_leakage").fetchone()[0]
    assert s.true_positives + s.false_positives == flagged
