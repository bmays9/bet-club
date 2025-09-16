import os
import requests
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.timezone import now
from score_predict.models import Fixture, GameTemplate, GameInstance, GameEntry
from score_predict.utils import group_fixtures_by_consecutive_days

# RapidAPI configuration
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_SOFA_HOST = os.getenv("RAPIDAPI_SOFA_HOST")

HEADERS = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
    "X-RapidAPI-Host": RAPIDAPI_SOFA_HOST
}

# SofaScore English league IDs
ENGLISH_LEAGUES = {
    "Premier League": {"short_name": "EPL", "tournament_id": 17, "season_id": 76986},
    "Championship": {"short_name": "ECH", "tournament_id": 18, "season_id": 77347},
    "League One": {"short_name": "EL1", "tournament_id": 24, "season_id": 77352},
    "League Two": {"short_name": "EL2", "tournament_id": 25, "season_id": 77351},
}
ENGLISH_LEAGUE_IDS = {v["tournament_id"] for v in ENGLISH_LEAGUES.values()}


def get_block_start_date(first_fixture_date):
    """
    Returns the start date of the Fri–Mon or Tue–Thu block for a given date.
    """
    weekday = first_fixture_date.weekday()  # Mon=0 ... Sun=6

    if weekday in [1, 2, 3]:  # Tue, Wed, Thu
        block_start = first_fixture_date - timedelta(days=weekday - 1)
        game_type = "midweek"
    else:  # Fri–Mon
        days_from_friday = (weekday - 4) % 7
        block_start = first_fixture_date - timedelta(days=days_from_friday)
        game_type = "weekend"

    return block_start, game_type


def assign_fixtures_to_templates(new_fixtures):
    grouped_blocks = group_fixtures_by_consecutive_days(new_fixtures)

    for block in grouped_blocks:
        # Normalize to Fri (weekend) or Tue (midweek)
        block_start, game_type = get_block_start_date(block[0].date)
        block_end = block[-1].date.date()

        league_ids = {f.league_id for f in block}

        # Consistent slug for each block (prevents duplicates)
        if league_ids.issubset(ENGLISH_LEAGUE_IDS):
            slug = f"en-{game_type}-{block_start}"
        else:
            slug = f"{block[0].league_id}-{game_type}-{block_start}"

        with transaction.atomic():
            template, created = GameTemplate.objects.get_or_create(
                slug=slug,
                defaults={
                    "game_type": game_type,
                    "week": block_start.isocalendar()[1],
                    "start_date": block_start,
                    "end_date": block_end,
                }
            )

            # If template already exists but needs a later end_date, update it
            if not created and template.end_date < block_end:
                template.end_date = block_end
                template.save(update_fields=["end_date"])

            print(f"{'🆕 Created' if created else '✅ Using existing'} template: {slug}")

            # Assign fixtures to this template
            for fixture in block:
                fixture.gametemplate = template
                fixture.save(update_fields=["gametemplate"])



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
        if response.status_code != 200:
            print(f"Error fetching fixtures for {league_name}: {response.status_code}")
            continue

        data = response.json()
        events = data.get("events", [])

        for fixture in events:
            dt_utc = datetime.utcfromtimestamp(fixture["startTimestamp"]).replace(tzinfo=timezone.utc)
            fixtures.append({
                "fixture_id": fixture["id"],
                "league_id": ids["tournament_id"],
                "league_short_name": ids["short_name"],
                "date": dt_utc,
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
    help = "Fetch new fixtures and assign them to GameTemplates"

    def handle(self, *args, **options):
        new_fixtures = get_next_fixtures()

        # Store only brand-new fixtures
        created_count = 0
        for f in new_fixtures:
            if not Fixture.objects.filter(fixture_id=f["fixture_id"]).exists():
                Fixture.objects.create(**f)
                created_count += 1

        print(f"✔ {created_count} new fixtures added.")

        # Assign unassigned fixtures into templates
        unassigned = Fixture.objects.filter(gametemplate__isnull=True).order_by("date")
        assign_fixtures_to_templates(unassigned)


# Optional utility functions
def create_weekly_prediction_games():
    today = now().date()
    current_week = today.isocalendar()[1]

    # Define week window (Tue–Mon)
    this_tuesday = today + timedelta((1 - today.weekday()) % 7)
    next_monday = this_tuesday + timedelta(days=6)

    fixtures = Fixture.objects.filter(date__range=(this_tuesday, next_monday))

    # Midweek: Tue–Thu
    midweek_fixtures = fixtures.filter(date__week_day__in=[3, 4, 5])
    if midweek_fixtures.exists():
        game, _ = GameInstance.objects.update_or_create(
            week=current_week,
            game_type="Midweek",
            defaults={"start_date": this_tuesday, "end_date": this_tuesday + timedelta(days=2)}
        )
        game.fixtures.set(midweek_fixtures)

    # Weekend: Fri–Mon
    weekend_fixtures = fixtures.filter(date__week_day__in=[6, 7, 1, 2])
    if weekend_fixtures.exists():
        game, _ = GameInstance.objects.update_or_create(
            week=current_week,
            game_type="Weekend",
            defaults={"start_date": this_tuesday + timedelta(days=3), "end_date": next_monday}
        )
        game.fixtures.set(weekend_fixtures)


def create_game_instance(game_type="weekend"):
    fixtures = Fixture.objects.filter(date__gte=now()).order_by("date")

    if game_type == "midweek":
        fixtures = fixtures.filter(date__week_day__in=[2, 3, 4])  # Tue–Thu
    else:
        fixtures = fixtures.filter(date__week_day__in=[6, 7, 1])  # Fri–Sun

    if fixtures.exists():
        template = GameTemplate.objects.filter(game_type=game_type).first()
        if template:
            game = GameInstance.objects.create(template=template, start_date=now())
            game.fixtures.set(fixtures[:template.num_fixtures])
            game.save()
