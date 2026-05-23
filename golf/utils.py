# golf/utils.py
from django.utils import timezone
from datetime import timedelta, datetime


GOLF_EVENT_REFRESH_DAYS = 7
GOLF_RANKINGS_REFRESH_DAYS = 30


def maybe_fetch_golf_events():
    """
    Fetch upcoming golf events from the API at most once per week.
    Also re-fetches automatically if the calendar year has changed since last fetch.
    """
    from updater.models import UpdateTracker
    from django.core.management import call_command

    tracker, _ = UpdateTracker.objects.get_or_create(pk=1)
    current_year = datetime.now().year

    last_check = tracker.last_golf_events_check
    year_changed = last_check and last_check.year < current_year
    interval_passed = last_check and (
        timezone.now() - last_check >= timedelta(days=GOLF_EVENT_REFRESH_DAYS)
    )

    if not last_check or interval_passed or year_changed:
        try:
            call_command("fetch_golf_events", year=current_year, verbosity=0)
            tracker.last_golf_events_check = timezone.now()
            tracker.save(update_fields=["last_golf_events_check"])
            print(f"[golf] fetched {current_year} events OK")
            return True
        except Exception as e:
            print(f"[golf] fetch_golf_events failed: {e}")
            return False

    return False


def maybe_update_rankings():
    """
    Update world rankings at most once per month.
    Called from updater/utils.py as part of the regular update cycle.
    """
    from updater.models import UpdateTracker
    from django.core.management import call_command

    tracker, _ = UpdateTracker.objects.get_or_create(pk=1)
    last_check = tracker.last_golf_rankings_check

    if not last_check or (
        timezone.now() - last_check >= timedelta(days=GOLF_RANKINGS_REFRESH_DAYS)
    ):
        try:
            call_command("update_world_rankings", verbosity=0)
            tracker.last_golf_rankings_check = timezone.now()
            tracker.save(update_fields=["last_golf_rankings_check"])
            print("[golf] world rankings updated OK")
            return True
        except Exception as e:
            print(f"[golf] update_world_rankings failed: {e}")
            return False

    return False

def maybe_update_leaderboard():
    """
    Update leaderboard scores once daily for any golf event currently in progress
    that has an active game. Never calls the API more than once per 24 hours.
    """
    import logging
    from django.utils import timezone
    from django.core.management import call_command
    from updater.models import UpdateTracker
    from golf.models import GolfEvent, GolfGame

    logger = logging.getLogger(__name__)

    tracker, _ = UpdateTracker.objects.get_or_create(id=1)

    # Gate: max once per 24 hours
    if (tracker.last_golf_rankings_check and
            timezone.now() - tracker.last_golf_rankings_check < timezone.timedelta(hours=24)):
        return

    # Find events that are currently in progress (start_date passed, end_date not yet)
    today = timezone.now()
    active_events = GolfEvent.objects.filter(
        start_date__lte=today,
        end_date__gte=today,
    ).select_related("tour")

    if not active_events.exists():
        logger.info("[golf] No active events for leaderboard update")
        return

    # Only call API if there is an active game for this event
    events_with_games = active_events.filter(
        golf_games__status__in=[GolfGame.Status.ACTIVE, GolfGame.Status.FINISHED],
    ).distinct()

    if not events_with_games.exists():
        logger.info("[golf] Active events found but no active games -- skipping leaderboard")
        return

    updated = 0
    for event in events_with_games:
        try:
            call_command("update_leaderboard", event_id=event.tourn_id, verbosity=0)
            updated += 1
            logger.info(f"[golf] Updated leaderboard for {event.name}")
        except Exception as e:
            logger.error(f"[golf] Leaderboard update failed for {event.name}: {e}")

    if updated:
        tracker.last_golf_rankings_check = timezone.now()
        tracker.save(update_fields=["last_golf_rankings_check"])
