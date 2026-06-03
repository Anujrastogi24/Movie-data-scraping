"""Metadata orchestration.

Produces a single ``Movie``-shaped kwargs dict for a title by combining sources
in priority order (Step 2):

1. TMDB website scrape (:class:`home.services.tmdb_service.TMDBService`) — rich
   data: cast, director, runtime, rating, backdrop.
2. The project's existing IMDb-suggestion + Wikipedia path
   (:class:`home.metadata_provider.LegacyProvider`) — proven, zero-config,
   guarantees imports still succeed when the TMDB scrape comes back empty.

Best match selection reuses :class:`home.movie_matcher.MovieMatcher` so the
scoring rules (exact title > fuzzy, +year, +language) are shared with the rest
of the system. Lower-priority sources only *fill gaps*; they never overwrite a
field a higher-priority source already populated.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from home.metadata_provider import LegacyProvider
from home.movie_matcher import MovieCandidate, MovieMatcher
from home.services.tmdb_service import TMDBResult, TMDBService

logger = logging.getLogger(__name__)

# Fields that make up a complete Movie record (used to detect "gaps").
_META_FIELDS = (
    "Title", "description", "image", "backdrop", "genres", "release_year",
    "language", "runtime", "rating", "cast", "director", "tLink",
)


class MetadataService:
    """Fetch and merge movie metadata from prioritized legal sources."""

    matcher = MovieMatcher()

    def __init__(self) -> None:
        self._tmdb = TMDBService()
        self._legacy = LegacyProvider()

    def fetch_metadata(self, title: str) -> Optional[Dict[str, Any]]:
        """Return Movie kwargs for the best match of ``title``, or None.

        Never raises — every source is wrapped defensively.
        """
        title = (title or "").strip()
        if not title:
            return None

        details: Dict[str, Any] = {}

        # 1) TMDB website scrape (primary).
        tmdb_details = self._from_tmdb(title)
        if tmdb_details:
            details = tmdb_details

        # 2) Legacy IMDb/Wikipedia — fills any gaps (and is the sole source if
        #    the TMDB scrape failed entirely).
        if not details or _has_gaps(details):
            legacy_details = self._from_legacy(title)
            if legacy_details:
                details = _merge(primary=details, secondary=legacy_details)

        if not details:
            logger.info("No metadata found for %r from any source.", title)
            return None

        details.setdefault("download_status", "pending")
        return details

    # -- per-source helpers ---------------------------------------------------
    def _from_tmdb(self, title: str) -> Optional[Dict[str, Any]]:
        try:
            results = self._tmdb.search(title, limit=10)
        except Exception as exc:
            logger.warning("TMDB search failed for %r: %s", title, exc)
            return None
        if not results:
            return None

        match = self.matcher.best_match(_to_candidates(results), title)
        if match is None:
            return None
        chosen = next(
            (r for r in results if r.title == match.candidate.title and
             (r.year or "") == (match.candidate.year or "")),
            results[0],
        )
        try:
            return self._tmdb.fetch_details(chosen)
        except Exception as exc:
            logger.warning("TMDB details failed for %r: %s", title, exc)
            return None

    def _from_legacy(self, title: str) -> Optional[Dict[str, Any]]:
        try:
            candidates = self._legacy.search(title, limit=10)
        except Exception as exc:
            logger.warning("Legacy search failed for %r: %s", title, exc)
            return None
        match = self.matcher.best_match(candidates, title)
        if match is None:
            return None
        try:
            return self._legacy.details(match.candidate)
        except Exception as exc:
            logger.warning("Legacy details failed for %r: %s", title, exc)
            return None


# ---- helpers ---------------------------------------------------------------
def _to_candidates(results: List[TMDBResult]) -> List[MovieCandidate]:
    return [
        MovieCandidate(
            title=r.title, year=r.year, image=r.poster,
            description=r.overview, source="TMDB", raw=r.raw,
        )
        for r in results
    ]


def _has_gaps(details: Dict[str, Any]) -> bool:
    """True if any important field is still empty (worth a fallback lookup)."""
    return any(not str(details.get(f, "")).strip() for f in _META_FIELDS)


def _merge(primary: Dict[str, Any], secondary: Dict[str, Any]) -> Dict[str, Any]:
    """Return primary with empty fields backfilled from secondary."""
    merged = dict(secondary)        # start with secondary...
    for key, value in primary.items():  # ...primary wins where it has a value
        if str(value).strip():
            merged[key] = value
        else:
            merged.setdefault(key, value)
    # Carry provenance from whichever source actually had the title.
    merged["source"] = primary.get("source") or secondary.get("source", "")
    merged.pop("_imdb_url", None)
    return merged
