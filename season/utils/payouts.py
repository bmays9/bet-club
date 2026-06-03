# season/utils/payouts.py
from decimal import Decimal
from django.db.models import Sum
from season.models import (
    PrizePool, PrizePayout, PlayerScoreSnapshot,
    PlayerPick, PlayerGame, PickType, StandingsRow, Handicap,
)
from season.utils.season_helpers import get_latest_batches_map


def _epl_adjusted_points(pure_points, league_name):
    """EPL plays 38 games vs 46. Adjust WIN/LOSE picks upward for ranking."""
    pts = Decimal(str(pure_points))
    if league_name == "Premier League":
        return (pts / Decimal("38")) * Decimal("46")
    return pts


def allocate_payouts_for_game(game, batch_map):
    print(f"\n=== Allocating payouts for game {game.id}: {game.name} ===")

    num_players = game.players.count()
    batch_id_list = [b.id for b in batch_map.values()]

    # -------------------------------------------------------
    # Overall standings
    # One snapshot per player per league -- sum across leagues
    # then deduplicate to get one total per player
    # -------------------------------------------------------
    overall_payouts = PrizePayout.objects.filter(
        prize_pool__game=game,
        prize_pool__category="overall",
        rank__isnull=False,
    ).order_by("rank")

    # Build player -> total map (summed across all leagues, one entry per player)
    player_totals = {}
    for snap in PlayerScoreSnapshot.objects.filter(
        player_game__game=game,
        batch_id__in=batch_id_list,
    ).select_related("player_game__user"):
        pid = snap.player_game_id
        player_totals[pid] = player_totals.get(pid, Decimal("0")) + snap.league_total_points

    ranked_players = sorted(player_totals.items(), key=lambda x: x[1], reverse=True)

    for payout in overall_payouts:
        rank_idx = payout.rank - 1
        if rank_idx >= len(ranked_players):
            continue
        target_total = ranked_players[rank_idx][1]
        tied_ids = [pid for pid, total in ranked_players if total == target_total]
        tied_pgs = list(PlayerGame.objects.filter(id__in=tied_ids).select_related("user"))

        # Assign first winner to existing row
        payout.recipient = tied_pgs[0]
        payout.points = target_total
        payout.save(update_fields=["recipient", "points"])
        print(f"  Overall rank {payout.rank}: {tied_pgs[0].user.username}")

    # -------------------------------------------------------
    # League winners
    # Find top scorer per league using latest batch per league
    # -------------------------------------------------------
    league_payouts = PrizePayout.objects.filter(
        prize_pool__game=game,
        prize_pool__category="league_total",
    ).select_related("prize_pool__league")

    for payout in league_payouts:
        league = payout.prize_pool.league
        batch = batch_map.get(league.id)
        if not batch:
            print(f"  No batch for {league.name}")
            continue

        snaps = (
            PlayerScoreSnapshot.objects
            .filter(player_game__game=game, batch_id=batch.id)
            .select_related("player_game__user")
            .order_by("-league_total_points")
        )
        if not snaps.exists():
            print(f"  No snapshots for {league.name}")
            continue

        top_pts = snaps.first().league_total_points
        winners = [s.player_game for s in snaps if s.league_total_points == top_pts]
        # Calculate prize for display but DO NOT overwrite amount --
        # amount is set at game creation and must not change
        prize = payout.entry_fee_per_player * Decimal(str(num_players - 1)) if payout.entry_fee_per_player else (payout.amount or Decimal("0"))

        payout.recipient = winners[0]
        payout.points = top_pts
        payout.save(update_fields=["recipient", "points"])
        print(f"  {league.name} winner: {winners[0].user.username} ({top_pts} pts) prize=GBP{prize}")

    # -------------------------------------------------------
    # Teams to Win -- build ranked list with EPL adjustment
    # -------------------------------------------------------
    win_picks = PlayerPick.objects.filter(
        game_league__game=game,
        pick_type__in=[PickType.WIN, PickType.HANDICAP],
    ).select_related("player_game__user", "team", "game_league__league")

    teams = []
    for pick in win_picks:
        batch = batch_map.get(pick.game_league.league_id)
        if not batch:
            continue
        row = StandingsRow.objects.filter(batch=batch, team=pick.team).first()
        if not row:
            continue
        pure = Decimal(str(row.pure_points))
        league_name = pick.game_league.league.name
        season_games = pick.game_league.league.season_games

        if pick.pick_type == PickType.HANDICAP:
            hcp = Handicap.objects.filter(game_league=pick.game_league, team=pick.team).first()
            if hcp and season_games:
                per_game = Decimal(str(hcp.points)) / Decimal(str(season_games))
                total = pure + per_game * Decimal(str(row.played))
            else:
                total = pure
        else:
            # WIN: apply EPL adjustment
            total = _epl_adjusted_points(pure, league_name)

        teams.append({"pick": pick, "total_points": total})

    teams_sorted = sorted(teams, key=lambda x: x["total_points"], reverse=True)
    print(f"  Teams-to-Win top 5: {[(t['pick'].team.name, round(t['total_points'], 1)) for t in teams_sorted[:5]]}")
    print(f"  Teams-to-Win bot 5: {[(t['pick'].team.name, round(t['total_points'], 1)) for t in teams_sorted[-5:]]}")

    # All payouts in one pool -- positive amount = winner receives,
    # negative amount = that ranked player pays in
    # Positive ranks index from top (rank 1 = best), 
    # negative amounts index from bottom (rank 1 of worst = last place)
    win_payouts = PrizePayout.objects.filter(
        prize_pool__game=game,
        prize_pool__category="teams_to_win",
        rank__isnull=False,
    ).order_by("amount")  # negatives first (worst), then positives (best)

    # Split into positive (best) and negative (worst) payouts
    positive_payouts = [p for p in win_payouts if p.amount and p.amount > 0]
    negative_payouts = [p for p in win_payouts if p.amount and p.amount < 0]

    # Positive payouts: rank 1 = best team (highest points)
    # Sort positives by amount descending (biggest prize = rank 1)
    for i, payout in enumerate(sorted(positive_payouts, key=lambda p: p.amount, reverse=True)):
        if i >= len(teams_sorted):
            continue
        pick = teams_sorted[i]["pick"]
        pts = teams_sorted[i]["total_points"]
        payout.winning_pick = pick
        payout.recipient = pick.player_game
        payout.points = pts
        payout.save(update_fields=["winning_pick", "recipient", "points"])
        print(f"  Teams-to-Win rank {i+1} best: {pick.player_game.user.username} - {pick.team.name} = {round(pts,1)} prize=+GBP{payout.amount}")

    # Negative payouts: rank 1 = worst team (lowest points)
    # Sort negatives by amount ascending (biggest penalty = rank 1 worst)
    for i, payout in enumerate(sorted(negative_payouts, key=lambda p: p.amount)):
        idx = -(i + 1)  # index from end of sorted list
        if abs(idx) > len(teams_sorted):
            continue
        pick = teams_sorted[idx]["pick"]
        pts = teams_sorted[idx]["total_points"]
        payout.winning_pick = pick
        payout.recipient = pick.player_game
        payout.points = pts
        payout.save(update_fields=["winning_pick", "recipient", "points"])
        print(f"  Teams-to-Win rank {i+1} worst: {pick.player_game.user.username} - {pick.team.name} = {round(pts,1)} penalty=GBP{payout.amount}")

    # -------------------------------------------------------
    # Teams to Lose -- EPL adjusted, lowest = best
    # -------------------------------------------------------
    lose_picks = PlayerPick.objects.filter(
        game_league__game=game,
        pick_type=PickType.LOSE,
    ).select_related("player_game__user", "team", "game_league__league")

    lose_teams = []
    for pick in lose_picks:
        batch = batch_map.get(pick.game_league.league_id)
        if not batch:
            continue
        row = StandingsRow.objects.filter(batch=batch, team=pick.team).first()
        if not row:
            continue
        pure = Decimal(str(row.pure_points))
        adj = _epl_adjusted_points(pure, pick.game_league.league.name)
        lose_teams.append({"pick": pick, "total_points": adj})

    lose_sorted = sorted(lose_teams, key=lambda x: x["total_points"])  # lowest first
    print(f"  Teams-to-Lose bottom 5: {[(t['pick'].team.name, round(t['total_points'], 1)) for t in lose_sorted[:5]]}")

    lose_payouts = PrizePayout.objects.filter(
        prize_pool__game=game,
        prize_pool__category="teams_to_lose",
        rank__isnull=False,
    )

    lose_positive = [p for p in lose_payouts if p.amount and p.amount > 0]
    lose_negative = [p for p in lose_payouts if p.amount and p.amount < 0]

    # Best lose pick = lowest points (lose_sorted[0] = worst team in real life)
    for i, payout in enumerate(sorted(lose_positive, key=lambda p: p.amount, reverse=True)):
        if i >= len(lose_sorted):
            continue
        pick = lose_sorted[i]["pick"]
        pts = lose_sorted[i]["total_points"]
        payout.winning_pick = pick
        payout.recipient = pick.player_game
        payout.points = pts
        payout.save(update_fields=["winning_pick", "recipient", "points"])
        print(f"  Teams-to-Lose rank {i+1} best: {pick.player_game.user.username} - {pick.team.name} = {round(pts,1)} prize=+GBP{payout.amount}")

    # Worst lose pick = highest points (team did well, bad pick)
    for i, payout in enumerate(sorted(lose_negative, key=lambda p: p.amount)):
        idx = -(i + 1)
        if abs(idx) > len(lose_sorted):
            continue
        pick = lose_sorted[idx]["pick"]
        pts = lose_sorted[idx]["total_points"]
        payout.winning_pick = pick
        payout.recipient = pick.player_game
        payout.points = pts
        payout.save(update_fields=["winning_pick", "recipient", "points"])
        print(f"  Teams-to-Lose rank {i+1} worst: {pick.player_game.user.username} - {pick.team.name} = {round(pts,1)} penalty=GBP{payout.amount}")
