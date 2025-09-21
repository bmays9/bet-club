from django.contrib import admin
from django_summernote.admin import SummernoteModelAdmin
from .models import Fixture, Prediction, GameTemplate, GameInstance, GameEntry

@admin.register(Fixture)
class FixtureAdmin(SummernoteModelAdmin):
    list_display = ('date', 'league_short_name', 'home_team', 'away_team', 'status_code', 'home_score', 'away_score', 'gametemplate')
    search_fields = ['date', 'league_short_name', 'home_team', 'away_team', 'status_code']
    list_filter = ('date', 'league_short_name','status_code', 'gametemplate')

@admin.register(GameTemplate)
class GameTemplateAdmin(SummernoteModelAdmin):
    list_display = ('id', 'slug', 'week', 'game_type', 'start_date', 'end_date')
    search_fields = ['week']
    list_filter = ('week', 'game_type')

@admin.register(GameEntry)
class GameEntryAdmin(SummernoteModelAdmin):
    list_display = ('id', 'game', 'player', 'total_score', 'alt_score')
    search_fields = ['id']
    list_filter = ('game', 'player')

@admin.register(Prediction)
class PredictionAdmin(SummernoteModelAdmin):
    list_display = ('id', 'game_instance', 'player', 'fixture', 'score', 'alternate_score')
    search_fields = ['player', 'game_instance']
    list_filter = ('game_instance', 'player')

@admin.register(GameInstance)
class GameInstanceAdmin(SummernoteModelAdmin):
    list_display = ('group', 'template', 'winner_list','entry_fee')
    search_fields = ['group', 'template']
    list_filter = ('group', 'template')

    def winner_list(self, obj):
        return ", ".join(user.username for user in obj.winners.all())
    winner_list.short_description = "Winners"

# Register your models here.
# admin.site.register(GameInstance)
