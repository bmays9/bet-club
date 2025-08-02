# score_predict/management/commands/update_results.py
from django.core.management.base import BaseCommand
from score_predict.models import Fixture, Prediction, GameEntry
from django.db import transaction
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

                if status != "finished":
                    continue

                try:
                    fixture = Fixture.objects.get(fixture_id=fixture_id)
                except Fixture.DoesNotExist:
                    continue  # skip fixtures not in our DB

                with transaction.atomic():
                    fixture.status = "finished"
                    fixture.home_score = home_score
                    fixture.away_score = away_score
                    fixture.save()

                    predictions = Prediction.objects.filter(fixture=fixture)
                    for prediction in predictions:
                        points = self.calculate_points(prediction, fixture)
                        prediction.points_awarded = points
                        prediction.save()

                        entry = GameEntry.objects.get(game=prediction.game_instance, player=prediction.player)
                        entry.total_score += points
                        entry.save()

        self.stdout.write(self.style.SUCCESS("Fixture results and predictions updated!"))

        self.stdout.write(self.style.SUCCESS("Fixture results updated! Now updating scores..."))
        update_scores(stdout=self.stdout)  # call score update after fixtures updated
        self.stdout.write(self.style.SUCCESS("Scores updated!"))
