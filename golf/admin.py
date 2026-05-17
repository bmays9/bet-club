from django.contrib import admin
from django_summernote.admin import SummernoteModelAdmin
from .models import (
    GolfTour, GolfEvent, Golfer, EventEntry, GolferScore,
    UserOrder, GolfGame, GolfGameEntry, DraftSlot, DraftPick,
    RolloverPot, GolfGameResult,
)


# -------------------------------------------------------
# Inline classes
# -------------------------------------------------------

class EventEntryInline(admin.TabularInline):
    model = EventEntry
    extra = 0
    fields = ("golfer", "status", "made_cut")
    readonly_fields = ("golfer",)
    can_delete = False
    show_change_link = True
    ordering = ("golfer__world_ranking",)


class GolfGameInline(admin.TabularInline):
    model = GolfGame
    extra = 0
    fields = ("group", "status", "entry_fee", "missed_cut_fine", "pick_method", "created_by")
    readonly_fields = ("group", "status", "created_by")
    can_delete = False
    show_change_link = True


class GolfGameEntryInline(admin.TabularInline):
    model = GolfGameEntry
    extra = 0
    fields = ("user", "draft_position", "final_rank", "final_score", "total_fines")
    readonly_fields = ("user", "joined_at")
    can_delete = False


class DraftSlotInline(admin.TabularInline):
    model = DraftSlot
    extra = 0
    fields = ("pick_number", "round_number", "game_entry", "opens_at", "closes_at", "completed", "auto_assigned")
    readonly_fields = ("pick_number", "round_number", "game_entry", "opens_at", "closes_at")
    can_delete = False
    ordering = ("pick_number",)


class DraftPickInline(admin.TabularInline):
    model = DraftPick
    extra = 0
    fields = ("round_number", "game_entry", "golfer", "auto_assigned", "made_cut", "total_strokes", "is_tournament_winner")
    readonly_fields = ("round_number", "game_entry", "golfer", "picked_at")
    can_delete = False
    ordering = ("round_number",)


class GolferScoreInline(admin.TabularInline):
    model = GolferScore
    extra = 0
    fields = ("round", "score", "total_score", "thru", "position")
    ordering = ("round",)


class UserOrderInline(admin.TabularInline):
    model = UserOrder
    extra = 0
    fields = ("user", "selection_rank", "golfer")
    readonly_fields = ("user",)
    ordering = ("user", "selection_rank")


# -------------------------------------------------------
# Main admin classes
# -------------------------------------------------------

@admin.register(GolfTour)
class GolfTourAdmin(SummernoteModelAdmin):
    list_display = ("tour_name", "tour_id", "season_id", "active")
    list_filter = ("active",)
    search_fields = ("tour_name",)


@admin.register(GolfEvent)
class GolfEventAdmin(SummernoteModelAdmin):
    list_display = (
        "name", "tour", "year", "start_date", "end_date",
        "status", "current_round", "entry_count", "game_count"
    )
    list_filter = ("tour", "year", "status")
    search_fields = ("name",)
    ordering = ("-start_date",)
    readonly_fields = ("tourn_id",)
    inlines = [GolfGameInline, EventEntryInline]

    def entry_count(self, obj):
        return obj.entries.count()
    entry_count.short_description = "Entries"

    def game_count(self, obj):
        return obj.golf_games.count()
    game_count.short_description = "Games"


@admin.register(Golfer)
class GolferAdmin(SummernoteModelAdmin):
    list_display = ("full_name", "country", "world_ranking", "is_amateur")
    list_filter = ("is_amateur", "country")
    search_fields = ("first_name", "last_name")
    ordering = ("world_ranking",)
    inlines = [GolferScoreInline]


@admin.register(EventEntry)
class EventEntryAdmin(SummernoteModelAdmin):
    list_display = ("golfer", "event", "status", "made_cut")
    list_filter = ("event__tour", "made_cut", "event")
    search_fields = ("golfer__first_name", "golfer__last_name", "event__name")
    autocomplete_fields = ("golfer", "event")


