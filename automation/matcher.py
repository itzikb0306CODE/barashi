"""Fuzzy-match bank transaction counterparty names against an OXS roster
(tenants for payments, suppliers for expenses).

Money is on the line here, so the rule is conservative on purpose: a match
is only returned when it is both above a confidence floor *and* clearly
better than the next-best candidate. Anything else is reported as
unmatched/ambiguous and must be skipped by the caller rather than guessed.
"""
from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz, process

MIN_SCORE = 85  # 0-100 rapidfuzz score floor to even consider a match
MIN_GAP = 8  # required lead over the runner-up to call it unambiguous


@dataclass(frozen=True)
class Candidate:
    """One entry in the roster being matched against (a tenant or a supplier)."""

    id: str
    name: str
    extra: dict | None = None  # e.g. {"apartment_url": ..., "phone": ..., "email": ...}


@dataclass(frozen=True)
class MatchResult:
    candidate: Candidate | None
    score: float
    reason: str  # "matched" | "no_candidates" | "below_threshold" | "ambiguous"


def _normalize(name: str) -> str:
    return " ".join(name.strip().split())


def match_name(raw_name: str | None, roster: list[Candidate]) -> MatchResult:
    """Find the best unambiguous match for raw_name in roster, or explain why not."""
    if not raw_name or not raw_name.strip():
        return MatchResult(None, 0.0, "no_candidates")
    if not roster:
        return MatchResult(None, 0.0, "no_candidates")

    query = _normalize(raw_name)
    choices = {c.id: _normalize(c.name) for c in roster}

    ranked = process.extract(
        query, choices, scorer=fuzz.token_sort_ratio, limit=2
    )
    if not ranked:
        return MatchResult(None, 0.0, "no_candidates")

    top_name, top_score, top_id = ranked[0]
    if top_score < MIN_SCORE:
        return MatchResult(None, top_score, "below_threshold")

    if len(ranked) > 1:
        _, second_score, _ = ranked[1]
        if top_score - second_score < MIN_GAP:
            return MatchResult(None, top_score, "ambiguous")

    winner = next(c for c in roster if c.id == top_id)
    return MatchResult(winner, top_score, "matched")
