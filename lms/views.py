from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max
from django.utils import timezone
from django.utils.timezone import now
from datetime import timedelta, date as date_type
from decimal import Decimal
from .models import LMSGame, LMSRound, LMSEntry, LMSPick
from .forms import LMSPickForm, CreateLMSGameForm
from groups.models import UserGroup
from lms.utils import get_auto_pick_teams_for_round
from score_predict.models import Fixture
from collections import defaultdict
from player_messages.utils import create_message


def get_season_year(dt):
    """Football season year = year the season started (Aug start)."""
    d = dt.date() if hasattr(dt, 'date') else dt
    return d.year if d.month >= 8 else d.year - 1


def round_is_closed(round_obj, game):
    if game.deadline_mode == "extended":
        return False
    earliest = round_obj.fixtures.order_by("date").first()
    if not earliest:
        return False
    return timezone.now() >= earliest.date


@login_required
def lms_pick(request, game_id, round_id):
    game = get_object_or_404(LMSGame, id=game_id)
    round_obj = get_object_or_404(LMSRound, id=round_id, game=game)
    entry, created = LMSEntry.objects.get_or_create(game=game, user=request.user)

    if game.deadline_mode == "first_game" and round_is_closed(round_obj, game):
        messages.error(request, "The round is closed -- no more picks allowed.")
        return redirect("lms_game_detail", game_id=game.id)

    if not entry.alive:
        messages.error(request, "You have been eliminated from this game.")
        return redirect("lms_game_detail", game_id=game.id)

    if LMSPick.objects.filter(entry=entry, round=round_obj).exists():
        messages.warning(request, "You have already made a pick for this round.")
        return redirect("lms_game_detail", game_id=game.id)

    if request.method == "POST":
        team_name = request.POST.get("team_name", "").strip()
        if not team_name:
            messages.error(request, "Please select a team.")
        elif entry.picks.filter(team_name=team_name).exists():
            messages.error(request, f"You already picked {team_name} in a previous round.")
        else:
            fixture = (
                round_obj.fixtures.filter(home_team=team_name).first()
                or round_obj.fixtures.filter(away_team=team_name).first()
            )
            if not fixture:
                messages.error(request, "No fixture found for that team.")
            elif fixture.date <= timezone.now():
                messages.error(request, f"Cannot pick {team_name} -- that fixture has already started.")
            else:
                LMSPick.objects.create(
                    entry=entry, round=round_obj,
                    fixture=fixture, team_name=team_name
                )
                code = "LM-ENT" if round_obj.round_number == 1 else "LM-PCK"
                create_message(
                    code=code,
                    context={"User": request.user, "league": game.get_league_display(),
                             "round": round_obj.round_number},
                    receiver=request.user, actor=request.user,
                    group=game.group,
                    link=f"lms_game_detail:{game.id}",
                )
                messages.success(request, f"You picked {team_name}!")
                return redirect("lms_game_detail", game_id=game.id)

    fixtures = round_obj.fixtures.all().order_by("date")
    user_picks = LMSPick.objects.filter(entry__user=request.user, entry__game=game)
    used_teams = [p.team_name for p in user_picks]

    return render(request, "lms/lms_pick.html", {
        "game": game,
        "round": round_obj,
        "entry": entry,
        "fixtures": fixtures,
        "used_teams": used_teams,
    })


@login_required
def lms_dashboard(request):
    current = now()
    user_entries = (
        LMSEntry.objects
        .filter(user=request.user, game__active=True)
        .select_related("game", "game__group")
        .order_by("game__created_at")
    )

    entries_with_rounds = []
    for entry in user_entries:
        next_round = (
            LMSRound.objects
            .filter(game=entry.game, completed=False)
            .order_by("round_number")
            .first()
        )
        existing_pick = None
        if next_round:
            existing_pick = (
                LMSPick.objects
                .filter(entry=entry, round=next_round)
                .select_related("fixture")
                .first()
            )

        if entry.eliminated_round == 0:
            status = "Out"
        elif not entry.alive:
            status = "Out"
        elif existing_pick:
            status = "Pending" if existing_pick.result == "PENDING" else "Alive"
        else:
            status = "No Pick"

        entries_with_rounds.append({
            "entry": entry,
            "next_round": next_round,
            "existing_pick": existing_pick,
            "status": status,
        })

    user_groups = request.user.joined_groups.all()
    potential_games = (
        LMSGame.objects
        .filter(group__in=user_groups, active=True)
        .exclude(entries__user=request.user)
        .prefetch_related("rounds")
    )

    joinable_games = []
    for game in potential_games:
        round1 = game.rounds.filter(round_number=1).first()
        if round1 and round1.start_date > current:
            joinable_games.append({"game": game, "round1": round1})

    return render(request, "lms/dashboard.html", {
        "entries_with_rounds": entries_with_rounds,
        "joinable_games": joinable_games,
    })


