from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.generic.detail import DetailView
from django.db import transaction
from django.db.models import Prefetch, Count
from django.shortcuts import get_object_or_404, render
from .models import GameTemplate, GameInstance, Prediction, Fixture, GameEntry
from collections import defaultdict, OrderedDict
from groups.models import UserGroup
from django.utils.dateparse import parse_date
from django.utils.timezone import make_aware, get_current_timezone
from decimal import Decimal
from django.views import generic
import json
from datetime import date, datetime
from updater.utils import maybe_update

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
        
        
        user = self.request.user

        if user.is_authenticated:
            user_groups = self.request.user.joined_groups.all()
            group_entries = []

            for group in user_groups:
                try:
                    game_instance = GameInstance.objects.get(template=self.selected_template, group=group)
                    num_players = game_instance.players.count()
                    has_entered = user in game_instance.players.all()
                except GameInstance.DoesNotExist:
                    num_players = 0
                    has_entered = False

                group_entries.append({
                    "group": group,
                    "num_players": num_players,
                    "has_entered": has_entered,
                })

            context["group_entries"] = group_entries
        else:
            context["group_entries"] = []

        print(context)
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
def game_summary(request, group_id, template_slug):
    group = get_object_or_404(UserGroup, id=group_id)
    template = get_object_or_404(GameTemplate, slug=template_slug)
    try:
        game = GameInstance.objects.get(group=group, template=template)
        player_count = game.players.count()
        pot = player_count * game.entry_fee
        has_entered = request.user in game.players.all()
    except GameInstance.DoesNotExist:
        player_count = 0
        pot = 0
        has_entered = False

    return JsonResponse({
        "group_name": group.name,
        "player_count": player_count,
        "pot": str(pot),
        "has_entered": has_entered,
        "game_id": game.id if has_entered else None
    })

class GameDetailView(DetailView):
    model = GameInstance
    template_name = "score_predict/game_detail.html"
    context_object_name = "game"

    def dispatch(self, request, *args, **kwargs):
        maybe_update()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        game = self.object

        # Prefetch predictions for all entries in one go
        entries = GameEntry.objects.filter(game=game).select_related('player').order_by('-total_score', '-alt_score')

        prediction_data = []
        for entry in entries:
            predictions = Prediction.objects.filter(game_instance=game, player=entry.player).select_related('fixture')
            prediction_data.append({
                'player': entry.player,
                'total_score': entry.total_score,
                'alt_score': entry.alt_score,
                'predictions': predictions,
            })

        context['entries'] = prediction_data
        return context

def points_scoring(request):
    return render(request, 'score_predict/scoring.html')


@login_required
def game_history(request):
    # Groups the user belongs to
    groups = UserGroup.objects.filter(members=request.user)
    # groups = request.user.joined_groups.all()

    # Get selected group from query params (default to first group)
    group_id = request.GET.get("group")
    selected_group = None
    games = []

    if groups.exists():
        if group_id:
            selected_group = groups.filter(id=group_id).first()
        else:
            selected_group = groups.first()

        # Get completed games for that group (winner is not None)
        games = (
            GameInstance.objects.filter(group=selected_group)
            .exclude(winners__isnull=True)
            .prefetch_related("winners") 
             .annotate(player_count=Count('players'))  # Count the players M2M relation
            .order_by("-id")
        )
        
       # Add prize pot info for each game
    games_with_pot = []
    for game in games:
        player_count = game.players.count()
        prize_pot = player_count * game.entry_fee
        games_with_pot.append({
            'game': game,
            'player_count': player_count,
            'prize_pot': prize_pot,
        })

    context = {
        'groups': groups,
        'selected_group': selected_group,
        'games': games_with_pot,
    }
    return render(request, 'score_predict/game_history.html', context)