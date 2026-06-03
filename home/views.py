import ast
import re
from urllib.parse import parse_qs, urlencode, urlparse

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from home.models import Movie
from home.scraping import suggest_titles, _youtube_trailer
from home.services import MovieImportService
from home.services.provider_service import ProviderService


def _split_values(value):
    if not value:
        return []

    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]

    text = str(value).strip()
    if not text:
        return []

    try:
        parsed = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        parsed = None

    if isinstance(parsed, (list, tuple, set)):
        return [str(item).strip() for item in parsed if str(item).strip()]

    return [item.strip() for item in re.split(r"[\n,]+", text) if item.strip()]


def _embed_src(value):
    match = re.search(r"""src=["']([^"']+)["']""", value, re.IGNORECASE)
    return match.group(1).strip() if match else value


def _youtube_embed_url(url):
    parsed = urlparse(url)
    host = parsed.netloc.lower().replace("www.", "")

    if host in {"youtu.be"}:
        video_id = parsed.path.strip("/").split("/", 1)[0]
    elif host in {"youtube.com", "m.youtube.com"} and parsed.path == "/watch":
        video_id = parse_qs(parsed.query).get("v", [""])[0]
    elif host in {"youtube.com", "m.youtube.com"} and parsed.path.startswith("/embed/"):
        return url
    else:
        return ""

    return f"https://www.youtube.com/embed/{video_id}" if video_id else ""


def _player_url(value):
    url = _embed_src(value)
    return _youtube_embed_url(url) or url


def _movie_payload(movie):
    return {
        "id": movie.id,
        "title": movie.Title,
        "description": movie.description,
        "image": movie.image,
        "genres": _split_values(movie.genres),
        "movie_links": _split_values(movie.mLink),
        "embedded_links": _split_values(movie.embedLink),
        "trailer_links": _split_values(movie.tLink),
        "download_links": _split_values(movie.dLink),
        "detail_url": f"/movies/{movie.id}/",
    }


def _is_direct_video_url(url):
    clean_url = url.lower().split("?", 1)[0]
    return clean_url.endswith((".mp4", ".webm", ".ogg", ".m3u8"))


def _player_type(url):
    return "video" if _is_direct_video_url(url) else "iframe"


def _is_youtube(url):
    return "youtube.com/embed" in url or "youtube.com/watch" in url or "youtu.be/" in url


def _player_links(movie):
    links = []
    seen = set()
    for url in _split_values(movie.embedLink):
        url = _player_url(url)
        if url not in seen:
            links.append({"url": url, "kind": "Embedded Player", "player": "iframe"})
            seen.add(url)
    for url in _split_values(movie.mLink):
        url = _player_url(url)
        if url not in seen:
            links.append({"url": url, "kind": "Play Movie", "player": _player_type(url)})
            seen.add(url)
    for url in _split_values(movie.tLink):
        url = _player_url(url)
        if url not in seen:
            links.append({"url": url, "kind": "Trailer", "player": _player_type(url)})
            seen.add(url)
    for url in _split_values(movie.dLink):
        if url not in seen and _is_direct_video_url(url):
            links.append({"url": url, "kind": "Play Download", "player": "video"})
            seen.add(url)

    # Surface a working YouTube trailer as the default player. Many legacy
    # entries store dead .mp4 links; a YouTube embed is the reliable fallback.
    # Stable sort keeps every other link's relative order intact.
    links.sort(key=lambda link: 0 if _is_youtube(link["url"]) else 1)

    # Number labels per kind in final display order (e.g. "Trailer", "Trailer 2").
    counters = {}
    for link in links:
        counters[link["kind"]] = counters.get(link["kind"], 0) + 1
        n = counters[link["kind"]]
        link["label"] = link["kind"] if n == 1 else f"{link['kind']} {n}"
    return links


def _genre_list():
    genres = set()
    for movie in Movie.objects.exclude(genres="").only("genres"):
        genres.update(_split_values(movie.genres))
    return sorted(genres, key=str.lower)


def _year_list():
    years = set()
    for movie in Movie.objects.only("Title", "description"):
        text = f"{movie.Title} {movie.description}"
        years.update(re.findall(r"\b(?:19|20)\d{2}\b", text))
    return sorted(years, reverse=True)


