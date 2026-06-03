"""External movie search scraping.

Tries BeautifulSoup4 + requests first (fast). If the HTML response is empty
or the page needs JavaScript, falls back to Selenium using the bundled
chromedriver.exe from the project root.
"""

import json
import os
import re
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

try:
    import requests
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    HAS_SELENIUM = True
except ImportError:
    HAS_SELENIUM = False


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROMEDRIVER_PATH = os.path.join(PROJECT_ROOT, "chromedriver.exe")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

REQUEST_TIMEOUT = 10


def _fetch_requests(url):
    if not HAS_BS4:
        return ""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200 and resp.text:
            return resp.text
    except Exception:
        return ""
    return ""


def _fetch_selenium(url):
    if not HAS_SELENIUM or not os.path.exists(CHROMEDRIVER_PATH):
        return ""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--log-level=3")
    options.add_argument(f"user-agent={HEADERS['User-Agent']}")
    driver = None
    try:
        service = Service(CHROMEDRIVER_PATH)
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(20)
        driver.get(url)
        return driver.page_source or ""
    except Exception:
        return ""
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


def _fetch(url, require_marker=None):
    """Fetch URL. Use requests+bs4 first; fall back to Selenium if needed.

    require_marker: optional substring expected in usable HTML. If absent,
    treat the response as empty and try the fallback.
    """
    html = _fetch_requests(url)
    if html and (require_marker is None or require_marker in html):
        return html
    return _fetch_selenium(url)


def _abs_url(base, href):
    if not href:
        return ""
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        parsed = urlparse(base)
        return f"{parsed.scheme}://{parsed.netloc}{href}"
    return href


def _clean_image(src):
    if not src:
        return ""
    # IMDb thumbnails come with a size mod like ._V1_QL75_UX140_.jpg — strip it
    return re.sub(r"\._V1_[^.]*(\.[a-zA-Z]+)$", r"._V1_\1", src)


IMDB_STOPWORDS = {"movie", "movies", "film", "the", "a", "an", "watch", "online",
                  "full", "hd", "trailer", "show", "tv", "series", "season"}


def _imdb_slug(query):
    """Normalize a free-text query to IMDb's expected slug.

    IMDb's suggestion API expects underscore-joined alphanumeric tokens
    (e.g. 'avengers_endgame'). Generic words like 'movie' kill matches,
    so drop them — but only if doing so still leaves a non-empty slug.
    """
    tokens = re.findall(r"[a-z0-9]+", query.lower())
    if not tokens:
        return ""
    filtered = [t for t in tokens if t not in IMDB_STOPWORDS]
    if not filtered:
        filtered = tokens
    return "_".join(filtered)


def search_imdb(query, limit=10):
    """Use IMDb's public suggestion JSON API — the find page is bot-blocked."""
    if not HAS_BS4:
        return []
    slug = _imdb_slug(query)
    if not slug:
        return []
    first = slug[0]
    url = f"https://v2.sg.media-imdb.com/suggestion/{first}/{quote_plus(slug)}.json"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception:
        return []

    results = []
    for item in (data.get("d") or [])[:limit]:
        imdb_id = item.get("id") or ""
        # Filter out persons (nm...) and other non-title IDs — we only want titles (tt...)
        if not imdb_id.startswith("tt"):
            continue
        kind = item.get("q") or ""
        if kind and kind not in {"feature", "TV series", "TV mini series",
                                  "TV movie", "TV mini-series", "short", "video",
                                  "musicVideo"}:
            continue
        title = item.get("l") or ""
        if not title:
            continue
        image_obj = item.get("i") or {}
        results.append({
            "title": title,
            "year": str(item.get("y") or ""),
            "image": _clean_image(image_obj.get("imageUrl", "")),
            "url": f"https://www.imdb.com/title/{imdb_id}/" if imdb_id else "",
            "source": "IMDb",
            "description": ", ".join(filter(None, [kind, item.get("s") or ""])),
        })
    return results


