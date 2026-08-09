from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.generic.detail import DetailView
from django.views.generic import ListView
from django.db import transaction
from django.db.models import Prefetch, Count, Q, Sum, Max
from django.shortcuts import get_object_or_404, render
from .models import GameTemplate, GameInstance, Prediction, Fixture, GameEntry
from player_messages.models import PlayerMessage
from collections import defaultdict, OrderedDict
from groups.models import UserGroup
from django.utils import timezone
from django.utils.timezone import now, get_current_timezone
from decimal import Decimal
import json
from datetime import date, datetime
from player_messages.utils import create_message


LEAGUE_ORDER = {
    "EPL": "Premier League",
    "ECH": "Championship",
    "EL1": "League One",
    "EL2": "League Two",
}


class FixtureList(ListView):
    template_name = "score_predict/fixtures.html"
    model = Fixture
    context_object_name = "fixtures"

    def get_queryset(self):
        today = datetime.now(get_current_timezone()).date()
        next_template = (
            GameTemplate.objects
            .filter(Q(start_date__gte=today) | Q(end_date__gte=today))
            .order_by("start_date")
            .first()
        )
        self.selected_template = next_template
        if next_template:
            return (
                Fixture.objects
                .filter(gametemplate=next_template)
                .exclude(status_code__in=[60, 90])
                .order_by("date")
            )
        return Fixture.objects.none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        grouped = defaultdict(list)
        for fixture in self.object_list:
            if fixture.league_short_name in LEAGUE_ORDER:
                grouped[fixture.league_short_name].append(fixture)

        ordered_grouped = OrderedDict()
        for key in LEAGUE_ORDER:
            if key in grouped:
                ordered_grouped[LEAGUE_ORDER[key]] = grouped[key]

        context["fixture_list"] = ordered_grouped
        context["game_template"] = self.selected_template

        user = self.request.user
        if user.is_authenticated:
            user_groups = user.joined_groups.all()
            group_entries = []
            for group in user_groups:
                game_instance = None
                num_players = 0
                has_entered = False
                prize_pot = Decimal("0.00")
                if self.selected_template:
                    try:
                        game_instance = GameInstance.objects.get(
                            template=self.selected_template, group=group
                        )
                        num_players = game_instance.players.count()
                        has_entered = game_instance.players.filter(id=user.id).exists()
                        prize_pot = game_instance.entry_fee * num_players
                    except GameInstance.DoesNotExist:
                        pass

                group_entries.append({
                    "group": group,
                    "game_instance": game_instance,
                    "num_players": num_players,
                    "has_entered": has_entered,
                    "prize_pot": prize_pot,
                })
            context["group_entries"] = group_entries
        else:
            context["group_entries"] = []

        return context


@login_required
def submit_predictions(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=400)

    try:
        data = json.loads(request.body)
        user = request.user
        group_id = data.get("group_id")
        template_id = data.get("game_template_id")
        predictions_data = data.get("predictions", [])

        if not group_id or not template_id or not isinstance(predictions_data, list):
            return JsonResponse({"error": "Invalid data format"}, status=400)

        group = get_object_or_404(UserGroup, id=group_id)
        game_template = get_object_or_404(GameTemplate, id=template_id)

        game_instance, created = GameInstance.objects.get_or_create(
            template=game_template,
            group=group,
            defaults={"entry_fee": Decimal("5.00")},
        )

        # Reject if any fixture has already started
        fixture_ids = [item.get("fixture_id") for item in predictions_data if item.get("fixture_id")]
        fixtures = Fixture.objects.filter(id__in=fixture_ids)
        started = fixtures.filter(date__lte=now())
        if started.exists():
            names = ", ".join(f"{f.home_team} vs {f.away_team}" for f in started)
            return JsonResponse({
                "error": f"Cannot submit -- fixtures already started: {names}"
            }, status=400)

        for item in predictions_data:
            fixture_id = item.get("fixture_id")
            home_score = item.get("home_score")
            away_score = item.get("away_score")
            if fixture_id is None or home_score is None or away_score is None:
                continue
            fixture = get_object_or_404(Fixture, id=fixture_id)
            Prediction.objects.update_or_create(
                game_instance=game_instance,
                player=user,
                fixture=fixture,
                defaults={
                    "predicted_home_score": home_score,
                    "predicted_away_score": away_score,
                },
            )

        if not game_instance.players.filter(id=user.id).exists():
            game_instance.players.add(user)
            create_message(
                code="SP-ENT",
                context={"User": user},
                group=group,
                receiver=user,
                actor=user,
                link="scores",
            )

        return JsonResponse({"status": "success", "game_instance_id": game_instance.id})

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def game_summary(request, group_id, template_slug):
    group = get_object_or_404(UserGroup, id=group_id)
    template = get_object_or_404(GameTemplate, slug=template_slug)
    game = None
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
        "game_id": game.id if game else None,
    })


