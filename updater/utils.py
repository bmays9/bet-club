from django.utils import timezone
from datetime import timedelta
from updater.models import UpdateTracker, LeagueUpdateTracker
from score_predict.models import Fixture, GameInstance, GameTemplate
from season.models import League
from django.core.management import call_command
from django.utils import timezone
from django.db.models import Q

def maybe_update_not():
    # Can delete this
    tracker, _ = UpdateTracker.objects.get_or_create(pk=1)

    UPDATE_INTERVAL_MINUTES = 60
    UPDATE_INTERVAL_DAYS = 7
    RESULTS_DELAY_HOURS = 2

    if tracker.should_update_results(UPDATE_INTERVAL_MINUTES):
        pending_fixtures = Fixture.objects.filter(
            date__lte=timezone.now() - timedelta(hours=RESULTS_DELAY_HOURS),
            status_code__lt=100
        )
        # update all games
        if pending_fixtures.exists(): 
            call_command('update_results', verbosity=0)
            call_command('update_scores', verbosity=0)
            call_command('update_lms_results', verbosity=0)
            tracker.last_results_check = timezone.now()
            tracker.save()

    if tracker.should_update_fixtures(UPDATE_INTERVAL_DAYS):
        call_command('update_fixtures', verbosity=0)
        tracker.last_fixtures_check = timezone.now()
        tracker.save()

    games = GameInstance.objects.filter(
        template__start_date__lt=timezone.now().date(),  # game has started
        winners__isnull=True                             # no winners assigned
    ).distinct()

    #if games.exists():   # ✅ only runs score updates if at least one match
    #    call_command('update_scores', verbosity=0)
    #    call_command('update_lms_results', verbosity=0)

def maybe_update():
    UPDATE_INTERVAL_MINUTES = 60
    UPDATE_INTERVAL_DAYS = 7
    RESULTS_DELAY_HOURS = 2

    for league in League.objects.all():
        tracker, _ = LeagueUpdateTracker.objects.get_or_create(league=league)

        fixtures = Fixture.objects.filter(league_id=league.tournament_id)

        # --- Results ---
        if tracker.should_update_results(fixtures, UPDATE_INTERVAL_MINUTES):
            pending_fixtures = fixtures.filter(
                date__lte=timezone.now() - timedelta(hours=RESULTS_DELAY_HOURS),
                status_code__lt=100
            )
            if pending_fixtures.exists():
                call_command("update_results", league.code, verbosity=0)
                call_command("update_scores", league.code, verbosity=0)
                call_command("update_lms_results", league.code, verbosity=0)
                tracker.last_results_check = timezone.now()
                tracker.save()

        # --- Fixtures ---
        if tracker.should_update_fixtures(UPDATE_INTERVAL_DAYS):
            call_command("update_fixtures", league.code, verbosity=0)
            tracker.last_fixtures_check = timezone.now()
            tracker.save()

        # --- Tables ---
        if tracker.should_update_tables(fixtures, interval_minutes=120):
            call_command("update_tables", league.code, verbosity=0)
            tracker.last_tables_check = timezone.now()
            tracker.save()

            