def search_duckduckgo(query, limit=8):
    """Generic movie search via DuckDuckGo HTML; useful as a broad fallback."""
    if not HAS_BS4:
        return []
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query + ' movie')}"
    html = _fetch(url, require_marker="result__a")
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    results = []
    for item in soup.select("div.result")[:limit]:
        a = item.select_one("a.result__a")
        snippet = item.select_one("a.result__snippet, div.result__snippet")
        if not a:
            continue
        title = a.get_text(strip=True)
        href = _unwrap_ddg(a.get("href", ""))
        text = snippet.get_text(" ", strip=True) if snippet else ""
        year_match = re.search(r"\b(19|20)\d{2}\b", text + " " + title)
        results.append({
            "title": title,
            "year": year_match.group(0) if year_match else "",
            "image": "",
            "url": href,
            "source": "Web",
            "description": text,
        })
    return results


def _unwrap_ddg(href):
    """DuckDuckGo HTML wraps results in /l/?uddg=<real-url>. Extract it."""
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if parsed.path == "/l/" or parsed.path.endswith("/l/"):
        uddg = parse_qs(parsed.query).get("uddg") or parse_qs(parsed.query).get("u")
        if uddg:
            return unquote(uddg[0])
    return href


GENRE_KEYWORDS = (
    "action", "adventure", "animation", "biography", "biographical", "comedy",
    "crime", "documentary", "drama", "epic", "family", "fantasy", "historical",
    "horror", "musical", "mystery", "noir", "romantic", "romance", "sci-fi",
    "science fiction", "slasher", "sport", "sports", "spy", "superhero",
    "supernatural", "thriller", "war", "western",
)


def _extract_genres(text):
    """Pull genre-ish keywords out of a Wikipedia-style summary's first sentence."""
    if not text:
        return ""
    first = text.split(".")[0].lower()
    found = []
    seen = set()
    for kw in GENRE_KEYWORDS:
        if kw in first and kw not in seen:
            seen.add(kw)
            found.append(kw.title())
    return ", ".join(found)


def _wiki_summary(title_guess):
    """Resolve a free-form title via Wikipedia opensearch, then fetch the
    REST summary. Returns (extract, image_url) or (None, None)."""
    if not HAS_BS4:
        return None, None
    try:
        os_resp = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={"action": "opensearch", "search": title_guess, "limit": 3,
                    "namespace": 0, "format": "json"},
            headers=HEADERS, timeout=REQUEST_TIMEOUT,
        )
        if os_resp.status_code != 200:
            return None, None
        os_data = os_resp.json()
        titles = os_data[1] if len(os_data) > 1 else []
        if not titles:
            return None, None
        page_title = titles[0]
        sum_resp = requests.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote_plus(page_title.replace(' ', '_'))}",
            headers=HEADERS, timeout=REQUEST_TIMEOUT,
        )
        if sum_resp.status_code != 200:
            return None, None
        data = sum_resp.json()
        extract = (data.get("extract") or "").strip()
        # Skip disambiguation pages
        if "may refer to" in extract.lower() or data.get("type") == "disambiguation":
            # Try the next candidate (often the disambiguated article)
            for alt in titles[1:]:
                alt_resp = requests.get(
                    f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote_plus(alt.replace(' ', '_'))}",
                    headers=HEADERS, timeout=REQUEST_TIMEOUT,
                )
                if alt_resp.status_code != 200:
                    continue
                alt_data = alt_resp.json()
                alt_extract = (alt_data.get("extract") or "").strip()
                if alt_extract and "may refer to" not in alt_extract.lower():
                    extract = alt_extract
                    data = alt_data
                    break
        image = ((data.get("originalimage") or {}).get("source")
                 or (data.get("thumbnail") or {}).get("source") or "")
        return extract or None, image or None
    except Exception:
        return None, None


def _youtube_trailer(query):
    """Scrape YouTube search results HTML for the first videoId match."""
    if not HAS_BS4:
        return ""
    url = f"https://www.youtube.com/results?search_query={quote_plus(query + ' official trailer')}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return ""
        match = re.search(r'"videoId":"([\w-]{11})"', resp.text)
        if match:
            return f"https://www.youtube.com/watch?v={match.group(1)}"
    except Exception:
        return ""
    return ""


