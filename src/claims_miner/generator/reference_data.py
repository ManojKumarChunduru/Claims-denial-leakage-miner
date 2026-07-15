"""Domain reference data for the synthetic claims generator.

Everything here is public-domain healthcare billing vocabulary: CARC codes
from the X12 Claim Adjustment Reason Code set, sample CPT/ICD-10 codes, and
plausible payer and department names. No real patient, provider, or payer
data appears anywhere in this project.
"""

from __future__ import annotations

# Payers with their timely-filing limits in days. Limits vary by payer in
# the real world (Medicare 365, many commercial plans 90 to 180), which is
# exactly what makes timely-filing denials a rules problem and not a
# constant-threshold problem.
PAYERS: dict[str, dict] = {
    "P001": {"name": "Medicare",            "filing_limit_days": 365},
    "P002": {"name": "Medicaid",            "filing_limit_days": 180},
    "P003": {"name": "Blue Shield PPO",     "filing_limit_days": 90},
    "P004": {"name": "UnitedHealth HMO",    "filing_limit_days": 90},
    "P005": {"name": "Aetna Commercial",    "filing_limit_days": 120},
    "P006": {"name": "Cigna Open Access",   "filing_limit_days": 90},
    "P007": {"name": "Humana Advantage",    "filing_limit_days": 180},
    "P008": {"name": "Tricare",             "filing_limit_days": 365},
}

# Hospital departments. auth_required drives the missing-authorization
# error class: elective and imaging-heavy departments need pre-auth,
# emergency care does not.
DEPARTMENTS: dict[str, dict] = {
    "D01": {"name": "Emergency",          "auth_required": False},
    "D02": {"name": "Inpatient Surgery",  "auth_required": True},
    "D03": {"name": "Outpatient Surgery", "auth_required": True},
    "D04": {"name": "Radiology",          "auth_required": True},
    "D05": {"name": "Cardiology",         "auth_required": True},
    "D06": {"name": "Laboratory",         "auth_required": False},
    "D07": {"name": "Physical Therapy",   "auth_required": True},
    "D08": {"name": "Observation",        "auth_required": False},
    "D09": {"name": "Oncology",           "auth_required": True},
    "D10": {"name": "Maternity",          "auth_required": False},
}

# CPT/HCPCS procedure codes with a typical billed-amount range and the set
# of ICD-10 diagnosis codes considered clinically consistent with them.
# The pairs are simplified but directionally realistic; the point is that
# an (ICD-10, CPT) combination outside this map is a codeable error.
PROCEDURES: dict[str, dict] = {
    "99283": {"desc": "ED visit, moderate severity",   "amount": (400, 1200),   "valid_dx": ["R07.9", "R10.9", "S09.90XA", "J06.9"], "modifier_required": False},
    "99285": {"desc": "ED visit, high severity",       "amount": (900, 2500),   "valid_dx": ["R07.9", "I21.9", "J96.00", "R55"],     "modifier_required": False},
    "70450": {"desc": "CT head without contrast",      "amount": (800, 2200),   "valid_dx": ["R51.9", "S09.90XA", "I63.9", "R55"],   "modifier_required": False},
    "72148": {"desc": "MRI lumbar spine",              "amount": (1200, 3200),  "valid_dx": ["M54.5", "M51.26", "M48.06"],           "modifier_required": False},
    "93000": {"desc": "Electrocardiogram, complete",   "amount": (150, 450),    "valid_dx": ["R07.9", "I21.9", "I48.91", "R00.2"],   "modifier_required": False},
    "93458": {"desc": "Cardiac catheterization",       "amount": (4500, 12000), "valid_dx": ["I21.9", "I25.10", "I20.9"],            "modifier_required": False},
    "27447": {"desc": "Total knee arthroplasty",       "amount": (18000, 42000),"valid_dx": ["M17.11", "M17.12", "M17.0"],           "modifier_required": True},
    "47562": {"desc": "Laparoscopic cholecystectomy",  "amount": (9000, 22000), "valid_dx": ["K80.20", "K81.0", "K80.10"],           "modifier_required": True},
    "80053": {"desc": "Comprehensive metabolic panel", "amount": (40, 160),     "valid_dx": ["E11.9", "N18.3", "R53.83", "I10"],     "modifier_required": False},
    "85025": {"desc": "Complete blood count",          "amount": (25, 110),     "valid_dx": ["D64.9", "R50.9", "E11.9", "I10"],      "modifier_required": False},
    "97110": {"desc": "Therapeutic exercises",         "amount": (90, 260),     "valid_dx": ["M54.5", "M25.561", "M17.11"],          "modifier_required": True},
    "96413": {"desc": "Chemotherapy infusion, 1st hr", "amount": (1500, 5200),  "valid_dx": ["C50.911", "C34.90", "C18.9"],          "modifier_required": False},
    "59400": {"desc": "Routine obstetric care",        "amount": (6000, 14000), "valid_dx": ["O80", "Z34.90", "O34.21"],             "modifier_required": False},
    "43239": {"desc": "Upper GI endoscopy w/ biopsy",  "amount": (2500, 7500),  "valid_dx": ["K21.9", "K29.70", "R13.10"],           "modifier_required": True},
    "71046": {"desc": "Chest X-ray, 2 views",          "amount": (120, 380),    "valid_dx": ["J06.9", "R05.9", "J96.00", "J18.9"],   "modifier_required": False},
}

