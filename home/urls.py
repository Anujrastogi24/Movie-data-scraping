from django.contrib import admin
from django.urls import path
from home import views

urlpatterns = [
    path("", views.index, name='home'),
    path("index.html", views.index, name='home'),
    path("about", views.about, name='about'),
    path("services", views.services, name='services'),
    path("login.html", views.loginUser, name="login"),
    path("logout", views.logoutUser, name="logout"),
    path("user.html", views.userpage, name="user"),
    path("preview/", views.adddata, name="adddata"),
    path("preview.html", views.previewdata, name="previewdata"),
    path("searchdata/", views.searchdata, name="searchdata"),
    path("api/suggest/", views.suggest_api, name="suggest_api"),
    path("movies/import/", views.import_movie, name="import_movie"),
    path("movies/<int:movie_id>/", views.movie_detail, name="movie_detail"),
    path("api/movies/", views.movie_api, name="movie_api"),
    path("api/movies/<int:movie_id>/", views.movie_api, name="movie_api_detail"),
]

admin.site.site_header = "MovieCinema"
admin.site.site_title = "Log In -MovieCinema"
admin.site.index_title = "Welcome to MovieCinema Admin Portal"
