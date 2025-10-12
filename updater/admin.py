from django.contrib import admin
from django_summernote.admin import SummernoteModelAdmin
from .models import LeagueUpdateTracker, UpdateTracker

# Register your models here.

@admin.register(UpdateTracker)
class UpdateTrackerAdmin(SummernoteModelAdmin):
    list_display = ('last_fixtures_check', 'last_results_check', 'last_tables_check')


@admin.register(LeagueUpdateTracker)
class LeagueUpdateTrackerAdmin(SummernoteModelAdmin):
    list_display = ('league', 'last_fixtures_check', 'last_results_check', 'last_tables_check')
   