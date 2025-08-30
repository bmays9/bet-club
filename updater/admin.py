from django.contrib import admin
from django_summernote.admin import SummernoteModelAdmin
from .models import UpdateTracker

# Register your models here.

@admin.register(UpdateTracker)
class UpdateTrackerAdmin(SummernoteModelAdmin):
    list_display = ('last_fixtures_check', 'last_results_check', 'last_tables_check')