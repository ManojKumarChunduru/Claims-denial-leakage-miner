"""Payer adjudication: turns claims plus ground-truth labels into
835-shaped remittances.

Adjudication logic:

- Claims with an injected preventable error are denied with the CARC code
  a payer would typically use for that error. With probability
  NOISY_CARC_RATE the payer instead uses the generic code from the
  reference taxonomy (usually CARC 16, "claim lacks information"), which
  mirrors the real-world pain that remit codes alone often cannot tell a
  biller what actually went wrong.
- A configured share of clean claims receive background denials (medical
  necessity, prior-payer adjudication, fee schedule) that are real denials
  but not preventable leakage.
- Everything else pays at a contracted rate between 45% and 75% of billed,
  with the remainder as a contractual adjustment (CARC 45 on paid claims
  is an adjustment, not a denial, and the denial_flag stays false).

The engine reads labels because it plays the payer, who by definition
knows why a claim fails. The detection layer never sees labels.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from claims_miner.config import GeneratorConfig
from claims_miner.generator import reference_data as ref

NOISY_CARC_RATE = 0.20
REMIT_LAG_DAYS = (14, 45)


def adjudicate(
    claims: pd.DataFrame, labels: pd.DataFrame, cfg: GeneratorConfig
) -> pd.DataFrame:
    """Produce one 835-shaped remit row per claim."""
    rng = np.random.default_rng(cfg.seed + 1)
    n = len(claims)
    merged = claims.merge(labels, on="claim_id", how="left", validate="one_to_one")

    carc = np.empty(n, dtype=object)
    denial_flag = np.zeros(n, dtype=bool)
    paid = np.zeros(n, dtype=float)

    contracted_rate = 0.45 + rng.random(n) * 0.30
    noisy = rng.random(n) < NOISY_CARC_RATE
    background = rng.random(n) < cfg.background_denial_rate
    background_codes = rng.choice(list(ref.BACKGROUND_DENIALS.keys()), size=n)

    is_preventable = merged["is_preventable"].fillna(False).to_numpy(dtype=bool)
    injected = merged["injected_error"].to_numpy(dtype=object)

    for i in range(n):
        if is_preventable[i]:
            meta = ref.PREVENTABLE_ERRORS[injected[i]]
            carc[i] = meta["noisy_carc"] if noisy[i] else meta["carc"]
            denial_flag[i] = True
            paid[i] = 0.0
        elif background[i]:
            carc[i] = background_codes[i]
            denial_flag[i] = True
            paid[i] = 0.0
        else:
            carc[i] = "45"  # contractual adjustment on a paid claim
            denial_flag[i] = False
            paid[i] = round(merged.at[i, "billed_amount"] * contracted_rate[i], 2)

    remit_lag = rng.integers(REMIT_LAG_DAYS[0], REMIT_LAG_DAYS[1], size=n)

    remits = pd.DataFrame(
        {
            "remit_id": [f"RMT{cfg.seed:02d}{i:09d}" for i in range(n)],
            "claim_id": merged["claim_id"],
            "payer_id": merged["payer_id"],
            "remit_date": pd.to_datetime(merged["submission_date"])
            + pd.to_timedelta(remit_lag, unit="D"),
            "carc_code": carc,
            "denial_flag": denial_flag,
            "paid_amount": paid,
            "billed_amount": merged["billed_amount"],
            "adjustment_amount": np.round(merged["billed_amount"].to_numpy() - paid, 2),
        }
    )
    return remits
