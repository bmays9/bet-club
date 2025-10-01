from django.utils.timezone import now
from calendar import monthrange
from datetime import timedelta
from score_predict.models import Fixture

def should_mark_month_end(batch_time=None):
    """
    Check if the batch should be flagged as a month-end batch.
    A month ends when all fixtures in that calendar month are finished.
    """
    if batch_time is None:
        batch_time = now()

    year = batch_time.year
    month = batch_time.month

    # Last day of this month
    last_day = monthrange(year, month)[1]
    month_end = batch_time.replace(day=last_day, hour=23, minute=59, second=59)

    # Get all fixtures for this month
    fixtures = Fixture.objects.filter(
        date__year=year,
        date__month=month
    )

    if not fixtures.exists():
        return False

    # Find the latest fixture in this month
    last_fixture = fixtures.order_by("-date").first()

    # If our batch is AFTER the last fixture in the month then mark as month end
    return batch_time >= last_fixture.date + timedelta(hours=1)
