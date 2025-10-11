from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from score_predict.models import Fixture
from score_predict.management.commands.update_fixtures import ENGLISH_LEAGUES, HEADERS
import requests


class Command(BaseCommand):
    help = "Update fixtures and score predictions with latest results."

    def add_arguments(self, parser):
        parser.add_argument(
            "league_code",
            nargs="?",
            type=str,
            help="Optional league short_name (e.g. EPL, ECH, EL1, EL2). If omitted, updates all leagues.",
        )

    def handle(self, *args, **options):
        league_code = options.get("league_code")

        # Choose leagues
        if league_code:
            leagues_to_update = {
                name: ids for name, ids in ENGLISH_LEAGUES.items()
                if ids["short_name"] == league_code
            }
            if not leagues_to_update:
                self.stdout.write(self.style.ERROR(f"Unknown league code: {league_code}"))
                return
        else:
            leagues_to_update = ENGLISH_LEAGUES

        url = "https://sofascore.p.rapidapi.com/tournaments/get-last-matches"

        for league_name, ids in leagues_to_update.items():
            self.stdout.write(f"Fetching updated results for {league_name}...")

            querystring = {
                "tournamentId": str(ids["tournament_id"]),
                "seasonId": str(ids["season_id"]),
                "pageIndex": "0"
            }

            response = requests.get(url, headers=HEADERS, params=querystring)
            if response.status_code != 200:
                self.stdout.write(self.style.ERROR(f"API error for {league_name}"))
                continue

            matches = response.json().get("events", [])
            updated_count = 0

            for match in matches:
                fixture_id = match["id"]
                status_code = match["status"]["code"]
                status_description = match["status"]["type"]

                home_score = match.get("homeScore", {}).get("current")
                away_score = match.get("awayScore", {}).get("current")

                try:
                    fixture = Fixture.objects.get(fixture_id=fixture_id)
                except Fixture.DoesNotExist:
                    continue  # skip unknown fixtures

                with transaction.atomic():
                    fixture.status_code = status_code
                    fixture.status_description = status_description
                    fixture.home_score = home_score
                    fixture.away_score = away_score
                    fixture.updated_at = timezone.now()
                    fixture.save(update_fields=[
                        "status_code", "status_description",
                        "home_score", "away_score", "updated_at"
                    ])
                    updated_count += 1

            self.stdout.write(self.style.SUCCESS(
                f"{updated_count} fixtures updated for {league_name}"
            ))
