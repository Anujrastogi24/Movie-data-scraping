from datetime import timedelta

from django.db import models
from django.utils import timezone


class Movie(models.Model):
    """A movie/TV entry.

    The link fields (``mLink``/``embedLink``/``tLink``/``dLink``) store one or
    more URLs separated by a newline or comma. ``mLink`` is the canonical
    "movie_links" store and ``dLink`` the "download_links" store; the service
    layer reads/writes them through the :attr:`movie_links` / :attr:`download_links`
    helpers so callers never have to know the legacy field names.
    """

    class DownloadStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        AVAILABLE = "available", "Available"
        FAILED = "failed", "Failed"

    Title = models.CharField(max_length=100)
    description = models.TextField(max_length=1000)
    image = models.TextField(max_length=500, blank=True)
    genres = models.CharField(max_length=255, blank=True)
    mLink = models.TextField(max_length=1200, blank=True)
    embedLink = models.TextField(max_length=1200, blank=True)
    tLink = models.TextField(max_length=1200, blank=True)
    dLink = models.TextField(max_length=1200, blank=True)

    # Structured metadata populated by the import service.
    release_year = models.CharField(max_length=8, blank=True)
    language = models.CharField(max_length=80, blank=True)
    quality = models.CharField(max_length=120, blank=True)
    file_size = models.CharField(max_length=60, blank=True)

    # Rich detail-page metadata (Step 2).
    backdrop = models.TextField(max_length=500, blank=True)
    runtime = models.CharField(max_length=40, blank=True)   # e.g. "148 min"
    rating = models.CharField(max_length=16, blank=True)    # e.g. "8.8"
    cast = models.TextField(max_length=1000, blank=True)    # comma/newline separated
    director = models.CharField(max_length=255, blank=True)
    download_status = models.CharField(
        max_length=20,
        choices=DownloadStatus.choices,
        default=DownloadStatus.PENDING,
    )

    # Provenance — used to dedupe/cache imported records.
    source = models.CharField(max_length=40, blank=True)
    external_id = models.CharField(max_length=64, blank=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    def __str__(self) -> str:
        return self.Title

    # --- Convenience accessors that name the legacy link fields clearly ------
    @property
    def movie_links(self) -> str:
        return self.mLink

    @movie_links.setter
    def movie_links(self, value: str) -> None:
        self.mLink = value or ""

    @property
    def download_links(self) -> str:
        return self.dLink

    @download_links.setter
    def download_links(self, value: str) -> None:
        self.dLink = value or ""


class MovieProvider(models.Model):
    """A legal place to watch a given Movie (Step 6).

    One row per (movie, provider, country). Populated by
    ``home.services.watch_provider_service`` and refreshed on a 7-day cycle by
    the ``refresh_providers`` management command.
    """

    movie = models.ForeignKey(
        Movie, on_delete=models.CASCADE, related_name="providers",
    )
    provider_name = models.CharField(max_length=120)
    provider_logo = models.TextField(max_length=500, blank=True)
    watch_url = models.TextField(max_length=1000)
    is_free = models.BooleanField(default=False)
    country = models.CharField(max_length=8, default="US")
    last_checked = models.DateTimeField(default=timezone.now)
    source = models.CharField(max_length=40, blank=True)  # which discovery source found it

    class Meta:
        # A provider/url pair is unique per movie+country so refreshes upsert.
        unique_together = ("movie", "provider_name", "country", "watch_url")
        ordering = ("-is_free", "provider_name")

    def __str__(self) -> str:
        tier = "Free" if self.is_free else "Paid"
        return f"{self.movie.Title} — {self.provider_name} ({tier})"

    # Default freshness window for provider links (Step 7).
    REFRESH_AFTER = timedelta(days=7)

    def is_stale(self, now=None) -> bool:
        """True if this link hasn't been re-checked within the refresh window."""
        now = now or timezone.now()
        return (now - self.last_checked) > self.REFRESH_AFTER
