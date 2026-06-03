"""Backward-compatibility shim.

The import orchestration moved into the ``home.services`` package (see
``home/services/movie_import_service.py``). This module re-exports the public
names so any existing imports — ``from home.scraping_service import
MovieImportService`` — keep working.

New code should import from ``home.services`` directly.
"""

from home.services.movie_import_service import ImportResult, MovieImportService

__all__ = ["ImportResult", "MovieImportService"]
