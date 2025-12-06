from django.utils import timezone
import random
from lms.models import LMSPick, LMSEntry
from score_predict.models import Fixture

# TODO plug in real standings API
def get_latest_league_table(league_short):
    """
    MUST RETURN:
    [
        {"team_id": 123, "position": 20},
        ...
    ]
    lowest = highest position number
    """
    raise NotImplementedError("Add your league table API call here")


def assign_lowest_team(entry, round_obj):
    """Assign the lowest-ranked available team to the player."""
    standings = get_latest_league_table(entry.game.league)

    # Sort lowest first (highest position number)
    standings_sorted = sorted(standings, key=lambda t: t["position"], reverse=True)

    used_team_ids = set(
        LMSPick.objects.filter(entry=entry).values_list("team_id", flat=True)
    )

    round_team_ids = set(
        list(round_obj.fixtures.values_list("home_team_id", flat=True)) +
        list(round_obj.fixtures.values_list("away_team_id", flat=True))
    )

    for row in standings_sorted:
        team_id = row["team_id"]

        if team_id in used_team_ids:
            continue
        if team_id not in round_team_ids:
            continue

        # Assign auto-pick
        LMSPick.objects.create(
            entry=entry,
            round=round_obj,
            team_id=team_id,
            auto_assigned=True,
        )
        return True

    # No valid team eliminate
    entry.alive = False
    entry.eliminated_round = round_obj.round_number
    entry.save()
    return False


def handle_missing_picks(game, round_obj):
    """Apply no-pick rule on all entries missing a pick *after round closes*."""

    # Only apply if first game cutoff
    if game.deadline_mode != "first_game":
        return

    now = timezone.now()
    earliest_fixture = round_obj.fixtures.order_by("date").first()
    if not earliest_fixture:
        return

    # Round is NOT yet closed
    if now < earliest_fixture.date:
        return

    # Round IS closed  process missing picks
    entries = game.entries.filter(alive=True)
    for entry in entries:
        has_pick = LMSPick.objects.filter(entry=entry, round=round_obj).exists()
        if has_pick:
            continue

        # No pick submitted
        if game.no_pick_rule == "elimination":
            entry.alive = False
            entry.eliminated_round = round_obj.round_number
            entry.save()

        elif game.no_pick_rule == "lowest_team":
            assign_lowest_team(entry, round_obj)
        
        elif game.no_pick_rule == "random_team":
            assign_random_valid_away_team(entry, round_obj)


def assign_random_valid_away_team(entry, round_obj):
    """
    Assign a random AWAY team from round fixtures,
    but only if ALL alive entrants can legally pick that team.
    If no valid team available → eliminate the entrant.
    """

    game = entry.game

    # Only use this logic after Round 1
    #if round_obj.round_number == 1:
    #    return False  # fallback to elimination handled outside

    # --- 1️ Collect all away teams in the round ---
    away_team_ids = list(
        round_obj.fixtures.values_list("away_team_id", flat=True)
    )

    # --- 2️ Get previously picked teams per entrant ---
    alive_entries = game.entries.filter(alive=True)

    entrants_used_teams = {
        e.id: set(
            LMSPick.objects.filter(entry=e).values_list("team_id", flat=True)
        )
        for e in alive_entries
    }

    # --- 3️ Find away teams that are valid for all alive entrants ---
    valid_teams = []
    for team_id in away_team_ids:
        # Team must not have been used by ANY alive entrant
        is_valid_for_all = all(
            team_id not in entrants_used_teams[e.id]
            for e in alive_entries
        )
        if is_valid_for_all:
            valid_teams.append(team_id)

    # --- 4️ Randomly assign from valid teams 
    if valid_teams:
        chosen_team = random.choice(valid_teams)

        LMSPick.objects.create(
            entry=entry,
            round=round_obj,
            team_id=chosen_team,
            auto_assigned=True,
        )
        return True

    # --- No valid team exists so eliminate entrant
    entry.alive = False
    entry.eliminated_round = round_obj.round_number
    entry.save()
    return False