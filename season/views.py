# season/views.py
from .models import (
    PlayerScoreSnapshot, StandingsRow, PlayerPick, PickType,
    Handicap, StandingsBatch, PrizePool, PrizePayout,
    PrizeCategory, PlayerGame, Game, GameLeague, League, Team,
)
from .utils.season_helpers import (
    get_group_and_game_selection,
    get_latest_batch_ids,
    get_latest_batches_map,
    get_month_start_batch_ids,
)
from calendar import monthrange, month_name
from collections import OrderedDict
from datetime import date
from decimal import Decimal
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Max
from django.utils.timezone import now
from season.prize_config import (
    TEAMS_TO_WIN_BEST, TEAMS_TO_WIN_WORST,
    TEAMS_TO_LOSE_BEST, TEAMS_TO_LOSE_WORST,
    LEAGUE_WINNER_PER_PLAYER, MONTHLY_PER_PLAYER,
    OVERALL_LOSER_PENALTIES,
)
from season.services.create_game import create_season_game
from groups.models import UserGroup

CATEGORY_ORDER = [
    "Overall", "Leagues", "Teams to Win", "Teams to Lose", "Monthly",
]

CATEGORY_MAP = {
    "overall": "Overall",
    "league_total": "Leagues",
    "league": "Leagues",
    "leagues": "Leagues",
    "teams_to_win": "Teams to Win",
    "teams to win": "Teams to Win",
    "teams_to_lose": "Teams to Lose",
    "teams to lose": "Teams to Lose",
    "monthly_winner": "Monthly",
    "monthly": "Monthly",
    "month": "Monthly",
}

LEAGUE_CODE_MAP = {
    "Premier League": "PL",
    "Championship": "CH",
    "League One": "L1",
    "League Two": "L2",
}

PICK_TYPE_CODE = {"win": "W", "handicap": "H", "lose": "L"}

# EPL adjustment: EPL plays 38 games vs 46 in other leagues.
# For win/lose ranking tables only: adjusted_points = points / 38 * 46
# This ONLY applies to WIN and LOSE picks, NOT handicap picks.
EPL_SEASON_GAMES = 38
OTHER_SEASON_GAMES = 46


def _base_ctx(sel):
    return {
        "user_groups": sel["user_groups"],
        "selected_group": sel["selected_group"],
        "group_games": sel["group_games"],
        "selected_game": sel["selected_game"],
    }


def season_overall(request):
    sel = get_group_and_game_selection(request.user, request)
    ctx = _base_ctx(sel)
    selected_game = sel["selected_game"]
    selected_group = sel["selected_group"]
    player_games = sel["player_games"]

    # ---- Open/Draft games visible to group members ----
    open_games = []
    if selected_group:
        for g in Game.objects.filter(
            group=selected_group,
            status__in=[Game.Status.OPEN, Game.Status.DRAFT],
        ).select_related("created_by").prefetch_related("players"):

            is_creator = g.created_by == request.user
            is_member = g.players.filter(user=request.user).exists()

            # Check handicaps
            game_leagues = GameLeague.objects.filter(game=g, active=True).select_related("league")
            missing_handicaps = []
            for gl in game_leagues:
                batch = get_latest_batches_map().get(gl.league_id)
                if batch:
                    teams_in_league = StandingsRow.objects.filter(
                        batch=batch
                    ).values_list("team_id", flat=True)
                    for team_id in teams_in_league:
                        if not Handicap.objects.filter(game_league=gl, team_id=team_id).exists():
                            missing_handicaps.append(gl.league.name)
                            break

            open_games.append({
                "game": g,
                "is_creator": is_creator,
                "is_member": is_member,
                "num_players": g.players.count(),
                "missing_handicaps": list(set(missing_handicaps)),
                "has_order": g.players.count() > 0,
            })

    ctx["open_games"] = open_games

    if not selected_game:
        ctx.update({"overall": [], "league_ranks": {}, "latest_time": None})
        return render(request, "season/season_overall.html", ctx)

    # Latest batch IDs filtered to leagues in this game
    game_league_ids = GameLeague.objects.filter(
        game=selected_game
    ).values_list("league_id", flat=True)

    batch_ids = get_latest_batch_ids()
    # Further filter to only batches for leagues in this game
    batch_ids = list(
        StandingsBatch.objects.filter(
            id__in=batch_ids,
            league_id__in=game_league_ids,
        ).values_list("id", flat=True)
    )

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

    # Player net totals via custom queryset
    players = PlayerGame.objects.with_net_total(game=selected_game)
    player_map = {pg.user.username: pg for pg in players}

    overall_list = []
    for snap in overall:
        username = snap["player_game__user__username"]
        pg = player_map.get(username)
        overall_list.append({
            "username": username,
            "total_points": snap["total"],
            "total_payouts": getattr(pg, "total_payouts", 0),
            "total_fees": getattr(pg, "total_fees", 0),
            "net_total": getattr(pg, "money_total", 0),
        })

    ctx.update({
        "overall": overall_list,
        "league_ranks": league_ranks,
        "latest_time": latest_time,
        "players": players,
    })
    return render(request, "season/season_overall.html", ctx)


