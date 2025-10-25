from django.urls import path
from . import views

urlpatterns = [
    path("events/", views.filtered_events, name="golf-events"),
    path("event/<int:event_id>/entries/", views.event_entries_view, name="event_entries"),
    path("event/<int:event_id>/pick-order/", views.pick_order_view, name="pick_order"),
]