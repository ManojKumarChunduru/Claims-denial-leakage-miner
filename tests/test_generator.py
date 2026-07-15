from __future__ import annotations

import pandas as pd

from claims_miner.config import GeneratorConfig
from claims_miner.generator import reference_data as ref
from claims_miner.generator.claims_factory import generate_claims
from claims_miner.generator.denial_engine import NOISY_CARC_RATE


def test_deterministic_with_seed():
    cfg = GeneratorConfig(seed=11, n_claims=500)
    a = generate_claims(cfg)
    b = generate_claims(cfg)
    pd.testing.assert_frame_equal(a.claims, b.claims)
    pd.testing.assert_frame_equal(a.labels, b.labels)


def test_label_rate_matches_config(generated):
    data, _ = generated
    rate = data.labels["is_preventable"].mean()
    assert abs(rate - 0.12) < 0.001


def test_timely_filing_claims_exceed_payer_limit(generated):
    data, _ = generated
    merged = data.claims.merge(data.labels, on="claim_id")
    tf = merged[merged["injected_error"] == "timely_filing"]
    assert len(tf) > 0
    lag = (tf["submission_date"] - tf["service_date"]).dt.days
    limits = tf["payer_id"].map(lambda p: ref.PAYERS[p]["filing_limit_days"])
    assert (lag > limits).all()


def test_missing_modifier_injection_keeps_dx_valid(generated):
    """Regression: the missing_modifier injection once swapped the CPT
    without re-drawing the diagnosis, silently adding a second error that
    outranked the labeled one in rule precedence (cause accuracy 0.84)."""
    data, _ = generated
    merged = data.claims.merge(data.labels, on="claim_id")
    mm = merged[merged["injected_error"] == "missing_modifier"]
    assert len(mm) > 0
    assert mm["modifier"].isna().all()
    for _, row in mm.iterrows():
        assert row["icd10_code"] in ref.PROCEDURES[row["cpt_code"]]["valid_dx"]


def test_all_preventable_claims_are_denied(generated):
    data, remits = generated
    merged = remits.merge(data.labels, on="claim_id")
    assert merged.loc[merged["is_preventable"], "denial_flag"].all()


def test_paid_claims_pay_within_contracted_band(generated):
    _, remits = generated
    paid = remits[~remits["denial_flag"]]
    ratio = paid["paid_amount"] / paid["billed_amount"]
    assert (ratio >= 0.45).all() and (ratio <= 0.75).all()


def test_noisy_carc_rate_is_close_to_configured(generated):
    data, remits = generated
    merged = remits.merge(data.labels, on="claim_id")
    prev = merged[merged["is_preventable"]].copy()
    expected = prev["injected_error"].map(lambda e: ref.PREVENTABLE_ERRORS[e]["carc"])
    noisy_share = (prev["carc_code"] != expected).mean()
    # Only errors whose noisy code differs from the primary can look noisy,
    # so the observed share sits below NOISY_CARC_RATE. Just bound it.
    assert 0.05 < noisy_share <= NOISY_CARC_RATE + 0.05
