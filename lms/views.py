# lms/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.utils import timezone
from django.utils.timezone import now
from datetime import timedelta
from .models import LMSGame, LMSRound, LMSEntry, LMSGame, LMSPick
from .forms import LMSPickForm, CreateLMSGameForm
from groups.models import UserGroup
from score_predict.models import Fixture


@login_required
def lms_pick(request, game_id, round_id):
    game = get_object_or_404(LMSGame, id=game_id)
    round = get_object_or_404(LMSRound, id=round_id, game=game)

    # Get or create entry for the user
    entry, created = LMSEntry.objects.get_or_create(game=game, user=request.user)

    if not entry.alive:
        messages.error(request, "You have been eliminated from this game.")
        return redirect("lms_game_detail", game_id=game.id)

    # Check if user already made a pick this round
    if LMSPick.objects.filter(entry=entry, round=round).exists():
        messages.warning(request, "You have already made a pick for this round.")
        return redirect("lms_game_detail", game_id=game.id)

    if request.method == "POST":
        form = LMSPickForm(request.POST, game=game, round=round, entry=entry)
        if form.is_valid():
            team_name = form.cleaned_data["team_name"]

            # Ensure team not already picked in earlier rounds
            if entry.picks.filter(team_name=team_name).exists():
                messages.error(request, f"You already picked {team_name} in a previous round.")
            else:
                # Create pick
                LMSPick.objects.create(
                    entry=entry,
                    round=round,
                    fixture=round.get_fixtures().filter(
                        home_team=team_name
                    ).first() or round.get_fixtures().filter(
                        away_team=team_name
                    ).first(),
                    team_name=team_name
                )
                messages.success(request, f"You picked {team_name} for this round.")
                return redirect("lms_game_detail", game_id=game.id)
    else:
        form = LMSPickForm(game=game, round=round, entry=entry)

    fixtures = round.get_fixtures()

    return render(request, "lms/lms_pick.html", {
        "game": game,
        "round": round,
        "entry": entry,
        "fixtures": fixtures,
        "form": form,
    })

def lms_dashboard(request):
    now = timezone.now()

    # Games user has joined
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
            existing_pick = LMSPick.objects.filter(entry=entry, round=next_round).first()

        entries_with_rounds.append({
            "entry": entry,
            "next_round": next_round,
            "existing_pick": existing_pick,
        })

    # User's groups
    user_groups = request.user.joined_groups.all()

    # Potential joinable games: active, user in group, not joined yet
    potential_games = (
        LMSGame.objects
        .filter(group__in=user_groups, active=True)
        .exclude(entries__user=request.user)
        .prefetch_related("rounds")
    )

    # Filter joinable games where round 1 exists and hasn't started yet
    joinable_games = []
    for game in potential_games:
        round1 = game.rounds.filter(round_number=1).first()
        if round1 and round1.start_date > now:
            game.next_round = round1  # handy for template
            joinable_games.append(game)

    for game in potential_games:
        round1 = game.rounds.filter(round_number=1).first()  # instead of get()
    
        if round1 and round1.start_date > now:
            joinable_games.append({
                'game': game,
                'round1': round1,
            })

    context = {
        "entries_with_rounds": entries_with_rounds,
        "joinable_games": joinable_games,
    }
    return render(request, "lms/dashboard.html", context)


def lms_game_detail(request, game_id):
    game = get_object_or_404(LMSGame, id=game_id)
    round_obj = game.rounds.filter(completed=False).first()
    entry = LMSEntry.objects.filter(user=request.user, game=game).first()

    user_pick = None
    if entry and round_obj:
        user_pick = LMSPick.objects.filter(entry=entry, round=round_obj).first()

    entries = LMSEntry.objects.filter(game=game).select_related("user")

    # Get all unfinished games in this group (for dropdown/tabs)
    other_games = LMSGame.objects.filter(group=game.group, active=True).exclude(id=game.id)

    return render(request, "lms/game_detail.html", {
        "game": game,
        "round": round_obj,
        "entry": entry,
        "user_pick": user_pick,
        "entries": entries,
        "other_games": other_games,
    })

@login_required
def create_game(request):
    if request.method == "POST":
        form = CreateLMSGameForm(request.POST, user=request.user)
        if form.is_valid():
            game = form.save(commit=False)
            game.save()

            today = now().date()
            created_round = None

            print(f"DEBUG: Game League {game.league} ")

            # Look ahead up to 30 days for the first valid block
            for days_ahead in range(0, 30):
                current_day = today + timedelta(days=days_ahead)
                weekday = current_day.weekday()  # Monday=0 ... Sunday=6

                if weekday == 4:  # Friday → weekend block
                    block_start = current_day
                    block_end = block_start + timedelta(days=3)  # Fri–Mon
                elif weekday == 1:  # Tuesday → midweek block
                    block_start = current_day
                    block_end = block_start + timedelta(days=2)  # Tue–Thu
                else:
                    continue  # not the start of a block, skip

                fixtures = Fixture.objects.filter(
                    league_short_name=game.league,
                    date__range=(block_start, block_end)
                ).order_by("date")

                print(f"DEBUG: Checking block {block_start} to {block_end}, found {fixtures.count()} fixtures")

                if fixtures.count() >= 7:
                    created_round = LMSRound.objects.create(
                        game=game,
                        round_number=1,
                        start_date=fixtures.first().date,
                        end_date=fixtures.last().date,
                    )
                    created_round.fixtures.set(fixtures)
                    print(f"DEBUG: Created LMSRound {created_round} with {fixtures.count()} fixtures")
                    break  # stop after creating the first valid round

            if not created_round:
                print("DEBUG: No valid fixture block found within 30 days.")

            return redirect("lms_game_detail", game.id)
    else:
        form = CreateLMSGameForm(user=request.user)

    return render(request, "lms/create_game.html", {"form": form})