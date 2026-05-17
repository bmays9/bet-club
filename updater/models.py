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
        return timezone.now() - self.last_results_check >= timezone.timedelta(minutes=interval_minutes)

    def should_update_fixtures(self, interval_days=10):
        if not self.last_fixtures_check:
            return True
        return timezone.now() - self.last_fixtures_check >= timezone.timedelta(days=interval_days)

    def should_update_tables(self, interval_minutes=60):
        if not self.last_tables_check:
            return True
        return timezone.now() - self.last_tables_check >= timezone.timedelta(minutes=interval_minutes)


class LeagueUpdateTracker(models.Model):
    league = models.OneToOneField("season.League", on_delete=models.CASCADE)
    last_fixtures_check = models.DateTimeField(null=True, blank=True)
    last_results_check = models.DateTimeField(null=True, blank=True)
    last_tables_check = models.DateTimeField(null=True, blank=True)

    def should_update_results(self, fixtures, interval_minutes=60):
        if not self.last_results_check:
            return True

        pending = fixtures.filter(
            date__lte=timezone.now(),
            status_code__lt=100
        ).exists()

        return pending and timezone.now() - self.last_results_check >= timezone.timedelta(minutes=interval_minutes)

    def should_update_fixtures(self, interval_days=7):
        if not self.last_fixtures_check:
            return True
        return timezone.now() - self.last_fixtures_check >= timezone.timedelta(days=interval_days)

    def should_update_tables(self, fixtures, interval_minutes=120):
        if not self.last_tables_check:
            return True

        new_results = fixtures.filter(
            date__lte=timezone.now(),
            status_code=100,
            updated_at__gte=self.last_tables_check
        ).exists()

        return new_results and timezone.now() - self.last_tables_check >= timezone.timedelta(minutes=interval_minutes)
