import os
import requests
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.timezone import now
from season.utils.season_helpers import should_mark_month_end
from season.models import League, Team, StandingsBatch, StandingsRow
from score_predict.management.commands.update_fixtures import ENGLISH_LEAGUES

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_SOFA_HOST = os.getenv("RAPIDAPI_SOFA_HOST")

HEADERS = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
    "X-RapidAPI-Host": RAPIDAPI_SOFA_HOST,
}


def fetch_table(tournament_id, season_id):
    url = "https://sofascore.p.rapidapi.com/tournaments/get-standings"
    params = {
        "tournamentId": str(tournament_id),
        "seasonId": str(season_id),
        "pageIndex": "0",
    }
    response = requests.get(url, headers=HEADERS, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def get_or_update_team(team_data, league):
    """
    Look up team by sofascore_id alone (globally unique).
    If the team has moved leagues (promoted/relegated), update their league.
    If name conflict exists in new league, update the existing team's sofascore_id.
    """
    sofascore_id = team_data["id"]
    name = team_data["name"]
    short_name = team_data.get("shortName") or name[:3]

    # Try to find by sofascore_id first (most reliable)
    team = Team.objects.filter(sofascore_id=sofascore_id).first()

    if team:
        changed = False
        if team.league_id != league.id:
            print(f"  Team '{name}' moved from {team.league} to {league.name}")
            team.league = league
            changed = True
        if team.name != name:
            team.name = name
            changed = True
        if team.short_name != short_name:
            team.short_name = short_name
            changed = True
        if changed:
            team.save()
        return team

    # Not found by sofascore_id -- check by name in this league
    team = Team.objects.filter(league=league, name=name).first()
    if team:
        # Same team, just update sofascore_id
        team.sofascore_id = sofascore_id
        team.short_name = short_name
        team.save()
        return team

    # Genuinely new team
    team = Team.objects.create(
        sofascore_id=sofascore_id,
        league=league,
        name=name,
        short_name=short_name,
    )
    print(f"  New team created: {name} ({league.name})")
    return team


def save_standings(league, data):
    standings = next(
        (s for s in data.get("standings", []) if s["type"] == "total"), None
    )
    if not standings:
        return None

    with transaction.atomic():
        batch = StandingsBatch.objects.create(
            league=league,
            taken_at=now(),
            season_round=None,
            source="sofascore",
        )
        if should_mark_month_end(batch.taken_at):
            batch.is_month_end = True
            batch.save(update_fields=["is_month_end"])

        for row in standings["rows"]:
            team = get_or_update_team(row["team"], league)
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
    help = "Fetch current standings for English leagues."

    def add_arguments(self, parser):
        parser.add_argument(
            "--league_code",
            type=str,
            help="Optional league code (EPL, ECH, EL1, EL2).",
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

            self.stdout.write(f"Fetching {league_name}...")
            try:
                data = fetch_table(ids["tournament_id"], ids["season_id"])
                batch = save_standings(league, data)
                if batch:
                    self.stdout.write(self.style.SUCCESS(
                        f"  Saved {league_name} ({batch.id}) @ {batch.taken_at:%Y-%m-%d %H:%M}"
                    ))
                else:
                    self.stdout.write(self.style.WARNING(f"  No standings for {league_name}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  Failed {league_name}: {e}"))