def _pick_best_imdb(candidates, query):
    """Rank IMDb suggestion candidates to pick the most likely intended title.

    Prefer feature films, then proximity to any year mentioned in the query."""
    if not candidates:
        return None
    year_hint = None
    year_match = re.search(r"\b(19|20)\d{2}\b", query)
    if year_match:
        try:
            year_hint = int(year_match.group(0))
        except ValueError:
            year_hint = None

    q_lower = query.lower()
    wants_tv = any(k in q_lower for k in ("series", "season", "episode", "tv show"))

    def score(c):
        s = 0
        kind = (c.get("description") or "").lower()
        if wants_tv:
            if "tv" in kind or "series" in kind:
                s += 50
        else:
            if "feature" in kind:
                s += 50
            elif "tv movie" in kind:
                s += 30
            elif "musicvideo" in kind or "music video" in kind:
                s -= 30
            elif "short" in kind:
                s -= 20
        if year_hint and c.get("year"):
            try:
                diff = abs(int(c["year"]) - year_hint)
                s += max(0, 30 - diff * 3)
            except ValueError:
                pass
        # Title overlap with query words (sans year + stopwords)
        q_tokens = {t for t in re.findall(r"[a-z0-9]+", q_lower)
                    if t not in IMDB_STOPWORDS and not t.isdigit()}
        t_tokens = {t for t in re.findall(r"[a-z0-9]+", c.get("title", "").lower())}
        if q_tokens:
            s += len(q_tokens & t_tokens) * 5
        return s

    return max(candidates, key=score)


def _enrich_details(title, year="", image="", imdb_url=""):
    """Build a full Movie-creatable dict for a known title/year.

    Pulls a synopsis + poster from Wikipedia and a trailer from YouTube.
    Used both by `scrape_movie_details` (after ranking) and directly by the
    import endpoint when the user has already picked an exact suggestion."""
    title = (title or "").strip()
    year = (year or "").strip()
    display_title = f"{title} ({year})" if year else title

    # Description + better image from Wikipedia. Wikipedia's opensearch
    # rarely matches when a year is in the query, so try title-only first.
    extract, wiki_image = _wiki_summary(f"{title} film")
    if not extract:
        extract, alt_image = _wiki_summary(title)
        wiki_image = wiki_image or alt_image

    description = extract or (
        f"{title} is a {year} title. Details were scraped automatically; "
        "edit this entry to add a full synopsis."
    )

    image = image or wiki_image or ""
    genres = _extract_genres(extract or "")

    # Trailer from YouTube
    trailer_url = _youtube_trailer(f"{title} {year}".strip())

    return {
        "Title": display_title,
        "description": description[:1000],
        "image": image,
        "genres": genres,
        "mLink": "",
        "embedLink": "",
        "tLink": trailer_url,
        "dLink": "",
        "_imdb_url": imdb_url or "",
    }


def suggest_titles(query, limit=8):
    """Fast typeahead: return lightweight title suggestions for the search bar.

    Uses IMDb's suggestion JSON API only (no Selenium / slow scraping) so it
    stays responsive while the user types. Each item is
    {title, year, image, url, source}."""
    query = (query or "").strip()
    if not query:
        return []
    return search_imdb(query, limit=limit)


def scrape_movie_details(query):
    """Fetch rich movie metadata for the best match to `query`.

    Returns a dict compatible with Movie.objects.create(...) kwargs, or None
    if no usable match was found. Year tokens in the query are used for
    ranking but stripped from the IMDb lookup (their suggestion API rarely
    indexes by year)."""
    query = (query or "").strip()
    if not query:
        return None

    title_only = re.sub(r"\b(19|20)\d{2}\b", "", query).strip() or query
    candidates = search_imdb(title_only, limit=10)
    if not candidates:
        candidates = search_imdb(query, limit=10)
    if not candidates:
        return None

    top = _pick_best_imdb(candidates, query)
    if not top:
        return None

    return _enrich_details(
        top["title"],
        top.get("year") or "",
        image=top.get("image") or "",
        imdb_url=top.get("url", ""),
    )


def search_external(query):
    """Aggregate scraped movie results for a search query.

    Returns a list of dicts: {title, year, image, url, source, description}.
    """
    query = (query or "").strip()
    if not query:
        return []

    aggregated = []
    seen = set()

    def add(items):
        for item in items:
            key = (item.get("title", "").lower(), item.get("url", ""))
            if key in seen:
                continue
            seen.add(key)
            aggregated.append(item)

    try:
        add(search_imdb(query))
    except Exception:
        pass

    try:
        add(search_duckduckgo(query))
    except Exception:
        pass

    return aggregated
