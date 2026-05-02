from django.contrib import admin
from django.contrib.admin.models import LogEntry

@admin.register(LogEntry)
class LogEntryAdmin(admin.ModelAdmin):
    list_display = ['action_time', 'user', 'content_type', 'object_repr', 'action_flag']
    list_filter = ['user', 'action_flag']
    search_fields = ['object_repr']


# Register your models here.
from .models import BankBalance, BankMessage

admin.site.register(BankBalance)
admin.site.register(BankMessage)
