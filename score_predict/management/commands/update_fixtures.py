import requests
from datetime import datetime, timedelta, timezone
from django.db.models import Q
from django.utils.text import slugify
from django.utils.timezone import now, make_aware
from django.contrib.auth.models import User
from django.conf import settings
from django.core.management.base import BaseCommand
from score_predict.models import Fixture, GameTemplate, GameInstance, GameEntry
from score_predict.utils import group_fixtures_by_consecutive_days
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
                # Convert naive UTC datetime to aware UTC datetime
                naive_utc_dt = datetime.utcfromtimestamp(fixture["startTimestamp"])
                aware_utc_dt = naive_utc_dt.replace(tzinfo=timezone.utc)

                fixtures.append({
                    "fixture_id": fixture["id"],
                    "league_id": ids["tournament_id"],
                    "league_short_name": ids["short_name"],
                    "date": aware_utc_dt,  # timezone aware datetime here
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
    help = "Fetch new fixtures and assign them to a gametemplate if unassigned"

    def handle(self, *args, **options):
        new_fixtures = get_next_fixtures()
        created_count = 0

                # ✅ Create new Fixture objects
        for f in new_fixtures:
            if not Fixture.objects.filter(fixture_id=f["fixture_id"]).exists():
                Fixture.objects.create(**f)
                created_count += 1

        print(f"✔ {created_count} new fixtures added.")

        # Group unassigned fixtures by consecutive days
        unassigned = Fixture.objects.filter(gametemplate__isnull=True).order_by("date")
        grouped_sets = group_fixtures_by_consecutive_days(unassigned)

        # 🔍 Debug: print each group
        for i, group in enumerate(grouped_sets, 1):
            print(f"\n📦 Group {i} ({len(group)} fixtures):")
            for fixture in group:
                print(f" - {fixture.date.date()} | {fixture.home_team} vs {fixture.away_team}")

        for fixture_group in grouped_sets:
            if not fixture_group:
                continue

            first_date = fixture_group[0].date.date()
            last_date = fixture_group[-1].date.date()
            week_number = first_date.isocalendar()[1]

            # Determine game_type by weekday
            weekdays = [f.date.weekday() for f in fixture_group]  # 0=Mon ... 6=Sun
            if all(day in [1, 2, 3] for day in weekdays):  # Tue, Wed, Thu
                game_type = "midweek"
            else:
                game_type = "weekend"

            week_number = first_date.isocalendar().week
            slug = slugify(f"EN-{game_type}-week-{week_number}-{first_date.isoformat()}")

            # ✅ Get or Create a new GameTemplate
            template, created = GameTemplate.objects.get_or_create(
                slug=slug,
                defaults={
                    'game_type': game_type,
                    'week': week_number,
                    'start_date': first_date,
                    'end_date': last_date,
                }
            )
            if created:
                print(f"Created new GameTemplate: {slug}")
            else:
                print(f"GameTemplate already exists: {slug}")

            # Assign fixtures to this template (add without duplicates)
            for f in fixture_group:
                # Set the fixture's gametemplate field to this template
                f.gametemplate = template
                f.save()

            # ✅ Add to M2M relation for consistency
            print(f"{'🆕 Created' if created else '✅ Reused'} template '{slug}' with {len(fixture_group)} fixtures.")


def create_weekly_prediction_games():
    today = now().date()
    current_week = today.isocalendar().week

    # Define week window
    this_tuesday = today + timedelta((1 - today.weekday()) % 7)  # Next Tuesday
    next_monday = this_tuesday + timedelta(days=6)

    fixtures = Fixture.objects.filter(date__range=(this_tuesday, next_monday))

    # Midweek: Tue - Thu
    midweek_start = this_tuesday
    midweek_end = this_tuesday + timedelta(days=2)
    midweek_fixtures = fixtures.filter(date__week_day__in=[3, 4, 5])  # Tue=3, Wed=4, Thu=5

    # Weekend: Fri - Mon
    weekend_start = this_tuesday + timedelta(days=3)
    weekend_end = next_monday
    weekend_fixtures = fixtures.filter(date__week_day__in=[6, 7, 2, 1])  # Fri=6, Sat=7, Sun=1, Mon=2

    # Create Game objects if there are fixtures
    if midweek_fixtures.exists():
        Game.objects.update_or_create(
            week=current_week,
            game_type="Midweek",
            defaults={
                "start_date": midweek_start,
                "end_date": midweek_end,
            }
        )[0].fixtures.set(midweek_fixtures)

    if weekend_fixtures.exists():
        Game.objects.update_or_create(
            week=current_week,
            game_type="Weekend",
            defaults={
                "start_date": weekend_start,
                "end_date": weekend_end,
            }
        )[0].fixtures.set(weekend_fixtures)

def create_game_instance(game_type="weekend"):
    fixtures = Fixture.objects.filter(
        date__gte=timezone.now()
    ).order_by("date")

    if game_type == "midweek":
        fixtures = fixtures.filter(date__week_day__in=[2, 3, 4])  # Tue, Wed, Thu
    else:
        fixtures = fixtures.filter(date__week_day__in=[6, 7, 1])  # Fri, Sat, Sun

    if fixtures.exists():
        template = GameTemplate.objects.get(name=game_type)  # Ensure templates exist
        game = GameInstance.objects.create(template=template, start_date=timezone.now())
        game.fixtures.set(fixtures[:template.num_fixtures])  # Or some logic to limit fixtures
        game.save()
