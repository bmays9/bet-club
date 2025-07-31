# lms/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path("dashboard/", views.lms_dashboard, name="lms_dashboard"),  
    path("game/<int:game_id>/", views.lms_game_detail, name="lms_game_detail"),
    path("game/<int:game_id>/round/<int:round_id>/pick/", views.lms_pick, name="lms_pick"),
]
