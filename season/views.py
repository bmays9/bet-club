from django.shortcuts import render
from django.db.models import Sum, Avg, F, Max
from .models import PlayerScoreSnapshot, StandingsRow, PlayerPick, PickType, Handicap, StandingsBatch

def season_overall(request):
    # Get latest batch per league
    latest_batches = (
        StandingsBatch.objects.values("league_id")
        .annotate(latest_taken_at=Max("taken_at"))
    )

    batch_ids = []
    for row in latest_batches:
        b = StandingsBatch.objects.filter(
            league_id=row["league_id"], taken_at=row["latest_taken_at"]
        ).first()
        if b:
            batch_ids.append(b.id)

    if not batch_ids:
        return render(request, "season/season_overall.html", {"batch": None, "snaps": []})

    # Fetch snapshots for these latest batches
    snaps = PlayerScoreSnapshot.objects.filter(batch_id__in=batch_ids)

    # Aggregate overall points per player across leagues
    overall = (
        snaps.values("player_game_id", "player_game__user__username")
        .annotate(total=Sum("league_total_points"))
        .order_by("-total")
    )

    # Build a dict mapping player -> league -> league_rank
    league_ranks = {}
    for snap in snaps:
        username = snap.player_game.user.username
        league_name = snap.game_league.league.name
        league_ranks.setdefault(username, {})[league_name] = snap.league_rank

    cann_rows = []
    for idx, row in enumerate(overall, start=1):
        pid = row["player_game_id"]
        cann_rows.append({
            "row_number": idx,
            "username": row["player_game__user__username"],
            "total": row["total"],
            "league_ranks": league_ranks.get(pid, {}),
            "money": 0,  # placeholder
        })

    # For display we can pass the latest timestamp overall
    latest_time = (
        StandingsBatch.objects.filter(id__in=batch_ids)
        .aggregate(latest=Max("taken_at"))["latest"]
    )

    print("Over", overall)
    print("Cann", cann_rows)

    return render(request, "season/season_overall.html", {
        "overall": overall,
        "league_ranks": league_ranks,
        "latest_time": latest_time,
    })


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