@login_required
def lms_game_detail(request, game_id):
    game = get_object_or_404(LMSGame, id=game_id)
    entry = LMSEntry.objects.filter(game=game, user=request.user).first()

    round_obj = (
        LMSRound.objects.filter(game=game, completed=False)
        .order_by("round_number").first()
    ) or LMSRound.objects.filter(game=game).order_by("-round_number").first()

    rounds = LMSRound.objects.filter(game=game).order_by("round_number").prefetch_related("fixtures")
    entries = LMSEntry.objects.filter(game=game).select_related("user")

    user_pick = None
    if entry and round_obj:
        user_pick = LMSPick.objects.filter(entry=entry, round=round_obj).first()

    # Build picks_by_entry_and_round for history table
    all_picks = LMSPick.objects.filter(
        entry__game=game
    ).select_related("entry__user", "round", "fixture")

    picks_by_entry_and_round = defaultdict(dict)
    for pick in all_picks:
        picks_by_entry_and_round[pick.entry_id][pick.round_id] = pick

    league_display_name = game.get_league_display()
    prize_pot = game.entries.count() * game.entry_fee

    # Winner info for inactive games
    winner_entry = None
    winner_last_pick = None
    entries_for_results = None
    if not game.active:
        if game.winner:
            winner_entry = LMSEntry.objects.filter(
                game=game, user=game.winner
            ).first()
            if winner_entry:
                winner_last_pick = (
                    LMSPick.objects
                    .filter(entry=winner_entry, result="WIN")
                    .order_by("-round__round_number")
                    .first()
                )
        entries_for_results = sorted(
            entries,
            key=lambda e: (e.eliminated_round is None, e.eliminated_round or 0)
        )

    # Show current round picks only after deadline
    show_current_picks = False
    if round_obj:
        active_entries = entries.filter(alive=True)
        if round_obj.round_number == 1:
            first_fixture = round_obj.fixtures.order_by("date").first()
            if first_fixture and timezone.now() >= first_fixture.date:
                show_current_picks = True
        else:
            picks_made = LMSPick.objects.filter(
                round=round_obj, entry__in=active_entries
            ).count()
            if picks_made == active_entries.count() and active_entries.count() > 0:
                show_current_picks = True

    other_games = LMSGame.objects.filter(
        group=game.group, active=True
    ).exclude(id=game.id)

    return render(request, "lms/game_detail.html", {
        "game": game,
        "league_display_name": league_display_name,
        "round": round_obj,
        "entry": entry,
        "user_pick": user_pick,
        "entries": entries,
        "rounds": rounds,
        "picks_by_entry_and_round": picks_by_entry_and_round,
        "other_games": other_games,
        "prize_pot": prize_pot,
        "winner_entry": winner_entry,
        "winner_last_pick": winner_last_pick,
        "entries_for_results": entries_for_results,
        "show_current_picks": show_current_picks,
        "now": timezone.now(),
    })


