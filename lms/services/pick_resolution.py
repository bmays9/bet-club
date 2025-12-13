# lms/services/pick_resolution.py

from django.utils import timezone
from lms.models import LMSPick, LMSEntry


def assign_missing_picks(game, round_obj):
    """
    Assign auto-picks to alive entries who failed to pick
    once the picking deadline has passed.
    """

    # Only applies to no_pick_rule != elimination
    if game.no_pick_rule != "elimination":
        return

    # Determine deadline = kickoff of first fixture
    first_fixture = round_obj.fixtures.order_by("date").first()
    if not first_fixture or timezone.now() < first_fixture.date:
        return  # Deadline not passed yet

    auto_teams = [
        round_obj.auto_pick_team,
        round_obj.auto_pick_team1,
        round_obj.auto_pick_team2,
        round_obj.auto_pick_team3,
    ]
    auto_teams = [t for t in auto_teams if t]

    if not auto_teams:
        return

    alive_entries = LMSEntry.objects.filter(game=game, alive=True)

    for entry in alive_entries:
        if LMSPick.objects.filter(entry=entry, round=round_obj).exists():
            continue  # already picked

        # Pick first available auto team
        for team in auto_teams:
            if LMSPick.objects.filter(entry=entry, team_name=team).exists():
                continue  # team already used by this entry

            fixture = (
                round_obj.fixtures.filter(away_team=team).first()
                or round_obj.fixtures.filter(home_team=team).first()
            )

            if fixture:
                LMSPick.objects.create(
                    entry=entry,
                    round=round_obj,
                    fixture=fixture,
                    team_name=team,
                    result="PENDING",
                )
                break


def handle_unresolved_postponed_picks(game, round_obj):
    """
    After the round end date, resolve any picks that are still
    pending due to postponed or cancelled fixtures. Assign them a random team
    """

    POSTPONED_STATUS_CODES = (60, 90)
    FINAL_STATUS_CODES = (100,)

    if timezone.now().date() <= round_obj.end_date:
        return  # Too early

    pending_picks = round_obj.picks.filter(result="PENDING")

        # Ordered list of auto-picks
    auto_picks = [
        round_obj.auto_pick_team1,
        round_obj.auto_pick_team2,
        round_obj.auto_pick_team3,
    ]

    # Only fixtures belonging to this round
    round_fixtures = {fx.home_team: fx for fx in round_obj.fixtures.all()}
    round_fixtures.update({fx.away_team: fx for fx in round_obj.fixtures.all()})

    for pick in pending_picks:
        fixture = pick.fixture

        if not fixture:
            continue

        # Skip if fixture is actually playable now
        if fixture.status_code in FINAL_STATUS_CODES:
            continue

        if fixture.status_code not in POSTPONED_STATUS_CODES:
            continue

        # Try auto-picks in order
        for team in auto_picks:
            if not team:
                continue

            new_fixture = round_fixtures.get(team)

            if not new_fixture:
                continue

            # Skip if replacement fixture also postponed/cancelled
            if new_fixture.status_code in POSTPONED_STATUS_CODES:
                continue

            #  Reassign existing pick
            pick.team_name = team
            pick.fixture = new_fixture
            pick.result = "PENDING"
            pick.save()

            break  # Stop after first valid auto-pick


def round_deadline_passed(round_obj):
    game = round_obj.game

    if game.deadline_mode != "first_game":
        return False

    first_fixture = round_obj.fixtures.order_by("date").first()
    return first_fixture and timezone.now() >= first_fixture.date