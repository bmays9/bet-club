from .models import PlayerScoreSnapshot, StandingsRow, PlayerPick, PickType, Handicap, StandingsBatch, PrizePool, PrizePayout, PrizeCategory, PlayerGame, Game
from .utils.season_helpers import (
    get_group_and_game_selection,
    get_latest_batch_ids,
    get_latest_batches_map,
)
from calendar import monthrange, month_name
from collections import OrderedDict
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from decimal import Decimal
from django.shortcuts import render
from django.db.models import Prefetch, Sum, Avg, F, Max, DecimalField, ExpressionWrapper, Value, IntegerField, Case, When
from django.db.models.functions import Cast
from django.utils import timezone
from django.utils.timezone import now
from groups.models import UserGroup
import calendar

CATEGORY_ORDER = [
    "Overall",
    "Leagues",
    "Teams to Win",
    "Teams to Lose",
    "Monthly",
]

# map internal choice values (and some display variants) to our normalized group names
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

def season_overall(request):
    sel = get_group_and_game_selection(request.user, request)
    user_groups = sel["user_groups"]
    selected_group = sel["selected_group"]
    group_games = sel["group_games"]
    selected_game = sel["selected_game"]
    player_games = sel["player_games"]

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
    batch_ids = get_latest_batch_ids()

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

    # All players in a season, with their net totals
    players = PlayerGame.objects.with_net_total(game=selected_game)
    player_map = {pg.user.username: pg for pg in players}

    # Get all payouts for the game once
    all_payouts = PrizePayout.objects.filter(prize_pool__game=selected_game)

    for pgp in PlayerGame.objects.filter(game=selected_game):
        print(f"\n{pgp.user.username}")
        for p in all_payouts:
            won = "Y" if p.recipient_id == pgp.id else "N"
            print(
                f"  Payout: {p}, "
                f"amount={p.amount}, entry_fee={p.entry_fee_per_player}, won={won}"
            )

    # Then show the annotated totals
    for pg in players:
        print(pg.user.username, pg.total_payouts, pg.total_fees, pg.money_total)


    overall_list = []
    for snap in overall:  # overall from PlayerScoreSnapshot aggregation
        username = snap["player_game__user__username"]
        total_points = snap["total"]
        pg = player_map.get(username)

        overall_list.append({
            "username": username,
            "total_points": total_points,
            "total_payouts": getattr(pg, "total_payouts", 0),
            "total_fees": getattr(pg, "total_fees", 0),
            "net_total": getattr(pg, "money_total", 0),
        })

    print ("overall", overall_list)
    print ("league_ranks", league_ranks)
    print ("latest_time", latest_time)
    print ("user_groups", user_groups)
    print ("selected_group", selected_group)
    print ("group_games", group_games)
    print ("selected_game", selected_game)

    return render(request, "season/season_overall.html", {
        "overall": overall_list,
        "league_ranks": league_ranks,
        "latest_time": latest_time,
        "user_groups": user_groups,
        "selected_group": selected_group,
        "group_games": group_games,
        "selected_game": selected_game,
        "players": players,   # annotated player totals
    })


def season_teams_to_win(request):
    sel = get_group_and_game_selection(request.user, request)
    user_groups = sel["user_groups"]
    selected_group = sel["selected_group"]
    group_games = sel["group_games"]
    selected_game = sel["selected_game"]
    player_games = sel["player_games"]

    league_latest_batch = get_latest_batches_map()
    if not league_latest_batch:
        return render(request, "season/towin.html", {
            "teams": [], "worst_teams": [], "batch": None
        })
    
    picks = PlayerPick.objects.filter(
        game_league__league_id__in=league_latest_batch.keys(),
        pick_type__in=[PickType.HANDICAP, PickType.WIN]
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
        "user_groups": user_groups,
        "selected_group": selected_group,
        "group_games": group_games,
        "selected_game": selected_game,
    })


def season_teams_to_lose(request):
    sel = get_group_and_game_selection(request.user, request)
    user_groups = sel["user_groups"]
    selected_group = sel["selected_group"]
    group_games = sel["group_games"]
    selected_game = sel["selected_game"]
    player_games = sel["player_games"]

    league_latest_batch = get_latest_batches_map()
    if not league_latest_batch:
        return render(request, "season/tolose.html", {
            "teams": [], "worst_teams": [], "batch": None
        })

    picks = PlayerPick.objects.filter(
        pick_type="lose",
        game_league__league_id__in=league_latest_batch.keys()
    ).select_related('player_game__user', 'team', 'game_league', 'game_league__league')


    # Get all PlayerPick objects of type 'lose' for the latest batch of each league
    picks = PlayerPick.objects.filter(
        pick_type="lose",
        game_league__league_id__in=league_latest_batch.keys()
    ).select_related('player_game__user', 'team', 'game_league', 'game_league__league')

    # Modifier for leagues with fewer teams
    league_modifier = {
        "Premier League": 1.2105,
        "Championship": 1,
        "League One": 1,
        "League Two": 1
        }

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
        "user_groups": user_groups,
        "selected_group": selected_group,
        "group_games": group_games,
        "selected_game": selected_game,
    })