def _filtered_movies(request):
    movies = Movie.objects.all().order_by("-id")
    query = request.GET.get("q") or request.POST.get("Title") or ""
    genre = request.GET.get("genre") or ""
    year = request.GET.get("year") or ""
    content_type = request.GET.get("type") or ""

    if query:
        movies = movies.filter(
            Q(Title__icontains=query)
            | Q(description__icontains=query)
            | Q(genres__icontains=query)
        )

    if genre:
        movies = movies.filter(genres__icontains=genre)

    if year:
        movies = movies.filter(Q(Title__icontains=year) | Q(description__icontains=year))

    if content_type == "tv":
        movies = movies.filter(Q(Title__icontains="season") | Q(Title__icontains="episode") | Q(genres__icontains="tv") | Q(genres__icontains="web series"))
    elif content_type == "movie":
        movies = movies.exclude(Q(Title__icontains="season") | Q(Title__icontains="episode") | Q(genres__icontains="tv") | Q(genres__icontains="web series"))

    return movies, query, genre, year, content_type


def _suggestion_cards(query, limit=10):
    """Build importable suggestion cards (title + year + poster) from IMDb for
    `query`. Shared by the search page ("top matches") and the typeahead API.
    Each card carries the data needed to import the movie on click."""
    cards = []
    q = (query or "").strip()
    if len(q) < 2:
        return cards
    try:
        items = suggest_titles(q, limit=limit)
    except Exception:
        return cards
    for item in items:
        title = (item.get("title") or "").strip()
        if not title:
            continue
        year = str(item.get("year") or "").strip()
        cards.append({
            "title": title,
            "year": year,
            "label": f"{title} ({year})" if year else title,
            "image": item.get("image") or "",
            "imdb_url": item.get("url") or "",
            "source": item.get("source") or "IMDb",
        })
    return cards


def _recommended_movies(result_movies, limit=8):
    """Recommend movies already in the DB for the search results page. Prefers
    titles that share genres with the current results; falls back to the newest
    movies. Excludes the movies already shown in the results section."""
    exclude_ids = list(result_movies.values_list("id", flat=True)[:60])
    base = Movie.objects.exclude(id__in=exclude_ids)

    genres = set()
    for movie in result_movies[:5]:
        genres.update(_split_values(movie.genres))

    recommended = []
    if genres:
        genre_query = Q()
        for genre in list(genres)[:3]:
            genre_query |= Q(genres__icontains=genre)
        recommended = list(base.filter(genre_query).order_by("-id")[:limit])
    if not recommended:
        recommended = list(base.order_by("-id")[:limit])
    return recommended


def index(request):
    movies, query, selected_genre, selected_year, selected_type = _filtered_movies(request)

    # On a search: 1) DB matches above, 2) top-10 importable web matches,
    # 3) recommended movies already in the library.
    similar_results = _suggestion_cards(query, limit=10) if query else []
    recommended_movies = _recommended_movies(movies) if query else []

    return render(request, "index.html", {
        "movies": movies,
        "featured_movie": movies.first(),
        "genres": _genre_list(),
        "years": _year_list(),
        "query": query,
        "selected_genre": selected_genre,
        "selected_year": selected_year,
        "selected_type": selected_type,
        "similar_results": similar_results,
        "recommended_movies": recommended_movies,
    })


def about(request):
    return JsonResponse({"message": "MovieCinema"})


def services(request):
    return JsonResponse({"message": "Movie browsing, genre filtering, and embedded playback"})


@login_required(login_url="/login.html")
def adddata(request):
    if request.method != "POST":
        return redirect("user")

    Movie.objects.create(
        Title=request.POST.get("TITLE", "").strip(),
        description=request.POST.get("DESCRIPTION", "").strip(),
        image=request.POST.get("IMAGE", "").strip(),
        genres=request.POST.get("GENRES", "").strip(),
        mLink=request.POST.get("MLINK", "").strip(),
        embedLink=request.POST.get("EMBEDLINK", "").strip(),
        tLink=request.POST.get("TLINK", "").strip(),
        dLink=request.POST.get("DLINK", "").strip(),
    )
    return redirect("previewdata")


@login_required(login_url="/login.html")
def previewdata(request):
    movies = Movie.objects.all().order_by("-id")
    return render(request, "preview.html", {"movies": movies})


def loginUser(request):
    error = ""
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect("user")
        error = "Invalid username or password."

    return render(request, "login.html", {"error": error})


def logoutUser(request):
    logout(request)
    return redirect("/login.html")


