"""Legal "Where to Watch" discovery (Steps 3 & 4).

Discovers places to legally watch a movie, trying sources in priority order:

    1. TMDB Watch Providers (JustWatch-backed) — authoritative, broad
    2. Internet Archive  — public-domain / freely licensed films (real API)
    3. Tubi / Pluto TV / Crackle / Plex — free, ad-supported (best-effort scrape)
    4. Google fallback   — only if nothing above matched (Selenium, best-effort)

Each source implements the small :class:`WatchSource` interface, so adding or
removing one is a one-line registry change. Piracy sources are explicitly out of
scope. Best-effort scrapers (Tubi/Pluto/Crackle/Plex/Google) have no public API
and *will* need occasional selector maintenance — they fail closed (return []),
never raise.

Public surface:
    WatchProviderService().discover(movie, country="US") -> list[ProviderResult]
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urljoin, urlparse

from home.services.selenium_driver import handle_loading_screen, retry, selenium_available
from home.services.tmdb_service import TMDBService

logger = logging.getLogger(__name__)

try:
    import requests
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except Exception:  # pragma: no cover
    HAS_BS4 = False

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
TIMEOUT = 10


@dataclass
class ProviderResult:
    """A normalized provider hit — maps 1:1 onto MovieProvider fields."""

    provider_name: str
    watch_url: str
    provider_logo: str = ""
    is_free: bool = False
    country: str = "US"
    source: str = ""


@dataclass
class MovieContext:
    """The minimal movie info a source needs to search."""

    title: str
    year: str = ""
    external_id: str = ""     # TMDB numeric id when source == "TMDB"
    source: str = ""          # which metadata source produced the record

    @property
    def bare_title(self) -> str:
        return re.sub(r"\s*\(\d{4}\)\s*$", "", self.title).strip() or self.title

    @property
    def tmdb_path(self) -> str:
        return f"/movie/{self.external_id}" if self.external_id else ""


def _session() -> "requests.Session":
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def _title_matches(query_title: str, text: str) -> bool:
    """Loose check that ``text`` plausibly refers to the queried title."""
    q_tokens = {t for t in re.findall(r"[a-z0-9]+", query_title.lower()) if len(t) > 2}
    if not q_tokens:
        return False
    t_lower = text.lower()
    hits = sum(1 for t in q_tokens if t in t_lower)
    return hits >= max(1, len(q_tokens) // 2)


# --------------------------------------------------------------------------- #
# Source interface + implementations
# --------------------------------------------------------------------------- #
class WatchSource(ABC):
    name: str = "source"

    @abstractmethod
    def discover(self, ctx: MovieContext, country: str) -> List[ProviderResult]:
        """Return provider hits for ``ctx``. Must never raise."""


class TMDBWatchSource(WatchSource):
    """Authoritative provider list scraped from TMDB's /watch page."""

    name = "TMDB Watch Providers"

    def __init__(self) -> None:
        self._tmdb = TMDBService()

    def discover(self, ctx: MovieContext, country: str) -> List[ProviderResult]:
        path = ctx.tmdb_path
        try:
            if not path:
                # Metadata came from a non-TMDB source — search TMDB to get a path.
                results = self._tmdb.search(ctx.bare_title, limit=1)
                if not results:
                    return []
                path = results[0].path
            raw = self._tmdb.fetch_watch_providers(path, country=country)
        except Exception as exc:
            logger.warning("%s failed: %s", self.name, exc)
            return []
        return [_as_result(item, default_source=self.name) for item in raw]


class InternetArchiveSource(WatchSource):
    """Public-domain / freely licensed films via the Archive.org API (free)."""

    name = "Internet Archive"
    API = "https://archive.org/advancedsearch.php"

    @retry(times=2, exceptions=(Exception,), label="archive.discover")
    def _query(self, ctx: MovieContext) -> List[Dict[str, Any]]:
        if not HAS_BS4:
            return []
        params = {
            "q": f'title:("{ctx.bare_title}") AND mediatype:(movies)',
            "fl[]": ["identifier", "title", "year"],
            "rows": "5",
            "output": "json",
        }
        resp = _session().get(self.API, params=params, timeout=TIMEOUT)
        if resp.status_code != 200:
            return []
        return (resp.json().get("response", {}) or {}).get("docs", []) or []

    def discover(self, ctx: MovieContext, country: str) -> List[ProviderResult]:
        try:
            docs = self._query(ctx)
        except Exception as exc:
            logger.warning("%s failed: %s", self.name, exc)
            return []

        results: List[ProviderResult] = []
        for doc in docs:
            title = str(doc.get("title", ""))
            if not _title_matches(ctx.bare_title, title):
                continue
            if ctx.year and str(doc.get("year", "")) and str(doc["year"]) != ctx.year:
                continue
            identifier = doc.get("identifier")
            if not identifier:
                continue
            results.append(ProviderResult(
                provider_name="Internet Archive",
                watch_url=f"https://archive.org/details/{identifier}",
                provider_logo="https://archive.org/images/glogo.jpg",
                is_free=True,
                country=country,
                source=self.name,
            ))
            break  # one good public-domain hit is enough
        return results


