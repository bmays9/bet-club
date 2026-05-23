import threading
import time
import logging
from django.apps import AppConfig

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 300  # check every 5 minutes, but API calls gated by tracker


def background_updater():
    """
    Runs in a background thread after server startup.
    Calls maybe_update() every 5 minutes -- but maybe_update() itself
    only makes real API calls when the LeagueUpdateTracker intervals
    have elapsed, so API usage stays controlled.
    """
    # Wait for Django to fully start before first run
    time.sleep(30)

    while True:
        try:
            from updater.utils import maybe_update
            maybe_update()
        except Exception as e:
            logger.error(f"[updater] background update failed: {e}")

        time.sleep(CHECK_INTERVAL_SECONDS)


class UpdaterConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'updater'

    def ready(self):
        import os
        # Only start the background thread in the main process.
        # Django's dev server runs ready() twice (reloader + main),
        # RUN_MAIN guards against starting two threads in dev.
        if os.environ.get('RUN_MAIN') == 'true' or not os.environ.get('RUN_MAIN'):
            # In production (gunicorn) RUN_MAIN is not set, so always start.
            # In dev, RUN_MAIN='true' means we're in the main process.
            is_dev_main = os.environ.get('RUN_MAIN') == 'true'
            is_production = os.environ.get('RUN_MAIN') is None

            if is_dev_main or is_production:
                t = threading.Thread(
                    target=background_updater,
                    daemon=True,
                    name="background-updater",
                )
                t.start()
                logger.info("[updater] Background update thread started.")
