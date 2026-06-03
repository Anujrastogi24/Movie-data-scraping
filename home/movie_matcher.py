"""Movie matching/scoring.

Given a free-text query and a list of candidate results from a metadata
provider, decide which candidate the user most likely meant. Pure functions,
no I/O — so it is trivially unit-testable and reused by every provider.

Scoring priorities (per the import spec):

* Exact (normalized) title match            -> highest priority
* Similar title match (token / sequence)    -> second priority
* Release-year match                         -> increases score
* Language match                             -> increases score
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Dict, Optional, Sequence

# Generic words that should not drive a title match.
STOPWORDS = frozenset({
    "movie", "movies", "film", "the", "a", "an", "watch", "online",
    "full", "hd", "trailer", "show", "tv", "series", "season",
})


@dataclass
class MovieCandidate:
    """A normalized search result from any metadata provider."""

    title: str
    year: str = ""
    language: str = ""
    image: str = ""
    description: str = ""
    genres: str = ""
    url: str = ""
    source: str = ""
    external_id: str = ""
    # Provider-specific extra payload (kept for the details() lookup).
    raw: Dict[str, Any] = field(default_factory=dict)


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9\s]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokens(text: str, drop_stopwords: bool = True) -> set:
    toks = {t for t in _normalize(text).split() if t}
    if drop_stopwords:
        toks = {t for t in toks if t not in STOPWORDS and not t.isdigit()}
    return toks


def extract_year(text: str) -> Optional[str]:
    """Return the first 1900–2099 year found in ``text``, else None."""
    match = re.search(r"\b(?:19|20)\d{2}\b", text or "")
    return match.group(0) if match else None


def _title_similarity(query_title: str, candidate_title: str) -> float:
    """0.0–1.0 similarity combining sequence ratio and token overlap."""
    q_norm = _normalize(query_title)
    c_norm = _normalize(candidate_title)
    if not q_norm or not c_norm:
        return 0.0

    seq = SequenceMatcher(None, q_norm, c_norm).ratio()

    q_tok, c_tok = _tokens(query_title), _tokens(candidate_title)
    if q_tok and c_tok:
        jaccard = len(q_tok & c_tok) / len(q_tok | c_tok)
    else:
        jaccard = 0.0

    return max(seq, jaccard)


@dataclass
class MatchResult:
    candidate: MovieCandidate
    score: float
    exact: bool


class MovieMatcher:
    """Scores candidates against a query and selects the best one."""

    # Weights — tuned so an exact title always outranks a close-but-not-exact
    # title, while year/language act as tie-breakers.
    EXACT_TITLE = 100.0
    SIMILAR_TITLE = 60.0          # multiplied by the 0–1 similarity
    YEAR_MATCH = 25.0
    YEAR_NEAR = 10.0              # within 1 year
    LANGUAGE_MATCH = 15.0
    MIN_SIMILARITY = 0.40        # below this a candidate is rejected

    def score(
        self,
        candidate: MovieCandidate,
        query_title: str,
        year: str = "",
        language: str = "",
    ) -> MatchResult:
        similarity = _title_similarity(query_title, candidate.title)
        exact = _normalize(query_title) == _normalize(candidate.title)

        score = self.EXACT_TITLE if exact else self.SIMILAR_TITLE * similarity

        if year and candidate.year:
            try:
                diff = abs(int(year) - int(candidate.year))
            except ValueError:
                diff = None
            if diff == 0:
                score += self.YEAR_MATCH
            elif diff == 1:
                score += self.YEAR_NEAR

        if language and candidate.language:
            if _normalize(language) == _normalize(candidate.language):
                score += self.LANGUAGE_MATCH

        return MatchResult(candidate=candidate, score=score, exact=exact)

    def best_match(
        self,
        candidates: Sequence[MovieCandidate],
        query: str,
        language: str = "",
    ) -> Optional[MatchResult]:
        """Return the highest-scoring candidate, or None if none clear the bar.

        Year/title hints are parsed out of ``query`` itself, so callers can pass
        a raw user string like ``"Inception 2010"``.
        """
        if not candidates:
            return None

        year = extract_year(query) or ""
        query_title = re.sub(r"\b(?:19|20)\d{2}\b", "", query).strip() or query

        best: Optional[MatchResult] = None
        for candidate in candidates:
            result = self.score(candidate, query_title, year=year, language=language)
            # Reject weak fuzzy matches outright (exact matches always pass).
            if not result.exact and _title_similarity(query_title, candidate.title) < self.MIN_SIMILARITY:
                continue
            if best is None or result.score > best.score:
                best = result
        return best
