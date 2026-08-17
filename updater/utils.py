from django.utils import timezone
from datetime import timedelta
from updater.models import UpdateTracker, LeagueUpdateTracker
from score_predict.models import Fixture, GameInstance, GameTemplate
from season.models import League
from django.core.management import call_command
from django.utils.timezone import now
from datetime import timedelta
from django.db.models import Q
from django.core.management.base import CommandError
import traceback


def maybe_update():
    UPDATE_INTERVAL_MINUTES = 60
    UPDATE_INTERVAL_DAYS = 7
    RESULTS_DELAY_HOURS = 2

    results_updated = False
    tables_updated = False

    for league in League.objects.all():
        tracker, _ = LeagueUpdateTracker.objects.get_or_create(league=league)
        fixtures = Fixture.objects.filter(league_id=league.tournament_id)

        # --- Results ---
        if tracker.should_update_results(fixtures, UPDATE_INTERVAL_MINUTES):
            pending_fixtures = fixtures.filter(
                date__lte=timezone.now() - timedelta(hours=RESULTS_DELAY_HOURS)
            ).exclude(
                status_code__in=[100, 90, 60]
            )
            pending_fixtures = pending_fixtures.exclude(date__gt=now())

            if pending_fixtures.exists():
                print(f"Updating results for {league.name} ({league.code}) - {pending_fixtures.count()} pending fixtures")
                call_command("update_results", league_code=league.code, verbosity=0)
                tracker.last_results_check = timezone.now()
                tracker.save()
                results_updated = True

        # --- Fixtures ---
        if tracker.should_update_fixtures(fixtures, UPDATE_INTERVAL_DAYS):
            call_command("update_fixtures", league_code=league.code, verbosity=0)
            tracker.last_fixtures_check = timezone.now()
            tracker.save()

        # --- Tables ---
        if tracker.should_update_tables(fixtures, interval_minutes=120):
            call_command("fetch_standings", league_code=league.code, verbosity=0)
            tracker.last_tables_check = timezone.now()
            tracker.save()
            tables_updated = True

    # --- Run these once, after all leagues are processed ---
    if results_updated:
        call_command("update_scores", verbosity=0)
        call_command("update_lms_results", verbosity=0)

    # Season scores only update when standings have changed
    # Track standings updates separately from results
    if tables_updated:
        call_command("update_season_scores", verbosity=0)

    # --- Golf rankings: once a month ---
    from golf.utils import maybe_update_rankings, maybe_update_leaderboard
    maybe_update_rankings()

    # --- Golf leaderboard: once daily for in-progress tournaments ---
    maybe_update_leaderboard()

    # --- Season monthly prize: check if a calendar month just ended ---
    try:
        from season.utils.season_helpers import should_mark_month_end
        from django.utils.timezone import now as tz_now
        if should_mark_month_end(tz_now()):
            call_command("finalise_monthly_winners", verbosity=0)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"[season] monthly prize check failed: {e}")