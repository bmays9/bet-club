# golf/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.utils.timezone import now
from datetime import date, timedelta

from golf.models import (
    GolfEvent, EventEntry, GolferScore, UserOrder,
    GolfGame, GolfGameEntry, DraftSlot, DraftPick, RolloverPot,
    GolfGameResult,
)
from golf.forms import CreateGolfGameForm
from golf.services.draft import (
    submit_pick, get_available_golfers, get_best_available_for_player
)
from golf.utils import maybe_fetch_golf_events


# ---------------------------------------------
# Event list -- main golf landing page
# ---------------------------------------------

@login_required
def filtered_events(request):
    from django.utils.timezone import make_aware
    from datetime import datetime as dt
    from golf.utils import maybe_fetch_golf_events
    maybe_fetch_golf_events()  # no-op if fetched within last 7 days or same year

    today = now().date()
    # Window: ended no more than 7 days ago, starts no more than 10 days ahead
    window_start = make_aware(dt.combine(today - timedelta(days=7), dt.min.time()))
    window_end = make_aware(dt.combine(today + timedelta(days=10), dt.max.time()))

    # Fetch any event whose window overlaps with our display range:
    # - started before window_end AND ended after window_start
    # This correctly catches: finished (last 7d), live (ongoing), upcoming (next 10d)
    events = list(
        GolfEvent.objects.filter(
            start_date__lte=window_end,
            end_date__gte=window_start,
        ).order_by("start_date").select_related("tour")
    )



    user_groups = request.user.joined_groups.all()

    live_events = []
    upcoming_events = []
    finished_events = []

    # Pre-fetch entry existence for all events in one query (no API calls)
    events_with_entries = set(
        EventEntry.objects.filter(event__in=events)
        .values_list("event_id", flat=True)
        .distinct()
    )

    # Pre-fetch all group games for these events in one query
    all_group_games = list(
        GolfGame.objects.filter(
            event__in=events, group__in=user_groups
        ).select_related("group", "event")
    )

    # Pre-fetch which games this user has joined
    joined_game_ids_global = set(
        GolfGameEntry.objects.filter(
            game__in=all_group_games, user=request.user
        ).values_list("game_id", flat=True)
    )

    # Organise group games by event id for O(1) lookup
    games_by_event = {}
    for g in all_group_games:
        games_by_event.setdefault(g.event_id, []).append(g)

    current = now()
    # For upcoming events with no entries yet, try fetching entries from API
    # Only do this for events starting in the future (not live or finished)
    from golf.management.commands.fetch_entries import fetch_entries
    for event in events:
        if event.id not in events_with_entries and event.start_date > current:
            print(f"[golf] no entries for upcoming event {event.name}, attempting fetch...")
            fetched = fetch_entries(event)
            if fetched:
                events_with_entries.add(event.id)
                print(f"[golf] entries fetched for {event.name}")
            else:
                print(f"[golf] no entries available yet for {event.name}")

    for event in events:
        event.has_entries = event.id in events_with_entries
        group_games = games_by_event.get(event.id, [])
        joined_game_ids = {g.id for g in group_games if g.id in joined_game_ids_global}

        groups_with_game = {g.group_id for g in group_games}
        can_create = any(ug.id not in groups_with_game for ug in user_groups)

        # Determine event state for display logic
        draft_open = event.draft_opens
        day_of_tournament = make_aware(dt.combine(event.start_date.date(), dt.min.time()))
        entries_open = current < draft_open          # before draft window
        draft_live = draft_open <= current < day_of_tournament  # draft window open
        tournament_started = current >= day_of_tournament
        can_create_game = not tournament_started and event.has_entries

        item = {
            "event": event,
            "group_games": group_games,
            "joined_game_ids": joined_game_ids,
            "user_groups": user_groups,
            "can_create": can_create and can_create_game,
            "entries_open": entries_open,
            "draft_live": draft_live,
            "tournament_started": tournament_started,
        }

        status_lower = event.status.lower() if event.status else ""

        # Add end_date buffer: treat end_date as end of that day (23:59:59)
        from django.utils.timezone import make_aware
        from datetime import datetime as dt
        end_of_day = make_aware(dt.combine(event.end_date.date(), dt.max.time()))

        is_live = "in progress" in status_lower or (event.start_date <= current <= end_of_day)
        is_finished = end_of_day < current
        is_upcoming = event.start_date > current

        if is_live:
            live_events.append(item)
        elif is_finished:
            finished_events.append(item)
        else:
            upcoming_events.append(item)

    return render(request, "golf/event_list.html", {
        "live_events": live_events,
        "upcoming_events": upcoming_events,
        "finished_events": finished_events,

    })


