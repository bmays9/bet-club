from . import views
from django.urls import path, include

urlpatterns = [
    path('', views.FixtureList.as_view(), name='scores'),
    path("submit-predictions/", views.submit_predictions, name="submit_predictions"),
    path("game/<int:pk>/", views.GameDetailView.as_view(), name="game_detail"),
    path("game-summary/<int:group_id>/<slug:template_slug>/", views.game_summary, name="game_summary"),
]