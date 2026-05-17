import os
import requests
from django.core.management.base import BaseCommand
from golf.models import GolfEvent, GolfTour
from datetime import datetime, timezone


class Command(BaseCommand):
    help = "Fetches golf events and stores them in the database"

    def add_arguments(self, parser):
        parser.add_argument(
            "--year",
            type=int,
            default=None,
            help="Season year to fetch (defaults to current year)",
        )

    def handle(self, *args, **kwargs):
        year = kwargs.get("year") or datetime.now().year

        RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
        HEADERS = {
            "X-RapidAPI-Key": RAPIDAPI_KEY,
            "X-RapidAPI-Host": "live-golf-data.p.rapidapi.com",
        }

        tours = [
            {"name": "PGA Tour", "orgId": "1"},
            {"name": "LIV Tour", "orgId": "2"},
        ]

        for tour_info in tours:
            self.stdout.write(f"Fetching {tour_info['name']} schedule for {year}...")

            url = "https://live-golf-data.p.rapidapi.com/schedule"
            querystring = {"orgId": tour_info["orgId"], "year": str(year)}

            try:
                response = requests.get(url, headers=HEADERS, params=querystring, timeout=30)
                response.raise_for_status()
                data = response.json()
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to fetch {tour_info['name']}: {e}"))
                continue

            schedule = data.get("schedule", [])
            if not schedule:
                self.stdout.write(self.style.WARNING(f"No schedule data for {tour_info['name']}"))
                continue

            tour, _ = GolfTour.objects.update_or_create(
                tour_id=int(tour_info["orgId"]),
                defaults={"season_id": year, "tour_name": tour_info["name"]},
            )

            created_count = 0
            updated_count = 0

            for event_data in schedule:
                try:
                    tourn_id = event_data.get("tournId")
                    name = event_data.get("name")

                    if not tourn_id or not name:
                        continue

                    # Parse dates from UNIX timestamp in milliseconds
                    start_ts = int(event_data["date"]["start"]["$date"]["$numberLong"]) / 1000
                    end_ts = int(event_data["date"]["end"]["$date"]["$numberLong"]) / 1000
                    start_date = datetime.fromtimestamp(start_ts, tz=timezone.utc)
                    end_date = datetime.fromtimestamp(end_ts, tz=timezone.utc)

                    purse_raw = event_data.get("purse", {})
                    purse = int(purse_raw.get("$numberInt", 0)) if isinstance(purse_raw, dict) else 0
                    week_number = int(event_data["date"].get("weekNumber", 0))

                    event, created = GolfEvent.objects.update_or_create(
                        tourn_id=tourn_id,
                        defaults={
                            "name": name,
                            "tour": tour,
                            "year": year,
                            "purse": purse,
                            "start_date": start_date,
                            "end_date": end_date,
                            "week_number": week_number,
                            "playing_format": event_data.get("format", ""),
                            "status": event_data.get("status", "Scheduled"),
                        },
                    )

                    if created:
                        created_count += 1
                    else:
                        updated_count += 1

                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Error saving event '{event_data.get('name', '?')}': {e}"))
                    continue

            self.stdout.write(self.style.SUCCESS(
                f"{tour_info['name']}: {created_count} created, {updated_count} updated"
            ))