# ---------------------------------------------
# Create a game for an event
# ---------------------------------------------

@login_required
def create_golf_game(request, event_id):
    event = get_object_or_404(GolfEvent, tourn_id=event_id)

    if request.method == "POST":
        form = CreateGolfGameForm(request.POST, user=request.user)
        if form.is_valid():
            game = form.save(commit=False)
            game.event = event
            game.created_by = request.user
            game.save()

            # Auto-join the creator
            GolfGameEntry.objects.create(game=game, user=request.user)

            messages.success(request, f"Game created for {event.name}!")
            return redirect("golf_game_detail", game_id=game.id)
    else:
        form = CreateGolfGameForm(user=request.user)

    return render(request, "golf/create_game.html", {
        "form": form,
        "event": event,
    })


# ---------------------------------------------
# Join a game
# ---------------------------------------------

@login_required
def join_golf_game(request, game_id):
    game = get_object_or_404(GolfGame, id=game_id)

    if game.status != GolfGame.Status.OPEN:
        messages.error(request, "This game is no longer open to join.")
        return redirect("golf_game_detail", game_id=game.id)

    if GolfGameEntry.objects.filter(game=game, user=request.user).exists():
        messages.warning(request, "You have already joined this game.")
        return redirect("golf_game_detail", game_id=game.id)

    GolfGameEntry.objects.create(game=game, user=request.user)
    messages.success(request, f"You've joined the game for {game.event.name}!")
    return redirect("golf_game_detail", game_id=game.id)


# ---------------------------------------------
# Game detail page
# ---------------------------------------------

