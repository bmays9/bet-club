# score_predict/management/commands/update_results.py
from django.core.management.base import BaseCommand
from score_predict.models import Fixture, Prediction, GameEntry
from django.db import transaction
from score_predict.management.commands.update_scores import update_scores
import requests

# import shared constants from update_fixtures
from score_predict.management.commands.update_fixtures import ENGLISH_LEAGUES, HEADERS


class Command(BaseCommand):
    help = "Update fixtures and score predictions with latest results."

    def handle(self, *args, **kwargs):
        self.stdout.write("Fetching updated fixture results...")
        
        url = "https://sofascore.p.rapidapi.com/tournaments/get-last-matches"

        for league_name, ids in ENGLISH_LEAGUES.items():
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
            for match in matches:
                fixture_id = match["id"]
                
                status = match["status"]["type"]
                home_score = match.get("homeScore", {}).get("current")
                away_score = match.get("awayScore", {}).get("current")

                try:
                    fixture = Fixture.objects.get(fixture_id=fixture_id)
                except Fixture.DoesNotExist:
                    continue  # skip fixtures not in our DB

                with transaction.atomic():
                    fixture.status_code = match["status"]["code"]  # e.g. 100 for finished
                    fixture.status_description = status            # e.g. "finished"
                    fixture.home_score = home_score
                    fixture.away_score = away_score
                    fixture.save()

        self.stdout.write(self.style.SUCCESS("Fixture results updated!"))
        # update_scores(stdout=self.stdout)  # call score update after fixtures updated
        # self.stdout.write(self.style.SUCCESS("Scores updated!"))
