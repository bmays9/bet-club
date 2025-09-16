from decimal import Decimal
from django.shortcuts import render
from django.db.models import Sum, Avg, F, Max, DecimalField, ExpressionWrapper, Value, IntegerField, Case, When
from django.db.models.functions import Cast
from .models import PlayerScoreSnapshot, StandingsRow, PlayerPick, PickType, Handicap, StandingsBatch, PrizePool, PrizeCategory, PlayerGame, Game
from groups.models import UserGroup

def season_overall(request):
    user_groups = UserGroup.objects.filter(members=request.user)
    selected_group_id = request.GET.get("group")
    selected_game_id = request.GET.get("game")

    # Auto-select group if only one
    if not selected_group_id and user_groups.count() == 1:
        selected_group = user_groups.first()
    else:
        selected_group = user_groups.filter(id=selected_group_id).first()

    print (selected_group)
    # Games for dropdown
    group_games = Game.objects.filter(group=selected_group) if selected_group else Game.objects.none()

    # Auto-select game if only one
    if not selected_game_id and group_games.count() == 1:
        selected_game = group_games.first()
    else:
        selected_game = group_games.filter(id=selected_game_id).first()

    print (group_games)
    print (selected_game)

    # PlayerGames for scoring
    player_games = PlayerGame.objects.filter(game__group=selected_group)
    if selected_game:
        player_games = player_games.filter(game=selected_game)

    if not selected_game:
        return render(request, "season/season_overall.html", {
            "overall": [],
            "league_ranks": {},
            "latest_time": None,
            "user_groups": user_groups,
            "selected_group": selected_group,
            "group_games": group_games,
            "selected_game": None,
        })

    # Get latest batch per league
    latest_batches = (
        StandingsBatch.objects.values("league_id")
        .annotate(latest_taken_at=Max("taken_at"))
    )

    batch_ids = [
        b.id for row in latest_batches
        if (b := StandingsBatch.objects.filter(
            league_id=row["league_id"], taken_at=row["latest_taken_at"]
        ).first())
    ]

    snaps = PlayerScoreSnapshot.objects.filter(
        batch_id__in=batch_ids,
        player_game__in=player_games,
    ).select_related("player_game__user", "game_league__league")

    overall = (
        snaps.values("player_game_id", "player_game__user__username")
        .annotate(total=Sum("league_total_points"))
        .order_by("-total")
    )

    league_ranks = {}
    for snap in snaps:
        username = snap.player_game.user.username
        league_name = snap.game_league.league.name
        league_ranks.setdefault(username, {})[league_name] = snap.league_rank

    latest_time = (
        StandingsBatch.objects.filter(id__in=batch_ids)
        .aggregate(latest=Max("taken_at"))["latest"]
    )
    print ("overall", overall)
    print ("league_ranks", league_ranks)
    print ("latest_time", latest_time)
    print ("user_groups", user_groups)
    print ("selected_group", selected_group)
    print ("group_games", group_games)
    print ("selected_game", selected_game)

    return render(request, "season/season_overall.html", {
        "overall": overall,
        "league_ranks": league_ranks,
        "latest_time": latest_time,
        "user_groups": user_groups,
        "selected_group": selected_group,
        "group_games": group_games,
        "selected_game": selected_game,
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
        game_league__league_id__in=league_latest_batch.keys(),
        pick_type__in=[PickType.HANDICAP, PickType.WIN]  # only handicap and win picks
    ).select_related(
        'player_game__user', 'team', 'game_league', 'game_league__league'
    )

    print(picks)

    teams = []
    
    # Modifier for leagues with fewer teams
    league_modifier = {
        "Premier League": 1.2105,
        "Championship": 1,
        "League One": 1,
        "League Two": 1
        }
    
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
        
        else:
       
            total_points = total_points * league_modifier.get(pick.game_league.league.name)

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

    # Attach prize amounts ---------------------------------
    # Get the PrizePool for this game/category
    prize_pool = PrizePool.objects.filter(
        game__in=[p["player_game"].game for p in teams_sorted[:1]],  # take any game
        category=PrizeCategory.TEAMS_TO_WIN,
        active=True,
    ).prefetch_related("payouts").first()

    payout_map = {}
    if prize_pool:
        for payout in prize_pool.payouts.all():
            if payout.rank:  # fixed rank payouts
                payout_map[payout.rank] = payout.amount
            elif payout.entry_fee_per_player:  # entry fee-based
                num_players = prize_pool.game.player_games.count()
                payout_map[1] = payout.calculate_prize(num_players)

    # Annotate teams with prize (top list)
    for idx, team in enumerate(teams_sorted, start=1):
        team["rank"] = idx
        team["prize"] = payout_map.get(idx, Decimal("0.00"))

    # Annotate worst teams with prize (bottom list)
    for idx, team in enumerate(worst_teams, start=1):
        team["rank"] = idx
        team["prize"] = payout_map.get(idx, Decimal("0.00"))

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
    
    # Modifier for leagues with fewer teams
    league_modifier = {
        "Premier League": 1.2105,
        "Championship": 1,
        "League One": 1,
        "League Two": 1
        }

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
        total_points = row.pure_points * league_modifier.get(pick.game_league.league.name) if row else 0

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

    # Attach prize amounts ---------------------------------
    # Get the PrizePool for this game/category
    prize_pool = PrizePool.objects.filter(
        game__in=[p["player_game"].game for p in teams_sorted[:1]],  # take any game
        category=PrizeCategory.TEAMS_TO_LOSE,
        active=True,
    ).prefetch_related("payouts").first()

    payout_map = {}
    if prize_pool:
        for payout in prize_pool.payouts.all():
            if payout.rank:  # fixed rank payouts
                payout_map[payout.rank] = payout.amount
            elif payout.entry_fee_per_player:  # entry fee-based
                num_players = prize_pool.game.player_games.count()
                payout_map[1] = payout.calculate_prize(num_players)

    # Annotate teams with prize (top list)
    for idx, team in enumerate(teams_sorted, start=1):
        team["rank"] = idx
        team["prize"] = payout_map.get(idx, Decimal("0.00"))

    # Annotate worst teams with prize (bottom list)
    for idx, team in enumerate(worst_teams, start=1):
        team["rank"] = idx
        team["prize"] = payout_map.get(idx, Decimal("0.00"))

    return render(request, "season/tolose.html", {
        "batch": max(league_latest_batch.values(), key=lambda b: b.taken_at),
        "teams": teams_sorted,
        "worst_teams": worst_teams,
    })

def season_by_league(request):
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
        return render(request, "season/byleagues.html", {"batch": None, "league_data": {}})

    # Fetch snapshots for these latest batches
    snaps = (
        PlayerScoreSnapshot.objects.filter(batch_id__in=batch_ids)
        .select_related("player_game__user", "game_league__league")
    )

    # Build league -> player -> stats
    league_data = {}
    for snap in snaps:
        league_name = snap.game_league.league.name
        username = snap.player_game.user.username

        league_entry = league_data.setdefault(league_name, {})
        player_entry = league_entry.setdefault(username, {"games_played": 0, "total_points": 0})

        #player_entry["games_played"] += snap.league_games_played
        player_entry["total_points"] += snap.league_total_points

    # Sort players in each league by total_points descending
    for league_name, players in league_data.items():
        sorted_players = dict(
            sorted(players.items(), key=lambda x: x[1]["total_points"], reverse=True)
        )
        league_data[league_name] = sorted_players

    # Get a reference batch (latest overall by taken_at)
    latest_batch = StandingsBatch.objects.filter(id__in=batch_ids).order_by("-taken_at").first()

    return render(
        request,
        "season/byleagues.html",
        {"batch": latest_batch, "league_data": league_data},
    )


def season_by_not_league(request):
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
    league_points = {}
    for snap in snaps:
        username = snap.player_game.user.username
        league_name = snap.game_league.league.name
        league_points = snap.game_league.league.name
        league_ranks.setdefault(username, {})[league_name] = snap.league_rank

    print("s", snaps)
    print("lr", league_ranks)
    return render(request, "season/byleagues.html", {"snaps": snaps, "batch": latest_batch})
