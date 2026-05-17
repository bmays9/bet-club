# golf/services/scoring.py
"""
Scoring and settlement logic:
  - update_pick_scores()     -- updates DraftPick scores from GolferScore data
  - check_cut()              -- marks made_cut on DraftPick after round 2
  - settle_game()            -- called at tournament end, pays out via apply_batch
"""

from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from golf.models import (
    GolfGame, GolfGameEntry, DraftPick, GolferScore,
    EventEntry, RolloverPot, GolfGameResult,
)
from bank.services import apply_batch


CUT_ROUND = 2  # cut determined after round 2


def update_pick_scores(game):
    """
    For each DraftPick in the game, sum all completed round scores
    and update total_strokes. Also flags tournament winner.
    """
    picks = DraftPick.objects.filter(game=game).select_related("golfer", "game_entry")

    # Find the tournament leader (lowest total strokes among those who made cut)
    winner_golfer_id = None
    if game.event.status.lower() in ("finished", "complete", "official"):
        # Get the golfer with position "1" or "T1"
        leader = (
            GolferScore.objects
            .filter(event=game.event, round=4)
            .order_by("position")
            .first()
        )
        if leader:
            winner_golfer_id = leader.golfer_id

    for pick in picks:
        rounds = GolferScore.objects.filter(golfer=pick.golfer, event=game.event)
        if rounds.exists():
            total = sum(r.score for r in rounds if r.score is not None)
            pick.total_strokes = total
            pick.is_tournament_winner = (pick.golfer_id == winner_golfer_id)
            pick.save(update_fields=["total_strokes", "is_tournament_winner"])


def check_cut(game):
    """
    After round 2 completes, determine which golfers made/missed the cut.
    Updates DraftPick.made_cut and GolfGameEntry.total_fines.
    """
    if not game.event.current_round or game.event.current_round < CUT_ROUND + 1:
        return  # Cut not yet determined

    picks = DraftPick.objects.filter(game=game).select_related("golfer", "game_entry")

    for pick in picks:
        if pick.made_cut is not None:
            continue  # already determined

        entry = EventEntry.objects.filter(
            event=game.event, golfer=pick.golfer
        ).first()

        if not entry:
            continue

        # Missed cut: status contains "cut", "wd", "dq" or made_cut=False
        status_lower = entry.status.lower()
        missed = (
            entry.made_cut is False
            or any(s in status_lower for s in ["cut", "wd", "dq", "withdraw"])
        )

        pick.made_cut = not missed
        pick.save(update_fields=["made_cut"])

        if missed:
            game_entry = pick.game_entry
            game_entry.total_fines += game.missed_cut_fine
            game_entry.save(update_fields=["total_fines"])


@transaction.atomic
def settle_game(game):
    """
    Called at tournament end. Handles:
    1. Score each player's best N golfers -> rank players
    2. Main pot -> winner takes all (entry fees)
    3. Secondary pot -> player who picked the tournament winner
       (or rolls over to next game in the group)
    4. Fines -> deducted from each player's balance per missed golfer
    5. GolfGameResult rows created for draft order next time
    6. RolloverPot updated
    7. game.status = FINISHED
    """

    entries = list(game.game_entries.select_related("user"))
    if not entries:
        return

    # -- 1. Score each player ------------------------------------------
    scoring_picks = game.scoring_picks  # best N count (default 3)

    player_scores = []
    for entry in entries:
        picks = (
            DraftPick.objects
            .filter(game_entry=entry, made_cut=True)
            .exclude(total_strokes=None)
            .order_by("total_strokes")
        )
        best = list(picks[:scoring_picks])
        score = sum(p.total_strokes for p in best) if best else 9999
        player_scores.append((entry, score))

    player_scores.sort(key=lambda x: x[1])  # lowest strokes wins

    # Assign ranks (handle ties)
    rank = 1
    for i, (entry, score) in enumerate(player_scores):
        if i > 0 and score != player_scores[i - 1][1]:
            rank = i + 1
        entry.final_score = score
        entry.final_rank = rank
        entry.save(update_fields=["final_score", "final_rank"])

    # -- 2. Main pot ---------------------------------------------------
    all_users = [e.user for e in entries]
    winner_entry, _ = player_scores[0]
    main_pot = game.entry_fee * len(entries)

    # Handle tied winners -- split pot
    top_score = player_scores[0][1]
    winners = [e.user for e, s in player_scores if s == top_score]

    apply_batch(
        group=game.group,
        entrants=all_users,
        winners=winners,
        entry_fee=game.entry_fee,
        prize_pool=main_pot,
        description=f"Golf Main Pot - {game.event.name} ({game.group.name})",
    )

    # -- 3. Fines -> secondary pot --------------------------------------
    total_fines = sum(e.total_fines for e in entries)

    # Charge each player their fines
    for entry in entries:
        if entry.total_fines > 0:
            apply_batch(
                group=game.group,
                entrants=[entry.user],
                winners=[],
                entry_fee=entry.total_fines,
                prize_pool=Decimal("0.00"),
                description=(
                    f"Golf Missed Cut Fines - {game.event.name} "
                    f"({entry.total_fines / game.missed_cut_fine:.0f} golfer(s))"
                ),
            )

    # -- 4. Secondary pot payout ---------------------------------------
    rollover, _ = RolloverPot.objects.get_or_create(group=game.group)
    secondary_pot = total_fines + rollover.balance + game.rollover_amount

    # Find who picked the tournament winner
    winning_pick = DraftPick.objects.filter(
        game=game, is_tournament_winner=True
    ).select_related("game_entry__user").first()

    if winning_pick and secondary_pot > 0:
        secondary_winner = winning_pick.game_entry.user
        apply_batch(
            group=game.group,
            entrants=[],       # fines already collected above
            winners=[secondary_winner],
            entry_fee=Decimal("0.00"),
            prize_pool=secondary_pot,
            description=(
                f"Golf Secondary Pot - {game.event.name} "
                f"(picked tournament winner {winning_pick.golfer.full_name})"
            ),
        )
        rollover.balance = Decimal("0.00")
    else:
        # Roll over to next game
        rollover.balance = secondary_pot

    rollover.last_event = game.event
    rollover.save()

    # Pass rollover forward to the next open game in this group
    next_game = (
        GolfGame.objects
        .filter(group=game.group, status=GolfGame.Status.OPEN)
        .exclude(id=game.id)
        .order_by("event__start_date")
        .first()
    )
    if next_game and rollover.balance > 0:
        next_game.rollover_amount = rollover.balance
        next_game.save(update_fields=["rollover_amount"])

    # -- 5. GolfGameResult ---------------------------------------------
    for entry, score in player_scores:
        won_secondary = (
            secondary_pot if (
                winning_pick and winning_pick.game_entry == entry and rollover.balance == 0
            ) else Decimal("0.00")
        )
        won_main = main_pot / len(winners) if entry.user in winners else Decimal("0.00")

        GolfGameResult.objects.update_or_create(
            game=game,
            user=entry.user,
            defaults={
                "final_rank": entry.final_rank,
                "final_score": score,
                "main_pot_won": won_main,
                "secondary_pot_won": won_secondary,
                "fines_paid": entry.total_fines,
            },
        )

    # -- 6. Mark game finished -----------------------------------------
    game.status = GolfGame.Status.FINISHED
    game.save(update_fields=["status"])