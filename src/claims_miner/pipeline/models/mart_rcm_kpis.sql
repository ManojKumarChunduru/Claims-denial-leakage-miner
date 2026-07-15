-- Mart: monthly revenue cycle KPIs, the grain Power BI consumes.
CREATE OR REPLACE TABLE mart_rcm_kpis AS
WITH claim_month AS (
    SELECT
        DATE_TRUNC('month', c.service_date) AS service_month,
        c.claim_id,
        c.billed_amount,
        r.denial_flag,
        r.paid_amount,
        DATEDIFF('day', c.submission_date, r.remit_date) AS days_to_remit,
        c.submission_lag_days
    FROM stg_claims c
    JOIN stg_remits r USING (claim_id)
)
SELECT
    service_month,
    COUNT(*)                                   AS total_claims,
    SUM(billed_amount)                         AS billed_dollars,
    SUM(paid_amount)                           AS paid_dollars,
    SUM(CASE WHEN denial_flag THEN 1 ELSE 0 END)             AS denied_claims,
    SUM(CASE WHEN denial_flag THEN billed_amount ELSE 0 END) AS denied_dollars,
    ROUND(AVG(CASE WHEN denial_flag THEN 1.0 ELSE 0.0 END), 4) AS denial_rate,
    ROUND(1.0 - AVG(CASE WHEN denial_flag THEN 1.0 ELSE 0.0 END), 4) AS first_pass_yield,
    ROUND(AVG(days_to_remit), 1)               AS avg_days_to_remit,
    ROUND(AVG(submission_lag_days), 1)         AS avg_submission_lag_days
FROM claim_month
GROUP BY 1
ORDER BY 1;
