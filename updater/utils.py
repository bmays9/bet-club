from django.utils import timezone
from datetime import timedelta
from updater.models import UpdateTracker
from score_predict.models import Fixture
from django.core.management import call_command

def maybe_update():
    tracker, _ = UpdateTracker.objects.get_or_create(pk=1)

    UPDATE_INTERVAL_MINUTES = 60
    RESULTS_DELAY_HOURS = 2

    if tracker.should_update_fixtures_results(UPDATE_INTERVAL_MINUTES):
        pending_fixtures = Fixture.objects.filter(
            date__lte=timezone.now() - timedelta(hours=RESULTS_DELAY_HOURS),
            status_code__lt=100
        )
        if pending_fixtures.exists():
            call_command('update_fixtures', verbosity=0)
            call_command('update_results', verbosity=0)
            call_command('update_scores', verbosity=0)
            tracker.last_fixtures_results_check = timezone.now()
            tracker.save()
