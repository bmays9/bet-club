import os
import requests
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.timezone import now
from season.utils.month_end import should_mark_month_end
from season.models import League, Team, StandingsBatch, StandingsRow
from score_predict.management.commands.update_fixtures import ENGLISH_LEAGUES

# RapidAPI config
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_SOFA_HOST = os.getenv("RAPIDAPI_SOFA_HOST")

HEADERS = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
    "X-RapidAPI-Host": RAPIDAPI_SOFA_HOST,
}


def fetch_table(tournament_id, season_id):
    url = "https://sofascore.p.rapidapi.com/tournaments/get-standings"
    params = {"tournamentId": str(tournament_id), "seasonId": str(season_id), "pageIndex": "0"}
    response = requests.get(url, headers=HEADERS, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def save_standings(league, data):
    standings = next((s for s in data.get("standings", []) if s["type"] == "total"), None)
    if not standings:
        return None

    with transaction.atomic():
        batch = StandingsBatch.objects.create(
            league=league, taken_at=now(), season_round=None, source="sofascore"
        )
        if should_mark_month_end(batch.taken_at):
            batch.is_month_end = True
            batch.save(update_fields=["is_month_end"])

        for row in standings["rows"]:
            team_data = row["team"]
            team, _ = Team.objects.get_or_create(
                sofascore_id=team_data["id"],
                league=league,
                defaults={
                    "name": team_data["name"],
                    "short_name": team_data.get("shortName") or team_data["name"][:3],
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
    help = "Fetch current standings for English leagues (or a specific league if provided)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--league_code",
            type=str,
            help="Optional league short_name (EPL, ECH, EL1, EL2). Updates all if omitted.",
        )

    def handle(self, *args, **options):
        league_code = options.get("league_code")

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

        for league_name, ids in leagues_to_update.items():
            try:
                league = League.objects.get(code=ids["short_name"])
            except League.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"League {league_name} not found in DB"))
                continue

            self.stdout.write(f"Fetching {league_name} standings...")
            data = fetch_table(ids["tournament_id"], ids["season_id"])
            batch = save_standings(league, data)

            if batch:
                self.stdout.write(self.style.SUCCESS(
                    f"Saved {league_name} standings @ {batch.taken_at}"
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    f"No standings found for {league_name}"
                ))
