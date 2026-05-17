# golf/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path("events/", views.filtered_events, name="golf-events"),
    path("history/", views.golf_history, name="golf_history"),
    path("event/<str:event_id>/entries/", views.event_entries_view, name="event_entries"),
    path("event/<str:event_id>/pick-order/", views.pick_order_view, name="pick_order"),
    path("event/<str:event_id>/create-game/", views.create_golf_game, name="golf_create_game"),
    path("game/<int:game_id>/join/", views.join_golf_game, name="golf_join_game"),
    path("game/<int:game_id>/", views.golf_game_detail, name="golf_game_detail"),
    path("game/<int:game_id>/pick/", views.make_draft_pick, name="golf_make_pick"),
    path("game/<int:game_id>/leaderboard/", views.leaderboard_view, name="golf_leaderboard"),
    path("game/<int:game_id>/start-draft/", views.close_entries_and_start_draft, name="golf_start_draft"),
]
