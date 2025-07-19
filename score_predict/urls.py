from . import views
from django.urls import path, include

urlpatterns = [
    path('', views.FixtureList.as_view(), name='scores'),
    path("submit-predictions/", views.submit_predictions, name="submit_predictions"),
]