@login_required
def golf_game_detail(request, game_id):
    game = get_object_or_404(GolfGame, id=game_id)

    # Process any expired draft slots before rendering
    if game.status == GolfGame.Status.DRAFTING:
        from golf.services.draft import process_expired_slots, draft_is_complete
        process_expired_slots(game)
        if draft_is_complete(game):
            game.status = GolfGame.Status.ACTIVE
            game.save(update_fields=["status"])

    # Redirect to leaderboard once draft is done -- that's the main game page
    if game.status in (GolfGame.Status.ACTIVE, GolfGame.Status.FINISHED):
        from django.shortcuts import redirect as _redirect
        return _redirect("golf_leaderboard", game_id=game.id)

    user_entry = GolfGameEntry.objects.filter(game=game, user=request.user).first()

    entries = game.game_entries.select_related("user").order_by("draft_position")
    all_picks = DraftPick.objects.filter(game=game).select_related(
        "golfer", "game_entry__user"
    ).order_by("game_entry__draft_position", "round_number")

    # Organise picks by player
    picks_by_player = {}
    for pick in all_picks:
        uid = pick.game_entry.user_id
        picks_by_player.setdefault(uid, []).append(pick)

    # Draft schedule
    draft_slots = DraftSlot.objects.filter(game=game).select_related(
        "game_entry__user"
    ).order_by("pick_number")

    # Current active slot - must have real times set and be within window
    active_slot = draft_slots.filter(
        opens_at__isnull=False,
        opens_at__lte=now(),
        closes_at__gt=now(),
        completed=False,
    ).first()

    # If no active slot, check if there is a timed slot that hasn't opened yet
    # (i.e. the very next slot - opened but window not reached - shouldn't happen
    # in dynamic draft but guard anyway)
    if not active_slot:
        # Check for a slot with times set but not yet open
        next_timed = draft_slots.filter(
            opens_at__isnull=False,
            opens_at__gt=now(),
            completed=False,
        ).order_by("pick_number").first()
    else:
        next_timed = None

    # Rollover pot for this group
    rollover = RolloverPot.objects.filter(group=game.group).first()

    # Secondary pot = fines collected so far + rollover
    total_fines = sum(e.total_fines for e in entries)
    secondary_pot = total_fines + (rollover.balance if rollover else 0) + game.rollover_amount

    # Group members who haven't joined yet
    joined_user_ids = set(entries.values_list("user_id", flat=True))
    non_entrants = game.group.members.exclude(id__in=joined_user_ids)

    # ---- Draft-specific context ----
    available_golfers = []
    user_slot = None
    my_preferences = []
    already_picked_ids = set()
    picked_by = {}

    if game.status == GolfGame.Status.DRAFTING:
        # Available golfers (not yet picked)
        already_picked_ids = set(
            DraftPick.objects.filter(game=game)
            .values_list("golfer_id", flat=True)
        )

        # Who picked which golfer
        for pick in DraftPick.objects.filter(game=game).select_related(
            "golfer", "game_entry__user"
        ):
            picked_by[pick.golfer_id] = pick.game_entry.user.username

        # All available entries ordered by world ranking
        available_golfers = list(
            EventEntry.objects.filter(event=game.event)
            .exclude(golfer_id__in=already_picked_ids)
            .select_related("golfer")
            .order_by("golfer__world_ranking")
        )

        # Current user's active slot
        if user_entry:
            user_slot = DraftSlot.objects.filter(
                game=game,
                game_entry=user_entry,
                completed=False,
                opens_at__isnull=False,
                opens_at__lte=now(),
                closes_at__gt=now(),
            ).first()

            # User's preference order (for display during draft)
            my_preferences = list(
                UserOrder.objects.filter(
                    user=request.user, event=game.event
                ).order_by("selection_rank").select_related("golfer")
            )

    # Build player_teams for active/finished display
    picks_by_entry = {}
    for pick in all_picks:
        picks_by_entry.setdefault(pick.game_entry_id, []).append(pick)

    player_teams = [
        {"entry": entry, "picks": picks_by_entry.get(entry.id, [])}
        for entry in entries
    ]

    # Next slot after active (so player knows when their next turn is)
    next_user_slot = None
    if user_entry and not user_slot:
        # Next timed slot for this user (pending/untimed slots don't have a time yet)
        next_user_slot = DraftSlot.objects.filter(
            game=game,
            game_entry=user_entry,
            completed=False,
            opens_at__isnull=False,
            opens_at__gt=now(),
        ).order_by("opens_at").first()

        # If no timed slot, find their next pending slot (pick number)
        if not next_user_slot:
            next_user_slot = DraftSlot.objects.filter(
                game=game,
                game_entry=user_entry,
                completed=False,
                opens_at__isnull=True,
            ).order_by("pick_number").first()

    from golf.services.draft import draft_is_complete
    context = {
        "game": game,
        "draft_complete": draft_is_complete(game),
        "user_entry": user_entry,
        "entries": entries,
        "non_entrants": non_entrants,
        "player_teams": player_teams,
        "picks_by_player": picks_by_player,
        "draft_slots": draft_slots,
        "active_slot": active_slot,
        "user_slot": user_slot,
        "next_user_slot": next_user_slot,
        "available_golfers": available_golfers,
        "my_preferences": my_preferences,
        "already_picked_ids": already_picked_ids,
        "picked_by": picked_by,
        "main_pot": game.total_main_pot,
        "secondary_pot": secondary_pot,
        "rollover_amount": game.rollover_amount,
        "now": now(),
    }
    return render(request, "golf/game_detail.html", context)


# ---------------------------------------------
# Preference ordering (pre-draft)
# ---------------------------------------------

