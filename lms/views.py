# lms/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .models import LMSGame, LMSRound, LMSEntry, LMSGame, LMSPick
from .forms import LMSPickForm
from groups.models import UserGroup


@login_required
def lms_pick(request, game_id, round_id):
    game = get_object_or_404(LMSGame, id=game_id)
    round = get_object_or_404(LMSRound, id=round_id, game=game)
    entry = get_object_or_404(LMSEntry, game=game, user=request.user)

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
    """
    Show the user's active Last Man Standing games for all groups they are in.
    """
    # Get all LMS games the user has joined via LMSEntry
    user_entries = (
        LMSEntry.objects
        .filter(user=request.user, game__active=True)
        .select_related("game", "game__group")
        .order_by("game__created_at")
    )

    # You could also add progress info for each entry
    entries_with_rounds = []
    for entry in user_entries:
        # Get the next round that isn’t completed yet
        next_round = (
            LMSRound.objects
            .filter(game=entry.game, completed=False)
            .order_by("round_number")
            .first()
        )

        # Check if the user already made a pick for that round
        existing_pick = None
        if next_round:
            existing_pick = LMSPick.objects.filter(entry=entry, round=next_round).first()

        entries_with_rounds.append({
            "entry": entry,
            "next_round": next_round,
            "existing_pick": existing_pick,
        })

    context = {
        "entries_with_rounds": entries_with_rounds,
    }

    return render(request, "lms/dashboard.html", context)

def lms_game_detail(request, game_id):
    game = get_object_or_404(LMSGame, id=game_id)
    round_obj = game.rounds.filter(is_active=True).first()
    entry = LMSEntry.objects.filter(user=request.user, game=game).first()

    user_pick = None
    if entry and round_obj:
        user_pick = LMSPick.objects.filter(entry=entry, round=round_obj).first()

    entries = LMSEntry.objects.filter(game=game).select_related("user")

    # Get all unfinished games in this group (for dropdown/tabs)
    other_games = LMSGame.objects.filter(group=game.group, finished=False).exclude(id=game.id)

    return render(request, "lms/game_detail.html", {
        "game": game,
        "round": round_obj,
        "entry": entry,
        "user_pick": user_pick,
        "entries": entries,
        "other_games": other_games,
    })