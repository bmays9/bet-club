import os
import requests
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.timezone import now

from season.models import League, Team, StandingsBatch, StandingsRow
from score_predict.management.commands.update_fixtures import ENGLISH_LEAGUES

# RapidAPI configuration
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_SOFA_HOST = os.getenv("RAPIDAPI_SOFA_HOST")

HEADERS = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
    "X-RapidAPI-Host": RAPIDAPI_SOFA_HOST
}


def fetch_table(tournament_id: int, season_id: int) -> dict:
    url = "https://sofascore.p.rapidapi.com/tournaments/get-standings"
    querystring = {
        "tournamentId": str(tournament_id),
        "seasonId": str(season_id),
        "pageIndex": "0",
    }
    resp = requests.get(url, headers=HEADERS, params=querystring, timeout=30)
    resp.raise_for_status()
    return resp.json()


def save_standings(league: League, data: dict):
    # pick the "total" standings
    standings = next((s for s in data.get("standings", []) if s["type"] == "total"), None)
    if not standings:
        return None

    with transaction.atomic():
        # Create one batch **per league**
        batch = StandingsBatch.objects.create(
            league=league,
            taken_at=now(),
            season_round=None,
            source="sofascore",
        )

        for row in standings["rows"]:
            team_id = row["team"]["id"]
            team, _ = Team.objects.get_or_create(
                sofascore_id=team_id,
                league=league,
                defaults={
                    "name": row["team"]["name"],
                     "short_name": row["team"].get("shortName") or row["team"]["name"][:3],
                },
            )

            StandingsRow.objects.create(
                batch=batch,
                team=team,
                position=row["position"],
                played=row["matches"],
                wins=row["wins"],
                draws=row["draws"],
                losses=row["losses"],
                goals_for=row["scoresFor"],
                goals_against=row["scoresAgainst"],
            )
    return batch


class Command(BaseCommand):
    help = "Fetch current standings for the 4 English leagues from SofaScore"

    def handle(self, *args, **options):
        for league_name, ids in ENGLISH_LEAGUES.items():
            try:
                league = League.objects.get(code=ids["short_name"])
            except League.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"League {league_name} not found in DB"))
                continue

            self.stdout.write(f"Fetching {league_name} standings...")
            data = fetch_table(ids["tournament_id"], ids["season_id"])
            batch = save_standings(league, data)

            if batch:
                self.stdout.write(self.style.SUCCESS(f"Saved {league_name} standings @ {batch.taken_at}"))
            else:
                self.stdout.write(self.style.WARNING(f"No standings found for {league_name}"))