@admin.register(GolferScore)
class GolferScoreAdmin(SummernoteModelAdmin):
    list_display = ("golfer", "event", "round", "score", "total_score", "thru", "position")
    list_filter = ("event__tour", "round", "event")
    search_fields = ("golfer__first_name", "golfer__last_name", "event__name")
    ordering = ("event", "position", "round")


@admin.register(UserOrder)
class UserOrderAdmin(SummernoteModelAdmin):
    list_display = ("user", "event", "selection_rank", "golfer")
    list_filter = ("event__tour", "event")
    search_fields = ("user__username", "golfer__first_name", "golfer__last_name")
    ordering = ("event", "user", "selection_rank")


@admin.register(GolfGame)
class GolfGameAdmin(SummernoteModelAdmin):
    list_display = (
        "event", "group", "status", "pick_method",
        "entry_fee", "missed_cut_fine", "player_count",
        "picks_per_player", "scoring_picks", "rollover_amount", "created_by"
    )
    list_filter = ("status", "pick_method", "group", "event__tour")
    search_fields = ("event__name", "group__name")
    readonly_fields = ("created_at",)
    inlines = [GolfGameEntryInline, DraftSlotInline, DraftPickInline]
    actions = ["reset_draft_slots"]

    def player_count(self, obj):
        return obj.game_entries.count()
    player_count.short_description = "Players"

    def reset_draft_slots(self, request, queryset):
        """Admin action to delete and regenerate draft slots for selected games."""
        from golf.models import DraftSlot
        from golf.services.draft import generate_draft_slots
        count = 0
        for game in queryset.filter(status="drafting"):
            DraftSlot.objects.filter(game=game).delete()
            generate_draft_slots(game)
            count += 1
        self.message_user(request, f"Draft slots regenerated for {count} game(s).")
    reset_draft_slots.short_description = "Reset draft slots (regenerate from now)"


@admin.register(GolfGameEntry)
class GolfGameEntryAdmin(SummernoteModelAdmin):
    list_display = (
        "user", "game", "draft_position",
        "final_rank", "final_score", "total_fines", "joined_at"
    )
    list_filter = ("game__group", "game__event__tour", "game")
    search_fields = ("user__username", "game__event__name")
    readonly_fields = ("joined_at",)
    ordering = ("game", "draft_position")


@admin.register(DraftSlot)
class DraftSlotAdmin(SummernoteModelAdmin):
    list_display = (
        "game", "pick_number", "round_number", "game_entry",
        "opens_at", "closes_at", "completed", "auto_assigned"
    )
    list_filter = ("game__group", "completed", "auto_assigned", "round_number")
    search_fields = ("game__event__name", "game_entry__user__username")
    ordering = ("game", "pick_number")
    readonly_fields = ("pick_number", "round_number")


@admin.register(DraftPick)
class DraftPickAdmin(SummernoteModelAdmin):
    list_display = (
        "game", "round_number", "game_entry", "golfer",
        "auto_assigned", "made_cut", "total_strokes",
        "is_tournament_winner", "picked_at"
    )
    list_filter = (
        "game__group", "auto_assigned", "made_cut",
        "is_tournament_winner", "round_number"
    )
    search_fields = (
        "game__event__name", "game_entry__user__username",
        "golfer__first_name", "golfer__last_name"
    )
    readonly_fields = ("picked_at",)
    ordering = ("game", "round_number", "game_entry__draft_position")


@admin.register(RolloverPot)
class RolloverPotAdmin(SummernoteModelAdmin):
    list_display = ("group", "balance", "last_event", "last_updated")
    search_fields = ("group__name",)
    readonly_fields = ("last_updated",)


@admin.register(GolfGameResult)
class GolfGameResultAdmin(SummernoteModelAdmin):
    list_display = (
        "user", "game", "final_rank", "final_score",
        "main_pot_won", "secondary_pot_won", "fines_paid"
    )
    list_filter = ("game__group", "game__event__tour")
    search_fields = ("user__username", "game__event__name")
    ordering = ("game", "final_rank")