def season_teams_to_win(request):
    sel = get_group_and_game_selection(request.user, request)
    ctx = _base_ctx(sel)
    selected_game = sel["selected_game"]

    league_latest_batch = get_latest_batches_map()
    if not league_latest_batch:
        ctx.update({"teams": [], "worst_teams": [], "batch": None})
        return render(request, "season/towin.html", ctx)

    picks = PlayerPick.objects.filter(
        game_league__game=selected_game,
        pick_type__in=[PickType.HANDICAP, PickType.WIN],
    ).select_related(
        "player_game__user", "team", "game_league", "game_league__league"
    ) if selected_game else PlayerPick.objects.none()

    teams = []
    for pick in picks:
        batch = league_latest_batch.get(pick.game_league.league_id)
        if not batch:
            continue
        row = pick.team.standings_rows.filter(batch=batch).first()
        games_played = row.played if row else 0
        pure_points = row.pure_points if row else 0
        total_points = Decimal(str(pure_points))


        if pick.pick_type == PickType.HANDICAP:
            # Handicap picks: add handicap bonus, NO league adjustment
            hcp = pick.team.handicaps.filter(game_league=pick.game_league).first()
            if hcp:
                season_games = pick.game_league.league.season_games
                total_points += Decimal(str(round(hcp.points * games_played / season_games, 2)))
        elif pick.pick_type == PickType.WIN:
            # Win picks only: apply points-per-game adjustment for EPL
            # EPL plays 38 games vs 46 in other leagues
            # Adjusted points = pure_points / 38 * 46
            league_name = pick.game_league.league.name
            season_games = pick.game_league.league.season_games
            if league_name == "Premier League" and season_games > 0:
                total_points = (total_points / Decimal("38")) * Decimal("46")

        teams.append({
            "team": pick.team,
            "player_game": pick.player_game,
            "league": LEAGUE_CODE_MAP.get(pick.game_league.league.name, pick.game_league.league.name),
            "pick_type": PICK_TYPE_CODE.get(pick.pick_type, pick.pick_type),
            "games_played": games_played,
            "total_points": total_points,
        })

    teams_sorted = sorted(teams, key=lambda x: x["total_points"], reverse=True)[:20]
    worst_teams = sorted(teams, key=lambda x: x["total_points"])[:20]

    prize_pool = _get_prize_pool(selected_game, PrizeCategory.TEAMS_TO_WIN)
    payout_map = _build_payout_map(prize_pool, selected_game)

    for idx, t in enumerate(teams_sorted, 1):
        t["rank"] = idx
        t["prize"] = payout_map.get(idx, Decimal("0.00"))
    for idx, t in enumerate(worst_teams, 1):
        t["rank"] = idx
        t["prize"] = payout_map.get(idx, Decimal("0.00"))

    ctx.update({
        "batch": max(league_latest_batch.values(), key=lambda b: b.taken_at) if league_latest_batch else None,
        "teams": teams_sorted,
        "worst_teams": worst_teams,
    })
    return render(request, "season/towin.html", ctx)


