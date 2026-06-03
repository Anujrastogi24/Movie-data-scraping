"""Scrape the public TMDB *website* for rich movie metadata (no API key).

Per the project decision, we do not use the TMDB REST API; we read the same
public web pages a user would (themoviedb.org). Strategy per request:

1. Try ``requests`` + BeautifulSoup first — TMDB pages are largely
   server-rendered, so this is fast and avoids spinning up a browser.
2. Fall back to Selenium (shared :mod:`home.services.selenium_driver`) only when
   the static HTML is missing the bits we need (JS-gated content, challenge).

Everything is best-effort and defensive: selectors are tried in order and any
field we can't find is simply returned blank. TMDB markup can change, so parse
failures are logged, never raised.

Public surface:
    TMDBService().search(title) -> list[TMDBResult]
    TMDBService().fetch_details(result_or_path) -> dict   # Movie-shaped kwargs
    TMDBService().fetch_watch_providers(result_or_path, country) -> list[dict]
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urljoin

from home.services.selenium_driver import (
    handle_loading_screen,
    retry,
    selenium_available,
)

logger = logging.getLogger(__name__)

try:
    import requests
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except Exception:  # pragma: no cover
    HAS_BS4 = False

BASE = "https://www.themoviedb.org"
IMG = "https://image.tmdb.org/t/p"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
TIMEOUT = 12


@dataclass
class TMDBResult:
    title: str
    year: str = ""
    path: str = ""           # e.g. "/movie/27205-inception"
    poster: str = ""
    overview: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


class TMDBService:
    """Website scraper for TMDB metadata + watch providers."""

    def __init__(self) -> None:
        self._session = requests.Session() if HAS_BS4 else None
        if self._session is not None:
            self._session.headers.update(HEADERS)

    # -- low-level fetch ------------------------------------------------------
    @retry(times=3, exceptions=(Exception,), label="tmdb.fetch")
    def _fetch_requests(self, url: str) -> str:
        if self._session is None:
            return ""
        resp = self._session.get(url, timeout=TIMEOUT)
        if resp.status_code == 200 and resp.text:
            return resp.text
        logger.debug("TMDB requests fetch %s -> HTTP %s", url, resp.status_code)
        return ""

    def _fetch_selenium(self, url: str, wait_css: str = "body") -> str:
        if not selenium_available():
            return ""
        from selenium.webdriver.common.by import By  # local import
        from home.services.selenium_driver import get_driver, wait_for
        try:
            with get_driver() as driver:
                driver.get(url)
                handle_loading_screen(driver)
                wait_for(driver, By.CSS_SELECTOR, wait_css)
                return driver.page_source or ""
        except Exception as exc:
            logger.warning("TMDB selenium fetch failed for %s: %s", url, exc)
            return ""

    def _fetch(self, url: str, marker: Optional[str] = None, wait_css: str = "body") -> str:
        """requests-first, selenium-fallback. ``marker`` validates static HTML."""
        try:
            html = self._fetch_requests(url)
        except Exception:
            html = ""
        if html and (marker is None or marker in html):
            return html
        return self._fetch_selenium(url, wait_css=wait_css)

    # -- search ---------------------------------------------------------------
    def search(self, title: str, limit: int = 10) -> List[TMDBResult]:
        title = (title or "").strip()
        if not HAS_BS4 or not title:
            return []
        url = f"{BASE}/search/movie?query={quote_plus(title)}"
        html = self._fetch(url, marker="card", wait_css="div.search_results")
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        results: List[TMDBResult] = []
        # TMDB renders each result as a `.card.style_1` with an <h2><a> title.
        for card in soup.select("div.card.style_1, div.card.v4.tight")[:limit]:
            link = card.select_one("a.image, h2 a, a.result")
            if not link or not link.get("href"):
                continue
            href = link.get("href", "")
            if "/movie/" not in href:
                continue
            title_text = link.get("title") or link.get_text(strip=True)
            img = card.select_one("img.poster, img")
            poster = img.get("src") or img.get("data-src") if img else ""
            release = card.select_one(".release_date, .content p")
            year = ""
            if release:
                ymatch = re.search(r"(19|20)\d{2}", release.get_text(" ", strip=True))
                year = ymatch.group(0) if ymatch else ""
            results.append(TMDBResult(
                title=(title_text or "").strip(),
                year=year,
                path=href.split("?")[0],
                poster=_abs_img(poster or ""),
            ))
        return results

    # -- details --------------------------------------------------------------
    def fetch_details(self, ref: Any) -> Optional[Dict[str, Any]]:
        path = ref.path if isinstance(ref, TMDBResult) else str(ref or "")
        if not path:
            return None
        url = urljoin(BASE, path)
        html = self._fetch(url, marker="og:title", wait_css="section.header")
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")
        title = _meta(soup, "og:title") or _text(soup.select_one("h2 a"))
        title = re.sub(r"\s*\(\d{4}\)\s*$", "", title).strip()
        overview = _meta(soup, "og:description") or _text(soup.select_one("div.overview p"))

        # Release year + runtime live in the facts line.
        facts = _text(soup.select_one("span.release, div.facts"))
        year = ""
        ymatch = re.search(r"(19|20)\d{2}", facts or _text(soup.select_one("span.tag.release_date")))
        if ymatch:
            year = ymatch.group(0)
        runtime = ""
        rmatch = re.search(r"(\d+h\s*\d*m|\d+\s*min|\d+m)", facts)
        if rmatch:
            runtime = _normalize_runtime(rmatch.group(0))

        genres = ", ".join(
            _text(a) for a in soup.select("span.genres a") if _text(a)
        )
        rating = _rating(soup)
        poster = _abs_img(_attr(soup.select_one("img.poster, img.backdrop"), "src"))
        backdrop = _backdrop(soup)
        cast = _cast(soup)
        director = _director(soup)
        trailer = _trailer(soup)

        return {
            "Title": _display_title(title, year),
            "description": (overview or "")[:1000],
            "image": poster,
            "backdrop": backdrop,
            "genres": genres,
            "release_year": year,
            "runtime": runtime,
            "rating": rating,
            "cast": cast,
            "director": director,
            "tLink": trailer,
            "source": "TMDB",
            "external_id": _movie_id(path),
            "_tmdb_path": path,
        }

    # -- watch providers ------------------------------------------------------
    def fetch_watch_providers(self, ref: Any, country: str = "US") -> List[Dict[str, Any]]:
        """Scrape /movie/<id>/watch for JustWatch-backed legal providers."""
        path = ref.path if isinstance(ref, TMDBResult) else str(ref or "")
        if not HAS_BS4 or not path:
            return []
        watch_path = f"{path.rstrip('/')}/watch"
        url = urljoin(BASE, f"{watch_path}?locale={country}")
        html = self._fetch(url, marker="ott_provider", wait_css="div.ott_provider")
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        providers: List[Dict[str, Any]] = []
        seen = set()
        # Sections are grouped by offer type: flatrate/free/ads/rent/buy.
        for group in soup.select("div.ott_provider"):
            heading = _text(group.select_one("h3")).lower()
            is_free = any(k in heading for k in ("free", "ads"))
            for link in group.select("ul li a"):
                name = (link.get("title") or _attr(link.select_one("img"), "alt")
                        or "").strip()
                if not name or name.lower() in seen:
                    continue
                logo = _abs_img(_attr(link.select_one("img"), "src"))
                watch_url = urljoin(BASE, link.get("href", "")) or url
                seen.add(name.lower())
                providers.append({
                    "provider_name": name,
                    "provider_logo": logo,
                    "watch_url": watch_url,
                    "is_free": is_free,
                    "country": country,
                    "source": "TMDB/JustWatch",
                })
        return providers


# ---- parsing helpers -------------------------------------------------------
def _display_title(title: str, year: str = "") -> str:
    title = (title or "").strip()
    return f"{title} ({year})" if year and title else title


def _abs_img(src: str) -> str:
    if not src:
        return ""
    if src.startswith("//"):
        return "https:" + src
    if src.startswith("/t/p") or src.startswith("/p/"):
        return urljoin(IMG, src)
    return src


def _text(node) -> str:
    return node.get_text(" ", strip=True) if node else ""


def _attr(node, name: str) -> str:
    return (node.get(name, "") if node else "") or ""


def _meta(soup, prop: str) -> str:
    tag = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
    return (tag.get("content", "").strip() if tag else "")


def _movie_id(path: str) -> str:
    m = re.search(r"/movie/(\d+)", path or "")
    return m.group(1) if m else ""


def _normalize_runtime(raw: str) -> str:
    raw = raw.strip()
    m = re.match(r"(\d+)h\s*(\d+)?m?", raw)
    if m:
        hours = int(m.group(1))
        mins = int(m.group(2) or 0)
        return f"{hours * 60 + mins} min"
    m = re.match(r"(\d+)\s*m", raw)
    if m:
        return f"{int(m.group(1))} min"
    return raw


def _rating(soup) -> str:
    node = soup.select_one("div.user_score_chart")
    if node and node.get("data-percent"):
        try:
            return f"{round(float(node['data-percent']) / 10, 1)}"
        except ValueError:
            pass
    txt = _meta(soup, "og:title")
    return ""


def _backdrop(soup) -> str:
    node = soup.select_one("div.backdrop, [style*='backdrop']")
    style = _attr(node, "style")
    m = re.search(r"url\(([^)]+)\)", style)
    if m:
        return _abs_img(m.group(1).strip("'\""))
    return ""


def _cast(soup, limit: int = 12) -> str:
    names = []
    for card in soup.select("ol.people.scroller li.card, ol.people li"):
        name = _text(card.select_one("p a, a"))
        if name and name not in names:
            names.append(name)
        if len(names) >= limit:
            break
    return ", ".join(names)


def _director(soup) -> str:
    for profile in soup.select("ol.people.no_image li.profile, div.header_info li.profile"):
        role = _text(profile.select_one("p.character, span.character")).lower()
        if "director" in role:
            name = _text(profile.select_one("a, p.name a"))
            if name:
                return name
    return ""


def _trailer(soup) -> str:
    node = soup.select_one("a.play_trailer[data-id], a[href*='youtube'], a[data-site='YouTube']")
    if not node:
        return ""
    vid = node.get("data-id")
    if vid:
        return f"https://www.youtube.com/watch?v={vid}"
    href = node.get("href", "")
    return href if "youtube" in href else ""