@login_required
def pick_order_view(request, event_id):
    event = get_object_or_404(GolfEvent, tourn_id=event_id)
    entries = EventEntry.objects.filter(event=event).select_related("golfer").order_by(
        "golfer__world_ranking"
    )
    existing_order = UserOrder.objects.filter(
        user=request.user, event=event
    ).select_related("golfer").order_by("selection_rank")

    if request.method == "POST":
        UserOrder.objects.filter(user=request.user, event=event).delete()
        for i, golfer_id in enumerate(request.POST.getlist("golfer_order"), start=1):
            golfer = get_object_or_404(
                EventEntry, event=event, golfer_id=golfer_id
            ).golfer
            UserOrder.objects.create(
                user=request.user,
                event=event,
                golfer=golfer,
                selection_rank=i,
            )
        count = request.POST.getlist("golfer_order")
        messages.success(
            request,
            f"Preference order saved for {len(count)} golfer(s)."
        )
        return redirect("pick_order", event_id=event.tourn_id)

    # Find golfers already drafted in any game for this event in the user's groups
    user_groups = request.user.joined_groups.all()
    games_for_event = GolfGame.objects.filter(
        event=event, group__in=user_groups
    )
    already_picked_ids = set(
        DraftPick.objects.filter(game__in=games_for_event)
        .values_list("golfer_id", flat=True)
    )

    # Attach picked_by info to each entry for display
    picked_by = {}
    for pick in DraftPick.objects.filter(
        game__in=games_for_event
    ).select_related("golfer", "game_entry__user"):
        picked_by[pick.golfer_id] = pick.game_entry.user.username

    # Build ordered list: user preference order first, then remaining by world ranking
    ordered_ids = list(
        UserOrder.objects.filter(user=request.user, event=event)
        .order_by("selection_rank")
        .values_list("golfer_id", flat=True)
    )
    ordered_set = set(ordered_ids)
    remaining = [
        e for e in entries if e.golfer_id not in ordered_set
    ]

    # Build display list: saved order first, then remaining by world ranking
    saved_ids = list(existing_order.values_list("golfer_id", flat=True))
    saved_id_set = set(saved_ids)

    # Ordered golfer entries: saved order first, then unsaved by world ranking
    saved_entries = sorted(
        [e for e in entries if e.golfer_id in saved_id_set],
        key=lambda e: saved_ids.index(e.golfer_id)
    )
    unsaved_entries = [e for e in entries if e.golfer_id not in saved_id_set]
    display_entries = saved_entries + unsaved_entries

    return render(request, "golf/pick_order.html", {
        "event": event,
        "entries": display_entries,
        "existing_order": existing_order,
        "already_picked_ids": already_picked_ids,
        "picked_by": picked_by,
        "games_for_event": games_for_event,
    })


# ---------------------------------------------
# Live draft pick view
# ---------------------------------------------

@login_required
def make_draft_pick(request, game_id):
    """Handle POST pick submission only. GET redirects to game detail."""
    game = get_object_or_404(GolfGame, id=game_id)
    user_entry = get_object_or_404(GolfGameEntry, game=game, user=request.user)

    if request.method == "POST":
        slot = DraftSlot.objects.filter(
            game=game,
            game_entry=user_entry,
            completed=False,
            opens_at__lte=now(),
            closes_at__gt=now(),
        ).first()

        if not slot:
            messages.error(request, "Your pick slot has expired.")
            return redirect("golf_game_detail", game_id=game.id)

        golfer_id = request.POST.get("golfer_id")
        if not golfer_id:
            messages.error(request, "Please select a golfer.")
            return redirect("golf_game_detail", game_id=game.id)

        from golf.models import Golfer
        golfer = get_object_or_404(Golfer, id=golfer_id)
        pick, error = submit_pick(game, user_entry, golfer, slot)
        if error:
            messages.error(request, error)
        else:
            messages.success(request, f"You picked {golfer.full_name}!")

    return redirect("golf_game_detail", game_id=game.id)


# ---------------------------------------------
# Event entries view (read-only)
# ---------------------------------------------

def event_entries_view(request, event_id):
    event = get_object_or_404(GolfEvent, tourn_id=event_id)
    entries = EventEntry.objects.filter(event=event).select_related("golfer").order_by(
        "golfer__world_ranking"
    )
    return render(request, "golf/event_entries.html", {
        "event": event,
        "entries": entries,
    })


# ---------------------------------------------
# Leaderboard view
# ---------------------------------------------

@login_required
# This replaces leaderboard_view in golf/views.py