def season_teams_to_lose(request):
    sel = get_group_and_game_selection(request.user, request)
    ctx = _base_ctx(sel)
    selected_game = sel["selected_game"]

    league_latest_batch = get_latest_batches_map()
    if not league_latest_batch:
        ctx.update({"teams": [], "worst_teams": [], "batch": None})
        return render(request, "season/tolose.html", ctx)

    picks = PlayerPick.objects.filter(
        game_league__game=selected_game,
        pick_type=PickType.LOSE,
    ).select_related(
        "player_game__user", "team", "game_league", "game_league__league"
    ) if selected_game else PlayerPick.objects.none()

    teams = []
    for pick in picks:
        batch = league_latest_batch.get(pick.game_league.league_id)
        if not batch:
            continue
        row = pick.team.standings_rows.filter(batch=batch).first()
        games_played = row.played if row else 0
        # Apply points-per-game adjustment for EPL lose picks
        # EPL plays 38 games vs 46 -- adjust: points / 38 * 46
        league_name = pick.game_league.league.name
        season_games = pick.game_league.league.season_games
        if row and league_name == "Premier League" and season_games > 0:
            total_points = (Decimal(str(row.pure_points)) / Decimal("38")) * Decimal("46")
        else:
            total_points = Decimal(str(row.pure_points)) if row else Decimal("0")

        teams.append({
            "team": pick.team,
            "player_game": pick.player_game,
            "league": LEAGUE_CODE_MAP.get(pick.game_league.league.name, pick.game_league.league.name),
            "pick_type": "L",
            "games_played": games_played,
            "total_points": total_points,
        })

    teams_sorted = sorted(teams, key=lambda x: x["total_points"])[:15]
    worst_teams = sorted(teams, key=lambda x: x["total_points"], reverse=True)[:15]

    prize_pool = _get_prize_pool(selected_game, PrizeCategory.TEAMS_TO_LOSE)
    payout_map = _build_payout_map(prize_pool, selected_game)

    for idx, t in enumerate(teams_sorted, 1):
        t["rank"] = idx
        t["prize"] = payout_map.get(idx, Decimal("0.00"))
    for idx, t in enumerate(worst_teams, 1):
        t["rank"] = idx
        t["prize"] = payout_map.get(idx, Decimal("0.00"))

    ctx.update({
        "batch": max(league_latest_batch.values(), key=lambda b: b.taken_at) if league_latest_batch else None,
        "teams": teams_sorted,
        "worst_teams": worst_teams,
    })
    return render(request, "season/tolose.html", ctx)


def season_by_league(request):
    sel = get_group_and_game_selection(request.user, request)
    ctx = _base_ctx(sel)
    selected_game = sel["selected_game"]
    player_games = sel["player_games"]

    batch_ids = get_latest_batch_ids()
    if not batch_ids:
        ctx.update({"batch": None, "league_data": {}})
        return render(request, "season/byleagues.html", ctx)

    snaps = (
        PlayerScoreSnapshot.objects
        .filter(batch_id__in=batch_ids, player_game__in=player_games)
        .select_related("player_game__user", "game_league__league")
    )

    league_data = {}
    for snap in snaps:
        league_name = snap.game_league.league.name
        username = snap.player_game.user.username
        entry = league_data.setdefault(league_name, {})
        player_entry = entry.setdefault(username, {"total_points": Decimal("0")})
        player_entry["total_points"] += snap.league_total_points

    for league_name in league_data:
        league_data[league_name] = dict(
            sorted(league_data[league_name].items(),
                   key=lambda x: x[1]["total_points"], reverse=True)
        )

    latest_batch = (
        StandingsBatch.objects.filter(id__in=batch_ids)
        .order_by("-taken_at").first()
    )
    ctx.update({"batch": latest_batch, "league_data": league_data})
    return render(request, "season/byleagues.html", ctx)


def season_my_teams(request):
    sel = get_group_and_game_selection(request.user, request)
    ctx = _base_ctx(sel)
    selected_game = sel["selected_game"]
    player_games = sel["player_games"]

    batch_ids = get_latest_batch_ids()
    league_batches = get_latest_batches_map()
    user = request.user

    picks = PlayerPick.objects.filter(
        player_game__user=user,
        player_game__in=player_games,
    ).select_related("player_game", "team", "game_league__league")

    picks_data = []
    for pick in picks:
        league = pick.game_league.league
        batch = league_batches.get(league.id)
        row = pick.team.standings_rows.filter(batch=batch).first() if batch else None

        pure_points = row.pure_points if row else 0
        played = row.played if row else 0
        hcp = pick.team.handicaps.filter(game_league=pick.game_league).first()
        our_points = pure_points
        if pick.pick_type == PickType.HANDICAP and hcp:
            our_points += round(hcp.points * played / league.season_games, 2)

        snap = (
            pick.player_game.score_snapshots
            .filter(game_league__league=league, batch=batch)
            .first()
        ) if batch else None

        picks_data.append({
            "pick_number": pick.pick_number,
            "team": pick.team,
            "pick_type": pick.pick_type[0].upper(),
            "league": league.name,
            "position": row.position if row else None,
            "played": played,
            "won": row.wins if row else 0,
            "drawn": row.draws if row else 0,
            "lost": row.losses if row else 0,
            "pure_points": pure_points,
            "our_points": our_points,
            "handicap": hcp.points if hcp else 0,
            "league_rank": snap.league_rank if snap else None,
        })

    ctx["picks_data"] = picks_data
    return render(request, "season/myteams.html", ctx)