class GameDetailView(DetailView):
    model = GameInstance
    template_name = "score_predict/game_detail.html"
    context_object_name = "game"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        game = self.object

        entries = (
            GameEntry.objects
            .filter(game=game)
            .select_related("player")
            .order_by("-total_score", "-alt_score")
        )

        prediction_data = []
        for entry in entries:
            predictions = (
                Prediction.objects
                .filter(game_instance=game, player=entry.player)
                .select_related("fixture")
                .order_by("fixture__date")
            )
            prediction_data.append({
                "player": entry.player,
                "total_score": entry.total_score,
                "alt_score": entry.alt_score,
                "predictions": predictions,
            })

        # Fixture score summary for header
        fixtures = (
            Fixture.objects
            .filter(gametemplate=game.template)
            .exclude(status_code__in=[60, 90])
            .order_by("date")
        )
        finished_count = fixtures.filter(status_code=100).count()

        context["entries"] = prediction_data
        context["fixtures"] = fixtures
        context["finished_count"] = finished_count
        context["total_fixtures"] = fixtures.count()
        context["is_complete"] = game.winners.exists()
        return context


def points_scoring(request):
    return render(request, "score_predict/scoring.html")


def get_season_year(date):
    """
    Football season year = the year the season STARTED.
    Seasons run Aug-May, so Aug 2024 - May 2025 = season 2024.
    """
    if date.month >= 8:
        return date.year
    return date.year - 1


@login_required
def game_history(request):
    groups = UserGroup.objects.filter(members=request.user)
    group_id = request.GET.get("group")
    season_filter = request.GET.get("season")  # year string or "all"
    selected_group = None
    games_with_data = []
    overall_pnl = Decimal("0.00")
    available_seasons = []

    if groups.exists():
        selected_group = groups.filter(id=group_id).first() if group_id else groups.first()

        all_games = (
            GameInstance.objects
            .filter(group=selected_group)
            .select_related("template")
            .prefetch_related("winners")
            .annotate(player_count=Count("players"))
            .order_by("-template__start_date")
        )

        # Build available seasons from game templates
        season_years = sorted(
            set(get_season_year(g.template.start_date) for g in all_games),
            reverse=True,
        )
        available_seasons = season_years

        # Default to most recent season
        if not season_filter and season_years:
            season_filter = str(season_years[0])

        # Apply season filter
        if season_filter and season_filter != "all":
            try:
                sy = int(season_filter)
                # Season sy runs Aug sy to May sy+1
                from datetime import date as date_type
                season_start = date_type(sy, 8, 1)
                season_end = date_type(sy + 1, 7, 31)
                games = all_games.filter(
                    template__start_date__gte=season_start,
                    template__start_date__lte=season_end,
                )
            except ValueError:
                games = all_games
        else:
            games = all_games

        for game in games:
            player_count = game.players.count()
            prize_pot = player_count * game.entry_fee

            user_entry = GameEntry.objects.filter(
                game=game, player=request.user
            ).first()

            user_rank = None
            if user_entry:
                better_count = GameEntry.objects.filter(
                    game=game,
                    total_score__gt=user_entry.total_score
                ).count()
                user_rank = better_count + 1

            pnl = None
            if user_entry:
                won = Decimal("0.00")
                if request.user in game.winners.all():
                    winner_count = game.winners.count()
                    won = prize_pot / winner_count
                cost = game.entry_fee
                pnl = won - cost
                overall_pnl += pnl

            games_with_data.append({
                "game": game,
                "player_count": player_count,
                "prize_pot": prize_pot,
                "user_entry": user_entry,
                "user_rank": user_rank,
                "pnl": pnl,
            })

    context = {
        "groups": groups,
        "selected_group": selected_group,
        "games": games_with_data,
        "overall_pnl": overall_pnl,
        "available_seasons": available_seasons,
        "selected_season": season_filter,
    }
    return render(request, "score_predict/game_history.html", context)
