# season/admin.py
from django.contrib import admin
from django.contrib import messages
from django.utils.html import format_html
from django.core.management import call_command
from django.utils.html import format_html
from django_summernote.admin import SummernoteModelAdmin
from io import StringIO
from .models import (
    League, Team, Game, GameLeague, PlayerGame, PlayerPick,
    Handicap, StandingsBatch, StandingsRow, PlayerScoreSnapshot,
    PrizePool, PrizePayout,
    SeasonDraft, DraftOrder, DraftSlotSeason,
)


# -------------------------------------------------------
# Inlines
# -------------------------------------------------------

class GameLeagueInline(admin.TabularInline):
    model = GameLeague
    extra = 0
    fields = ("league", "active")
    show_change_link = True


class PlayerGameInline(admin.TabularInline):
    model = PlayerGame
    extra = 0
    fields = ("user", "joined_at")
    readonly_fields = ("joined_at",)
    can_delete = False


class HandicapInline(admin.TabularInline):
    model = Handicap
    extra = 0
    fields = ("team", "points")


class PrizePoolInline(admin.TabularInline):
    model = PrizePool
    extra = 0
    fields = ("category", "league", "name", "active")
    show_change_link = True


class PrizePayoutInline(admin.TabularInline):
    model = PrizePayout
    extra = 0
    fields = ("rank", "amount", "entry_fee_per_player", "recipient", "awarded_for_month", "points")
    readonly_fields = ("recipient", "points")


class StandingsRowInline(admin.TabularInline):
    model = StandingsRow
    extra = 0
    fields = ("team", "position", "played", "wins", "draws", "losses")
    readonly_fields = ("team",)
    ordering = ("position",)


# -------------------------------------------------------
# Main admin classes
# -------------------------------------------------------

@admin.register(League)
class LeagueAdmin(SummernoteModelAdmin):
    list_display = ("name", "code", "country", "season_games", "tournament_id")
    search_fields = ("name", "code")


@admin.register(Team)
class TeamAdmin(SummernoteModelAdmin):
    list_display = ("name", "short_name", "league", "sofascore_id")
    list_filter = ("league",)
    search_fields = ("name", "short_name")
    ordering = ("league__name", "name")


@admin.register(Game)
class GameAdmin(SummernoteModelAdmin):
    list_display = (
        "name", "group", "status", "entry_fee",
        "start_date", "end_date", "player_count", "created_by",
    )
    list_filter = ("status", "group")
    search_fields = ("name", "group__name")
    readonly_fields = ("created_at", "updated_at")
    inlines = [GameLeagueInline, PlayerGameInline, PrizePoolInline]
    actions = ["dry_run_finalise", "finalise_season_action"]

    def player_count(self, obj):
        return obj.players.count()
    player_count.short_description = "Players"

    def _run_finalise(self, request, queryset, dry_run=False):
        if queryset.count() != 1:
            self.message_user(
                request,
                "Please select exactly one game to finalise.",
                level=messages.ERROR,
            )
            return

        game = queryset.first()

        if game.status == Game.Status.FINISHED:
            self.message_user(
                request,
                f"'{game.name}' is already finished.",
                level=messages.WARNING,
            )
            return

        out = StringIO()
        try:
            kwargs = {"game_id": game.id, "force": False, "dry_run": dry_run}
            call_command("finalise_season", stdout=out, **kwargs)
            output = out.getvalue()
            level = messages.SUCCESS
            prefix = "[DRY RUN] " if dry_run else ""
        except Exception as e:
            output = str(e)
            level = messages.ERROR
            prefix = "ERROR: "

        # Show first 500 chars in the admin message, rest goes to terminal
        summary = output.replace("\n", " | ")[:500]
        self.message_user(request, f"{prefix}{summary}", level=level)

    def dry_run_finalise(self, request, queryset):
        """Check if the season is ready to finalise without making changes."""
        self._run_finalise(request, queryset, dry_run=True)

    dry_run_finalise.short_description = (
        "Dry run: check season is ready to finalise"
    )

    def finalise_season_action(self, request, queryset):
        """Finalise the season: allocate prizes and settle bank balances."""
        self._run_finalise(request, queryset, dry_run=False)

    finalise_season_action.short_description = (
        "Finalise season (allocate prizes + settle bank)"
    )


@admin.register(GameLeague)
class GameLeagueAdmin(SummernoteModelAdmin):
    list_display = ("game", "league", "active")
    list_filter = ("league", "game")
    inlines = [HandicapInline]


@admin.register(PlayerGame)
class PlayerGameAdmin(SummernoteModelAdmin):
    list_display = ("user", "game", "joined_at")
    list_filter = ("game__group", "game")
    search_fields = ("user__username", "game__name")
    readonly_fields = ("joined_at",)


@admin.register(PlayerPick)
class PlayerPickAdmin(SummernoteModelAdmin):
    list_display = (
        "player_game", "game_league", "pick_type", "team", "pick_number"
    )
    list_filter = ("pick_type", "game_league__league", "game_league__game")
    search_fields = (
        "player_game__user__username", "team__name",
        "game_league__game__name",
    )
    ordering = ("game_league__game", "pick_number")


@admin.register(Handicap)
class HandicapAdmin(SummernoteModelAdmin):
    list_display = ("game_league", "team", "points")
    list_filter = ("game_league__league", "game_league__game")
    search_fields = ("team__name",)


