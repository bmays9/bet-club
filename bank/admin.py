from django.contrib import admin

# Register your models here.
from .models import BankBalance, BankMessage

admin.site.register(BankBalance)
admin.site.register(BankMessage)