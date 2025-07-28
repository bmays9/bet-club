from django.urls import path
from . import views

app_name = "bank"

urlpatterns = [
    path("money-list/", views.money_list, name="money_list"),
]
