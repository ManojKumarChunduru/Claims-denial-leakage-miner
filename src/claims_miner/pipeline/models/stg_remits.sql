-- Staging: typed remittances with CARC descriptions. One row per remit.
CREATE OR REPLACE VIEW stg_remits AS
SELECT
    r.remit_id,
    r.claim_id,
    r.payer_id,
    CAST(r.remit_date AS DATE) AS remit_date,
    r.carc_code,
    cc.carc_desc,
    r.denial_flag,
    r.paid_amount,
    r.billed_amount,
    r.adjustment_amount
FROM raw_remits r
LEFT JOIN ref_carc cc USING (carc_code);
