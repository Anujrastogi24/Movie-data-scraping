"""Service layer for MovieCinema.

All scraping / external-API / matching logic lives here so views stay thin.
The single public entry point is::

    from home.services import MovieImportService
    result = MovieImportService.import_movie(movie_title)

Modules:
    selenium_driver       - shared headless-Chrome helper + explicit-wait utils
    tmdb_service          - scrape the public TMDB website for rich metadata
    metadata_service      - orchestrate metadata (TMDB scrape -> IMDb fallback)
    watch_provider_service- discover legal "where to watch" providers
    provider_service      - persist/refresh MovieProvider rows (7-day cycle)
    movie_import_service  - top-level orchestrator (DB check -> import -> providers)
"""

from home.services.movie_import_service import MovieImportService, ImportResult

__all__ = ["MovieImportService", "ImportResult"]
