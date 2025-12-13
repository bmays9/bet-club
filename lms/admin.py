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
    list_display = ('game', 'round_number', 'start_date', 'end_date', 'completed', 'is_active','auto_pick_team1')
    search_fields = ['game']
    list_filter = ['completed']

@admin.register(LMSEntry)
class LMSEntryAdmin(SummernoteModelAdmin):
    list_display = ('game', 'user', 'alive', 'eliminated_round')
    search_fields = ['user', 'game']
    list_filter = ['alive', 'game', 'user']

@admin.register(LMSPick)
class LMSPickAdmin(SummernoteModelAdmin):
    list_display = ('get_user', 'get_group', 'get_league', 'get_round', 'team_name', 'result', 'fixture')
    search_fields = ['get_group', 'get_league']
    list_filter = ['result', 'round']

    def get_user(self, obj):
        return obj.entry.user.username
    get_user.short_description = 'User'

    def get_group(self, obj):
        return obj.round.game.group
    get_group.short_description = 'Group'

    def get_league(self, obj):
        return obj.round.game.league
    get_league.short_description = 'League'

    def get_round(self, obj):
        return obj.round.round_number
    get_round.short_description = 'Round'

# Register your models here.

