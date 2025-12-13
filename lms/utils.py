# lms/utils.py
import random
from .models import LMSEntry, LMSPick

def get_auto_pick_teams_for_round(game, created_round, fixtures, count=4):
    """
    Returns a list of `count` randomly shuffled away teams 
    that are valid for ALL alive players in the game.

    Applies only when:
    - round_number > 1
    - deadline_mode = "first_game"
    - no_pick_rule = "random_team"
    """
    print("picking the teams now")
    # RULE GUARD
    #if (
    #    created_round.round_number < 1 or
    #    game.deadline_mode != "first_game" or
    #    game.no_pick_rule != "random_team"
    #):
    #    return []

    # Collect away teams
    away_teams = [fx.away_team for fx in fixtures]
    print("away teams", away_teams)

    # Get alive entries
    alive_entries = LMSEntry.objects.filter(game=game, alive=True)

    valid_teams = []
    for team in away_teams:
        used_in_previous_rounds = LMSPick.objects.filter(
            entry__in=alive_entries,
            team_name=team
        ).exists()

        if not used_in_previous_rounds:
            valid_teams.append(team)

    # No valid teams
    if not valid_teams:
        return []

    # Shuffle & return first 3
    random.shuffle(valid_teams)
    return valid_teams[:count]
