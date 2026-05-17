import os
import requests
from datetime import datetime
from django.core.management.base import BaseCommand
from golf.models import Golfer


RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")

HEADERS = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
    "X-RapidAPI-Host": "live-golf-data.p.rapidapi.com",
}

OWGR_STAT_ID = "186"


def extract_rank(rank_value):
    """
    Safely extract an integer rank from whatever the API returns.
    Handles: int, float, str, or dict (e.g. {"value": 1} or {"$numberInt": "1"})
    """
    if isinstance(rank_value, (int, float)):
        return int(rank_value)
    if isinstance(rank_value, str):
        try:
            return int(rank_value.lstrip("T=").split(".")[0])
        except ValueError:
            return None
    if isinstance(rank_value, dict):
        # Try common nested formats
        for key in ("value", "$numberInt", "$numberLong", "rank", "position"):
            if key in rank_value:
                try:
                    return int(str(rank_value[key]).split(".")[0])
                except (ValueError, TypeError):
                    continue
    return None


class Command(BaseCommand):
    help = "Update world rankings for golfers from OWGR stat. Run once a month."

    def add_arguments(self, parser):
        parser.add_argument(
            "--year",
            type=int,
            default=None,
            help="Year to fetch rankings for (defaults to current year)",
        )

    def handle(self, *args, **options):
        year = options.get("year") or datetime.now().year
        self.stdout.write(f"Fetching OWGR rankings for {year}...")

        try:
            response = requests.get(
                "https://live-golf-data.p.rapidapi.com/stats",
                headers=HEADERS,
                params={"year": str(year), "statId": OWGR_STAT_ID},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to fetch rankings: {e}"))
            return

        rankings = data.get("rankings", [])
        if not rankings:
            self.stdout.write(self.style.WARNING(
                f"No rankings found. Response sample: {str(data)[:300]}"
            ))
            return

        # Log the first entry so we can see the exact shape
        if rankings:
            self.stdout.write(f"Sample entry: {rankings[0]}")

        self.stdout.write(f"Found {len(rankings)} ranked players.")

        updated = 0
        not_in_db = 0
        bad_rank = 0

        for entry in rankings:
            player_id = str(entry.get("playerId", ""))
            rank = extract_rank(entry.get("rank"))

            if not player_id or rank is None:
                bad_rank += 1
                continue

            rows = Golfer.objects.filter(golfer_id=player_id)
            if rows.exists():
                rows.update(world_ranking=rank)
                updated += 1
            else:
                not_in_db += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done: {updated} updated, {not_in_db} not in DB, {bad_rank} unparseable ranks."
        ))
