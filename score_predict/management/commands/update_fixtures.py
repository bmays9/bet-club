import os
import requests
from datetime import datetime, timedelta, timezone

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.timezone import now
from score_predict.models import Fixture, GameTemplate
from score_predict.utils import group_fixtures_by_consecutive_days

# RapidAPI configuration
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_SOFA_HOST = os.getenv("RAPIDAPI_SOFA_HOST")

HEADERS = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
    "X-RapidAPI-Host": RAPIDAPI_SOFA_HOST,
}

ENGLISH_LEAGUES = {
    "Premier League": {"short_name": "EPL", "tournament_id": 17, "season_id": 76986},
    "Championship": {"short_name": "ECH", "tournament_id": 18, "season_id": 77347},
    "League One": {"short_name": "EL1", "tournament_id": 24, "season_id": 77352},
    "League Two": {"short_name": "EL2", "tournament_id": 25, "season_id": 77351},
}

ENGLISH_LEAGUE_IDS = {v["tournament_id"] for v in ENGLISH_LEAGUES.values()}


def get_block_start_date(first_fixture_date):
    """Returns start date of Fri–Mon or Tue–Thu block."""
    weekday = first_fixture_date.weekday()  # Mon=0 ... Sun=6
    if weekday in [1, 2, 3]:  # Tue–Thu
        block_start = first_fixture_date - timedelta(days=weekday - 1)
        game_type = "midweek"
    else:  # Fri–Mon
        days_from_friday = (weekday - 4) % 7
        block_start = first_fixture_date - timedelta(days=days_from_friday)
        game_type = "weekend"
    return block_start, game_type


def fetch_next_fixtures(leagues_to_update):
    """Fetches upcoming fixtures for the given leagues."""
    fixtures = []
    url = "https://sofascore.p.rapidapi.com/tournaments/get-next-matches"

    for league_name, ids in leagues_to_update.items():
        print(f"📅 Fetching next fixtures for {league_name}...")
        querystring = {
            "tournamentId": str(ids["tournament_id"]),
            "seasonId": str(ids["season_id"]),
            "pageIndex": "0",
        }

        response = requests.get(url, headers=HEADERS, params=querystring)
        if response.status_code != 200:
            print(f"⚠️ Error fetching {league_name}: {response.status_code}")
            continue

        data = response.json()
        for match in data.get("events", []):
            dt_utc = datetime.utcfromtimestamp(match["startTimestamp"]).replace(tzinfo=timezone.utc)
            fixtures.append({
                "fixture_id": match["id"],
                "league_id": ids["tournament_id"],
                "league_short_name": ids["short_name"],
                "date": dt_utc,
                "home_team": match["homeTeam"]["name"],
                "away_team": match["awayTeam"]["name"],
                "home_colour": match.get("homeTeam", {}).get("teamColors", {}).get("primary"),
                "home_text": match.get("homeTeam", {}).get("teamColors", {}).get("text"),
                "away_colour": match.get("awayTeam", {}).get("teamColors", {}).get("primary"),
                "away_text": match.get("awayTeam", {}).get("teamColors", {}).get("text"),
                "final_result_only": match.get("finalResultOnly", False),
                "status_code": match.get("status", {}).get("code"),
                "status_description": match.get("status", {}).get("description"),
            })
    return fixtures


def store_fixtures(fixtures):
    """Create or update fixture entries."""
    saved = 0
    for f in fixtures:
        _, created = Fixture.objects.update_or_create(
            fixture_id=f["fixture_id"],
            defaults=f
        )
        if created:
            saved += 1
    print(f"✅ {saved} new fixtures saved ({len(fixtures)} total processed).")


def assign_fixtures_to_templates():
    """Groups upcoming fixtures into GameTemplates (midweek/weekend)."""
    fixtures = Fixture.objects.filter(date__gte=now()).order_by("date")
    if not fixtures.exists():
        print("⚠️ No future fixtures found.")
        return

    grouped_blocks = group_fixtures_by_consecutive_days(fixtures)

    for block in grouped_blocks:
        block_start, game_type = get_block_start_date(block[0].date)
        block_end = block[-1].date.date()
        league_ids = {f.league_id for f in block}

        slug = (
            f"en-{game_type}-{block_start.date()}"
            if league_ids.issubset(ENGLISH_LEAGUE_IDS)
            else f"{block[0].league_id}-{game_type}-{block_start.date()}"
        )

        with transaction.atomic():
            template, created = GameTemplate.objects.get_or_create(
                slug=slug,
                defaults={
                    "game_type": game_type,
                    "week": block_start.isocalendar()[1],
                    "start_date": block_start,
                    "end_date": block_end,
                },
            )
            if not created and template.end_date < block_end:
                template.end_date = block_end
                template.save(update_fields=["end_date"])

            Fixture.objects.filter(
                date__date__range=[block_start.date(), block_end],
                league_id__in=league_ids,
            ).update(gametemplate=template)

            print(f"{'🆕 Created' if created else '✅ Updated'} template {slug}")


class Command(BaseCommand):
    help = "Fetch new fixtures (per league if specified) and assign them to GameTemplates."

    def add_arguments(self, parser):
        parser.add_argument(
            "league_code",
            nargs="?",
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

        new_fixtures = fetch_next_fixtures(leagues_to_update)
        store_fixtures(new_fixtures)
        assign_fixtures_to_templates()
        self.stdout.write(self.style.SUCCESS("Fixtures updated successfully!"))
