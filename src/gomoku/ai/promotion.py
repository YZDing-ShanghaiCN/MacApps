"""Promotion decision for the iterate_model self-play training loop.

A candidate model replaces ``current.pt`` only when its 95% Wilson score
interval against the incumbent lies entirely above 0.5. A raw point score
above 0.5 is not sufficient evidence.
"""

from __future__ import annotations


def should_promote(report: dict) -> bool:
    """True iff the candidate's Wilson 95% CI lower bound exceeds 0.5.

    ``report`` is the arena report JSON as a dict; the candidate always
    plays as label ``A`` in the promotion match.
    """

    lower_bound = report["score_confidence_95"]["A"][0]
    return lower_bound > 0.5
