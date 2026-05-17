# bank/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path("money/", views.money_list, name="bank_money"),
    path("pay/", views.make_payment, name="make_payment"),
    path("pay/<int:payment_id>/confirm/", views.confirm_payment, name="confirm_payment"),
    path("pay/<int:payment_id>/cancel/", views.cancel_payment, name="cancel_payment"),
]
