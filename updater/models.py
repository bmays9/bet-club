# updater/models.py
from django.db import models
from django.utils import timezone


class UpdateTracker(models.Model):
    last_fixtures_check = models.DateTimeField(null=True, blank=True)
    last_results_check = models.DateTimeField(null=True, blank=True)
    last_tables_check = models.DateTimeField(null=True, blank=True)
    last_golf_events_check = models.DateTimeField(null=True, blank=True)
    last_golf_rankings_check = models.DateTimeField(null=True, blank=True)

    def should_update_results(self, interval_minutes=60):
        if not self.last_results_check:
            return True
        return (
            timezone.now() - self.last_results_check
            >= timezone.timedelta(minutes=interval_minutes)
        )

    def should_update_fixtures(self, interval_days=10):
        if not self.last_fixtures_check:
            return True
        return (
            timezone.now() - self.last_fixtures_check
            >= timezone.timedelta(days=interval_days)
        )

    def should_update_tables(self, interval_minutes=60):
        if not self.last_tables_check:
            return True
        return (
            timezone.now() - self.last_tables_check
            >= timezone.timedelta(minutes=interval_minutes)
        )


class LeagueUpdateTracker(models.Model):
    league = models.OneToOneField("season.League", on_delete=models.CASCADE)
    last_fixtures_check = models.DateTimeField(null=True, blank=True)
    last_results_check = models.DateTimeField(null=True, blank=True)
    last_tables_check = models.DateTimeField(null=True, blank=True)

    def should_update_results(self, fixtures, interval_minutes=60):
        """
        Only call results API if:
        - There are fixtures that have kicked off but aren't finished yet
        - AND enough time has passed since last check
        Never calls API if no fixtures have started.
        """
        # Never update if no fixtures have kicked off
        started_unfinished = fixtures.filter(
            date__lte=timezone.now(),
            status_code__lt=100,
        ).exclude(
            status_code__in=[90, 60]  # exclude abandoned/postponed
        ).exists()

        if not started_unfinished:
            return False

        if not self.last_results_check:
            return True

        return (
            timezone.now() - self.last_results_check
            >= timezone.timedelta(minutes=interval_minutes)
        )

    def should_update_fixtures(self, fixtures, interval_days=7):
        """
        Only refresh fixture list if:
        - Never checked before, OR
        - Interval has passed AND there are upcoming fixtures within 2 weeks
          (no point refreshing if season is over or on a long break)
        """
        if not self.last_fixtures_check:
            return True

        interval_passed = (
            timezone.now() - self.last_fixtures_check
            >= timezone.timedelta(days=interval_days)
        )
        if not interval_passed:
            return False

        # Only refresh if there are upcoming fixtures in the next 14 days
        # or no future fixtures at all (need to fetch next batch)
        future_fixtures = fixtures.filter(
            date__gt=timezone.now(),
            date__lt=timezone.now() + timezone.timedelta(days=14),
        )
        # If we have plenty of upcoming fixtures, no urgent need to refresh
        if future_fixtures.count() >= 5:
            return False

        return True

    def should_update_tables(self, fixtures, interval_minutes=120):
        """
        Only fetch standings if:
        - Fixtures have finished since the last standings check
        - AND enough time has passed since last check
        Never calls API if no new results since last table fetch.
        """
        if not self.last_tables_check:
            # Only fetch if any fixture has ever finished
            return fixtures.filter(status_code=100).exists()

        # Only update if there are newly finished fixtures since last check
        new_results = fixtures.filter(
            status_code=100,
            updated_at__gte=self.last_tables_check,
        ).exists()

        if not new_results:
            return False

        return (
            timezone.now() - self.last_tables_check
            >= timezone.timedelta(minutes=interval_minutes)
        )