@login_required
def leaderboard_view(request, game_id):
    """
    The main game page once drafting is complete.
    Shows:
    - Player standings (ranked by best scoring_picks scores)
    - Each player's full team with live scores
    - Missed cuts and fines
    - Full tournament leaderboard
    """
    game = get_object_or_404(GolfGame, id=game_id)
    user_entry = GolfGameEntry.objects.filter(game=game, user=request.user).first()
    event = game.event
    # Tournament started if status set, OR if scores exist for this event
    tournament_started = (
        event.status not in ("", None, "Scheduled", "scheduled")
        or GolferScore.objects.filter(event=event).exists()
    )

    # ---- All picks for the game ----
    all_picks = (
        DraftPick.objects
        .filter(game=game)
        .select_related("golfer", "game_entry__user")
        .order_by("game_entry__draft_position", "round_number")
    )

    # ---- All round scores per golfer from DB ----
    # latest_scores: golfer_id -> most recent GolferScore (for position/thru/total)
    # all_round_scores: golfer_id -> {round_num: GolferScore}
    latest_scores = {}
    all_round_scores = {}
    if tournament_started:
        scores_qs = (
            GolferScore.objects
            .filter(event=event)
            .order_by("golfer_id", "-round")
        )
        for s in scores_qs:
            if s.golfer_id not in latest_scores:
                latest_scores[s.golfer_id] = s
            all_round_scores.setdefault(s.golfer_id, {})[s.round] = s

    # ---- Build player standings ----
    entries = game.game_entries.select_related("user").order_by("draft_position")
    player_rows = []

    for entry in entries:
        picks = [p for p in all_picks if p.game_entry_id == entry.id]

        team = []
        missed_cut_count = 0
        for pick in picks:
            score_obj = latest_scores.get(pick.golfer_id)
            made_cut = pick.made_cut
            missed = not made_cut if made_cut is not None else False
            if missed:
                missed_cut_count += 1

            rounds = all_round_scores.get(pick.golfer_id, {})
            team.append({
                "pick": pick,
                "golfer": pick.golfer,
                "round_number": pick.round_number,
                "score_obj": score_obj,
                "rounds": rounds,
                "missed_cut": missed,
            })

        # Best scoring_picks scores count toward standing
        scoring_count = game.scoring_picks

        def get_total(t):
            """Get total score vs par. Check all round rows for a non-None total."""
            # First check latest round row
            s = t["score_obj"]
            if s and s.total_score is not None:
                return s.total_score
            # Check all round rows for any non-None total_score
            rounds = t["rounds"]
            if rounds:
                for r in sorted(rounds.values(), key=lambda x: -x.round):
                    if r.total_score is not None:
                        return r.total_score
                # Fall back: sum round_score values
                scores = [r.round_score for r in rounds.values() if r.round_score is not None]
                return sum(scores) if scores else None
            return None

        for t in team:
            t["total_vs_par"] = get_total(t)
            t["counting"] = False  # will be set below

        # Sort team: best scores first, missed cuts last
        def team_sort_key(t):
            if t["missed_cut"]:
                return (2, 9999)
            if t["total_vs_par"] is None:
                return (1, 9999)
            return (0, t["total_vs_par"])

        team.sort(key=team_sort_key)

        # Mark the best scoring_count as counting (missed cuts NEVER count)
        counting_so_far = 0
        for t in team:
            if not t["missed_cut"] and t["total_vs_par"] is not None and counting_so_far < scoring_count:
                t["counting"] = True
                counting_so_far += 1

        best_scores = [t for t in team if t["counting"]]
        fines = missed_cut_count * game.missed_cut_fine

        # Player is eliminated from main pot if they have fewer than
        # scoring_count valid (non-cut) picks with scores
        valid_picks = [t for t in team if not t["missed_cut"] and t["total_vs_par"] is not None]
        eliminated_from_main = len(valid_picks) < scoring_count

        if eliminated_from_main:
            total = None  # void score
        elif best_scores:
            total = sum(t["total_vs_par"] for t in best_scores)
        else:
            total = None

        player_rows.append({
            "entry": entry,
            "team": team,
            "total_score": total,
            "fines": fines,
            "missed_cuts": missed_cut_count,
            "eliminated_from_main": eliminated_from_main,
            "is_user": entry.user == request.user,
        })

    # Sort by total score ascending (lower = better in stroke play)
    if tournament_started:
        def standing_sort(r):
            if r["eliminated_from_main"]:
                return (1, 9999)
            if r["total_score"] is None:
                return (0, 9999)
            return (0, r["total_score"])
        player_rows.sort(key=standing_sort)
    else:
        player_rows.sort(key=lambda r: r["entry"].draft_position or 0)

    # ---- Full tournament leaderboard from DB ----
    event_leaderboard = []
    if tournament_started:
        seen2 = set()
        scores_for_lb = (
            GolferScore.objects
            .filter(event=event)
            .select_related("golfer")
            .order_by("golfer_id", "-round")
        )
        seen2 = set()
        for s in scores_for_lb:
            if s.golfer_id in seen2:
                continue
            seen2.add(s.golfer_id)
            golfer_rounds = all_round_scores.get(s.golfer_id, {})
            event_leaderboard.append({
                "golfer": s.golfer,
                "position": s.position,
                "current_round": s.round,
                "thru": s.thru,
                "total_score": s.total_score,
                "current_round_score": golfer_rounds.get(s.round),
                "rounds": golfer_rounds,
            })

        def sort_key(row):
            pos = str(row["position"] or "").lstrip("T=")
            try:
                return int(pos)
            except ValueError:
                return 9999

        event_leaderboard.sort(key=sort_key)

    # Picked golfer IDs for highlighting
    user_pick_golfer_ids = set()
    if user_entry:
        user_pick_golfer_ids = {
            p.golfer_id for p in all_picks
            if p.game_entry_id == user_entry.id
        }
    all_picked_ids = {p.golfer_id for p in all_picks}

    return render(request, "golf/leaderboard.html", {
        "game": game,
        "event": event,
        "user_entry": user_entry,
        "player_rows": player_rows,
        "event_leaderboard": event_leaderboard,
        "tournament_started": tournament_started,
        "user_pick_golfer_ids": user_pick_golfer_ids,
        "all_picked_ids": all_picked_ids,
        "main_pot": game.total_main_pot,
        "secondary_pot": game.total_secondary_pot if hasattr(game, 'total_secondary_pot') else 0,
        "scoring_picks": game.scoring_picks,
    })