def season_monthly(request):
    sel = get_group_and_game_selection(request.user, request)
    ctx = _base_ctx(sel)
    selected_game = sel["selected_game"]
    player_games = sel["player_games"]

    batch_ids = get_latest_batch_ids()
    month_start_batch_ids = get_month_start_batch_ids()

    if not batch_ids:
        ctx.update({"current_month_scores": [], "previous_winners": []})
        return render(request, "season/monthly.html", ctx)

    latest_totals = (
        PlayerScoreSnapshot.objects
        .filter(batch_id__in=batch_ids, player_game__in=player_games)
        .values("player_game_id", "player_game__user__username")
        .annotate(total_points=Sum("league_total_points"))
    )

    prev_totals_map = {
        row["player_game_id"]: row["total_points"]
        for row in PlayerScoreSnapshot.objects
        .filter(batch_id__in=month_start_batch_ids, player_game__in=player_games)
        .values("player_game_id")
        .annotate(total_points=Sum("league_total_points"))
    }

    current_month_scores = sorted([
        {
            "player_game_id": row["player_game_id"],
            "username": row["player_game__user__username"],
            "total_points": row["total_points"] - prev_totals_map.get(row["player_game_id"], 0),
        }
        for row in latest_totals
    ], key=lambda x: x["total_points"], reverse=True)

    previous_winners = []
    if selected_game:
        for pw in (
            PrizePayout.objects
            .filter(
                prize_pool__game=selected_game,
                prize_pool__category=PrizeCategory.MONTH_WINNER,
                recipient__isnull=False,
            )
            .select_related("recipient__user", "prize_pool__game")
            .order_by("-awarded_for_month")
        ):
            num_players = pw.prize_pool.game.players.count()
            previous_winners.append({
                "awarded_for_month": pw.awarded_for_month,
                "recipient": pw.recipient,
                "amount": pw.calculate_prize(num_players - 1),
            })

    ctx.update({
        "current_month_scores": current_month_scores,
        "previous_winners": previous_winners,
    })
    return render(request, "season/monthly.html", ctx)


def prize_summary(request):
    sel = get_group_and_game_selection(request.user, request)
    ctx = _base_ctx(sel)
    selected_game = sel["selected_game"]
    player_games = sel["player_games"]

    grouped = OrderedDict((k, []) for k in CATEGORY_ORDER)

    if not selected_game:
        ctx.update({"grouped_payouts": grouped, "category_columns": {}})
        return render(request, "season/season_money.html", ctx)

    try:
        num_players = player_games.count()
    except Exception:
        num_players = selected_game.players.count()

    payouts_qs = (
        PrizePayout.objects
        .filter(prize_pool__game=selected_game)
        .select_related(
            "prize_pool", "prize_pool__league",
            "recipient__user", "winning_pick__team",
        )
        .order_by("prize_pool__category", "rank")
    )

    for payout in payouts_qs:
        raw_cat = (payout.prize_pool.category or "").lower().strip()
        normalized = CATEGORY_MAP.get(raw_cat)
        if normalized is None and payout.prize_pool.league_id:
            normalized = "Leagues"
        if normalized is None:
            normalized = getattr(payout.prize_pool, "name", raw_cat) or "Other"

        try:
            if payout.recipient and payout.amount is not None:
                # Already settled row -- show the actual amount paid out
                prize_value = abs(payout.amount)
            elif payout.entry_fee_per_player and num_players:
                # Per-player: winner gets fee from each OTHER player (num_players - 1)
                prize_value = payout.entry_fee_per_player * Decimal(str(max(num_players - 1, 1)))
            elif payout.amount is not None:
                # Fixed amount row
                prize_value = abs(payout.amount)
            else:
                prize_value = None
        except Exception:
            prize_value = None

        # Skip monthly config rows (no recipient, no awarded_for_month)
        # Only show settled monthly rows where a winner was assigned
        is_monthly = normalized == "Monthly"
        is_config_row = payout.recipient is None and not payout.awarded_for_month
        if is_monthly and is_config_row:
            continue

        item = {
            "prize_pool": payout.prize_pool,
            "payout": payout,
            "rank": payout.rank,
            "recipient": payout.recipient,
            "winning_pick": payout.winning_pick,
            "league": payout.prize_pool.league,
            "points": payout.points,
            "prize_value": prize_value,
        }
        if normalized not in grouped:
            grouped[normalized] = []
        grouped[normalized].append(item)

    for items in grouped.values():
        items.sort(key=lambda it: (it["rank"] is None, it["rank"] or 0))

    for item in grouped.get("Monthly", []):
        closing_date = getattr(item["payout"], "awarded_for_month", None)
        item["month"] = month_name[closing_date.month] if closing_date else None

    category_columns = {
        "Overall": ["rank", "player", "points", "prize_value"],
        "Leagues": ["prize_pool", "player", "points", "prize_value"],
        "Teams to Win": ["rank", "player", "winning_pick", "league", "type", "points", "prize_value"],
        "Teams to Lose": ["rank", "player", "winning_pick", "league", "points", "prize_value"],
        "Monthly": ["month", "player", "points", "prize_value"],
    }

    ctx.update({
        "grouped_payouts": grouped,
        "num_players": num_players,
        "category_columns": category_columns,
    })
    return render(request, "season/season_money.html", ctx)


