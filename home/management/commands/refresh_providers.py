"""Refresh stale watch-provider links (Step 7).

Re-discovers "where to watch" providers for any Movie whose provider rows are
missing or older than the 7-day window (``MovieProvider.REFRESH_AFTER``). Intended
to run on a schedule (cron / Task Scheduler)::

    python manage.py refresh_providers
    python manage.py refresh_providers --country US --limit 50

It delegates to :class:`home.services.provider_service.ProviderService`, so the
discovery/upsert/dead-link-pruning logic lives in one place.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from home.services.provider_service import ProviderService


class Command(BaseCommand):
    help = "Refresh watch providers for movies with stale (>7 day) or missing data."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--country", default="US",
            help="Region code to refresh providers for (default: US).",
        )
        parser.add_argument(
            "--limit", type=int, default=None,
            help="Max number of movies to refresh in this run.",
        )

    def handle(self, *args, **options) -> None:
        country = options["country"]
        limit = options["limit"]
        self.stdout.write(f"Refreshing stale providers (country={country}, limit={limit})...")
        count = ProviderService().refresh_stale(country=country, limit=limit)
        self.stdout.write(self.style.SUCCESS(f"Refreshed providers for {count} movie(s)."))
