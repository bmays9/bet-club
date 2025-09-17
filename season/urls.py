from . import views
from django.urls import path, include

urlpatterns = [
    path('', views.season_overall, name='season_overall'),
    path("by-leagues/", views.season_by_league, name="season_by_league"),
    path("my-teams/", views.season_my_teams, name="season_my_teams"),
    path("teams-to-win/", views.season_teams_to_win, name="season_teams_to_win"),
    path("teams-to-lose/", views.season_teams_to_lose, name="season_teams_to_lose"),  
]