# -------------------------------------------------------
# Helpers
# -------------------------------------------------------

def _get_prize_pool(game, category):
    if not game:
        return None
    return PrizePool.objects.filter(
        game=game, category=category, active=True
    ).prefetch_related("payouts").first()


def _build_payout_map(prize_pool, game):
    if not prize_pool or not game:
        return {}
    num_players = game.players.count()
    payout_map = {}
    for payout in prize_pool.payouts.all():
        if payout.rank:
            payout_map[payout.rank] = payout.amount or Decimal("0.00")
        elif payout.entry_fee_per_player:
            payout_map[1] = payout.calculate_prize(num_players)
    return payout_map


@login_required
def create_game(request):
    leagues = League.objects.all().order_by("name")
    user_groups = UserGroup.objects.filter(members=request.user)

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        group_id = request.POST.get("group_id")
        league_ids = request.POST.getlist("league_ids")
        draft_date_str = request.POST.get("draft_date", "").strip()
        draft_method = request.POST.get("draft_method", "straight")

        # Prize overrides
        def get_amount(key, default):
            val = request.POST.get(key, "").strip()
            try:
                return Decimal(val) if val else default
            except Exception:
                return default

        errors = []
        if not name:
            errors.append("Game name is required.")
        if not group_id:
            errors.append("Please select a group.")
        if not league_ids:
            errors.append("Please select at least one league.")

        group = user_groups.filter(id=group_id).first()
        if not group:
            errors.append("Invalid group selected.")

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, "season/create_game.html", {
                "leagues": leagues,
                "user_groups": user_groups,
                "defaults": _default_amounts(),
            })

        selected_leagues = list(League.objects.filter(id__in=league_ids))

        # Parse prize overrides
        tw_best = [
            {"rank": i + 1, "amount": get_amount(f"tw_best_{i+1}", row["amount"])}
            for i, row in enumerate(TEAMS_TO_WIN_BEST)
        ]
        tw_worst = [
            {"rank": i + 1, "amount": get_amount(f"tw_worst_{i+1}", row["amount"])}
            for i, row in enumerate(TEAMS_TO_WIN_WORST)
        ]
        tl_best = [
            {"rank": i + 1, "amount": get_amount(f"tl_best_{i+1}", row["amount"])}
            for i, row in enumerate(TEAMS_TO_LOSE_BEST)
        ]
        tl_worst = [
            {"rank": i + 1, "amount": get_amount(f"tl_worst_{i+1}", row["amount"])}
            for i, row in enumerate(TEAMS_TO_LOSE_WORST)
        ]
        league_per_player = get_amount("league_per_player", LEAGUE_WINNER_PER_PLAYER)
        monthly_per_player = get_amount("monthly_per_player", MONTHLY_PER_PLAYER)

        draft_date = None
        if draft_date_str:
            from django.utils.dateparse import parse_datetime
            from django.utils.timezone import make_aware
            try:
                dt = parse_datetime(draft_date_str)
                draft_date = make_aware(dt) if dt and dt.tzinfo is None else dt
            except Exception:
                pass

        try:
            game = create_season_game(
                name=name,
                group=group,
                created_by=request.user,
                leagues=selected_leagues,
                draft_date=draft_date,
                draft_method=draft_method,
                teams_to_win_best=tw_best,
                teams_to_win_worst=tw_worst,
                teams_to_lose_best=tl_best,
                teams_to_lose_worst=tl_worst,
                league_winner_per_player=league_per_player,
                monthly_per_player=monthly_per_player,
            )
            messages.success(request, f"Game '{game.name}' created! Share the draft date with players.")
            return redirect("season_overall")
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            messages.error(request, f"Failed to create game: {e}")
            return render(request, "season/create_game.html", {
                "leagues": leagues,
                "user_groups": user_groups,
                "defaults": _default_amounts(),
                "error_detail": error_detail,
            })

    return render(request, "season/create_game.html", {
        "leagues": leagues,
        "user_groups": user_groups,
        "defaults": _default_amounts(),
    })


def _default_amounts():
    """Build defaults dict for template pre-filling."""
    return {
        "tw_best": TEAMS_TO_WIN_BEST,
        "tw_worst": TEAMS_TO_WIN_WORST,
        "tl_best": TEAMS_TO_LOSE_BEST,
        "tl_worst": TEAMS_TO_LOSE_WORST,
        "league_per_player": LEAGUE_WINNER_PER_PLAYER,
        "monthly_per_player": MONTHLY_PER_PLAYER,
        "overall_penalties": OVERALL_LOSER_PENALTIES,
    }


