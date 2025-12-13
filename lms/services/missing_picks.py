from django.utils import timezone
import random
from lms.models import LMSPick, LMSEntry
from score_predict.models import Fixture
from lms.services.pick_resolution import round_deadline_passed


#Once a round is closed, ensure every alive entry has a pick, using pre-defined auto-picks.”

def handle_missing_picks(game, round_obj):
    if not round_deadline_passed(round_obj):
        return

    for entry in game.entries.filter(alive=True):
        if LMSPick.objects.filter(entry=entry, round=round_obj).exists():
            continue

        if game.no_pick_rule == "elimination":
            eliminate_entry(entry, round_obj)
            continue

        if game.no_pick_rule == "random_team":
            # handled centrally
            continue


def assign_missing_picks(game, round_obj):
    """
    Assign auto-picks for alive entries with no pick once the round is closed.
    Safe to call multiple times.
    """

    now = timezone.now()

    # ----------------------------
    # 1️⃣ Is the round closed?
    # ----------------------------
    round_closed = False

    if game.deadline_mode == "first_game":
        round_closed = round_obj.start_date <= now
    else:
        # extended deadline — only enforce after round end
        round_closed = round_obj.end_date < now

    if not round_closed:
        return  # nothing to do yet

    # ----------------------------
    # 2️⃣ Get auto-pick teams
    # ----------------------------
    auto_teams = [
        round_obj.auto_pick_team_1,
        round_obj.auto_pick_team_2,
        round_obj.auto_pick_team_3,
    ]
    auto_teams = [t for t in auto_teams if t]

    if not auto_teams:
        return  # no auto-picks configured

    # ----------------------------
    # 3️⃣ Alive entries with no pick
    # ----------------------------
    alive_entries = game.entries.filter(alive=True)

    missing_entries = [
        entry for entry in alive_entries
        if not LMSPick.objects.filter(entry=entry, round=round_obj).exists()
    ]

    if not missing_entries:
        return

    # ----------------------------
    # 4️⃣ Assign picks in order
    # ----------------------------
    team_index = 0

    for entry in missing_entries:
        team_name = auto_teams[team_index % len(auto_teams)]

        fixture = round_obj.fixtures.filter(
            away_team=team_name
        ).first()

        if not fixture:
            continue  # safety — should not happen

        LMSPick.objects.create(
            entry=entry,
            round=round_obj,
            fixture=fixture,
            team_name=team_name,
            result="PENDING",
        )

        team_index += 1