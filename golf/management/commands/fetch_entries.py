import os
import requests
from golf.models import GolfEvent, EventEntry, Golfer
from django.core.management.base import BaseCommand


def fetch_entries(event):
    """Fetch and save entry list for a single event"""
    url = "https://live-golf-data.p.rapidapi.com/tournament"
    RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")

    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "live-golf-data.p.rapidapi.com"
    }

    params = {
        "orgId": str(event.tour.tour_id),
        "tournId": event.tourn_id,
        "year": str(event.year)
    }

    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        print(f"Failed for {event.name} ({response.status_code})")
        return False

    data = response.json()
    players = data.get("players", [])
    print("Data", data)
    print("Players", players)
    if not players:
        print(f" No players found for {event.name}")
        return False

    for p in players:
        golfer, _ = Golfer.objects.update_or_create(
            golfer_id=p["playerId"],
            defaults={
                "first_name": p.get("firstName", ""),
                "last_name": p.get("lastName", ""),
                "is_amateur": p.get("isAmateur", False),
            },
        )
        EventEntry.objects.update_or_create(
            event=event,
            golfer=golfer,
            defaults={"status": p.get("status", "")},
        )

    print(f" Entries saved for {event.name}")
    return True


class Command(BaseCommand):
    help = "Fetch entry lists for all upcoming events"

    def handle(self, *args, **options):
        for event in GolfEvent.objects.filter(status="Scheduled"):
            fetch_entries(event)
