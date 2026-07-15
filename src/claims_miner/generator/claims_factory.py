"""Synthetic 837-shaped claim generation with labeled, injected errors.

The factory produces three artifacts:

1. claims: one row per institutional claim (837I-shaped, simplified).
2. labels: the ground truth of which claims carry an injected preventable
   error and which error class. Labels are written to a separate file and
   are never read by the detection layer; they exist only so the scorer
   can compute honest precision and recall.
3. The remittance side (835-shaped) is produced separately by the
   denial engine, which adjudicates these claims.

Design choices that keep the dataset honest:

- Not every denial is preventable. A background denial rate creates claims
  denied for medical-necessity or contractual reasons that a leakage
  detector must NOT flag.
- Clean claims are not perfectly clean. A small share of paid claims in
  auth-required departments legitimately lack an auth number on the claim
  record (auth handled offline), which is a realistic false-positive trap.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from claims_miner.config import GeneratorConfig
from claims_miner.generator import reference_data as ref

# Share of clean, payable claims in auth-required departments that carry no
# auth number on the claim record. Realistic trap for naive detectors.
AUTH_MISSING_ON_CLEAN_RATE = 0.03

# Share of injected duplicates whose "original" falls outside the generated
# window, so attribute-hash duplicate detection cannot see the pair.
ORPHAN_DUPLICATE_RATE = 0.15


@dataclass
class GeneratedData:
    claims: pd.DataFrame
    labels: pd.DataFrame


def _dates_between(rng: np.random.Generator, start: str, end: str, n: int) -> pd.Series:
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    span_days = (end_ts - start_ts).days
    offsets = rng.integers(0, span_days + 1, size=n)
    return pd.Series(pd.to_datetime(start_ts) + pd.to_timedelta(offsets, unit="D"))


def generate_claims(cfg: GeneratorConfig) -> GeneratedData:
    """Generate claims and ground-truth labels according to config."""
    rng = np.random.default_rng(cfg.seed)
    n = cfg.n_claims

    payer_ids = np.array(list(ref.PAYERS.keys()))
    dept_ids = np.array(list(ref.DEPARTMENTS.keys()))
    cpt_codes = np.array(list(ref.PROCEDURES.keys()))

    claims = pd.DataFrame(
        {
            "claim_id": [f"CLM{cfg.seed:02d}{i:09d}" for i in range(n)],
            "patient_id": [f"PAT{v:07d}" for v in rng.integers(1, max(2, n // 3), size=n)],
            "payer_id": rng.choice(payer_ids, size=n),
            "department_id": rng.choice(dept_ids, size=n),
            "cpt_code": rng.choice(cpt_codes, size=n),
        }
    )

    claims["service_date"] = _dates_between(rng, cfg.start_date, cfg.end_date, n)

    # Submission lag: most claims go out within 2 weeks, with a long tail.
    lag_days = rng.gamma(shape=2.0, scale=4.0, size=n).astype(int)
    claims["submission_date"] = claims["service_date"] + pd.to_timedelta(lag_days, unit="D")

    proc_meta = claims["cpt_code"].map(ref.PROCEDURES)
    lo = proc_meta.map(lambda p: p["amount"][0]).to_numpy(dtype=float)
    hi = proc_meta.map(lambda p: p["amount"][1]).to_numpy(dtype=float)
    claims["billed_amount"] = np.round(lo + rng.random(n) * (hi - lo), 2)
    claims["units"] = 1

    # Clinically consistent diagnosis for each claim (may be corrupted later).
    claims["icd10_code"] = [
        rng.choice(ref.PROCEDURES[cpt]["valid_dx"]) for cpt in claims["cpt_code"]
    ]

    # Modifier where the procedure requires one (may be blanked later).
    needs_mod = claims["cpt_code"].map(lambda c: ref.PROCEDURES[c]["modifier_required"])
    claims["modifier"] = np.where(needs_mod, rng.choice(ref.MODIFIERS, size=n), None)

    # Auth number where the department requires one (may be blanked later).
    dept_auth = claims["department_id"].map(lambda d: ref.DEPARTMENTS[d]["auth_required"])
    auth_numbers = np.array([f"AUTH{v:08d}" for v in rng.integers(0, 10**8, size=n)])
    claims["auth_number"] = np.where(dept_auth, auth_numbers, None)

    # Coverage window: nearly all patients covered well past service date.
    cov_end_offset = rng.integers(30, 720, size=n)
    claims["coverage_end_date"] = claims["service_date"] + pd.to_timedelta(cov_end_offset, unit="D")

    # Realistic trap: some clean auth-required claims lack an auth number.
    clean_auth_gap = dept_auth.to_numpy() & (rng.random(n) < AUTH_MISSING_ON_CLEAN_RATE)
    claims.loc[clean_auth_gap, "auth_number"] = None

    labels = _inject_errors(claims, cfg, rng)
    return GeneratedData(claims=claims, labels=labels)


def _inject_errors(
    claims: pd.DataFrame, cfg: GeneratorConfig, rng: np.random.Generator
) -> pd.DataFrame:
    """Corrupt a labeled subset of claims with preventable errors, in place."""
    n = len(claims)
    error_types = list(ref.PREVENTABLE_ERRORS.keys())
    n_errors = int(n * cfg.preventable_error_rate)
    error_idx = rng.choice(n, size=n_errors, replace=False)
    assigned = rng.choice(error_types, size=n_errors)

    labels = pd.DataFrame(
        {"claim_id": claims["claim_id"], "injected_error": None, "is_preventable": False}
    )

    for idx, err in zip(error_idx, assigned, strict=True):
        row = claims.index[idx]
        if err == "missing_auth":
            # Force into an auth-required department, then blank the auth.
            claims.at[row, "department_id"] = "D04"
            claims.at[row, "auth_number"] = None
        elif err == "timely_filing":
            limit = ref.PAYERS[claims.at[row, "payer_id"]]["filing_limit_days"]
            claims.at[row, "submission_date"] = claims.at[row, "service_date"] + pd.Timedelta(
                days=int(limit + rng.integers(5, 90))
            )
        elif err == "duplicate_claim":
            if rng.random() < ORPHAN_DUPLICATE_RATE:
                # Orphan duplicate: original outside the window. Attribute
                # hashing inside the dataset cannot pair it; only the payer
                # knows. Deliberate recall ceiling for the detector.
                pass
            else:
                source = claims.iloc[int(rng.integers(0, n))]
                for col in [
                    "patient_id", "payer_id", "department_id", "cpt_code", "service_date",
                    "billed_amount", "icd10_code", "modifier", "auth_number",
                    "coverage_end_date",
                ]:
                    claims.at[row, col] = source[col]
                claims.at[row, "submission_date"] = source["submission_date"] + pd.Timedelta(
                    days=int(rng.integers(1, 20))
                )
        elif err == "invalid_dx_pair":
            valid = set(ref.PROCEDURES[claims.at[row, "cpt_code"]]["valid_dx"])
            invalid_pool = [dx for dx in ref.ALL_DX if dx not in valid]
            claims.at[row, "icd10_code"] = str(rng.choice(invalid_pool))
        elif err == "missing_modifier":
            # Force onto a modifier-required procedure, then blank it.
            # The diagnosis must be re-drawn from the NEW procedure's valid
            # set, otherwise the claim silently carries a second error
            # (invalid dx pair) and the injected label lies about the
            # claim's true root cause.
            claims.at[row, "cpt_code"] = "27447"
            claims.at[row, "icd10_code"] = str(rng.choice(ref.PROCEDURES["27447"]["valid_dx"]))
            claims.at[row, "modifier"] = None
        elif err == "coverage_termed":
            claims.at[row, "coverage_end_date"] = claims.at[row, "service_date"] - pd.Timedelta(
                days=int(rng.integers(10, 120))
            )
        labels.iloc[idx, labels.columns.get_loc("injected_error")] = err
        labels.iloc[idx, labels.columns.get_loc("is_preventable")] = True

    return labels
