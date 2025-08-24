from django.contrib import admin
from django_summernote.admin import SummernoteModelAdmin
from .models import LMSEntry, LMSGame, LMSPick, LMSRound

@admin.register(LMSGame)
class LMSGameAdmin(SummernoteModelAdmin):
    list_display = ('id', 'group', 'league', 'active', 'winner', 'created_at')
    search_fields = ['group']
    list_filter = ('active', 'group', 'league')


@admin.register(LMSRound)
class LMSRoundAdmin(SummernoteModelAdmin):
    list_display = ('game', 'round_number', 'start_date', 'end_date', 'completed', 'is_active')
    search_fields = ['game']
    list_filter = ['completed']

@admin.register(LMSEntry)
class LMSEntryAdmin(SummernoteModelAdmin):
    list_display = ('game', 'user', 'alive', 'eliminated_round')
    search_fields = ['user', 'game']
    list_filter = ['alive', 'game', 'user']

@admin.register(LMSPick)
class LMSPickAdmin(SummernoteModelAdmin):
    list_display = ('entry', 'round', 'fixture', 'team_name', 'result')
    search_fields = ['entry']
    list_filter = ['result', 'round']

# Register your models here.