class _KeywordSiteSource(WatchSource):
    """Base for free ad-supported sites with a public search page but no API.

    Subclasses set ``name``, ``search_url`` (with a ``{q}`` placeholder),
    ``result_selector`` and ``domain``. Best-effort: returns at most one hit
    whose link text plausibly matches the title; fails closed otherwise.
    """

    search_url: str = ""
    result_selector: str = "a"
    domain: str = ""
    logo: str = ""
    is_free: bool = True

    def discover(self, ctx: MovieContext, country: str) -> List[ProviderResult]:
        if not HAS_BS4 or not self.search_url:
            return []
        url = self.search_url.format(q=quote_plus(ctx.bare_title))
        try:
            resp = _session().get(url, timeout=TIMEOUT)
            if resp.status_code != 200 or not resp.text:
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as exc:
            logger.debug("%s search failed: %s", self.name, exc)
            return []

        for link in soup.select(self.result_selector):
            href = link.get("href", "")
            text = link.get_text(" ", strip=True) or link.get("title", "")
            if not href or not _title_matches(ctx.bare_title, text):
                continue
            watch_url = href if href.startswith("http") else urljoin(self.domain, href)
            return [ProviderResult(
                provider_name=self.name,
                watch_url=watch_url,
                provider_logo=self.logo,
                is_free=self.is_free,
                country=country,
                source=self.name,
            )]
        return []


class TubiSource(_KeywordSiteSource):
    name = "Tubi"
    domain = "https://tubitv.com"
    search_url = "https://tubitv.com/search/{q}"
    result_selector = "a[href*='/movies/'], a[href*='/video/']"
    logo = "https://tubitv.com/favicon.ico"


class PlutoSource(_KeywordSiteSource):
    name = "Pluto TV"
    domain = "https://pluto.tv"
    search_url = "https://pluto.tv/en/search/details?query={q}"
    result_selector = "a[href*='/on-demand/movies/']"
    logo = "https://pluto.tv/favicon.ico"


class CrackleSource(_KeywordSiteSource):
    name = "Crackle"
    domain = "https://www.crackle.com"
    search_url = "https://www.crackle.com/search/{q}"
    result_selector = "a[href*='/watch/'], a[href*='/movies/']"
    logo = "https://www.crackle.com/favicon.ico"


class PlexSource(_KeywordSiteSource):
    name = "Plex"
    domain = "https://watch.plex.tv"
    search_url = "https://watch.plex.tv/search?query={q}"
    result_selector = "a[href*='/movie/']"
    logo = "https://watch.plex.tv/favicon.ico"


