from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db import transaction
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
        context["user_groups"] = self.request.user.joined_groups.all()
        return context


@login_required
##@transaction.atomic
def submit_predictions(request):
    if request.method == "POST":
        user = request.user
        group_id = request.POST.get("group_id")
        template_slug = request.POST.get("template_slug")  # e.g. "midweek-2025-wk30"
        predictions_data = request.POST.get("predictions")  # sent as JSON or form data

        group = get_object_or_404(UserGroup, id=group_id)
        game_template = get_object_or_404(GameTemplate, slug=template_slug)

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