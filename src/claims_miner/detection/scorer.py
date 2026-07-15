"""Score detection output against the generator's ground-truth labels.

This module is the only place in the codebase where the labels file is
read after generation. The separation is deliberate: the detector must
earn its precision and recall, and the scorer exists to keep it honest.

Metrics:
- precision: of the denied claims flagged as preventable, how many truly
  carried an injected error.
- recall: of the denied claims that truly carried an injected error, how
  many were flagged.
- cause_accuracy: of the true positives, how many were attributed to the
  CORRECT root cause. A detector that flags the right claims for the
  wrong reasons builds worklists that route to the wrong teams.
- dollar_recall: share of preventable denied dollars captured, since a
  revenue integrity program is measured in dollars, not claim counts.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass

import duckdb
import pandas as pd

from claims_miner.config import Settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Score:
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float
    cause_accuracy: float
    dollar_recall: float

    def as_dict(self) -> dict:
        return asdict(self)


def score(settings: Settings, con: duckdb.DuckDBPyConnection | None = None) -> Score:
    if con is None:
        con = duckdb.connect(settings.paths.duckdb_file)

    labels = pd.read_parquet(settings.paths.labels_file)
    con.register("_labels", labels)

    row = con.execute(
        """
        WITH truth AS (
            -- Preventable claims that were actually denied: the detector
            -- only sees denied claims, so undenied injections (none in
            -- this dataset) would be out of scope by design.
            SELECT l.claim_id, l.injected_error, d.denied_amount
            FROM _labels l
            JOIN fct_denials d USING (claim_id)
            WHERE l.is_preventable
        ),
        detected AS (
            SELECT claim_id, detected_cause, denied_amount FROM detected_leakage
        ),
        joined AS (
            SELECT
                COALESCE(t.claim_id, x.claim_id) AS claim_id,
                t.injected_error,
                x.detected_cause,
                t.claim_id IS NOT NULL AS is_true,
                x.claim_id IS NOT NULL AS is_flagged,
                COALESCE(t.denied_amount, 0) AS true_dollars
            FROM truth t
            FULL OUTER JOIN detected x USING (claim_id)
        )
        SELECT
            SUM(CASE WHEN is_true AND is_flagged THEN 1 ELSE 0 END) AS tp,
            SUM(CASE WHEN NOT is_true AND is_flagged THEN 1 ELSE 0 END) AS fp,
            SUM(CASE WHEN is_true AND NOT is_flagged THEN 1 ELSE 0 END) AS fn,
            SUM(CASE WHEN is_true AND is_flagged
                     AND injected_error = detected_cause THEN 1 ELSE 0 END) AS cause_correct,
            SUM(CASE WHEN is_true AND is_flagged THEN true_dollars ELSE 0 END) AS tp_dollars,
            SUM(CASE WHEN is_true THEN true_dollars ELSE 0 END) AS truth_dollars
        FROM joined
        """
    ).fetchone()
    con.unregister("_labels")

    tp, fp, fn, cause_correct, tp_dollars, truth_dollars = (
        int(row[0] or 0), int(row[1] or 0), int(row[2] or 0),
        int(row[3] or 0), float(row[4] or 0), float(row[5] or 0),
    )
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    result = Score(
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
        cause_accuracy=round(cause_correct / tp, 4) if tp else 0.0,
        dollar_recall=round(tp_dollars / truth_dollars, 4) if truth_dollars else 0.0,
    )
    log.info("scoring complete", extra=result.as_dict())
    return result
