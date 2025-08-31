from django.contrib import admin
from django_summernote.admin import SummernoteModelAdmin
from .models import PlayerMessage, MessageTemplate

# Register your models here.

@admin.register(MessageTemplate)
class MessageTemplateAdmin(SummernoteModelAdmin):
    list_display = ('code', 'audience', 'template_group', 'template_self')
    search_fields = ['code']
    list_filter = ('code', 'audience')

@admin.register(PlayerMessage)
class PlayerMessageAdmin(SummernoteModelAdmin):
    list_display = ('group', 'code', 'audience', 'receiver', 'message', 'created_at')
    search_fields = ['group', 'audience']
    list_filter = ('code', 'audience')