class GoogleFallbackSource(WatchSource):
    """Last resort (Step 4): Selenium Google search for an official page.

    Only invoked when every other source comes up empty. Google actively
    bot-blocks automation, so this is genuinely best-effort and disabled unless
    Selenium + chromedriver are available. We map result domains to known legal
    providers and ignore anything we can't identify.
    """

    name = "Google"
    QUERIES = ('{t} watch online official', '{t} streaming')

    # Recognized legal provider domains -> (display name, is_free).
    KNOWN = {
        "netflix.com": ("Netflix", False),
        "primevideo.com": ("Prime Video", False),
        "amazon.com": ("Prime Video", False),
        "hulu.com": ("Hulu", False),
        "max.com": ("Max", False),
        "hbomax.com": ("Max", False),
        "disneyplus.com": ("Disney+", False),
        "appletv.apple.com": ("Apple TV", False),
        "tv.apple.com": ("Apple TV", False),
        "peacocktv.com": ("Peacock", False),
        "paramountplus.com": ("Paramount+", False),
        "tubitv.com": ("Tubi", True),
        "pluto.tv": ("Pluto TV", True),
        "crackle.com": ("Crackle", True),
        "plex.tv": ("Plex", True),
        "archive.org": ("Internet Archive", True),
        "youtube.com": ("YouTube", False),
    }

    def discover(self, ctx: MovieContext, country: str) -> List[ProviderResult]:
        if not selenium_available():
            logger.info("%s fallback skipped — Selenium unavailable.", self.name)
            return []
        from selenium.webdriver.common.by import By
        from home.services.selenium_driver import get_driver, wait_for_all

        found: Dict[str, ProviderResult] = {}
        try:
            with get_driver() as driver:
                for template in self.QUERIES:
                    q = template.format(t=ctx.bare_title)
                    driver.get(f"https://www.google.com/search?q={quote_plus(q)}")
                    if not handle_loading_screen(driver):
                        continue
                    anchors = wait_for_all(driver, By.CSS_SELECTOR, "a[href^='http']", timeout=8)
                    for a in anchors:
                        href = a.get_attribute("href") or ""
                        domain = _registered_domain(href)
                        match = self._match_domain(domain)
                        if match and match[0] not in found:
                            name, is_free = match
                            found[name] = ProviderResult(
                                provider_name=name, watch_url=href,
                                provider_logo=f"https://{domain}/favicon.ico",
                                is_free=is_free, country=country, source=self.name,
                            )
                    if found:
                        break
        except Exception as exc:
            logger.warning("%s fallback failed: %s", self.name, exc)
            return []
        return list(found.values())

    def _match_domain(self, domain: str):
        for known, meta in self.KNOWN.items():
            if domain == known or domain.endswith("." + known):
                return meta
        return None


# Priority-ordered registry. Free, API-backed sources first; fragile scrapers
# next; Google fallback handled separately (only when nothing else matched).
DEFAULT_SOURCES: List[WatchSource] = [
    TMDBWatchSource(),
    InternetArchiveSource(),
    TubiSource(),
    PlutoSource(),
    CrackleSource(),
    PlexSource(),
]
FALLBACK_SOURCE: WatchSource = GoogleFallbackSource()


class WatchProviderService:
    """Runs the discovery sources and returns de-duplicated provider hits."""

    def __init__(
        self,
        sources: Optional[List[WatchSource]] = None,
        fallback: Optional[WatchSource] = None,
        use_fallback: bool = True,
    ) -> None:
        self.sources = sources if sources is not None else DEFAULT_SOURCES
        self.fallback = fallback if fallback is not None else FALLBACK_SOURCE
        self.use_fallback = use_fallback

    def discover(self, movie, country: str = "US") -> List[ProviderResult]:
        """Discover providers for a Movie instance (or MovieContext)."""
        ctx = movie if isinstance(movie, MovieContext) else MovieContext(
            title=getattr(movie, "Title", ""),
            year=getattr(movie, "release_year", ""),
            external_id=getattr(movie, "external_id", ""),
            source=getattr(movie, "source", ""),
        )

        results: List[ProviderResult] = []
        seen = set()
        for source in self.sources:
            try:
                hits = source.discover(ctx, country)
            except Exception as exc:  # sources should be safe, but never trust
                logger.warning("Source %s raised: %s", source.name, exc)
                continue
            for hit in hits:
                key = (hit.provider_name.lower(), hit.watch_url)
                if key not in seen:
                    seen.add(key)
                    results.append(hit)

        # Step 4: only escalate to Google when nothing legal was found.
        if not results and self.use_fallback:
            try:
                results.extend(self.fallback.discover(ctx, country))
            except Exception as exc:
                logger.warning("Fallback source raised: %s", exc)

        logger.info("Discovered %d provider(s) for %r.", len(results), ctx.title)
        return results


# ---- helpers ---------------------------------------------------------------
def _as_result(item: Dict[str, Any], default_source: str) -> ProviderResult:
    return ProviderResult(
        provider_name=item.get("provider_name", ""),
        watch_url=item.get("watch_url", ""),
        provider_logo=item.get("provider_logo", ""),
        is_free=bool(item.get("is_free", False)),
        country=item.get("country", "US"),
        source=item.get("source") or default_source,
    )


def _registered_domain(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return ""
    return host[4:] if host.startswith("www.") else host
