-- Staging: typed, conformed claims with reference attributes and derived
-- submission lag. One row per claim.
CREATE OR REPLACE VIEW stg_claims AS
SELECT
    c.claim_id,
    c.patient_id,
    c.payer_id,
    p.payer_name,
    p.filing_limit_days,
    c.department_id,
    d.department_name,
    d.auth_required,
    c.cpt_code,
    pr.cpt_desc,
    pr.modifier_required,
    c.icd10_code,
    c.modifier,
    c.auth_number,
    CAST(c.service_date AS DATE)      AS service_date,
    CAST(c.submission_date AS DATE)   AS submission_date,
    CAST(c.coverage_end_date AS DATE) AS coverage_end_date,
    DATEDIFF('day', c.service_date, c.submission_date) AS submission_lag_days,
    c.billed_amount,
    c.units
FROM raw_claims c
JOIN ref_payers p        USING (payer_id)
JOIN ref_departments d   USING (department_id)
JOIN ref_procedures pr   USING (cpt_code);
