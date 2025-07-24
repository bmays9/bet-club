from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db import transaction
from django.shortcuts import get_object_or_404
from .models import GameTemplate, GameInstance, Prediction, Fixture
from collections import defaultdict, OrderedDict
from groups.models import UserGroup
from django.utils.dateparse import parse_date
from django.utils.timezone import make_aware, get_current_timezone
from decimal import Decimal
from django.views import generic
import json
from datetime import date, datetime

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
        selected_tab = self.request.GET.get("tab", "weekend")
        today = datetime.now(get_current_timezone()).date()

        # Get the next GameTemplate of the selected type
        next_template = (
            GameTemplate.objects
            .filter(game_type__iexact=selected_tab, end_date__gte=today)
            .order_by("start_date")
            .first()
        )

        self.selected_template = next_template  # Save for use in context

        if next_template:
            return Fixture.objects.filter(gametemplate=next_template).order_by("date")
        return Fixture.objects.none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        grouped = defaultdict(list)

        for fixture in self.object_list:
            if fixture.league_short_name in LEAGUE_ORDER:
                grouped[fixture.league_short_name].append(fixture)

        ordered_grouped = OrderedDict()
        for key in LEAGUE_ORDER.keys():
            if key in grouped:
                ordered_grouped[LEAGUE_ORDER[key]] = grouped[key]

        context["fixture_list"] = ordered_grouped
        context["selected_tab"] = self.request.GET.get("tab", "weekend")
        context["game_template"] = self.selected_template
        if self.request.user.is_authenticated:
            context["user_groups"] = self.request.user.joined_groups.all()
        else:
            context["user_groups"] = []
        return context


@login_required
def submit_predictions(request):
    if request.method == "POST":
        try:
            # Parse JSON payload
            data = json.loads(request.body)

            user = request.user
            group_id = data.get("group_id")
            template_id = data.get("game_template_id")
            predictions_data = data.get("predictions", [])

            # Validate essential fields
            if not group_id or not template_id or not isinstance(predictions_data, list):
                return JsonResponse({"error": "Invalid data format"}, status=400)

            # Get the relevant objects
            group = get_object_or_404(UserGroup, id=group_id)
            game_template = get_object_or_404(GameTemplate, id=template_id)

            # Create or fetch GameInstance
            game_instance, created = GameInstance.objects.get_or_create(
                template=game_template,
                group=group,
                defaults={"entry_fee": Decimal("5.00")}
            )

            # Save or update predictions
            for item in predictions_data:
                fixture_id = item.get("fixture_id")
                home_score = item.get("home_score")
                away_score = item.get("away_score")

                if fixture_id is None or home_score is None or away_score is None:
                    continue  # Skip incomplete data

                fixture = get_object_or_404(Fixture, id=fixture_id)

                Prediction.objects.update_or_create(
                    game_instance=game_instance,
                    player=user,
                    fixture=fixture,
                    defaults={
                        "predicted_home_score": home_score,
                        "predicted_away_score": away_score,
                    }
                )

            # Ensure player is in the game instance
            game_instance.players.add(user)

            return JsonResponse({"status": "success", "game_instance_id": game_instance.id})

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid request method"}, status=400)


@login_required
##@transaction.atomic
def submit_predictions_theold_way(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        user = request.user
        data = json.loads(request.body)

        group_id = data.get("group_id")
        template_id = data.get("game_template_id")  # JSON sends `game_template_id`
        predictions_data = data.get("predictions", [])
        
        group = get_object_or_404(UserGroup, id=group_id)
        game_template = get_object_or_404(GameTemplate, id=template_id)

        # 🔑 Create or fetch the GameInstance for this group and template
        game_instance, created = GameInstance.objects.get_or_create(
            template=game_template,
            group=group,
            defaults={"entry_fee": Decimal("5.00")}
        )

        # 🔁 Loop through and save predictions (fixtures with user predictions only)
        for item in predictions_data:
            fixture_id = item.get("fixture_id")
            home_score = item.get("home_score")
            away_score = item.get("away_score")

            fixture = get_object_or_404(Fixture, id=fixture_id)

            prediction, _ = Prediction.objects.update_or_create(
                game_instance=game_instance,
                player=user,
                fixture=fixture,
                defaults={
                    "predicted_home_score": home_score,
                    "predicted_away_score": away_score,
                }
            )

        # 👥 Add the player to the game instance if not already added
        game_instance.players.add(user)

        return JsonResponse({"status": "success", "game_instance_id": game_instance.id})

    return JsonResponse({"error": "Invalid request method"}, status=400)