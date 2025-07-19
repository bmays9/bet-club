from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db import transaction
from .models import Prediction, Fixture, Game
from django.utils.dateparse import parse_date
from decimal import Decimal
from django.views import generic
import json
from datetime import date

LEAGUE_ORDER = {
    "EPL": "Premier League",
    "ECH": "Championship",
    "EL1": "League One",
    "EL2": "League Two"
}

def get_fixture_groups(user):
    today = now().date()
    weekday = today.weekday()

    # Define date ranges
    weekend_days = [4, 5, 6, 0]  # Fri–Mon
    midweek_days = [1, 2, 3]     # Tue–Thu

    weekend_fixtures = Fixture.objects.filter(
        date__week_day__in=[6, 7, 1, 2]  # Django week_day: Sunday=1, Saturday=7
    )

    midweek_fixtures = Fixture.objects.filter(
        date__week_day__in=[3, 4, 5]
    )

    return {
        "Weekend": weekend_fixtures,
        "Midweek": midweek_fixtures,
    }

class FixtureList(generic.ListView):
    
    template_name = "score_predict/fixtures.html"
    model = Fixture
    context_object_name = "fixtures"

    def get_queryset(self):
        # Simulated "today" in 2021 season
        today_real = datetime.today()
        today_fake = datetime(2021, today_real.month, today_real.day)

        # Make it timezone-aware if using USE_TZ
        today_fake_aware = make_aware(today_fake)

        return Fixture.objects.filter(
            date__gte=today_fake_aware
        ).order_by("date")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        grouped = defaultdict(list)

        for fixture in self.object_list:
            weekday = fixture.date.weekday()
            if fixture.league_short_name in LEAGUE_ORDER and weekday in VALID_WEEKDAYS:
                grouped[fixture.league_short_name].append(fixture)

        # Use OrderedDict to preserve custom league order
        ordered_grouped = OrderedDict()
        for key in LEAGUE_ORDER.keys():
            if key in grouped:
                ordered_grouped[LEAGUE_ORDER[key]] = grouped[key]

        context["fixture_list"] = ordered_grouped
        return context


@login_required
@transaction.atomic
def submit_predictions(request):
    if request.method == "POST":
        user = request.user
        data = request.POST

        # Extract predicted fixture IDs and scores from form
        predicted_fixtures = {}
        for key, value in data.items():
            if key.startswith("fixture_") and value.isdigit():
                parts = key.split("_")
                fixture_id = parts[1]
                team = parts[2]  # 'home' or 'away'
                predicted_fixtures.setdefault(fixture_id, {})[team] = int(value)

        # Fetch only the fixtures the user submitted predictions for
        fixture_ids = predicted_fixtures.keys()
        fixtures = Fixture.objects.filter(id__in=fixture_ids)

        # Get or create the current game (e.g. ScorePredict game for the week)
        game, _ = Game.objects.get_or_create(
            week=1,  # You can dynamically set this based on date
            defaults={
                'start_date': timezone.now().date(),
                'end_date': timezone.now().date() + timedelta(days=2),
                'entry_fee': Decimal(data.get('entry_fee', '5.00'))
            }
        )

        # Add user to the game if not already
        game.players.add(user)

        # Create/update predictions
        for fixture in fixtures:
            scores = predicted_fixtures[str(fixture.id)]
            home_score = scores.get('home')
            away_score = scores.get('away')

            if home_score is not None and away_score is not None:
                Prediction.objects.update_or_create(
                    player=user,
                    fixture=fixture,
                    defaults={
                        'predicted_home_score': home_score,
                        'predicted_away_score': away_score
                    }
                )

        messages.success(request, "Your predictions have been submitted!")
        return redirect('score_predict:fixtures')  # Update with your real redirect

    else:
        return redirect('score_predict:fixtures')