@login_required
def join_game(request, game_id):
    game = Game.objects.get(id=game_id)
    if game.status not in (Game.Status.OPEN, Game.Status.DRAFT):
        messages.error(request, "This game is not open for joining.")
        return redirect("season_overall")
    if game.players.filter(id=request.user.id).exists():
        messages.warning(request, "You have already joined this game.")
    else:
        PlayerGame.objects.create(game=game, user=request.user)
        messages.success(request, f"You have joined '{game.name}'.")
    return redirect("season_overall")


@login_required
def edit_handicaps(request, game_id):
    game = Game.objects.get(id=game_id)
    if game.created_by != request.user:
        messages.error(request, "Only the game creator can edit handicaps.")
        return redirect("season_overall")

    game_leagues = GameLeague.objects.filter(
        game=game, active=True
    ).select_related("league")

    batch_map = get_latest_batches_map()

    # Build team list per league with current handicap values
    league_data = []
    for gl in game_leagues:
        batch = batch_map.get(gl.league_id)
        teams = []
        if batch:
            for row in StandingsRow.objects.filter(
                batch=batch
            ).select_related("team").order_by("position"):
                hcp = Handicap.objects.filter(
                    game_league=gl, team=row.team
                ).first()
                teams.append({
                    "team": row.team,
                    "position": row.position,
                    "handicap": hcp.points if hcp else None,
                })
        league_data.append({"game_league": gl, "teams": teams})

    if request.method == "POST":
        for gl_data in league_data:
            gl = gl_data["game_league"]
            for t in gl_data["teams"]:
                key = f"hcp_{gl.id}_{t['team'].id}"
                val = request.POST.get(key, "").strip()
                if val:
                    try:
                        pts = Decimal(val)
                        Handicap.objects.update_or_create(
                            game_league=gl,
                            team=t["team"],
                            defaults={"points": pts},
                        )
                    except Exception:
                        pass
        messages.success(request, "Handicaps saved.")
        return redirect("season_edit_handicaps", game_id=game.id)

    return render(request, "season/edit_handicaps.html", {
        "game": game,
        "league_data": league_data,
    })


@login_required
def edit_draft_date(request, game_id):
    game = Game.objects.get(id=game_id)
    if game.created_by != request.user:
        messages.error(request, "Only the game creator can update the draft date.")
        return redirect("season_overall")

    if request.method == "POST":
        draft_date_str = request.POST.get("draft_date", "").strip()
        draft_method = request.POST.get("draft_method", game.draft_method)
        if draft_date_str:
            from django.utils.dateparse import parse_datetime
            from django.utils.timezone import make_aware
            try:
                dt = parse_datetime(draft_date_str)
                game.draft_date = make_aware(dt) if dt and dt.tzinfo is None else dt
                game.draft_method = draft_method
                game.save(update_fields=["draft_date", "draft_method"])
                messages.success(request, "Draft date updated.")
            except Exception as e:
                messages.error(request, f"Invalid date: {e}")
        return redirect("season_overall")

    return render(request, "season/edit_draft_date.html", {"game": game})


