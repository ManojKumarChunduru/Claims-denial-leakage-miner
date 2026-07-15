-- Fact: one row per DENIED claim, carrying every claim attribute the
-- detection rules need. This is the only table the detector reads, and it
-- contains no ground-truth labels by construction.
CREATE OR REPLACE TABLE fct_denials AS
SELECT
    c.claim_id,
    c.patient_id,
    c.payer_id,
    c.payer_name,
    c.filing_limit_days,
    c.department_id,
    c.department_name,
    c.auth_required,
    c.cpt_code,
    c.cpt_desc,
    c.modifier_required,
    c.icd10_code,
    c.modifier,
    c.auth_number,
    c.service_date,
    c.submission_date,
    c.coverage_end_date,
    c.submission_lag_days,
    r.remit_date,
    DATEDIFF('day', c.submission_date, r.remit_date) AS days_to_remit,
    r.carc_code,
    r.carc_desc,
    r.billed_amount,
    -- Denied claims pay zero in this dataset, so denied dollars equal
    -- billed dollars. Kept as an explicit column so downstream models do
    -- not re-derive the business rule.
    r.billed_amount AS denied_amount,
    vp.icd10_code IS NOT NULL AS dx_pair_valid
FROM stg_remits r
JOIN stg_claims c USING (claim_id)
LEFT JOIN ref_valid_dx_pairs vp
    ON vp.cpt_code = c.cpt_code AND vp.icd10_code = c.icd10_code
WHERE r.denial_flag;
