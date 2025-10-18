from django.contrib import admin
from django_summernote.admin import SummernoteModelAdmin
from .models import (
    GolfTour,
    GolfEvent,
    Golfer,
    EventEntry,
    GolferScore,
    UserPick,
    UserOrder,
)

@admin.register(GolfTour)
class GolfTourAdmin(SummernoteModelAdmin):
    list_display = ("tour_name", "tour_id", "season_id", "active")
    list_filter = ("active", "season_id")
    search_fields = ("tour_name",)
    summernote_fields = ()  # No long text fields, but keeps consistent UI


@admin.register(GolfEvent)
class GolfEventAdmin(SummernoteModelAdmin):
    list_display = ("name", "tour", "year", "start_date", "end_date", "status", "current_round")
    list_filter = ("tour", "year", "status")
    search_fields = ("name", "tour__tour_name")
    ordering = ("-start_date",)
    readonly_fields = ("tourn_id",)
    summernote_fields = ()  # Add description later if you want a rich text field


@admin.register(Golfer)
class GolferAdmin(SummernoteModelAdmin):
    list_display = ("first_name", "last_name", "country", "is_amateur")
    list_filter = ("is_amateur", "country")
    search_fields = ("first_name", "last_name", "country")
    summernote_fields = ()


@admin.register(EventEntry)
class EventEntryAdmin(SummernoteModelAdmin):
    list_display = ("event", "golfer", "status")
    list_filter = ("status", "event__tour")
    search_fields = ("event__name", "golfer__first_name", "golfer__last_name")
    summernote_fields = ()


@admin.register(GolferScore)
class GolferScoreAdmin(SummernoteModelAdmin):
    list_display = ("golfer", "event", "round", "score", "thru", "position")
    list_filter = ("event__tour", "round")
    search_fields = ("golfer__first_name", "golfer__last_name", "event__name")
    summernote_fields = ()


@admin.register(UserPick)
class UserPickAdmin(SummernoteModelAdmin):
    list_display = ("user", "event", "golfer")
    list_filter = ("event__tour",)
    search_fields = ("user__username", "event__name", "golfer__last_name")
    summernote_fields = ()


@admin.register(UserOrder)
class UserOrderAdmin(SummernoteModelAdmin):
    list_display = ("user", "event", "golfer", "selection_rank")
    list_filter = ("event__tour",)
    search_fields = ("user__username", "event__name", "golfer__last_name")
    ordering = ("event", "selection_rank")
    summernote_fields = ()
