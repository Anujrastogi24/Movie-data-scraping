# MovieCinema

A Django-based movie streaming and discovery web app. Browse a library of movies
and TV shows, search and filter by genre / year / type, watch embedded trailers
and players, and import new titles on the fly by scraping their details (poster,
description, genres, trailer) from the web.

## Features

- **Movie & TV library** — browse a catalog backed by SQLite, with a featured
  title, poster cards, and a detail page per movie.
- **Search & filters** — full-text search across title/description/genres, plus
  filtering by genre, year, and content type (movie vs. TV).
- **Live typeahead** — as you type in the search bar, importable suggestions
  (title + year + poster) are fetched from IMDb (`/api/suggest/`).
- **One-click import** — pick a suggestion and the app imports full details
  (title, poster, backdrop, genres, runtime, year, cast, director, rating,
  trailer) and opens its detail page (`/movies/import/`).
- **Where to Watch** — each movie shows legal streaming providers (TMDB Watch
  Providers, Internet Archive, Tubi, Pluto TV, Crackle, Plex) with logo,
  free/paid badge, and a watch link. Refreshed every 7 days. No piracy sources.
- **Embedded playback** — detail pages surface trailers, embedded players, movie
  links, and direct downloads, with YouTube trailers preferred as the default
  player. Missing trailers are auto-fetched from YouTube by title.
- **JSON API** — read movie data programmatically (`/api/movies/`,
  `/api/movies/<id>/`).
- **Auth-protected authoring** — log in to manually add movies and preview the
  library; full CRUD via the Django admin.

## Tech Stack

- **Backend:** Django 4.1, Python
- **Database:** SQLite (`db.sqlite3`)
- **Scraping:** BeautifulSoup4 + requests, with a Selenium + `chromedriver.exe`
  fallback for JavaScript-rendered pages
- **Frontend:** Django templates, Swiper.js, dash.js, vanilla JS

## Project Structure

```
MovieCinema/
├── manage.py              # Django entry point
├── requirement.txt        # Python dependencies
├── chromedriver.exe       # Selenium driver (scraping fallback)
├── db.sqlite3             # SQLite database
├── MovieCinema/           # Project settings package
│   ├── settings.py
│   ├── urls.py            # admin/ + includes home.urls
│   └── wsgi.py / asgi.py
├── home/                  # Main app
│   ├── models.py          # Movie + MovieProvider models
│   ├── views.py           # pages, search, import, JSON API
│   ├── urls.py            # URL routes
│   ├── admin.py           # Movie / MovieProvider admin
│   ├── scraping.py        # legacy IMDb / Wikipedia / YouTube helpers
│   ├── movie_matcher.py   # title/year/language match scoring
│   ├── metadata_provider.py
│   ├── services/          # import + watch-provider service layer
│   │   ├── movie_import_service.py    # MovieImportService.import_movie(title)
│   │   ├── metadata_service.py        # TMDB-scrape -> IMDb/Wikipedia fallback
│   │   ├── tmdb_service.py            # scrape public TMDB website (no API key)
│   │   ├── watch_provider_service.py  # legal "where to watch" discovery
│   │   ├── provider_service.py        # persist + 7-day refresh of providers
│   │   └── selenium_driver.py         # shared headless-Chrome + explicit waits
│   ├── management/commands/refresh_providers.py  # cron: refresh stale providers
│   └── templates/         # index, movie, login, user, preview, search
└── static/                # css / js / img
```

## Movie Import & "Where to Watch"

The import system is fully service-based — views only call one method:

```python
from home.services import MovieImportService
result = MovieImportService.import_movie("Inception")   # find-or-import + providers
```

Flow: **local DB check → metadata import → legal watch-provider discovery.**

- **Metadata** is gathered by scraping the public **TMDB website** (no API key),
  falling back to the existing **IMDb suggestion + Wikipedia + YouTube** path so
  imports never hard-fail. Captures title, description, poster, backdrop,
  genres, runtime, release year, cast, director, rating, and trailer.
