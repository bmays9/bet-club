"""
URL configuration for bet_club project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from game_horse import views as horse_views
from .views import horse_view, home_view  # Import the view
from bank.views import money_list

urlpatterns = [
    path("", money_list, name="index"),   # homepage → money_list,
    path("home/", money_list, name="home"),
    path("horse.html", horse_view, name="horse"),
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("bank/", include("bank.urls")),
    path("golf/", include("golf.urls")),
    path('groups/', include('groups.urls')),
    path("lms/", include("lms.urls"), name="lms"),
    path("scores/", include("score_predict.urls"), name="scores"),
    path("season/", include("season.urls"), name="season"),
    path("summernote/", include("django_summernote.urls")),
]