@admin.register(StandingsBatch)
class StandingsBatchAdmin(SummernoteModelAdmin):
    list_display = ("id", "league", "taken_at", "season_round", "is_month_end", "source", "row_count")
    list_filter = ("league", "is_month_end", "source")
    ordering = ("-taken_at",)
    inlines = [StandingsRowInline]
    list_per_page = 30
    actions = ["mark_as_month_end", "unmark_month_end"]

    def row_count(self, obj):
        return obj.rows.count()
    row_count.short_description = "Teams"

    def mark_as_month_end(self, request, queryset):
        count = queryset.update(is_month_end=True)
        self.message_user(request, f"{count} batch(es) marked as month-end.")
    mark_as_month_end.short_description = "Mark as month-end batch"

    def unmark_month_end(self, request, queryset):
        count = queryset.update(is_month_end=False)
        self.message_user(request, f"{count} batch(es) unmarked.")
    unmark_month_end.short_description = "Unmark month-end"


@admin.register(StandingsRow)
class StandingsRowAdmin(SummernoteModelAdmin):
    list_display = ("team", "batch", "position", "played", "wins", "draws", "losses")
    list_filter = ("batch__league", "batch")
    search_fields = ("team__name",)
    ordering = ("batch", "position")
    list_per_page = 50


@admin.register(PlayerScoreSnapshot)
class PlayerScoreSnapshotAdmin(SummernoteModelAdmin):
    list_display = (
        "player_game", "game_league", "batch",
        "win_points", "handicap_points", "lose_points",
        "league_total_points", "overall_total_points",
        "league_rank", "overall_rank",
    )
    list_filter = ("batch__league", "game_league__game", "batch")
    search_fields = ("player_game__user__username",)
    ordering = ("batch", "overall_rank")
    list_per_page = 50


@admin.register(PrizePool)
class PrizePoolAdmin(SummernoteModelAdmin):
    list_display = ("name", "game", "category", "league", "active")
    list_filter = ("category", "game", "active")
    search_fields = ("name", "game__name")
    inlines = [PrizePayoutInline]


@admin.register(PrizePayout)
class PrizePayoutAdmin(SummernoteModelAdmin):
    list_display = (
        "prize_pool", "rank", "amount", "entry_fee_per_player",
        "recipient", "awarded_for_month", "points",
    )
    list_filter = ("prize_pool__game", "prize_pool__category")
    search_fields = ("recipient__user__username",)
    readonly_fields = ("points",)


class DraftSlotInline(admin.TabularInline):
    model = DraftSlotSeason
    extra = 0
    fields = ("pick_number", "player_game", "pick_type", "game_league", "completed", "skipped")
    readonly_fields = ("pick_number", "player_game", "pick_type", "game_league")
    ordering = ("pick_number",)
    can_delete = False
    show_change_link = False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "player_game__user", "game_league__league"
        )


class DraftOrderInline(admin.TabularInline):
    model = DraftOrder
    extra = 0
    fields = ("position", "player_game")
    readonly_fields = ("player_game",)
    ordering = ("position",)


@admin.register(SeasonDraft)
class SeasonDraftAdmin(SummernoteModelAdmin):
    list_display = (
        "game", "phase", "method", "started_at",
        "slot_count", "completed_count", "pending_count",
        "current_picker", "current_pick_type", "current_league",
    )
    list_filter = ("phase", "method", "game__group")
    readonly_fields = ("started_at", "completed_at", "randomized_at_count")
    inlines = [DraftOrderInline, DraftSlotInline]

    def _next_slot(self, obj):
        return obj.slots.filter(completed=False).order_by("pick_number").first()

    def slot_count(self, obj):
        return obj.slots.count()
    slot_count.short_description = "Total"

    def completed_count(self, obj):
        return obj.slots.filter(completed=True).count()
    completed_count.short_description = "Done"

    def pending_count(self, obj):
        n = obj.slots.filter(completed=False).count()
        return format_html('<span style="color:{};">{}</span>',
                          "green" if n == 0 else "orange", n)
    pending_count.short_description = "Pending"

    def current_picker(self, obj):
        slot = self._next_slot(obj)
        if slot:
            return slot.player_game.user.username
        return "Draft complete"
    current_picker.short_description = "Whose turn"

    def current_pick_type(self, obj):
        slot = self._next_slot(obj)
        return slot.get_pick_type_display() if slot else "-"
    current_pick_type.short_description = "Pick type"

    def current_league(self, obj):
        slot = self._next_slot(obj)
        return slot.game_league.league.name if slot else "-"
    current_league.short_description = "League"


@admin.register(DraftSlotSeason)
class DraftSlotSeasonAdmin(SummernoteModelAdmin):
    list_display = (
        "pick_number", "game_name", "player_name",
        "pick_type", "league_name", "completed", "skipped",
    )
    list_filter = ("draft__game", "pick_type", "completed", "skipped")
    ordering = ("draft", "pick_number")
    list_per_page = 50
    list_display_links = ("pick_number",)
    actions = ["mark_complete", "mark_incomplete"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "draft__game", "player_game__user", "game_league__league",
        )

    def game_name(self, obj):
        return obj.draft.game.name
    game_name.short_description = "Game"

    def player_name(self, obj):
        return obj.player_game.user.username
    player_name.short_description = "Player"

    def league_name(self, obj):
        return obj.game_league.league.name
    league_name.short_description = "League"

    def mark_complete(self, request, queryset):
        count = queryset.update(completed=True)
        self.message_user(request, f"{count} slot(s) marked complete.")
    mark_complete.short_description = "Mark selected slots as complete"

    def mark_incomplete(self, request, queryset):
        count = queryset.update(completed=False)
        self.message_user(request, f"{count} slot(s) marked incomplete.")
    mark_incomplete.short_description = "Mark selected slots as incomplete (reset)"


@admin.register(DraftOrder)
class DraftOrderAdmin(SummernoteModelAdmin):
    list_display = ("draft", "position", "player_name")
    list_filter = ("draft__game",)
    ordering = ("draft", "position")

    def player_name(self, obj):
        return obj.player_game.user.username
    player_name.short_description = "Player"