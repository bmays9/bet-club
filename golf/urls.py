from django.urls import path
from . import views

urlpatterns = [
    path("events/", views.filtered_events, name="golf-events"),
]