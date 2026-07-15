"""Rule-based classification of denied claims into preventable root causes.

Input: fct_denials only (claim attributes plus the remit CARC code).
Output: a `detected_leakage` table with one row per denied claim the rules
classify as preventable, carrying the detected root cause.

Why the rules do not simply trust CARC codes: payers use generic codes
(CARC 16, "claim lacks information") for roughly a fifth of denials in
this dataset, matching the real-world experience that remit codes alone
often cannot drive worklists. Every rule therefore anchors on claim
attributes first and uses the CARC code as corroboration, not as truth.

Rule precedence: rules are evaluated in a fixed order and the first match
wins, so each denied claim receives at most one root cause. Order puts
the highest-precision attribute checks first.
"""

from __future__ import annotations

import logging

import duckdb
import pandas as pd

from claims_miner.config import Settings

log = logging.getLogger(__name__)

# Rule -> the CARC codes that corroborate it. A rule may still fire on a
# generic CARC 16 because the attribute evidence stands on its own.
RULES: dict[str, str] = {
    "duplicate_claim": (
        "Attribute-identical to another claim for the same patient, "
        "payer, procedure and service date, or payer says duplicate (CARC 18)"
    ),
    "coverage_termed": "Service date after the member coverage end date",
    "timely_filing": "Submission lag exceeds the payer filing limit",
    "missing_auth": "Auth-required department with no authorization number",
    "invalid_dx_pair": "Diagnosis outside the valid set for the procedure",
    "missing_modifier": "Modifier-required procedure billed without a modifier",
}

DETECTION_SQL = """
CREATE OR REPLACE TABLE detected_leakage AS
WITH dup_candidates AS (
    -- Claims sharing patient, payer, procedure and service date with at
    -- least one other claim in the window. The EARLIEST submission in the
    -- group is treated as the original and is not flagged.
    SELECT claim_id
    FROM (
        SELECT
            claim_id,
            ROW_NUMBER() OVER (
                PARTITION BY patient_id, payer_id, cpt_code, service_date
                ORDER BY submission_date, claim_id
            ) AS rn
        FROM stg_claims
    )
    WHERE rn > 1
),
classified AS (
    SELECT
        d.*,
        CASE
            WHEN d.claim_id IN (SELECT claim_id FROM dup_candidates)
              OR d.carc_code = '18'
                THEN 'duplicate_claim'
            WHEN d.service_date > d.coverage_end_date
                THEN 'coverage_termed'
            WHEN d.submission_lag_days > d.filing_limit_days
                THEN 'timely_filing'
            WHEN d.auth_required AND d.auth_number IS NULL
                THEN 'missing_auth'
            WHEN NOT d.dx_pair_valid
                THEN 'invalid_dx_pair'
            WHEN d.modifier_required AND d.modifier IS NULL
                THEN 'missing_modifier'
            ELSE NULL
        END AS detected_cause
    FROM fct_denials d
)
SELECT
    claim_id,
    patient_id,
    payer_id,
    payer_name,
    department_id,
    department_name,
    cpt_code,
    icd10_code,
    carc_code,
    carc_desc,
    service_date,
    submission_date,
    denied_amount,
    detected_cause
FROM classified
WHERE detected_cause IS NOT NULL;
"""

PATTERN_SQL = """
SELECT
    payer_name,
    detected_cause,
    department_name,
    COUNT(*)            AS denied_claims,
    SUM(denied_amount)  AS denied_dollars
FROM detected_leakage
GROUP BY 1, 2, 3
HAVING SUM(denied_amount) >= ? AND COUNT(*) >= ?
ORDER BY denied_dollars DESC
"""


def detect(settings: Settings, con: duckdb.DuckDBPyConnection | None = None) -> pd.DataFrame:
    """Run detection rules, materialize detected_leakage, return patterns.

    Returns the actionable pattern report: payer x cause x department
    cells above the configured dollar and claim-count floors.
    """
    if con is None:
        con = duckdb.connect(settings.paths.duckdb_file)
    con.execute(DETECTION_SQL)
    n = con.execute("SELECT count(*) FROM detected_leakage").fetchone()[0]
    dollars = con.execute(
        "SELECT COALESCE(SUM(denied_amount), 0) FROM detected_leakage"
    ).fetchone()[0]
    log.info(
        "detection complete",
        extra={"flagged_claims": n, "flagged_dollars": round(float(dollars), 2)},
    )
    patterns = con.execute(
        PATTERN_SQL,
        [settings.detection.min_pattern_dollars, settings.detection.min_pattern_claims],
    ).df()
    return patterns
