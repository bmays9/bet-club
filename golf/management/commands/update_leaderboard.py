import os
import requests
from django.core.management.base import BaseCommand
from django.utils.timezone import now
from golf.models import GolfEvent, Golfer, GolferScore, EventEntry

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_GOLF_HOST = "live-golf-data.p.rapidapi.com"

HEADERS = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
    "X-RapidAPI-Host": RAPIDAPI_GOLF_HOST,
}


def fetch_leaderboard(event):
    """Fetch live leaderboard scores for a single event."""
    url = "https://live-golf-data.p.rapidapi.com/leaderboard"
    params = {
        "orgId": str(event.tour.tour_id),
        "tournId": event.tourn_id,
        "year": str(event.year),
    }
    response = requests.get(url, headers=HEADERS, params=params, timeout=30)
    if response.status_code != 200:
        print(f"  Failed to fetch leaderboard for {event.name}: {response.status_code}")
        return None
    return response.json()


def save_leaderboard(event, data):
    """Parse leaderboard JSON and upsert GolferScore rows."""
    players = data.get("leaderboard", [])
    if not players:
        print(f"  No leaderboard data for {event.name}")
        return 0

    saved = 0
    for p in players:
        golfer_id = p.get("playerId")
        if not golfer_id:
            continue

        # Get or create golfer
        golfer, _ = Golfer.objects.update_or_create(
            golfer_id=golfer_id,
            defaults={
                "first_name": p.get("firstName", ""),
                "last_name": p.get("lastName", ""),
                "country": p.get("country", ""),
                "world_ranking": p.get("worldRanking", 2999),
            },
        )

        # Ensure EventEntry exists
        EventEntry.objects.get_or_create(
            event=event,
            golfer=golfer,
            defaults={"status": p.get("status", "")},
        )

        # Current round scores
        current_round = event.current_round or 1
        rounds_data = p.get("rounds", [])

        for round_data in rounds_data:
            round_num = round_data.get("roundNumber")
            if not round_num:
                continue

            GolferScore.objects.update_or_create(
                golfer=golfer,
                event=event,
                round=round_num,
                defaults={
                    "score": round_data.get("strokes"),
                    "thru": round_data.get("thru"),
                    "position": str(p.get("position", "")),
                },
            )

        # Also store overall position on current round row
        GolferScore.objects.filter(
            golfer=golfer, event=event, round=current_round
        ).update(position=str(p.get("position", "")))

        saved += 1

    # Update event status and current round
    event_status = data.get("eventStatus", "")
    current_round = data.get("currentRound")
    if event_status:
        event.status = event_status
    if current_round:
        event.current_round = current_round
    event.save(update_fields=["status", "current_round"])

    return saved


class Command(BaseCommand):
    help = "Fetch live leaderboard scores for active golf events."

    def add_arguments(self, parser):
        parser.add_argument(
            "--event_id",
            type=str,
            help="Optional tourn_id to update a single event.",
        )

    def handle(self, *args, **options):
        event_id = options.get("event_id")

        if event_id:
            events = GolfEvent.objects.filter(tourn_id=event_id)
        else:
            # Active = in progress or starting within 7 days
            from datetime import timedelta
            from django.utils.timezone import now
            today = now()
            events = GolfEvent.objects.filter(
                start_date__lte=today + timedelta(days=1),
                end_date__gte=today,
            ).select_related("tour")

        if not events.exists():
            self.stdout.write("No active events found.")
            return

        for event in events:
            self.stdout.write(f"Fetching leaderboard for {event.name}...")
            data = fetch_leaderboard(event)
            if data:
                count = save_leaderboard(event, data)
                self.stdout.write(
                    self.style.SUCCESS(f"  Saved scores for {count} golfers in {event.name}")
                )

        self.stdout.write(self.style.SUCCESS("Leaderboard update complete."))
