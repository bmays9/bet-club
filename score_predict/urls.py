from . import views
from django.urls import path, include

urlpatterns = [
    path('', views.FixtureList.as_view(), name='scores-home'),
]