@login_required
def golf_history(request):
    """
    Shows all finished golf games for the user's groups.
    Summarises players, winners, user's finish position and P&L.
    """
    user_groups = request.user.joined_groups.all()

    finished_games = (
        GolfGame.objects.filter(
            group__in=user_groups,
            status=GolfGame.Status.FINISHED,
        )
        .select_related("event", "event__tour", "group")
        .order_by("-event__start_date")
    )

    history = []
    for game in finished_games:
        entries = game.game_entries.select_related("user").order_by("final_rank")
        player_count = entries.count()

        # User's own result
        user_result = entries.filter(user=request.user).first()

        # Main pot winner(s) - rank 1
        main_winners = [e for e in entries if e.final_rank == 1]

        # Secondary pot winner - whoever picked the tournament winner
        secondary_winner_pick = (
            DraftPick.objects.filter(game=game, is_tournament_winner=True)
            .select_related("game_entry__user")
            .first()
        )
        secondary_winner = (
            secondary_winner_pick.game_entry.user if secondary_winner_pick else None
        )

        # User P&L for this game
        pnl = None
        if user_result:
            result = GolfGameResult.objects.filter(
                game=game, user=request.user
            ).first()
            if result:
                income = result.main_pot_won + result.secondary_pot_won
                cost = game.entry_fee + result.fines_paid
                pnl = income - cost

        history.append({
            "game": game,
            "player_count": player_count,
            "main_winners": main_winners,
            "secondary_winner": secondary_winner,
            "user_result": user_result,
            "pnl": pnl,
        })

    # Overall P&L across all finished games
    total_pnl = sum(
        h["pnl"] for h in history if h["pnl"] is not None
    )

    return render(request, "golf/history.html", {
        "history": history,
        "total_pnl": total_pnl,
        "user_groups": user_groups,
    })

@login_required
def close_entries_and_start_draft(request, game_id):
    """
    Allows the game creator to manually close entries and start the draft.
    Only available before the tournament starts. If tournament has started
    without a draft, the game is void.
    """
    from golf.services.draft import generate_draft_slots
    from django.utils.timezone import make_aware
    from datetime import datetime as dt

    game = get_object_or_404(GolfGame, id=game_id)

    if request.user != game.created_by:
        messages.error(request, "Only the game creator can start the draft.")
        return redirect("golf_game_detail", game_id=game.id)

    if game.status != GolfGame.Status.OPEN:
        messages.error(request, "Draft can only be started from an open game.")
        return redirect("golf_game_detail", game_id=game.id)

    current = now()
    day_of_tournament = make_aware(
        dt.combine(game.event.start_date.date(), dt.min.time())
    )

    # If tournament has already started, game is void
    if current >= day_of_tournament:
        game.status = GolfGame.Status.FINISHED
        game.save(update_fields=["status"])
        messages.error(
            request,
            "The tournament has already started. This game is void as no draft took place."
        )
        return redirect("golf_game_detail", game_id=game.id)

    if game.game_entries.count() < 2:
        messages.error(request, "At least 2 players must join before the draft can start.")
        return redirect("golf_game_detail", game_id=game.id)

    # Clear any previously generated slots (e.g. from a failed earlier attempt)
    DraftSlot.objects.filter(game=game).delete()

    # Start the draft - generate_draft_slots uses max(scheduled, now())
    game.status = GolfGame.Status.DRAFTING
    game.save(update_fields=["status"])
    generate_draft_slots(game)
    messages.success(request, "Entries closed. The draft has started!")
    return redirect("golf_game_detail", game_id=game.id)
