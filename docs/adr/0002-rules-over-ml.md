# ADR-0002: Deterministic rules over ML for denial classification

Status: accepted
Date: 2026-07-15

## Context

The detector must classify each denied claim into a preventable root
cause (or none). The taxonomy is small and known: authorization, timely
filing, duplicates, coding pairs, modifiers, eligibility. Output drives
worklists that route to specific operational teams, and revenue cycle
leadership must be able to ask "why was this claim flagged" and get an
answer a biller can act on.

## Options considered

1. Deterministic rules over claim attributes with CARC corroboration.
2. A supervised classifier (gradient boosting) trained on labeled denials.
3. A hybrid: rules first, model for the unclassified remainder.

## Decision

Deterministic rules, evaluated in fixed precedence order.

- Every rule is an auditable sentence. "Auth-required department with no
  authorization number" survives a compliance review and a payer dispute;
  a feature importance chart does not.
- The classes are attribute-defined, not statistical. A duplicate IS an
  attribute collision; a timely filing failure IS lag exceeding the payer
  limit. Learning what can be stated exactly adds error for no benefit.
  Measured against ground truth: 99.5% precision, 100% recall, 99.1%
  correct root cause attribution on the labeled set.
- Rules fire on day one with no training data. A model needs months of
  labeled denials, and labels in the wild are exactly the noisy CARC
  codes this project demonstrates are unreliable (20% of injected
  denials carry a generic code).

## Consequences

- Rules cannot discover unknown denial patterns; they only find what they
  encode. The unclassified denied remainder is surfaced in fct_denials
  minus detected_leakage, and that residue is the natural training set.
- The documented trigger for revisiting: when the unclassified share of
  denied dollars exceeds 20% for two consecutive months, add the hybrid
  option (option 3), keeping rules as the explainable first pass.
