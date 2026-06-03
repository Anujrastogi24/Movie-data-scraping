from django.contrib import admin

from .models import Movie, MovieProvider


class MovieProviderInline(admin.TabularInline):
    model = MovieProvider
    extra = 0
    fields = ("provider_name", "watch_url", "is_free", "country", "source", "last_checked")
    readonly_fields = ("last_checked",)


@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = ("Title", "genres", "release_year", "download_status")
    search_fields = ("Title", "description", "genres")
    list_filter = ("genres", "download_status")
    inlines = (MovieProviderInline,)
    fieldsets = (
        ("Movie details", {
            "fields": ("Title", "description", "image", "backdrop", "genres",
                       "release_year", "runtime", "rating", "language"),
        }),
        ("People", {
            "fields": ("cast", "director"),
        }),
        ("Video links", {
            "description": "Add one or more links separated by a new line or comma.",
            "fields": ("mLink", "embedLink", "tLink", "dLink"),
        }),
        ("Provenance", {
            "classes": ("collapse",),
            "fields": ("source", "external_id", "download_status"),
        }),
    )


@admin.register(MovieProvider)
class MovieProviderAdmin(admin.ModelAdmin):
    list_display = ("provider_name", "movie", "is_free", "country", "source", "last_checked")
    list_filter = ("is_free", "country", "source", "provider_name")
    search_fields = ("provider_name", "movie__Title")
    autocomplete_fields = ("movie",)