@login_required
def manage_draft_order(request, game_id):
    game = Game.objects.get(id=game_id)
    if game.created_by != request.user:
        messages.error(request, "Only the game creator can manage the draft order.")
        return redirect("season_overall")

    if game.status not in (Game.Status.OPEN, Game.Status.DRAFT):
        messages.error(request, "Draft order can only be set before the draft starts.")
        return redirect("season_overall")

    from season.models import SeasonDraft, DraftOrder
    from season.services.draft import create_draft, generate_draft_slots
    import random as _random

    # Get or create the draft object
    draft, _ = SeasonDraft.objects.get_or_create(
        game=game,
        defaults={"method": game.draft_method, "started_at": None},
    )

    players = list(
        PlayerGame.objects.filter(game=game).select_related("user").order_by("id")
    )
    current_order = list(
        DraftOrder.objects.filter(draft=draft).select_related("player_game__user").order_by("position")
    )
    current_order_ids = [do.player_game_id for do in current_order]

    # Track whether randomize has been used since last player joined
    # Store last_player_count on draft (we'll use a simple approach: compare
    # num players when order was last randomised vs now)
    can_randomize = (
        draft.randomized_at_count is None
        or draft.randomized_at_count < len(players)
    )

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "randomize" and can_randomize:
            shuffled = players.copy()
            _random.shuffle(shuffled)
            DraftOrder.objects.filter(draft=draft).delete()
            for i, pg in enumerate(shuffled, start=1):
                DraftOrder.objects.create(draft=draft, player_game=pg, position=i)
            draft.randomized_at_count = len(players)
            draft.save(update_fields=["randomized_at_count"])
            messages.success(request, "Draft order randomised.")
            return redirect("season_manage_draft_order", game_id=game.id)

        elif action == "save_order":
            order_ids = request.POST.getlist("player_order")
            DraftOrder.objects.filter(draft=draft).delete()
            for i, pg_id in enumerate(order_ids, start=1):
                pg = PlayerGame.objects.filter(id=pg_id, game=game).first()
                if pg:
                    DraftOrder.objects.create(draft=draft, player_game=pg, position=i)
            messages.success(request, "Draft order saved.")
            return redirect("season_manage_draft_order", game_id=game.id)

        elif action == "start_draft":
            if len(players) < 2:
                messages.error(request, "Need at least 2 players to start the draft.")
                return redirect("season_manage_draft_order", game_id=game.id)
            if not current_order:
                # Auto-set order if not set yet
                for i, pg in enumerate(players, start=1):
                    DraftOrder.objects.get_or_create(draft=draft, player_game=pg, defaults={"position": i})

            # Generate all draft slots
            generate_draft_slots(draft)

            # Transition game to DRAFT status
            game.status = Game.Status.DRAFT
            game.save(update_fields=["status"])
            draft.started_at = now()
            draft.save(update_fields=["started_at"])

            messages.success(request, "Draft started! Players can now make their picks.")
            return redirect("season_overall")

    return render(request, "season/manage_draft_order.html", {
        "game": game,
        "draft": draft,
        "players": players,
        "current_order": current_order,
        "can_randomize": can_randomize,
    })


