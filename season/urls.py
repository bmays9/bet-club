# season/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path("", views.season_overall, name="season_overall"),
    path("create/", views.create_game, name="season_create_game"),
    path("teams-to-win/", views.season_teams_to_win, name="season_teams_to_win"),
    path("teams-to-lose/", views.season_teams_to_lose, name="season_teams_to_lose"),
    path("by-league/", views.season_by_league, name="season_by_league"),
    path("my-teams/", views.season_my_teams, name="season_my_teams"),
    path("monthly/", views.season_monthly, name="season_monthly"),
    path("money/", views.prize_summary, name="season_money"),
    path("game/<int:game_id>/join/", views.join_game, name="season_join_game"),
    path("game/<int:game_id>/handicaps/", views.edit_handicaps, name="season_edit_handicaps"),
    path("game/<int:game_id>/draft-date/", views.edit_draft_date, name="season_edit_draft_date"),
    path("game/<int:game_id>/draft-order/", views.manage_draft_order, name="season_manage_draft_order"),
    path("game/<int:game_id>/draft/", views.season_draft, name="season_draft"),
]