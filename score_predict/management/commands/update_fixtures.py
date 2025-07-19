import requests
from datetime import datetime
from django.core.management.base import BaseCommand
from score_predict.models import Fixture
from django.conf import settings
import os

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_SOFA_HOST = os.environ.get('RAPIDAPI_SOFA_HOST')

#BASE_URL = "https://v3.football.api-sports.io/"

HEADERS = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
    "X-RapidAPI-Host": RAPIDAPI_SOFA_HOST
}

# SofaScore uses competition IDs for leagues:
ENGLISH_LEAGUES = {
    "Premier League": {"short_name": "EPL", "tournament_id": 17, "season_id": 76986},
    "Championship": {"short_name": "ECH", "tournament_id": 18, "season_id": 77347},
    "League One": {"short_name": "EL1", "tournament_id": 24, "season_id": 77352},
    "League Two": {"short_name": "EL2", "tournament_id": 25, "season_id": 77351},
}

def get_next_fixtures():
    
    fixtures = []

    for league_name, ids in ENGLISH_LEAGUES.items():
        url = "https://sofascore.p.rapidapi.com/tournaments/get-next-matches"
            
        querystring = {
            "tournamentId": str(ids["tournament_id"]),
            "seasonId": str(ids["season_id"]),
            "pageIndex": "0"
        }
        response = requests.get(url, headers=HEADERS, params=querystring)

        if response.status_code == 200:
            data = response.json()
            events = data.get("events", [])

            for fixture in events:
                fixtures.append({
                    "fixture_id": fixture["id"],
                    "league_id": ids["tournament_id"],
                    "league_short_name": ids["short_name"],
                    "date": datetime.utcfromtimestamp(fixture["startTimestamp"]),
                    "home_team": fixture["homeTeam"]["name"],
                    "away_team": fixture["awayTeam"]["name"],
                    "home_colour": fixture.get("homeTeam", {}).get("teamColors", {}).get("primary"),
                    "home_text": fixture.get("homeTeam", {}).get("teamColors", {}).get("text"),
                    "away_colour": fixture.get("awayTeam", {}).get("teamColors", {}).get("primary"),
                    "away_text": fixture.get("awayTeam", {}).get("teamColors", {}).get("text"),
                    "final_result_only": fixture.get("finalResultOnly", False),
                    "status_code": fixture.get("status", {}).get("code"),
                    "status_description": fixture.get("status", {}).get("description"),
                })
        else:
            print(f"Error fetching fixtures for {league_name}: {response.status_code}")

    return fixtures

def store_fixtures(fixtures):
    saved = 0
    for f in fixtures:
        _, created = Fixture.objects.update_or_create(
            fixture_id=f["fixture_id"],
            defaults={
                "league_id": f["league_id"],
                "league_short_name": f["league_short_name"],
                "date": f["date"],
                "home_team": f["home_team"],
                "away_team": f["away_team"],
                "home_colour": f.get("home_colour"),
                "home_text": f.get("home_text"),
                "away_colour": f.get("away_colour"),
                "away_text": f.get("away_text"),
                "final_result_only": f.get("final_result_only", False),
                "status_code": f.get("status_code"),
                "status_description": f.get("status_description"),
                "home_score": None,
                "away_score": None,
                "result": "N"
            }
        )
        if created:
            saved += 1
    print(f"{saved} new fixtures saved.")


class Command(BaseCommand):
    help = 'Fetch next fixtures for English leagues'

    def handle(self, *args, **kwargs):
        fixtures = get_next_fixtures()
        store_fixtures(fixtures)
        for f in fixtures:
            self.stdout.write(f"{f['league']}: {f['home_team']} vs {f['away_team']} on {f['date']}")