@login_required
def season_draft(request, game_id):
    from season.models import SeasonDraft, DraftOrder, DraftSlotSeason
    from season.services.draft import get_current_slot, submit_draft_pick

    game = Game.objects.get(id=game_id)
    if game.status != Game.Status.DRAFT:
        messages.error(request, "This game is not in draft mode.")
        return redirect("season_overall")

    try:
        draft = SeasonDraft.objects.get(game=game)
    except SeasonDraft.DoesNotExist:
        messages.error(request, "Draft not initialised.")
        return redirect("season_overall")

    player_game = PlayerGame.objects.filter(game=game, user=request.user).first()

    # --- Current slot: next incomplete slot globally (pick_number order = draft order) ---
    # Refresh draft from DB to get latest phase
    draft.refresh_from_db()
    current_slot = (
        DraftSlotSeason.objects.filter(draft=draft, completed=False)
        .order_by("pick_number")
        .select_related("player_game__user", "game_league__league")
        .first()
    )
    current_picker_slot = current_slot
    if player_game and current_slot:
        is_my_turn = current_slot.player_game_id == player_game.id
    else:
        is_my_turn = False

    # --- Handle pick submission ---
    if request.method == "POST" and is_my_turn:
        team_id = request.POST.get("team_id")
        pick_type = request.POST.get("pick_type")
        if team_id and pick_type:
            team = Team.objects.filter(id=team_id).first()
            if team:
                game_league = GameLeague.objects.filter(
                    game=game, league=team.league
                ).first()
                if not game_league:
                    messages.error(request, "League not found for this team.")
                    return redirect("season_draft", game_id=game.id)
                from season.services.draft import submit_draft_pick as _submit
                pick, error = _submit(
                    draft, current_slot, team, player_game, pick_type, game_league
                )
                if error:
                    messages.error(request, error)
                else:
                    messages.success(request, f"Picked {team.name} ({pick_type}).")
                return redirect("season_draft", game_id=game.id)

    # --- Draft order ---
    draft_order = list(
        DraftOrder.objects.filter(draft=draft)
        .order_by("position")
        .select_related("player_game__user")
    )

    # --- Completed picks (recent first for feed) ---
    # Join slots with their actual pick to show team name
    pick_by_number = {
        p.pick_number: p
        for p in PlayerPick.objects.filter(player_game__game=game)
        .select_related("team", "game_league__league", "player_game__user")
    }
    completed_slots = []
    for slot in (
        DraftSlotSeason.objects.filter(draft=draft, completed=True)
        .order_by("-pick_number")
        .select_related("player_game__user", "game_league__league")
    ):
        completed_slots.append({
            "slot": slot,
            "pick": pick_by_number.get(slot.pick_number),
        })

    # --- Teams per league with handicaps and picks ---
    LEAGUE_ORDER = ["Premier League", "Championship", "League One", "League Two"]
    game_leagues = {
        gl.league.name: gl
        for gl in GameLeague.objects.filter(game=game, active=True).select_related("league")
    }
    batch_map = get_latest_batches_map()

    # All picks made so far
    all_picks = list(
        PlayerPick.objects.filter(player_game__game=game)
        .select_related("team", "player_game__user", "game_league__league")
    )

    # My picks (must be after all_picks)
    my_picks = [p for p in all_picks if p.player_game == player_game]

    league_tables = []
    for league_name in LEAGUE_ORDER:
        gl = game_leagues.get(league_name)
        if not gl:
            continue
        batch = batch_map.get(gl.league_id)
        if not batch:
            continue

        rows = StandingsRow.objects.filter(batch=batch).select_related("team")

        teams = []
        for row in rows:
            hcp = Handicap.objects.filter(game_league=gl, team=row.team).first()
            win_pick = next(
                (p for p in all_picks
                 if p.team_id == row.team.id
                 and p.pick_type in [PickType.WIN, PickType.HANDICAP]
                 and p.game_league_id == gl.id), None
            )
            lose_pick = next(
                (p for p in all_picks
                 if p.team_id == row.team.id
                 and p.pick_type == PickType.LOSE
                 and p.game_league_id == gl.id), None
            )
            # Can this team be picked by the current user?
            from season.services.draft import get_available_teams
            # Player can pick from any league they haven't completed yet
            # Find what pick types are still needed for this league
            my_league_picks = [p for p in my_picks if p.game_league_id == gl.id]
            my_pick_types = {p.pick_type for p in my_league_picks}

            if is_my_turn and draft.phase == "win_lose":
                # Can pick WIN if not yet picked win in this league
                can_pick_win = PickType.WIN not in my_pick_types
                # Can pick LOSE if not yet picked lose in this league
                can_pick_lose = PickType.LOSE not in my_pick_types
                avail_for_win = can_pick_win and get_available_teams(
                    draft, gl, PickType.WIN, player_game
                ).filter(id=row.team.id).exists()
                avail_for_lose = can_pick_lose and get_available_teams(
                    draft, gl, PickType.LOSE, player_game
                ).filter(id=row.team.id).exists()
                available = avail_for_win or avail_for_lose
            elif is_my_turn and draft.phase == "handicap":
                can_pick_hcp = PickType.HANDICAP not in my_pick_types
                available = can_pick_hcp and get_available_teams(
                    draft, gl, PickType.HANDICAP, player_game
                ).filter(id=row.team.id).exists()
                avail_for_win = False
                avail_for_lose = False
            else:
                available = False
                avail_for_win = False
                avail_for_lose = False
            teams.append({
                "team": row.team,
                "position": row.position,
                "played": row.played,
                "handicap": hcp.points if hcp else None,
                "win_pick": win_pick,
                "lose_pick": lose_pick,
                "available": available,
                "avail_for_win": avail_for_win,
                "avail_for_lose": avail_for_lose,
            })

        # Sort by handicap value (0 first, then ascending), then position
        teams.sort(key=lambda t: (
            t["handicap"] is None,
            t["handicap"] or 0,
        ))

        league_tables.append({
            "league": gl.league,
            "game_league": gl,
            "teams": teams,
        })

    # --- My picks summary ---
    my_summary = {}
    for lg in LEAGUE_ORDER:
        gl = game_leagues.get(lg)
        if not gl:
            continue
        my_summary[lg] = {
            "win": next((p for p in my_picks if p.game_league_id == gl.id and p.pick_type == PickType.WIN), None),
            "handicap": next((p for p in my_picks if p.game_league_id == gl.id and p.pick_type == PickType.HANDICAP), None),
            "lose": next((p for p in my_picks if p.game_league_id == gl.id and p.pick_type == PickType.LOSE), None),
        }

    # --- Count picks per category per league ---
    pick_counts = {}
    for lg in LEAGUE_ORDER:
        gl = game_leagues.get(lg)
        if not gl:
            continue
        pick_counts[lg] = {
            "win": sum(1 for p in all_picks if p.game_league_id == gl.id and p.pick_type == PickType.WIN),
            "handicap": sum(1 for p in all_picks if p.game_league_id == gl.id and p.pick_type == PickType.HANDICAP),
            "lose": sum(1 for p in all_picks if p.game_league_id == gl.id and p.pick_type == PickType.LOSE),
        }

    return render(request, "season/draft.html", {
        "game": game,
        "draft": draft,
        "draft_phase": draft.phase,
        "current_slot": current_slot,
        "is_my_turn": is_my_turn,
        "player_game": player_game,
        "draft_order": draft_order,
        "completed_slots": completed_slots,
        "league_tables": league_tables,
        "my_summary": my_summary,
        "pick_counts": pick_counts,
        "league_order": LEAGUE_ORDER,
        "PickType": PickType,
    })