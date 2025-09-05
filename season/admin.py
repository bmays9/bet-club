from django.contrib import admin
from django_summernote.admin import SummernoteModelAdmin

from .models import (
    League,
    Team,
    Game,
    GameLeague,
    PlayerGame,
    Handicap,
    PlayerPick,
    StandingsBatch,
    StandingsRow,
    PlayerScoreSnapshot,
    PrizePool,
)

# -----------------------------
# Core reference data
# -----------------------------

@admin.register(League)
class LeagueAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "country", "season_games", "tournament_id", "season_id")
    search_fields = ("name", "code", "country")


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "league", "short_name", "sofascore_id")
    list_filter = ("league",)
    search_fields = ("name", "short_name")


# -----------------------------
# Game setup & participation
# -----------------------------

@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ("name", "group", "created_by", "status", "entry_fee", "start_date", "end_date")
    list_filter = ("status", "group")
    search_fields = ("name",)


@admin.register(GameLeague)
class GameLeagueAdmin(admin.ModelAdmin):
    list_display = ("game", "league", "active")
    list_filter = ("game", "league", "active")


@admin.register(PlayerGame)
class PlayerGameAdmin(admin.ModelAdmin):
    list_display = ("user", "game", "joined_at")
    list_filter = ("game",)
    search_fields = ("user__username",)


@admin.register(Handicap)
class HandicapAdmin(admin.ModelAdmin):
    list_display = ("game_league", "team", "points")
    list_filter = ("game_league", "team")


@admin.register(PlayerPick)
class PlayerPickAdmin(admin.ModelAdmin):
    list_display = ("player_game", "game_league", "pick_type", "team", "pick_number", "created_at")
    list_filter = ("pick_type", "game_league")
    search_fields = ("player_game__user__username", "team__name")


# -----------------------------
# Standings & scoring
# -----------------------------

@admin.register(StandingsBatch)
class StandingsBatchAdmin(admin.ModelAdmin):
    list_display = ("taken_at", "season_round", "source")
    list_filter = ("source",)
    date_hierarchy = "taken_at"


@admin.register(StandingsRow)
class StandingsRowAdmin(admin.ModelAdmin):
    list_display = ("batch", "team", "position", "played", "wins", "draws", "losses", "goals_for", "goals_against", "pure_points")
    list_filter = ("batch", "team")


@admin.register(PlayerScoreSnapshot)
class PlayerScoreSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "player_game",
        "game_league",
        "batch",
        "win_points",
        "handicap_points",
        "lose_points",
        "league_total_points",
        "overall_total_points",
        "league_rank",
        "overall_rank",
        "created_at",
    )
    list_filter = ("game_league", "batch")
    search_fields = ("player_game__user__username",)


# -----------------------------
# Prize pools
# -----------------------------

@admin.register(PrizePool)
class PrizePoolAdmin(admin.ModelAdmin):
    list_display = ("game", "category", "league", "name", "active")
    list_filter = ("category", "game", "league", "active")
    search_fields = ("name",)
