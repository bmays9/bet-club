import requests
import datetime
from django.core.management.base import BaseCommand
from score_predict.models import Fixture
from django.conf import settings
import os

API_KEY = os.getenv("API_FOOTBALL_KEY")
BASE_URL = "https://v3.football.api-sports.io/"

HEADERS = {
    'x-rapidapi-key': API_KEY
}

LEAGUES = {
    39: "PL",
    40: "CH",
    41: "L1",
    42: "L2"
}

class Command(BaseCommand):
    help = "Fetch and store fixtures & results from API-Football"

    def fetch_fixtures(self, date_from, date_to):
        fixtures = []
        for league_id in LEAGUES.keys():
            url = f"{BASE_URL}fixtures"
            params = {
                "league": league_id,
                "season": datetime.datetime.now().year,
                "from": date_from,
                "to": date_to,
            }
            response = requests.get(url, headers=HEADERS, params=params)
            data = response.json()
            if "response" in data:
                fixtures.extend(data["response"])
        return fixtures

    def handle(self, *args, **kwargs):
        today = datetime.date.today()
        past_week = (today - datetime.timedelta(days=7)).strftime('%Y-%m-%d')
        next_week = (today + datetime.timedelta(days=7)).strftime('%Y-%m-%d')

        # Fetch past results
        past_results = self.fetch_fixtures(past_week, today)
        self.store_fixtures(past_results, is_result=True)

        # Fetch upcoming fixtures
        upcoming_fixtures = self.fetch_fixtures(today, next_week)
        self.store_fixtures(upcoming_fixtures, is_result=False)

    def store_fixtures(self, fixtures, is_result):
        for fixture in fixtures:
            league_id = fixture["league"]["id"]
            fixture_id = fixture["fixture"]["id"]
            date = fixture["fixture"]["date"]
            home_team = fixture["teams"]["home"]["name"]
            away_team = fixture["teams"]["away"]["name"]
            home_score = fixture["goals"]["home"]
            away_score = fixture["goals"]["away"]

            result = None
            if is_result and home_score is not None and away_score is not None:
                if home_score > away_score:
                    result = 'H'
                elif home_score < away_score:
                    result = 'A'
                else:
                    result = 'D'

            obj, created = Fixture.objects.update_or_create(
                fixture_id=fixture_id,
                defaults={
                    "league_id": league_id,
                    "league_short_name": LEAGUES.get(league_id),
                    "date": date,
                    "home_team": home_team,
                    "away_team": away_team,
                    "home_score": home_score,
                    "away_score": away_score,
                    "result": result,
                }
            )

            if created:
                self.stdout.write(self.style.SUCCESS(f"Added {home_team} vs {away_team} ({LEAGUES.get(league_id)})"))
            else:
                self.stdout.write(self.style.SUCCESS(f"Updated {home_team} vs {away_team} ({LEAGUES.get(league_id)})"))