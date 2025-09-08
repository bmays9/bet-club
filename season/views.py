from django.shortcuts import render
from django.db.models import Sum, Avg, F, Max, DecimalField, ExpressionWrapper, Value, IntegerField, Case, When
from django.db.models.functions import Cast
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


def season_teams_to_win(request):
    # Get the latest batch for each league
    latest_batches = (
        StandingsBatch.objects.values("league_id")
        .annotate(latest_taken_at=Max("taken_at"))
    )

    # Map league_id -> batch
    league_latest_batch = {}
    for lb in latest_batches:
        batch = StandingsBatch.objects.filter(
            league_id=lb["league_id"], taken_at=lb["latest_taken_at"]
        ).first()
        if batch:
            league_latest_batch[lb["league_id"]] = batch

    if not league_latest_batch:
        return render(request, "season/towin.html", {
            "teams": [], "worst_teams": [], "batch": None
        })

    # Get all PlayerPick objects for the latest batch of each league
    picks = PlayerPick.objects.filter(
        game_league__league_id__in=league_latest_batch.keys()
    ).select_related('player_game__user', 'team', 'game_league', 'game_league__league')

    teams = []

    for pick in picks:
        batch = league_latest_batch.get(pick.game_league.league_id)
        if not batch:
            continue

        row = pick.team.standings_rows.filter(batch=batch).first()
        games_played = row.played if row else 0
        pure_points = row.pure_points if row else 0
        total_points = pure_points

        if pick.pick_type == "handicap":
            hcp = pick.team.handicaps.filter(game_league=pick.game_league).first()
            if hcp:
                season_games = pick.game_league.league.season_games
                total_points += round(hcp.points * games_played / season_games, 2)

        # Map league and pick type codes
        league_code_map = {
            "Premier League": "PL",
            "Championship": "CH",
            "League One": "L1",
            "League Two": "L2"
        }
        pick_type_code_map = {
            "win": "W",
            "handicap": "H",
            "lose": "L"
        }

        teams.append({
            "team": pick.team,
            "player_game": pick.player_game,
            "league": league_code_map.get(pick.game_league.league.name, pick.game_league.league.name),
            "pick_type": pick_type_code_map.get(pick.pick_type, pick.pick_type),
            "games_played": games_played,
            "total_points": total_points,
        })

    # Sort top 20 by total points
    teams_sorted = sorted(teams, key=lambda x: x["total_points"], reverse=True)[:20]

    # Sort worst 20 by total points
    worst_teams = sorted(teams, key=lambda x: x["total_points"])[:20]

    return render(request, "season/towin.html", {
        "batch": max(league_latest_batch.values(), key=lambda b: b.taken_at),
        "teams": teams_sorted,
        "worst_teams": worst_teams,
    })


def season_teams_to_lose(request):
    # Get the latest batch for each league
    latest_batches = (
        StandingsBatch.objects.values("league_id")
        .annotate(latest_taken_at=Max("taken_at"))
    )

    # Map league_id -> batch
    league_latest_batch = {}
    for lb in latest_batches:
        batch = StandingsBatch.objects.filter(
            league_id=lb["league_id"], taken_at=lb["latest_taken_at"]
        ).first()
        if batch:
            league_latest_batch[lb["league_id"]] = batch

    if not league_latest_batch:
        return render(request, "season/tolose.html", {
            "teams": [], "worst_teams": [], "batch": None
        })

    # Get all PlayerPick objects of type 'lose' for the latest batch of each league
    picks = PlayerPick.objects.filter(
        pick_type="lose",
        game_league__league_id__in=league_latest_batch.keys()
    ).select_related('player_game__user', 'team', 'game_league', 'game_league__league')

    teams = []

    league_code_map = {
        "Premier League": "PL",
        "Championship": "CH",
        "League One": "L1",
        "League Two": "L2"
    }

    for pick in picks:
        batch = league_latest_batch.get(pick.game_league.league_id)
        if not batch:
            continue

        row = pick.team.standings_rows.filter(batch=batch).first()
        games_played = row.played if row else 0
        total_points = row.pure_points if row else 0

        teams.append({
            "team": pick.team,
            "player_game": pick.player_game,
            "league": league_code_map.get(pick.game_league.league.name, pick.game_league.league.name),
            "pick_type": "L",
            "games_played": games_played,
            "total_points": total_points,
        })

    # Best 20 to lose = fewest points
    teams_sorted = sorted(teams, key=lambda x: x["total_points"])[:15]

    # Worst 20 to lose = most points
    worst_teams = sorted(teams, key=lambda x: x["total_points"], reverse=True)[:15]

    return render(request, "season/tolose.html", {
        "batch": max(league_latest_batch.values(), key=lambda b: b.taken_at),
        "teams": teams_sorted,
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
