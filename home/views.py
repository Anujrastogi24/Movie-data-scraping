from django.contrib.postgres import *
from django.shortcuts import render, HttpResponse, redirect 

from django.contrib.auth import authenticate
from django.contrib.auth import logout, login, authenticate
from home.models import Movie


def index(request):
    return render(request, 'index.html')


def about(request):
    return HttpResponse("This is About page")


def services(request):
    return HttpResponse("This is services")


def adddata(request):
    # data come from html to view
    Title = request.POST['TITLE']
    Description = request.POST['DESCRIPTION']
    Image = request.POST['IMAGE']


    Movie.objects.create(
        Title=Title, description=Description, image=Image)
    return redirect('previewdata')


def previewdata(request):
    all_data = Movie.objects.all()
    return render(request, "preview.html", {'key1': all_data})


def loginUser(request):
    if request.method == "POST":
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(username=username, password=password)
        if user is not None:
            # A backend authenticated the credentials
            login(request, user)
            return redirect("/user.html")

        else:
            # No backend authenticated the credentials
            return render(request, "login.html")

    return render(request, 'login.html')


def logoutUser(request):
    logout(request)
    return redirect("/login.html")


def userpage(request):
    if request.user.is_anonymous:
        return redirect("/login.html")
    return render(request, 'user.html')

def movie(request):
    return render(request, 'movie.html')
