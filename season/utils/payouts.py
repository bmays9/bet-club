from decimal import Decimal
from django.db.models import Max
from season.models import (
    Game,
    PrizePool,
    PrizePayout,
    PlayerScoreSnapshot,
    PlayerPick,
    PlayerGame,
    PickType,
    StandingsRow,
    Handicap
)

from season.utils.season_helpers import (
    get_group_and_game_selection,
    get_latest_batch_ids,
    get_latest_batches_map,
)

def allocate_payouts_for_game(game, batch_map):
    print(f"\n=== Allocating payouts for game {game.id}: {game.name} ===")

    payouts = PrizePayout.objects.filter(prize_pool__game=game).order_by('rank')
    print(f"Found {payouts.count()} payouts")

    latest_batch_ids = get_latest_batch_ids()

    # --- Overall (across all leagues) ---
    overall_payouts = payouts.filter(prize_pool__category="overall")
    print(f"Overall payouts {overall_payouts.count()}")
    
    for payout in overall_payouts:
        winners = (
            PlayerScoreSnapshot.objects.filter(
            player_game__game=game,
            batch_id__in=latest_batch_ids,   # only the latest snapshots
            overall_rank=payout.rank
        )
        .select_related("player_game")
        .values("player_game_id", "overall_total_points")   # only unique players
        .distinct()
        )

        if not winners.exists():
            print(f"No snapshot found for overall rank {payout.rank}")
            continue

        for w in winners:
            print("w in winner", w)
            pg = PlayerGame.objects.get(id=w["player_game_id"])
            payout.recipient = pg
            payout.points = w.get("overall_total_points")
            payout.save(update_fields=["recipient", "points"])
            print(f"Overall {payout} assigned to {pg}")

    # --- League Totals ---
    league_payouts = payouts.filter(prize_pool__category="league_total")
    print(f"League payouts: {league_payouts.count()}")
    print(f"latest batch ids: ", latest_batch_ids)
    for payout in league_payouts:
        print("Payout", payout)

        # Get latest snapshots for all leagues
        latest_snapshots = PlayerScoreSnapshot.objects.filter(
            player_game__game=game,
            batch_id__in=latest_batch_ids,
            league_rank=1,
            game_league__league=payout.prize_pool.league
        ).select_related("player_game", "game_league__league")

        print(f"latest snapshots", latest_snapshots)
        if not latest_snapshots.exists():
            print(f"No league winners found for payout {payout}")
            continue

        for snap in latest_snapshots:
            print("snap in latest snaps for leagues", snap)
            # Calculate prize
            num_players = snap.player_game.game.players.count()
            prize_amount = payout.calculate_prize(num_players)

            # Assign the payout
            payout.recipient = snap.player_game
            payout.amount = prize_amount
            payout.points = snap.league_total_points
            payout.save(update_fields=["recipient", "amount", "points"])
            print(f"League -> {payout} assigned to {snap.player_game} (prize: {prize_amount})")

    # --- Teams to Win (includes handicap) ---
    win_payouts = payouts.filter(prize_pool__category="teams_to_win")
    print(f"TeamstoWin payouts {win_payouts.count()}")
    
    # Fetch all win/handicap picks for this game
    win_picks = PlayerPick.objects.filter(
        game_league__game=game,
        pick_type__in=["win", "handicap"]
    ).select_related("player_game", "game_league", "team", "game_league__league")
    
    # Build a list with total_points for each pick
    teams = []
    for pick in win_picks:
        batch = batch_map.get(pick.game_league.league_id)
        if not batch:
            continue
    
        row = StandingsRow.objects.filter(batch=batch, team=pick.team).first()
        if not row:
            continue
    
        total_points = Decimal(row.pure_points)
        if pick.pick_type == "handicap":
            hcp = Handicap.objects.filter(game_league=pick.game_league, team=pick.team).first()
            if hcp:
                per_game = Decimal(hcp.points) / pick.game_league.league.season_games
                total_points += per_game * Decimal(row.played)
    
        teams.append({
            "pick": pick,
            "total_points": total_points
        })

    # Sort descending by total_points
    teams_sorted = sorted(teams, key=lambda x: x["total_points"], reverse=True)

    # Assign payouts by rank
    win_payouts = payouts.filter(prize_pool__category="teams_to_win").order_by("rank")
    for payout in win_payouts:
        if payout.rank - 1 < len(teams_sorted):
            top_team = teams_sorted[payout.rank - 1]["pick"]
            payout.winning_pick = top_team
            payout.recipient = top_team.player_game
            payout.points = teams_sorted[payout.rank - 1]["total_points"]
            payout.save(update_fields=["winning_pick", "points", "recipient"])
            print(f"Teams-to-Win -> {payout} assigned to {top_team} with recipient { top_team.player_game } ")
    
    # --- Teams to Lose ---
    lose_payouts = payouts.filter(prize_pool__category="teams_to_lose")
    print(f"TeamstoLose payouts: {lose_payouts.count()}")
    # Fetch all lose picks for this game
    lose_picks = PlayerPick.objects.filter(
        game_league__game=game,
        pick_type="lose"
    ).select_related("player_game", "game_league", "team", "game_league__league")
    
    # Build a list with total_points for each pick
    worst_teams = []
    for pick in lose_picks:
        batch = batch_map.get(pick.game_league.league_id)
        if not batch:
            continue

        row = StandingsRow.objects.filter(batch=batch, team=pick.team).first()
        if not row:
            continue

        total_points = Decimal(row.pure_points)
        worst_teams.append({
            "pick": pick,
            "total_points": total_points
        })

    # Sort ascending by total_points (worst teams first)
    worst_teams_sorted = sorted(worst_teams, key=lambda x: x["total_points"])
    
    # Assign payouts by rank
    lose_payouts = payouts.filter(prize_pool__category="teams_to_lose").order_by("rank")
    for payout in lose_payouts:
        if payout.rank - 1 < len(worst_teams_sorted):
            worst_team = worst_teams_sorted[payout.rank - 1]["pick"]
            payout.winning_pick = worst_team
            payout.recipient = worst_team.player_game
            payout.points = worst_teams_sorted[payout.rank - 1]["total_points"]
            payout.save(update_fields=["winning_pick", "points", "recipient"])
            print(f"Teams-to-Lose -> {payout} assigned to {worst_team}")