def season_by_league(request):
    sel = get_group_and_game_selection(request.user, request)
    user_groups = sel["user_groups"]
    selected_group = sel["selected_group"]
    group_games = sel["group_games"]
    selected_game = sel["selected_game"]
    player_games = sel["player_games"]

    batch_ids = get_latest_batch_ids()
    if not batch_ids:
        return render(request, "season/byleagues.html", {"batch": None, "league_data": {}})

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
        {
            "batch": latest_batch,
            "league_data": league_data,
            "user_groups": user_groups,
            "selected_group": selected_group,
            "group_games": group_games,
            "selected_game": selected_game,
            })


def season_my_teams(request):
    sel = get_group_and_game_selection(request.user, request)
    user_groups = sel["user_groups"]
    selected_group = sel["selected_group"]
    group_games = sel["group_games"]
    selected_game = sel["selected_game"]
    player_games = sel["player_games"]

    batch_ids = get_latest_batch_ids()
    if not batch_ids:
        return render(request, "season/myteams.html", {"batch": None, "league_data": {}})
    
    user = request.user

    # Get all picks by this user
    picks = PlayerPick.objects.filter(
        player_game__user=user
    ).select_related(
        "player_game", "team", "game_league__league"
    )

    print("Picks", picks)

    if not picks.exists():
        return render(request, "season/myteams.html", {"picks_data": []})

    # Latest batch for each league
    league_batches = get_latest_batches_map()  # {league_id: batch}

    # Build table rows
    picks_data = []

    for pick in picks:
        league = pick.game_league.league
        batch = league_batches.get(league.id)
        row = pick.team.standings_rows.filter(batch=batch).first() if batch else None

        # Standing info
        position = row.position if row else None
        played = row.played if row else 0
        won = row.wins if row else 0
        drawn = row.draws if row else 0
        lost = row.losses if row else 0
        pure_points = row.pure_points if row else 0

        # Handicap logic
        hcp = pick.team.handicaps.filter(game_league=pick.game_league).first()
        season_games = league.season_games
        handicap_points = hcp.points if hcp else 0
        our_points = pure_points
        if pick.pick_type == "handicap" and hcp:
            our_points += round(handicap_points * played / season_games, 2)

        # Payouts earned by this team for this user
        #payouts = pick.team.payouts.filter(
        #    player_game=pick.player_game
        #).aggregate(total=Sum("amount"))["total"] or 0

        # League rank from snapshots (if available)
        snap = pick.player_game.score_snapshots.filter(
            game_league__league=league, batch=batch
        ).first() if batch else None
        league_rank = snap.league_rank if snap else None

        # Short Pick Type
        short_pick_type = pick.pick_type[0]

        picks_data.append({
            "pick_number": pick.pick_number,
            "team": pick.team,
            "pick_type": short_pick_type,
            "league": league.name,
            "position": position,
            "played": played,
            "won": won,
            "drawn": drawn,
            "lost": lost,
            "pure_points": pure_points,
            "our_points": our_points,
            "handicap": handicap_points,
            # "payouts": payouts,
            "league_rank": league_rank,
        })
        
        # print("picksData", picks_data)

    return render(request, "season/myteams.html", {
        "user_groups": user_groups,
        "selected_group": selected_group,
        "group_games": group_games,
        "selected_game": selected_game,
        "picks_data": picks_data,
    })


def season_monthly(request):
    sel = get_group_and_game_selection(request.user, request)
    selected_game = sel["selected_game"]
    user_groups = sel["user_groups"]
    selected_group = sel["selected_group"]
    group_games = sel["group_games"]
    player_games = sel["player_games"]

    # Determine the current month
    today = now().date()
    first_day, last_day = today.replace(day=1), today.replace(day=monthrange(today.year, today.month)[1])

    # Get latest batch ids for the selected game
    batch_ids = get_latest_batch_ids()  # Returns list of batch IDs across leagues

    if not batch_ids:
        return render(request, "season/monthly.html", {
            "current_month_scores": [],
            "previous_winners": [],
            "user_groups": user_groups,
            "selected_group": selected_group,
            "group_games": group_games,
            "selected_game": selected_game,
        })

    # Current month scores: sum of points per PlayerGame across latest batches
    current_month_scores = (
        PlayerScoreSnapshot.objects
        .filter(batch_id__in=batch_ids, batch__taken_at__date__range=(first_day, last_day))
        .select_related('player_game__user', 'game_league__league')
        .values('player_game_id', 'player_game__user__username')
        .annotate(total_points=Sum('league_total_points'))
        .order_by('-total_points')
    )

    # Previous monthly winners: last awarded month for this game
    previous_winners = (
        PrizePayout.objects
        .filter(
            prize_pool__game=selected_game,
            prize_pool__category=PrizeCategory.MONTH_WINNER,
            recipient__isnull=False
            )
        .select_related('recipient__user', 'prize_pool__game')
        .order_by('-awarded_for_month')
        )

    # Add computed prize values
    previous_winners_with_amounts = []
    for pw in previous_winners:
        num_players = pw.prize_pool.game.players.count()
        prize_amount = pw.calculate_prize(num_players)
        previous_winners_with_amounts.append({
            "awarded_for_month": pw.awarded_for_month,
            "recipient": pw.recipient,
            "amount": prize_amount,
    })

    # Debug prints
    # print("Current Month Scores:")
    # for cms in current_month_scores:
    #     print(cms)

    print("\nPrevious Winners:")
    for pw in previous_winners:
        print(f"Month: {pw.awarded_for_month}, Recipient: {pw.recipient}, Prize: {pw.calculate_prize(pw.prize_pool.game.players.count())}")

    print("\nSelected Group:", selected_group)
    print("Selected Game:", selected_game)
    print("User Groups:", [g.name for g in user_groups])
    print("Group Games:", [g.name for g in group_games])

    return render(request, "season/monthly.html", {
        "current_month_scores": current_month_scores,
        "previous_winners": previous_winners_with_amounts,
        "user_groups": user_groups,
        "selected_group": selected_group,
        "group_games": group_games,
        "selected_game": selected_game,
    })

