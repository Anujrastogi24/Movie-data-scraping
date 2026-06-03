"""Legal metadata providers.

This module replaces the Google -> piracy-site pivot from the original spec
with official, terms-of-service-friendly sources:

* :class:`TMDBProvider` — The Movie Database (https://www.themoviedb.org), the
  industry-standard free movie API. Requires a ``TMDB_API_KEY`` (read from
  Django settings or the environment).
* :class:`LegacyProvider` — wraps the project's existing IMDb-suggestion +
  Wikipedia + YouTube scrapers (``home.scraping``) so imports keep working with
  zero configuration when no TMDB key is present.

Every provider exposes the same small interface::

    search(query, limit) -> list[MovieCandidate]
    details(candidate)    -> dict   # kwargs for Movie.objects.create(...)

so the import service is agnostic to where data comes from. Adding another
*authorized* source later is just another subclass.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter

try:  # urllib3 ships with requests; guard just in case.
    from urllib3.util.retry import Retry
    _HAS_RETRY = True
except Exception:  # pragma: no cover
    _HAS_RETRY = False

try:
    from django.conf import settings
except Exception:  # pragma: no cover - allows standalone import
    settings = None  # type: ignore

from home.movie_matcher import MovieCandidate

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 10


def _build_session(total_retries: int = 3, backoff: float = 0.4) -> requests.Session:
    """A requests Session with transparent retry/backoff for transient errors.

    Uses urllib3's Retry adapter rather than manual ``sleep`` loops, so there
    are no fixed sleeps in the hot path — backoff only kicks in on 429/5xx.
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent": "MovieCinema/1.0 (+https://localhost) Django metadata importer",
        "Accept": "application/json",
    })
    if _HAS_RETRY:
        retry = Retry(
            total=total_retries,
            connect=total_retries,
            read=total_retries,
            status=total_retries,
            backoff_factor=backoff,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
    return session


def _setting(name: str, default: Optional[str] = None) -> Optional[str]:
    """Read a config value from Django settings, falling back to env vars."""
    if settings is not None:
        value = getattr(settings, name, None)
        if value:
            return value
    return os.environ.get(name, default)


class MetadataProvider(ABC):
    """Interface implemented by every legal metadata source."""

    name: str = "provider"

    def __init__(self) -> None:
        self._session = _build_session()

    @property
    def enabled(self) -> bool:
        """Whether the provider is usable (e.g. has its API key configured)."""
        return True

    @abstractmethod
    def search(self, query: str, limit: int = 10) -> List[MovieCandidate]:
        """Return normalized candidates for ``query`` (best-effort, never raises)."""

    @abstractmethod
    def details(self, candidate: MovieCandidate) -> Optional[Dict[str, Any]]:
        """Return ``Movie.objects.create(...)`` kwargs for a chosen candidate."""


class TMDBProvider(MetadataProvider):
    """The Movie Database — official free API."""

    name = "TMDB"
    BASE = "https://api.themoviedb.org/3"
    IMG = "https://image.tmdb.org/t/p/w500"

    def __init__(self) -> None:
        super().__init__()
        self._api_key = _setting("TMDB_API_KEY")
        # TMDB also supports v4 bearer tokens.
        self._bearer = _setting("TMDB_READ_TOKEN")
        self._genre_map: Dict[int, str] = {}

    @property
    def enabled(self) -> bool:
        return bool(self._api_key or self._bearer)

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Optional[dict]:
        params = dict(params or {})
        headers = {}
        if self._bearer:
            headers["Authorization"] = f"Bearer {self._bearer}"
        elif self._api_key:
            params["api_key"] = self._api_key
        try:
            resp = self._session.get(
                f"{self.BASE}{path}", params=params, headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 200:
                return resp.json()
            logger.warning("TMDB %s returned HTTP %s", path, resp.status_code)
        except requests.RequestException as exc:
            logger.warning("TMDB request failed for %s: %s", path, exc)
        return None

    def _load_genre_map(self) -> Dict[int, str]:
        if self._genre_map:
            return self._genre_map
        data = self._get("/genre/movie/list", {"language": "en-US"})
        if data:
            self._genre_map = {g["id"]: g["name"] for g in data.get("genres", [])}
        return self._genre_map

    def search(self, query: str, limit: int = 10) -> List[MovieCandidate]:
        if not self.enabled or not query.strip():
            return []
        data = self._get("/search/movie", {
            "query": query.strip(), "include_adult": "false", "language": "en-US",
        })
        if not data:
            return []

        candidates: List[MovieCandidate] = []
        for item in (data.get("results") or [])[:limit]:
            title = item.get("title") or item.get("original_title") or ""
            if not title:
                continue
            release = item.get("release_date") or ""
            poster = item.get("poster_path") or ""
            candidates.append(MovieCandidate(
                title=title,
                year=release[:4] if release else "",
                language=item.get("original_language", ""),
                image=f"{self.IMG}{poster}" if poster else "",
                description=item.get("overview", ""),
                url=f"https://www.themoviedb.org/movie/{item.get('id')}",
                source=self.name,
                external_id=str(item.get("id") or ""),
                raw=item,
            ))
        return candidates

    def details(self, candidate: MovieCandidate) -> Optional[Dict[str, Any]]:
        movie_id = candidate.external_id
        full = self._get(
            f"/movie/{movie_id}",
            {"language": "en-US", "append_to_response": "videos"},
        ) if movie_id else None
        item = full or candidate.raw or {}

        # Genres: from the full payload if available, else map the id list.
        if item.get("genres"):
            genres = ", ".join(g.get("name", "") for g in item["genres"] if g.get("name"))
        else:
            gmap = self._load_genre_map()
            genres = ", ".join(
                gmap.get(gid, "") for gid in item.get("genre_ids", []) if gmap.get(gid)
            )

        trailer = self._best_trailer(item.get("videos", {}).get("results", []))
        release = item.get("release_date") or ""
        poster = item.get("poster_path") or ""

        return {
            "Title": _display_title(candidate.title, candidate.year or release[:4]),
            "description": (item.get("overview") or candidate.description or "")[:1000],
            "image": candidate.image or (f"{self.IMG}{poster}" if poster else ""),
            "genres": genres or candidate.genres,
            "release_year": (candidate.year or release[:4] or ""),
            "language": item.get("original_language", candidate.language) or "",
            "tLink": trailer,
            "source": self.name,
            "external_id": candidate.external_id,
        }

    @staticmethod
    def _best_trailer(videos: List[dict]) -> str:
        for video in videos:
            if (video.get("site") == "YouTube"
                    and video.get("type") == "Trailer"
                    and video.get("key")):
                return f"https://www.youtube.com/watch?v={video['key']}"
        for video in videos:  # any YouTube video as a fallback
            if video.get("site") == "YouTube" and video.get("key"):
                return f"https://www.youtube.com/watch?v={video['key']}"
        return ""


class LegacyProvider(MetadataProvider):
    """Wraps the project's existing IMDb/Wikipedia/YouTube scrapers.

    Zero-config fallback so the importer works before a TMDB key is set up.
    """

    name = "IMDb"

    def search(self, query: str, limit: int = 10) -> List[MovieCandidate]:
        from home import scraping  # local import: optional bs4 dependency
        try:
            raw = scraping.search_imdb(query, limit=limit)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("LegacyProvider search failed: %s", exc)
            return []

        candidates: List[MovieCandidate] = []
        for item in raw:
            candidates.append(MovieCandidate(
                title=item.get("title", ""),
                year=str(item.get("year") or ""),
                image=item.get("image", ""),
                description=item.get("description", ""),
                url=item.get("url", ""),
                source=self.name,
                raw=item,
            ))
        return candidates

    def details(self, candidate: MovieCandidate) -> Optional[Dict[str, Any]]:
        from home import scraping
        try:
            enriched = scraping._enrich_details(
                candidate.title,
                candidate.year,
                image=candidate.image,
                imdb_url=candidate.url,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("LegacyProvider details failed: %s", exc)
            return None
        if not enriched:
            return None
        enriched.pop("_imdb_url", None)
        enriched["release_year"] = candidate.year
        enriched["source"] = self.name
        return enriched


def _display_title(title: str, year: str = "") -> str:
    title = (title or "").strip()
    year = (year or "").strip()
    return f"{title} ({year})" if year else title
