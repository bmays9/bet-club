# season/views.py
from .models import (
    PlayerScoreSnapshot, StandingsRow, PlayerPick, PickType,
    Handicap, StandingsBatch, PrizePool, PrizePayout,
    PrizeCategory, PlayerGame, Game, GameLeague,
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
from django.shortcuts import render
from django.db.models import Sum, Max
from django.utils.timezone import now
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
    player_games = sel["player_games"]

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


    print("\n=== SEASON SUMMARY MONEY BREAKDOWN ===")

    for pg in players:
        print(f"\n{pg.user.username}")

        payouts = PrizePayout.objects.filter(
            recipient=pg
        ).select_related("prize_pool")

        payout_total = Decimal("0")

        for payout in payouts:
            amount = payout.amount or Decimal("0")
            payout_total += amount
    
            print(
                f"  PAYOUT | "
                f"pool={payout.prize_pool.name} | "
                f"category={payout.prize_pool.category} | "
                f"amount={amount}"
            )

        print(f"  TOTAL PAYOUTS = {payout_total}")
        print(f"  QUERYSET PAYOUTS = {getattr(pg, 'total_payouts', 0)}")
        print(f"  FEES = {getattr(pg, 'total_fees', 0)}")
        print(f"  NET = {getattr(pg, 'money_total', 0)}")

    print("\n=====================================")


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
