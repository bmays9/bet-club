from django.shortcuts import render
from django.db.models import Sum, Avg, F
from .models import PlayerScoreSnapshot, StandingsRow, PlayerPick, PickType, Handicap

from django.shortcuts import render
from django.db.models import Sum, F
from .models import PlayerScoreSnapshot, StandingsRow


def season_overall(request):
    latest_snapshot = PlayerScoreSnapshot.objects.order_by("-batch__taken_at").first()
    if not latest_snapshot:
        return render(request, "season/season_overall.html", {"snaps": [], "batch": None})

    latest_batch = latest_snapshot.batch
    snaps = (
        PlayerScoreSnapshot.objects.filter(batch=latest_batch)
        .values("player_game__user__username")
        .annotate(total=Sum("league_total_points"))
        .order_by("-total")
    )
    return render(request, "season/season_overall.html", {"snaps": snaps, "batch": latest_batch})


def season_best_teams(request):
    latest_row = StandingsRow.objects.order_by("-batch__taken_at").first()
    if not latest_row:
        return render(request, "season/season_best_teams.html", {
            "teams": [], "worst_teams": [], "batch": None
        })

    latest_batch = latest_row.batch
    teams = (
        StandingsRow.objects.filter(batch=latest_batch)
        .annotate(points=F("wins") * 3 + F("draws"))  # custom points calc
        .order_by("-points")[:10]
    )
    worst_teams = (
        StandingsRow.objects.filter(batch=latest_batch)
        .annotate(points=F("wins") * 3 + F("draws"))
        .order_by("points")[:10]
    )
    return render(request, "season/season_best_teams.html", {
        "batch": latest_batch,
        "teams": teams,
        "worst_teams": worst_teams,
    })


def season_best_by_league(request):
    latest_snapshot = PlayerScoreSnapshot.objects.order_by("-batch__taken_at").first()
    if not latest_snapshot:
        return render(request, "season/season_best_by_league.html", {"snaps": [], "batch": None})

    latest_batch = latest_snapshot.batch
    snaps = (
        PlayerScoreSnapshot.objects.filter(batch=latest_batch)
        .values("game_league__league__name", "player_game__user__username")
        .annotate(total=Sum("league_total_points"))
        .order_by("game_league__league__name", "-total")
    )
    return render(request, "season/season_best_by_league.html", {"snaps": snaps, "batch": latest_batch})
