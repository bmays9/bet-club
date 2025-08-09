# updater/models.py
from django.db import models
from django.utils import timezone

class UpdateTracker(models.Model):
    last_fixtures_check = models.DateTimeField(null=True, blank=True)
    last_results_check = models.DateTimeField(null=True, blank=True)
    last_tables_check = models.DateTimeField(null=True, blank=True)

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