# The full ICD-10 pool used for generating clean claims and for drawing
# deliberately inconsistent diagnoses.
ALL_DX: list[str] = sorted({dx for p in PROCEDURES.values() for dx in p["valid_dx"]})

# Common modifiers for procedures that require one.
MODIFIERS: list[str] = ["LT", "RT", "50", "59", "25"]

# Injected preventable error classes and the CARC code a payer would most
# often attach to the resulting denial. `noisy_carc` is the generic code a
# payer sometimes uses instead, which is what keeps detection non-trivial:
# CARC 16 ("claim lacks information") tells a biller almost nothing.
PREVENTABLE_ERRORS: dict[str, dict] = {
    "missing_auth":       {"carc": "197", "noisy_carc": "16", "desc": "Authorization absent for auth-required department"},
    "timely_filing":      {"carc": "29",  "noisy_carc": "29", "desc": "Submitted past the payer filing limit"},
    "duplicate_claim":    {"carc": "18",  "noisy_carc": "18", "desc": "Exact duplicate of a prior claim"},
    "invalid_dx_pair":    {"carc": "11",  "noisy_carc": "16", "desc": "Diagnosis inconsistent with the procedure"},
    "missing_modifier":   {"carc": "4",   "noisy_carc": "16", "desc": "Required modifier absent"},
    "coverage_termed":    {"carc": "27",  "noisy_carc": "26", "desc": "Service after coverage termination"},
}

# Denial reasons outside billing's control, used for background denials.
# These are real denials but not preventable leakage, and a good detector
# must not flag them.
BACKGROUND_DENIALS: dict[str, str] = {
    "50": "Non-covered: not deemed medically necessary by the payer",
    "23": "Impact of prior payer adjudication",
    "45": "Charge exceeds fee schedule or contracted rate",
}

CARC_DESCRIPTIONS: dict[str, str] = {
    "4":   "Procedure code inconsistent with the modifier used",
    "11":  "Diagnosis inconsistent with the procedure",
    "16":  "Claim lacks information or has submission error",
    "18":  "Exact duplicate claim or service",
    "23":  "Impact of prior payer adjudication",
    "26":  "Expenses incurred prior to coverage",
    "27":  "Expenses incurred after coverage terminated",
    "29":  "Time limit for filing has expired",
    "45":  "Charge exceeds fee schedule or contracted rate",
    "50":  "Non-covered: not medically necessary",
    "197": "Precertification or authorization absent",
}