def prize_summary(request):
    sel = get_group_and_game_selection(request.user, request)
    selected_game = sel["selected_game"]
    user_groups = sel["user_groups"]
    selected_group = sel["selected_group"]
    group_games = sel["group_games"]
    player_games = sel["player_games"]  # queryset or list of PlayerGame for selected_game

    # build empty ordered container using requested order
    grouped = OrderedDict((k, []) for k in CATEGORY_ORDER)

    if not selected_game:
        return render(request, "season/season_money.html", {
            "grouped_payouts": grouped,
            "user_groups": user_groups,
            "selected_group": selected_group,
            "group_games": group_games,
            "selected_game": selected_game,
        })

    # decide how to count players: prefer the player_games selection if provided
    try:
        num_players = player_games.count() if player_games is not None else selected_game.players.count()
    except Exception:
        # fallback if attribute doesn't exist; calling .count() defensively
        try:
            num_players = selected_game.players.count()
        except Exception:
            num_players = 0

    # fetch payouts for this game; prefetch related to avoid N+1 queries
    payouts_qs = PrizePayout.objects.filter(prize_pool__game=selected_game) \
        .select_related(
            "prize_pool",
            "prize_pool__league",
            "recipient__user",
            "winning_pick__team",
        ).order_by("prize_pool__category", "rank")

    # Build grouped data with calculated prize values
    for payout in payouts_qs:
        raw_cat = (payout.prize_pool.category or "").lower().strip()
        normalized = CATEGORY_MAP.get(raw_cat, None)

        # fallback: if prize_pool has a league set, treat it as "Leagues"
        if normalized is None and payout.prize_pool.league_id:
            normalized = "Leagues"

        # fallback to using the prize_pool's display string if nothing matched
        if normalized is None:
            # prefer the human label if available; else raw_cat
            normalized = getattr(payout.prize_pool, "name", raw_cat) or raw_cat or "Other"

        # prepare the item (calculate prize_value here)
        try:
            prize_value = payout.calculate_prize(num_players-1)
        except Exception:
            # defensive: ensure we never crash rendering the page
            prize_value = None

        item = {
            "prize_pool": payout.prize_pool,
            "payout": payout,
            "rank": payout.rank,
            "recipient": payout.recipient,         # PlayerGame or None
            "winning_pick": payout.winning_pick,   # PlayerPick or None
            "league": payout.prize_pool.league,    # League or None (useful for Leagues group)
            "points": payout.points,
            "prize_value": prize_value,
        }

        # ensure category present in grouped (if extra categories exist, append them)
        if normalized not in grouped:
            grouped[normalized] = []
        grouped[normalized].append(item)

    # sort each group's list by rank (None ranks go last)
    for cat, items in grouped.items():
        items.sort(key=lambda it: (it["rank"] is None, it["rank"] or 0))

    # Assign Months
    for item in grouped.get('Monthly', []):
        closing_date = getattr(item['payout'], 'awarded_for_month', None)
        print("closing date", closing_date)
        if closing_date:
            item['month'] = month_name[closing_date.month]  # e.g., "September"
        else:
            item['month'] = None

    category_columns = {
        "Overall": ["rank", "player", "points", "prize_value"],
        "Leagues": ["prize_pool", "player", "points", "prize_value"],
        "Teams to Win": ["rank", "player", "winning_pick", "league", "type",  "points", "prize_value"],
        "Teams to Lose": ["rank", "player", "winning_pick", "league", "points", "prize_value"],
        "Monthly": ["month", "player", "points", "prize_value"],
    }
    
    print("Normalized_Grouped", grouped)
    # Render
    return render(request, "season/season_money.html", {
        'grouped_payouts': grouped,
        "user_groups": user_groups,
        "selected_group": selected_group,
        "group_games": group_games,
        "selected_game": selected_game,
        "num_players": num_players,
        "category_columns": category_columns,
    })