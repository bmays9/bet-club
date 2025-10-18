import os
import requests
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils.dateparse import parse_datetime
from golf.models import GolfEvent, GolfTour
from datetime import datetime, timezone

class Command(BaseCommand):
    help = "Fetches golf events and stores them in the database"

    def handle(self, *args, **kwargs):
        url = "https://live-golf-data.p.rapidapi.com/schedule"

        # RapidAPI config
        RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
        RAPIDAPI_SOFA_HOST = os.getenv("RAPIDAPI_SOFA_HOST")

        HEADERS = {
            "X-RapidAPI-Key": RAPIDAPI_KEY,
            "X-RapidAPI-Host": "live-golf-data.p.rapidapi.com"
        }

        tours = [
            {"name": "PGA Tour", "orgId": "1"},
            {"name": "LIV Tour", "orgId": "2"},
        ]

        for tour_info in tours:
            self.stdout.write(f"Fetching events for {tour_info['name']}...")
            url = "https://live-golf-data.p.rapidapi.com/schedule"
            querystring = {"orgId": tour_info["orgId"], "year": "2025"}

            response = requests.get(url, headers=HEADERS, params=querystring)

            print("Status code:", response.status_code)
            try:
                data = response.json()
                print("Keys in response:", list(data.keys()))
                print("Sample of data:", data[:2] if isinstance(data, list) else data)
            except Exception as e:
                print("Failed to parse JSON:", e)
                print("Raw text:", response.text)

            try:
                data = response.json()
            except Exception as e:
                print(" Failed to parse JSON:", e)
                continue

            schedule = data.get("schedule", [])
            if not schedule:
                print(f" No valid data returned for {tour_info['name']}")
                continue

            tour, _ = GolfTour.objects.get_or_create(
                tour_id=int(tour_info["orgId"]),
                defaults={"season_id": 2025, "tour_name": tour_info["name"]}
            )

            for event_data in schedule:
                try:
                    tourn_id = event_data.get("tournId")
                    name = event_data.get("name")

                    # Parse dates (UNIX timestamp in ms)
                    start_ts = int(event_data["date"]["start"]["$date"]["$numberLong"]) / 1000
                    end_ts = int(event_data["date"]["end"]["$date"]["$numberLong"]) / 1000
                    start_date = datetime.fromtimestamp(start_ts, tz=timezone.utc)
                    end_date = datetime.fromtimestamp(end_ts, tz=timezone.utc)

                    purse = int(event_data.get("purse", {}).get("$numberInt", 0))
                    week_number = int(event_data["date"].get("weekNumber", 0))

                    event, created = GolfEvent.objects.update_or_create(
                        tourn_id=tourn_id,
                        defaults={
                            "name": name,
                            "tour": tour,
                            "year": 2025,
                            "purse": purse,
                            "start_date": start_date,
                            "end_date": end_date,
                            "week_number": week_number,
                            "playing_format": event_data.get("format", ""),
                            "status": data.get("status", "Scheduled"),
                        }
                    )

                    print(f"{' Created' if created else 'Updated'}: {name}")

                except Exception as e:
                    print(f" Error saving event: {e}")
                    continue