"""Top-level movie import orchestrator (Steps 1-3).

The one call the view layer makes::

    result = MovieImportService.import_movie(movie_title)

Flow:
    1. DB check  — return a cached Movie immediately if we already have it
                   (refreshing its watch providers if they're >7 days old).
    2. Metadata  — otherwise import metadata via MetadataService (TMDB scrape ->
                   IMDb/Wikipedia fallback) and persist a Movie row.
    3. Providers — discover & store legal "where to watch" links via
                   ProviderService.

Returns a uniform :class:`ImportResult`. Never raises — all failures are
reported through the result object. A short-lived cache (Django cache framework)
collapses duplicate concurrent imports of the same title.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from django.core.cache import cache

from home.models import Movie
from home.movie_matcher import MovieMatcher, extract_year
from home.services.metadata_service import MetadataService
from home.services.provider_service import ProviderService

logger = logging.getLogger(__name__)

# Cache the title->movie_id resolution briefly to coalesce duplicate imports.
_IMPORT_CACHE_TTL = 60 * 10  # 10 minutes


@dataclass
class ImportResult:
    """Uniform return value for an import attempt."""

    status: str                       # found | imported | not_found | error
    message: str = ""
    movie_id: Optional[int] = None
    created: bool = False
    download_status: str = ""
    providers: List[Dict[str, Any]] = field(default_factory=list)
    movie: Optional[Movie] = field(default=None, repr=False, compare=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "movie_id": self.movie_id,
            "created": self.created,
            "download_status": self.download_status,
            "providers": self.providers,
        }

    @property
    def ok(self) -> bool:
        return self.status in {"found", "imported"}


class MovieImportService:
    """Find-or-import a movie and attach legal watch providers."""

    matcher = MovieMatcher()
    metadata = MetadataService()
    providers = ProviderService()

    @classmethod
    def import_movie(
        cls,
        movie_title: str,
        *,
        country: str = "US",
        force_refresh: bool = False,
        with_providers: bool = True,
    ) -> ImportResult:
        title = (movie_title or "").strip()
        if not title:
            return ImportResult(status="error", message="No movie title provided.")

        # 1) DB check (Step 1).
        if not force_refresh:
            existing = cls._find_local(title)
            if existing is not None:
                if with_providers:
                    cls._sync_providers(existing, country)
                return cls._result("found", existing, created=False,
                                    message="Loaded from library.", country=country)

        # 2) Metadata import (Step 2).
        try:
            details = cls.metadata.fetch_metadata(title)
        except Exception as exc:
            logger.exception("Metadata import crashed for %r", title)
            return ImportResult(status="error", message=f"Import failed: {exc}")

        if not details:
            return ImportResult(
                status="not_found",
                message="Movie not found on external sources",
            )

        movie = cls._persist(details)

        # 3) Provider discovery (Step 3).
        if with_providers:
            cls._sync_providers(movie, country)

        cache.set(cls._cache_key(title), movie.id, _IMPORT_CACHE_TTL)
        return cls._result("imported", movie, created=True,
                           message="Imported from external sources.", country=country)

    # -- internals ------------------------------------------------------------
    @staticmethod
    def _cache_key(title: str) -> str:
        # Hash so the key is safe for every backend (no spaces/colons/length limits).
        digest = hashlib.sha1(title.strip().lower().encode("utf-8")).hexdigest()
        return f"movie_import_{digest}"

    @classmethod
    def _find_local(cls, title: str) -> Optional[Movie]:
        # Fast path: recently resolved title -> id.
        cached_id = cache.get(cls._cache_key(title))
        if cached_id:
            movie = Movie.objects.filter(pk=cached_id).first()
            if movie:
                return movie

        year = extract_year(title)
        bare = title
        if year:
            bare = title.replace(year, "").replace("()", "").strip()
        from django.db.models import Q
        movie = Movie.objects.filter(
            Q(Title__iexact=title)
            | Q(Title__iexact=bare)
            | Q(Title__istartswith=f"{bare} (")
        ).order_by("id").first()
        if movie:
            cache.set(cls._cache_key(title), movie.id, _IMPORT_CACHE_TTL)
        return movie

    @classmethod
    def _sync_providers(cls, movie: Movie, country: str) -> None:
        try:
            cls.providers.sync(movie, country=country)
        except Exception as exc:  # provider issues must not fail the import
            logger.warning("Provider sync failed for %r: %s", movie.Title, exc)

    @staticmethod
    def _persist(details: Dict[str, Any]) -> Movie:
        external_id = str(details.get("external_id") or "").strip()
        source = details.get("source", "")

        download_links = (details.get("dLink") or "").strip()
        download_status = (
            Movie.DownloadStatus.AVAILABLE if download_links
            else Movie.DownloadStatus.PENDING
        )

        defaults = {
            "Title": details.get("Title", "").strip(),
            "description": details.get("description", ""),
            "image": details.get("image", ""),
            "backdrop": details.get("backdrop", ""),
            "genres": details.get("genres", ""),
            "release_year": str(details.get("release_year") or "").strip(),
            "language": details.get("language", ""),
            "runtime": details.get("runtime", ""),
            "rating": details.get("rating", ""),
            "cast": details.get("cast", ""),
            "director": details.get("director", ""),
            "quality": details.get("quality", ""),
            "file_size": details.get("file_size", ""),
            "mLink": details.get("mLink", ""),
            "embedLink": details.get("embedLink", ""),
            "tLink": details.get("tLink", ""),
            "dLink": download_links,
            "download_status": download_status,
            "source": source,
        }

        if external_id and source:
            movie, _ = Movie.objects.update_or_create(
                external_id=external_id, source=source, defaults=defaults,
            )
            return movie
        return Movie.objects.create(external_id=external_id, **defaults)

    @classmethod
    def _result(cls, status: str, movie: Movie, *, created: bool,
                message: str, country: str) -> ImportResult:
        provider_rows = list(movie.providers.filter(country=country)) if movie.pk else []
        return ImportResult(
            status=status,
            message=message,
            movie_id=movie.id,
            created=created,
            download_status=movie.download_status,
            providers=[_provider_dict(p) for p in provider_rows],
            movie=movie,
        )


def _provider_dict(p) -> Dict[str, Any]:
    return {
        "provider_name": p.provider_name,
        "provider_logo": p.provider_logo,
        "watch_url": p.watch_url,
        "is_free": p.is_free,
        "country": p.country,
    }
