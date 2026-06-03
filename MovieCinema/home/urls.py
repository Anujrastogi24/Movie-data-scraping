from django.contrib import admin
from django.urls import path
from home import views, scraping

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
    path("searchdata/", scraping.searchdata, name="searchdata"),
    path("movie.html", views.movie , name="movie"),
]

admin.site.site_header = "MovieCinema"
admin.site.site_title = "Log In -MovieCinema"
admin.site.index_title = "Welcome to MovieCinema Admin Portal"