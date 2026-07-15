-- Fact: the leakage surface. Denied dollars aggregated by payer, CARC and
-- department, the three axes a revenue integrity team works.
CREATE OR REPLACE TABLE fct_leakage AS
SELECT
    payer_id,
    payer_name,
    carc_code,
    carc_desc,
    department_id,
    department_name,
    COUNT(*)                 AS denied_claims,
    SUM(denied_amount)       AS denied_dollars,
    AVG(denied_amount)       AS avg_denied_amount,
    MIN(service_date)        AS first_service_date,
    MAX(service_date)        AS last_service_date
FROM fct_denials
GROUP BY 1, 2, 3, 4, 5, 6;