@login_required
def create_game(request):
    if request.method == "POST":
        form = CreateLMSGameForm(request.POST, user=request.user)
        if form.is_valid():
            game = form.save(commit=False)
            game.save()

            create_message(
                code="LM-NEW",
                context={"User": request.user, "league": game.get_league_display()},
                group=game.group,
            )

            today = now().date()
            created_round = None

            # Look ahead up to 30 days for first valid fixture block
            for days_ahead in range(0, 30):
                current_day = today + timedelta(days=days_ahead)
                weekday = current_day.weekday()

                if weekday == 4:   # Friday -> Fri-Mon block
                    block_start = current_day
                    block_end = block_start + timedelta(days=3)
                elif weekday == 1:  # Tuesday -> Tue-Thu block
                    block_start = current_day
                    block_end = block_start + timedelta(days=2)
                else:
                    continue

                fixtures = Fixture.objects.filter(
                    league_short_name=game.league,
                    date__date__range=(block_start, block_end),
                ).order_by("date")


                if fixtures.count() >= 7:
                    created_round = LMSRound.objects.create(
                        game=game,
                        round_number=1,
                        start_date=fixtures.first().date,
                        end_date=fixtures.last().date,
                    )
                    created_round.fixtures.set(fixtures)

                    auto_picks = get_auto_pick_teams_for_round(
                        game, created_round, fixtures, count=4
                    )
                    if auto_picks:
                        created_round.auto_pick_team1 = auto_picks[0]
                        created_round.auto_pick_team2 = auto_picks[1] if len(auto_picks) > 1 else None
                        created_round.auto_pick_team3 = auto_picks[2] if len(auto_picks) > 2 else None
                        created_round.save()
                    break

            if not created_round:
                messages.warning(
                    request,
                    "Game created. No fixture block found yet -- "
                    "Round 1 will be created automatically before the next gameweek."
                )
            else:
                messages.success(request, "Game created with Round 1 ready.")

            return redirect("lms_dashboard")
    else:
        form = CreateLMSGameForm(user=request.user)
    return render(request, "lms/create_game.html", {"form": form})


@login_required
def lms_history(request):
    groups = UserGroup.objects.filter(members=request.user)
    group_id = request.GET.get("group")
    season_filter = request.GET.get("season")
    selected_group = None
    games_with_data = []
    available_seasons = []

    # Per-league P&L
    league_pnl = defaultdict(lambda: Decimal("0.00"))
    overall_pnl = Decimal("0.00")

    if groups.exists():
        selected_group = (
            groups.filter(id=group_id).first() if group_id else groups.first()
        )

        all_games = (
            LMSGame.objects
            .filter(group=selected_group, active=False)
            .select_related("winner")
            .annotate(player_count=Count("entries"))
            .order_by("-created_at")
        )

        # Build available seasons
        season_years = sorted(
            set(get_season_year(g.created_at) for g in all_games),
            reverse=True,
        )
        available_seasons = season_years

        if not season_filter and season_years:
            season_filter = str(season_years[0])

        if season_filter and season_filter != "all":
            try:
                sy = int(season_filter)
                season_start = date_type(sy, 8, 1)
                season_end = date_type(sy + 1, 7, 31)
                games = all_games.filter(
                    created_at__date__gte=season_start,
                    created_at__date__lte=season_end,
                )
            except ValueError:
                games = all_games
        else:
            games = all_games

        for game in games:
            player_count = game.player_count
            prize_pot = player_count * game.entry_fee

            user_entry = LMSEntry.objects.filter(
                game=game, user=request.user
            ).first()

            user_round_eliminated = None
            if user_entry and not user_entry.alive:
                user_round_eliminated = user_entry.eliminated_round

            pnl = None
            if user_entry:
                won = prize_pot if game.winner == request.user else Decimal("0.00")
                pnl = won - game.entry_fee
                overall_pnl += pnl
                league_pnl[game.get_league_display()] += pnl

            games_with_data.append({
                "game": game,
                "player_count": player_count,
                "prize_pot": prize_pot,
                "user_entry": user_entry,
                "user_round_eliminated": user_round_eliminated,
                "pnl": pnl,
            })

    context = {
        "groups": groups,
        "selected_group": selected_group,
        "games": games_with_data,
        "overall_pnl": overall_pnl,
        "league_pnl": dict(league_pnl),
        "available_seasons": available_seasons,
        "selected_season": season_filter,
    }
    return render(request, "lms/lms_history.html", context)


def lms_rules(request):
    return render(request, "lms/rules.html")