# season/payouts.py
from decimal import Decimal
from django.db.models import Max
from season.models import (
    Game, PrizePool, PrizePayout, PlayerScoreSnapshot,
    PlayerPick, PlayerGame, PickType, StandingsRow, Handicap,
)
from season.utils.season_helpers import (
    get_latest_batch_ids,
    get_latest_batches_map,
)


def _epl_adjusted_points(pure_points, league_name):
    """
    EPL teams play 38 games vs 46 in other leagues.
    Adjust EPL pure_points upward so rankings are comparable.
    Only applied for WIN and LOSE picks in ranking tables.
    """
    pts = Decimal(str(pure_points))
    if league_name == "Premier League":
        return (pts / Decimal("38")) * Decimal("46")
    return pts


def _split_payout(payout_obj, winners, prize_total, points_value, extra_fields=None):
    """
    Assign payout to winners, splitting prize equally among tied players.
    Creates additional PrizePayout rows for each tied winner beyond the first.
    """
    if not winners:
        return

    share = (prize_total / len(winners)).quantize(Decimal("0.01"))

    for i, winner in enumerate(winners):
        fields = {
            "amount": share,
            "points": points_value,
            **(extra_fields or {}),
        }
        if i == 0:
            # Update existing payout row
            for k, v in fields.items():
                setattr(payout_obj, k, v)
            if hasattr(winner, "player_game"):
                payout_obj.recipient = winner.player_game
                payout_obj.winning_pick = winner
            else:
                payout_obj.recipient = winner
            payout_obj.save()
        else:
            # Create additional row for each tied winner
            create_kwargs = {
                "prize_pool": payout_obj.prize_pool,
                "rank": payout_obj.rank,
                "amount": share,
                "points": points_value,
            }
            if hasattr(winner, "player_game"):
                create_kwargs["recipient"] = winner.player_game
                create_kwargs["winning_pick"] = winner
            else:
                create_kwargs["recipient"] = winner
            if extra_fields:
                create_kwargs.update(extra_fields)
            PrizePayout.objects.get_or_create(**create_kwargs)


def allocate_payouts_for_game(game, batch_map):
    print(f"\n=== Allocating payouts for game {game.id}: {game.name} ===")

    latest_batch_ids = get_latest_batch_ids()
    num_players = game.players.count()

    # -------------------------------------------------------
    # Overall position
    # -------------------------------------------------------
    overall_payouts = PrizePayout.objects.filter(
        prize_pool__game=game,
        prize_pool__category="overall",
    ).order_by("rank")

    for payout in overall_payouts:
        snapshots = (
            PlayerScoreSnapshot.objects
            .filter(
                player_game__game=game,
                batch_id__in=latest_batch_ids,
                overall_rank=payout.rank,
            )
            .select_related("player_game")
            .distinct()
        )
        if not snapshots.exists():
            print(f"  No snapshot for overall rank {payout.rank}")
            continue

        prize = payout.calculate_prize(num_players)
        points = snapshots.first().overall_total_points
        winners = [s.player_game for s in snapshots]
        _split_payout(payout, winners, prize, points)
        print(f"  Overall rank {payout.rank}: {[str(w) for w in winners]}")

    # -------------------------------------------------------
    # League totals
    # -------------------------------------------------------
    league_payouts = PrizePayout.objects.filter(
        prize_pool__game=game,
        prize_pool__category="league_total",
    ).order_by("rank")

    for payout in league_payouts:
        league = payout.prize_pool.league
        snapshots = (
            PlayerScoreSnapshot.objects
            .filter(
                player_game__game=game,
                batch_id__in=latest_batch_ids,
                league_rank=payout.rank,
                game_league__league=league,
            )
            .select_related("player_game", "game_league__league")
        )
        if not snapshots.exists():
            print(f"  No league winner for {league} rank {payout.rank}")
            continue

        prize = payout.calculate_prize(num_players)
        points = snapshots.first().league_total_points
        winners = [s.player_game for s in snapshots]
        _split_payout(payout, winners, prize, points)
        print(f"  League {league} rank {payout.rank}: {[str(w) for w in winners]}")

    # -------------------------------------------------------
    # Teams to Win (includes handicap)
    # -------------------------------------------------------
    win_picks = PlayerPick.objects.filter(
        game_league__game=game,
        pick_type__in=["win", "handicap"],
    ).select_related("player_game", "game_league", "team", "game_league__league")

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
            hcp = Handicap.objects.filter(
                game_league=pick.game_league, team=pick.team
            ).first()
            if hcp:
                per_game = Decimal(hcp.points) / pick.game_league.league.season_games
                total_points += per_game * Decimal(row.played)
        teams.append({"pick": pick, "total_points": total_points})

    teams_sorted = sorted(teams, key=lambda x: x["total_points"], reverse=True)

    win_payouts = PrizePayout.objects.filter(
        prize_pool__game=game,
        prize_pool__category="teams_to_win",
    ).order_by("rank")

    for payout in win_payouts:
        rank_idx = payout.rank - 1
        if rank_idx >= len(teams_sorted):
            continue
        top_score = teams_sorted[rank_idx]["total_points"]
        # Find all picks tied at this rank
        tied = [t["pick"] for t in teams_sorted if t["total_points"] == top_score]
        prize = payout.calculate_prize(num_players)
        _split_payout(payout, tied, prize, top_score)
        print(f"  Teams-to-Win rank {payout.rank}: {[str(t) for t in tied]}")

    # -------------------------------------------------------
    # Teams to Lose
    # -------------------------------------------------------
    lose_picks = PlayerPick.objects.filter(
        game_league__game=game,
        pick_type="lose",
    ).select_related("player_game", "game_league", "team", "game_league__league")

    worst_teams = []
    for pick in lose_picks:
        batch = batch_map.get(pick.game_league.league_id)
        if not batch:
            continue
        row = StandingsRow.objects.filter(batch=batch, team=pick.team).first()
        if not row:
            continue
        worst_teams.append({"pick": pick, "total_points": Decimal(row.pure_points)})

    worst_teams_sorted = sorted(worst_teams, key=lambda x: x["total_points"])

    lose_payouts = PrizePayout.objects.filter(
        prize_pool__game=game,
        prize_pool__category="teams_to_lose",
    ).order_by("rank")

    for payout in lose_payouts:
        rank_idx = payout.rank - 1
        if rank_idx >= len(worst_teams_sorted):
            continue
        worst_score = worst_teams_sorted[rank_idx]["total_points"]
        tied = [t["pick"] for t in worst_teams_sorted if t["total_points"] == worst_score]
        prize = payout.calculate_prize(num_players)
        _split_payout(payout, tied, prize, worst_score)
        print(f"  Teams-to-Lose rank {payout.rank}: {[str(t) for t in tied]}")
