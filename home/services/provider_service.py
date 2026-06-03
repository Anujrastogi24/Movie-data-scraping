"""Persist & refresh watch providers (Steps 6 & 7).

Bridges :class:`home.services.watch_provider_service.WatchProviderService`
(discovery) and the :class:`home.models.MovieProvider` table (storage):

* ``sync(movie)``        — return cached rows if fresh, else (re)discover + upsert
* ``needs_refresh(movie)`` — True if a movie has no rows or any row is >7 days old
* ``refresh_stale(...)`` — bulk refresh for the management command / cron

Upserts are keyed on (movie, provider_name, country, watch_url) — matching the
model's ``unique_together`` — so re-running discovery updates ``last_checked``
in place instead of creating duplicates.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from home.models import Movie, MovieProvider
from home.services.watch_provider_service import ProviderResult, WatchProviderService

logger = logging.getLogger(__name__)


class ProviderService:
    """Discovery-to-database glue with a 7-day freshness policy."""

    def __init__(self, discovery: Optional[WatchProviderService] = None) -> None:
        self._discovery = discovery or WatchProviderService()

    # -- queries --------------------------------------------------------------
    def needs_refresh(self, movie: Movie, country: str = "US") -> bool:
        """True if the movie has no providers, or any are past the refresh window."""
        rows = movie.providers.filter(country=country)
        if not rows.exists():
            return True
        now = timezone.now()
        return any(row.is_stale(now) for row in rows)

    # -- main entry points ----------------------------------------------------
    def sync(self, movie: Movie, country: str = "US", force: bool = False) -> List[MovieProvider]:
        """Return the movie's providers, refreshing from sources if stale.

        Never raises — discovery failures leave existing rows untouched and are
        logged.
        """
        if not force and not self.needs_refresh(movie, country):
            logger.debug("Providers for %r are fresh; serving cached rows.", movie.Title)
            return list(movie.providers.filter(country=country))

        try:
            results = self._discovery.discover(movie, country=country)
        except Exception as exc:
            logger.warning("Provider discovery failed for %r: %s", movie.Title, exc)
            return list(movie.providers.filter(country=country))

        if results:
            self._upsert(movie, results, country)
        else:
            # Nothing found this round — still bump last_checked so we honor the
            # 7-day cadence rather than retrying on every request.
            self._touch(movie, country)

        return list(movie.providers.filter(country=country))

    def refresh_stale(self, country: str = "US", limit: Optional[int] = None) -> int:
        """Refresh every movie that has stale/missing providers. Returns count."""
        cutoff = timezone.now() - MovieProvider.REFRESH_AFTER
        stale_q = Q(providers__isnull=True) | Q(providers__last_checked__lt=cutoff)
        movies = Movie.objects.filter(stale_q).distinct()
        if limit:
            movies = movies[:limit]

        refreshed = 0
        for movie in movies:
            self.sync(movie, country=country, force=True)
            refreshed += 1
        logger.info("Refreshed providers for %d movie(s).", refreshed)
        return refreshed

    # -- persistence ----------------------------------------------------------
    @transaction.atomic
    def _upsert(self, movie: Movie, results: List[ProviderResult], country: str) -> None:
        now = timezone.now()
        seen_keys = set()
        for r in results:
            if not r.provider_name or not r.watch_url:
                continue
            obj, _created = MovieProvider.objects.update_or_create(
                movie=movie,
                provider_name=r.provider_name,
                country=r.country or country,
                watch_url=r.watch_url,
                defaults={
                    "provider_logo": r.provider_logo,
                    "is_free": r.is_free,
                    "source": r.source,
                    "last_checked": now,
                },
            )
            seen_keys.add(obj.pk)

        # Drop rows for this country that discovery no longer returns (dead links).
        stale = movie.providers.filter(country=country).exclude(pk__in=seen_keys)
        removed = stale.count()
        if removed:
            stale.delete()
            logger.info("Removed %d stale provider row(s) for %r.", removed, movie.Title)

    def _touch(self, movie: Movie, country: str) -> None:
        """Bump last_checked on existing rows without changing them."""
        movie.providers.filter(country=country).update(last_checked=timezone.now())
