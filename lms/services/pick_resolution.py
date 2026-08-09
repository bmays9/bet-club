# lms/services/pick_resolution.py
from django.utils import timezone
from lms.models import LMSPick, LMSEntry


def assign_missing_picks(game, round_obj):
    """
    Assign auto-picks to alive entries who failed to pick
    once the picking deadline has passed.

    Handles both no_pick_rule values:
    - 'elimination': no auto-pick assigned; elimination handled
      separately in update_lms_results
    - 'random_team': assign pre-defined auto-pick team
    """
    # Only applies to random_team rule -- elimination is handled
    # in update_lms_results by marking entry.alive = False
    if game.no_pick_rule == "elimination":
        return

    # Determine deadline
    if game.deadline_mode == "first_game":
        first_fixture = round_obj.fixtures.order_by("date").first()
        if not first_fixture or timezone.now() < first_fixture.date:
            return  # Deadline not passed yet
    else:
        if timezone.now() < round_obj.end_date:
            return  # Extended deadline not passed

    # Auto-pick teams in priority order
    # auto_pick_team is the primary one for missing picks
    # auto_pick_team1/2/3 are backups for postponed fixtures
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
            continue  # Already has a pick

        # Find first auto team this entry hasn't used before
        for team in auto_teams:
            if LMSPick.objects.filter(entry=entry, team_name=team).exists():
                continue  # Already used this team in a previous round

            fixture = (
                round_obj.fixtures.filter(away_team=team).first()
                or round_obj.fixtures.filter(home_team=team).first()
            )

            if not fixture:
                continue

            LMSPick.objects.create(
                entry=entry,
                round=round_obj,
                fixture=fixture,
                team_name=team,
                auto_assigned=True,
                result="PENDING",
            )
            break


def handle_unresolved_postponed_picks(game, round_obj):
    """
    After the round end date, resolve any picks still pending
    due to postponed or cancelled fixtures.
    Reassigns them to the best available auto-pick backup.
    """
    POSTPONED_STATUS_CODES = (60, 90)
    FINAL_STATUS_CODES = (100,)

    if not round_obj.end_date:
        return

    if timezone.now() <= round_obj.end_date:
        return  # Too early

    pending_picks = round_obj.picks.filter(result="PENDING")
    if not pending_picks.exists():
        return

    # Backup auto-picks for postponed replacements
    auto_picks = [
        round_obj.auto_pick_team1,
        round_obj.auto_pick_team2,
        round_obj.auto_pick_team3,
    ]

    # Build team -> fixture map for this round
    round_fixtures = {}
    for fx in round_obj.fixtures.all():
        round_fixtures[fx.home_team] = fx
        round_fixtures[fx.away_team] = fx

    for pick in pending_picks:
        fixture = pick.fixture
        if not fixture:
            continue

        # Skip if fixture actually finished
        if fixture.status_code in FINAL_STATUS_CODES:
            continue

        # Only reassign postponed/cancelled fixtures
        if fixture.status_code not in POSTPONED_STATUS_CODES:
            continue

        # Find a valid replacement from auto-picks
        for team in auto_picks:
            if not team:
                continue

            # Don't assign a team the entry already used
            if LMSPick.objects.filter(
                entry=pick.entry, team_name=team
            ).exclude(id=pick.id).exists():
                continue

            new_fixture = round_fixtures.get(team)
            if not new_fixture:
                continue

            if new_fixture.status_code in POSTPONED_STATUS_CODES:
                continue  # Replacement also postponed

            pick.team_name = team
            pick.fixture = new_fixture
            pick.result = "PENDING"
            pick.auto_assigned = True
            pick.save(update_fields=["team_name", "fixture", "result", "auto_assigned"])
            break


def round_deadline_passed(round_obj):
    """Returns True if the pick deadline for this round has passed."""
    game = round_obj.game

    if game.deadline_mode == "first_game":
        first_fixture = round_obj.fixtures.order_by("date").first()
        return bool(first_fixture and timezone.now() >= first_fixture.date)
    else:
        return round_obj.end_date and timezone.now() >= round_obj.end_date
