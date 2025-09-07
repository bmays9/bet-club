from . import views
from django.urls import path, include

urlpatterns = [
    path('', views.season_overall, name='season_overall'),
]