@login_required(login_url="/login.html")
def userpage(request):
    return render(request, "user.html")


def searchdata(request):
    query = request.POST.get("Title", "").strip()
    if query:
        return redirect(f"/?{urlencode({'q': query})}")
    return redirect("home")


def suggest_api(request):
    """Live typeahead for the search bar. Returns JSON movie suggestions
    (title + year + poster) for the partial query the user has typed.

    Each suggestion carries the info needed to import it on click."""
    query = (request.GET.get("q") or "").strip()
    return JsonResponse({
        "query": query,
        "suggestions": _suggestion_cards(query, limit=10),
    })


def import_movie(request):
    """Import a movie the user picked from the suggestions.

    Thin wrapper over the service layer: all the cache-lookup / external
    metadata / matching / persistence logic lives in
    ``MovieImportService.import_movie``. On success we redirect to the movie's
    detail page (existing UX); on failure we return the documented JSON
    contract."""
    title = (request.GET.get("title") or request.POST.get("title") or "").strip()
    year = (request.GET.get("year") or request.POST.get("year") or "").strip()

    if not title:
        return redirect("home")

    movie_name = f"{title} ({year})" if year else title
    result = MovieImportService.import_movie(movie_name)

    if result.ok:
        return redirect("movie_detail", result.movie_id)

    if result.status == "not_found":
        return JsonResponse(
            {"status": "not_found", "message": "Movie not found on external sources"},
            status=404,
        )

    # status == "error" — surface the failure rather than silently redirecting.
    return JsonResponse(result.to_dict(), status=502)


def _ensure_trailer(movie):
    """Make sure `movie` has a playable YouTube trailer. Legacy entries point
    at dead .mp4 hosts, so if no YouTube link is present we scrape one from
    YouTube (by title) and cache it on the record. Best-effort and silent."""
    for url in _split_values(movie.tLink) + _split_values(movie.embedLink):
        if _is_youtube(url):
            return

    title = re.sub(r"\s*\(\d{4}\)\s*$", "", movie.Title).strip() or movie.Title
    try:
        trailer = _youtube_trailer(title)
    except Exception:
        trailer = ""
    if not trailer:
        return

    existing = [u for u in _split_values(movie.tLink) if u != trailer]
    movie.tLink = "\n".join([trailer] + existing)
    try:
        movie.save(update_fields=["tLink"])
    except Exception:
        pass


def movie_detail(request, movie_id):
    movie = get_object_or_404(Movie, pk=movie_id)
    _ensure_trailer(movie)
    genres = _split_values(movie.genres)
    player_links = _player_links(movie)
    all_recommended_movies = Movie.objects.exclude(pk=movie.pk)
    recommended_movies = all_recommended_movies
    if genres:
        recommended_query = Q()
        for genre in genres[:3]:
            recommended_query |= Q(genres__icontains=genre)
        recommended_movies = recommended_movies.filter(recommended_query)
    recommended_movies = list(recommended_movies.order_by("-id")[:8])
    if not recommended_movies:
        recommended_movies = list(all_recommended_movies.order_by("-id")[:8])

    return render(request, "movie.html", {
        "movie": movie,
        "genres": genres,
        "nav_genres": _genre_list(),
        "years": _year_list(),
        "mLink": _split_values(movie.mLink),
        "embedLink": _split_values(movie.embedLink),
        "tLink": _split_values(movie.tLink),
        "dLink": _split_values(movie.dLink),
        "player_links": player_links,
        "recommended_movies": recommended_movies,
        "download_status": movie.download_status,
        "watch_providers": _watch_providers(movie),
    })


def _watch_providers(movie, country="US"):
    """Return this movie's legal watch providers, refreshing if stale (>7 days).

    Best-effort: provider discovery must never break the detail page, so any
    failure just yields whatever rows are already stored.
    """
    try:
        return ProviderService().sync(movie, country=country)
    except Exception:
        return list(movie.providers.filter(country=country))


def movie_api(request, movie_id=None):
    if movie_id is not None:
        return JsonResponse(_movie_payload(get_object_or_404(Movie, pk=movie_id)))

    movies, query, selected_genre, selected_year, selected_type = _filtered_movies(request)
    return JsonResponse({
        "query": query,
        "genre": selected_genre,
        "year": selected_year,
        "type": selected_type,
        "results": [_movie_payload(movie) for movie in movies],
    })