- **Watch providers** (the `MovieProvider` model) are discovered from **legal**
  sources only, in priority order: TMDB Watch Providers (JustWatch-backed),
  Internet Archive, Tubi, Pluto TV, Crackle, Plex, then a best-effort Google
  fallback. **No piracy sources.** Each provider stores name, logo, watch URL,
  free/paid flag, and region, and is shown in a "Where to Watch" section on the
  detail page.
- Provider links auto-refresh every **7 days**; run on a schedule with
  `python manage.py refresh_providers`.

> **Note on the bundled `chromedriver.exe`:** it is pinned to Chrome 114. On
> newer Chrome the Selenium scrapers fall back to **Selenium Manager**, which
> auto-downloads a matching driver (needs one-time internet). The Tubi/Pluto/
> Crackle/Plex/Google scrapers are best-effort and may need selector
> maintenance; the API-backed sources (Internet Archive, IMDb, Wikipedia) are
> the reliable core.

## Getting Started

### Prerequisites

- Python 3.10+
- Google Chrome (only needed for the Selenium scraping fallback; the bundled
  `chromedriver.exe` is for Windows)

### Setup

```bash
# 1. (Optional) create and activate a virtual environment
python -m venv env
env\Scripts\activate        # Windows
# source env/bin/activate   # macOS / Linux

# 2. Install dependencies
pip install -r requirement.txt

# 3. Apply database migrations
python manage.py migrate

# 4. Create an admin user (for the admin panel and add/preview pages)
python manage.py createsuperuser

# 5. Run the development server
python manage.py runserver
```

Then open http://127.0.0.1:8000/ in your browser. The admin panel is at
http://127.0.0.1:8000/admin/.

## Key URLs

| Path                       | Description                              |
| -------------------------- | ---------------------------------------- |
| `/`                        | Home — library, search, and filters      |
| `/movies/<id>/`            | Movie detail page with players           |
| `/movies/import/`          | Import a scraped movie by title          |
| `/api/suggest/?q=`         | Typeahead suggestions (JSON)             |
| `/api/movies/`             | List movies, honoring search/filters     |
| `/api/movies/<id>/`        | Single movie payload (JSON)              |
| `/login.html`              | Log in                                   |
| `/user.html`               | Authenticated add-movie page             |
| `/preview.html`            | Library preview (auth required)          |
| `/admin/`                  | Django admin                             |

## Data Models

- **`Movie`** — `Title`, `description`, poster `image`, `backdrop`, `genres`,
  `release_year`, `runtime`, `rating`, `language`, `cast`, `director`, plus four
  kinds of newline/comma-separated video links: `mLink` (movie), `embedLink`
  (embedded player), `tLink` (trailer), `dLink` (download).
- **`MovieProvider`** — one legal "where to watch" entry per movie: `movie`,
  `provider_name`, `provider_logo`, `watch_url`, `is_free`, `country`,
  `last_checked` (drives the 7-day refresh).

## Optional Configuration

All optional — the app runs with zero setup. Set via environment variables:

| Env var | Effect |
| ------- | ------ |
| `REDIS_URL` | e.g. `redis://127.0.0.1:6379/1` — use Redis for caching; otherwise an in-process local-memory cache is used |
| `TMDB_API_KEY` | enables the optional TMDB REST provider in `home/metadata_provider.py` (the service layer scrapes the TMDB website by default and needs no key) |

Schedule provider refresh (cron / Windows Task Scheduler):

```bash
python manage.py refresh_providers            # all stale (>7 days) movies
python manage.py refresh_providers --limit 50 # cap work per run
```

## Notes

- `DEBUG = True` and a development `SECRET_KEY` are set in `settings.py`. These
  are **not suitable for production** — set `DEBUG = False`, supply a secret key
  from the environment, and restrict `ALLOWED_HOSTS` before deploying.
- Watch-provider discovery uses **legal sources only** — no piracy sites. Some
  free-streaming scrapers are best-effort and may need maintenance.
- Scraping targets third-party sites and may break if those sites change.
