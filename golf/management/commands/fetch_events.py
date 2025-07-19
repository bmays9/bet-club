import requests
from django.core.management.base import BaseCommand
from django.conf import settings
from golf.models import GolfEvent, GolfTour
from datetime import datetime

class Command(BaseCommand):
    help = "Fetches golf events and stores them in the database"

    def handle(self, *args, **kwargs):
        url = "https://golf-leaderboard-data.p.rapidapi.com/calendar/2025"

        headers = {
            "X-RapidAPI-Key": os.environ.get("GOLF_API_KEY"),
            "X-RapidAPI-Host": os.environ.get("GOLF_API_HOST"),
        }

        response = requests.get(url, headers=headers)
        data = response.json().get("results", [])

        for event in data:
            tour_id = event["tour_id"]
            tour, _ = GolfTour.objects.get_or_create(
                tour_id=tour_id,
                defaults={
                    "tour_name": event["tour"],
                    "season_id": event["season_id"],
                    "active": event.get("active", 1),
                }
            )

            GolfEvent.objects.update_or_create(
                event_id=event["id"],
                defaults={
                    "name": event["name"],
                    "start_date": event["start_date"],
                    "end_date": event["end_date"],
                    "course": event.get("course", ""),
                    "tour": tour,
                }
            )

        self.stdout.write(self.style.SUCCESS("Golf events synced successfully."))
