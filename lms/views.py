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
from collections import defaultdict


@login_required
def lms_pick(request, game_id, round_id):
    game = get_object_or_404(LMSGame, id=game_id)
    round = get_object_or_404(LMSRound, id=round_id, game=game)

    entry, created = LMSEntry.objects.get_or_create(game=game, user=request.user)

    if not entry.alive:
        messages.error(request, "You have been eliminated from this game.")
        return redirect("lms_game_detail", game_id=game.id)

    if LMSPick.objects.filter(entry=entry, round=round).exists():
        messages.warning(request, "You have already made a pick for this round.")
        return redirect("lms_game_detail", game_id=game.id)

    if request.method == "POST":
        print("DEBUG POST DATA:", request.POST)  # 👈 log form data

        form = LMSPickForm(request.POST, game=game, round=round, entry=entry)
        if form.is_valid():
            team_name = form.cleaned_data["team_name"]
            print("DEBUG VALID TEAM:", team_name)  # 👈 log chosen team

            if entry.picks.filter(team_name=team_name).exists():
                messages.error(request, f"You already picked {team_name} in a previous round.")
            else:
                fixture = round.fixtures.filter(
                    home_team=team_name
                ).first() or round.fixtures.filter(
                    away_team=team_name
                ).first()

                print("DEBUG MATCHED FIXTURE:", fixture)  # 👈 log fixture

                if fixture:
                    LMSPick.objects.create(
                        entry=entry,
                        round=round,
                        fixture=fixture,
                        team_name=team_name
                    )
                    messages.success(request, f"You picked {team_name} for this round.")
                    return redirect("lms_game_detail", game_id=game.id)
                else:
                    messages.error(request, "No fixture found for that team.")
        else:
            print("DEBUG FORM ERRORS:", form.errors)  # 👈 log form errors

    else:
        form = LMSPickForm(game=game, round=round, entry=entry)

    fixtures = round.fixtures.all()
    user_picks = LMSPick.objects.filter(entry__user=request.user, entry__game=game)
    used_teams = [pick.team_name for pick in user_picks]

    return render(request, "lms/lms_pick.html", {
        "game": game,
        "round": round,
        "entry": entry,
        "fixtures": fixtures,
        "used_teams": used_teams,
        "form": form,
    })

def lms_dashboard(request):
    now = timezone.now()

    #  live games that the user entered
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
        status = "No Pick"

        if next_round:
            existing_pick = LMSPick.objects.filter(entry=entry, round=next_round).select_related("fixture").first()

        # Determine status based on entry fields and picks
        if entry.eliminated_round == 0:
            status = "Out (No pick in Round 1)"
        elif not entry.alive:
            status = f"Out (Round {entry.eliminated_round})"
        elif existing_pick:
            fixture = existing_pick.fixture
            if fixture and getattr(fixture, "status", "").upper() == "FINISHED":
                # Did the pick win?
                if (fixture.home_team == existing_pick.team_name and fixture.home_score > fixture.away_score) or \
                   (fixture.away_team == existing_pick.team_name and fixture.away_score > fixture.home_score):
                    status = "Alive"
                else:
                    status = f"Out (Round {entry.eliminated_round})" if entry.eliminated_round else "Out"
            else:
                status = "Pending"
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
        if round1 and round1.start_date > now:
            joinable_games.append({
                'game': game,
                'round1': round1,
            })

    context = {
        "entries_with_rounds": entries_with_rounds,
        "joinable_games": joinable_games,
    }

    import pprint
    
    pprint.pprint({
        "entries_with_rounds": entries_with_rounds,
        "joinable_games": joinable_games,
    })
    return render(request, "lms/dashboard.html", context)

@login_required
def lms_game_detail(request, game_id):
    game = get_object_or_404(LMSGame, id=game_id)
    round_obj = game.rounds.filter(completed=False).first()
    entry = LMSEntry.objects.filter(user=request.user, game=game).first()

    user_pick = None
    if entry and round_obj:
        user_pick = LMSPick.objects.filter(entry=entry, round=round_obj).first()

    entries = LMSEntry.objects.filter(game=game).select_related("user")
    rounds = game.rounds.order_by("round_number")

    # Map league code to display name
    LEAGUE_DISPLAY_NAMES = {
        "EPL": "Premier League",
        "ECH": "Championship",
        "EL1": "League One",
        "EL2": "League Two",
    }
    league_display_name = LEAGUE_DISPLAY_NAMES.get(game.league, game.league)

    # Preload all picks for this game
    all_picks = LMSPick.objects.filter(
        entry__game=game,
        round__completed=True
        ).select_related("entry__user", "round").order_by("round__round_number")


    # Organize picks by entry and round
    picks_by_entry_and_round = defaultdict(dict)
    for pick in all_picks:
        picks_by_entry_and_round[pick.entry.id][pick.round.id] = pick

    # Other active games in the same group
    other_games = LMSGame.objects.filter(group=game.group, active=True).exclude(id=game.id)

    # Prepare a structure:
    picks_table = []
    if entries.exists():
        for entry in entries:
            row = {"player": entry.user.username, "picks": []}
            for rnd in rounds:
                pick = picks_by_entry_and_round.get(entry, {}).get(rnd)
                row["picks"].append(pick)
            picks_table.append(row)

    # import pprint
    #
    #pprint.pprint({
    #    "game": game,
    #    "league_display_name": league_display_name,
    #    "round": round_obj,
    #    "entry": entry,
    #    "user_pick": user_pick,
    #    "entries": entries,
    #    "rounds": rounds,
    #    "picks_table": picks_table,
    #    "picks_by_entry_and_round": picks_by_entry_and_round,
    #    "other_games": other_games,
    #})
    print("Entries:", entries)
    print("Rounds:", list(rounds))
    print("Picks by entry and round:", picks_by_entry_and_round)


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

            return redirect("lms_dashboard")
    else:
        form = CreateLMSGameForm(user=request.user)

    return render(request, "lms/create_game.html", {"form": form})

def pick_is_correct(pick):
    fixture = pick.fixture  # Assuming LMSPick has FK to Fixture
    if not fixture or fixture.status != "FINISHED":
        return None  # Result unknown yet

    # If the team picked is the winner
    if fixture.home_team == pick.team and fixture.home_score > fixture.away_score:
        return True
    if fixture.away_team == pick.team and fixture.away_score > fixture.home_score:
        return True
    return False

