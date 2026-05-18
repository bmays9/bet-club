# golf/services/draft.py

import random
from datetime import timedelta
from django.utils import timezone
from django.db import transaction

from golf.models import (
    GolfGame, GolfGameEntry, DraftSlot, DraftPick,
    UserOrder, GolfGameResult, EventEntry,
)

SLOT_DURATION_MINUTES = 60


# -------------------------------------------------------
# Draft order
# -------------------------------------------------------

def get_draft_order(game):
    """
    Returns ordered list of GolfGameEntry for round 1.
    Worst previous finisher picks first.
    New players inserted randomly but not first or last.
    """
    entries = list(game.game_entries.all())
    if not entries:
        return []

    last_results = {}
    for entry in entries:
        result = (
            GolfGameResult.objects
            .filter(user=entry.user, game__group=game.group)
            .exclude(game=game)
            .order_by("-game__created_at")
            .first()
        )
        if result:
            last_results[entry.user_id] = result.final_rank

    known = [e for e in entries if e.user_id in last_results]
    new_players = [e for e in entries if e.user_id not in last_results]

    known.sort(key=lambda e: last_results[e.user_id], reverse=True)

    for player in new_players:
        if len(known) <= 1:
            known.append(player)
        else:
            pos = random.randint(1, len(known) - 1)
            known.insert(pos, player)

    return known


# -------------------------------------------------------
# Slot order (the full sequence of picks for the draft)
# -------------------------------------------------------

def build_pick_sequence(game, ordered_entries):
    """
    Returns an ordered list of GolfGameEntry representing
    the full draft sequence across all rounds.
    Straight: [1,2,3,4,5, 1,2,3,4,5, ...]
    Snake:    [1,2,3,4,5, 5,4,3,2,1, ...]
    """
    sequence = []
    for round_num in range(1, game.picks_per_player + 1):
        if game.pick_method == GolfGame.PickMethod.SNAKE and round_num % 2 == 0:
            round_order = list(reversed(ordered_entries))
        else:
            round_order = list(ordered_entries)
        for entry in round_order:
            sequence.append((round_num, entry))
    return sequence


# -------------------------------------------------------
# Slot generation - dynamic, not pre-timed
# -------------------------------------------------------

def generate_draft_slots(game, start_from=None):
    """
    Create DraftSlot rows for the full draft.
    Only the FIRST slot gets real opens_at/closes_at times.
    All subsequent slots have opens_at=None -- they get timed
    dynamically when the previous slot completes via advance_draft().

    start_from: datetime to open the first slot. Defaults to now().
                Pass game.draft_start_time for automatic scheduled starts.
    """
    ordered_entries = get_draft_order(game)
    if not ordered_entries:
        return

    # Save draft positions
    for i, entry in enumerate(ordered_entries, start=1):
        entry.draft_position = i
        entry.save(update_fields=["draft_position"])

    sequence = build_pick_sequence(game, ordered_entries)

    # Default to now so manual/reset starts open immediately
    first_start = start_from or timezone.now()

    print(f"[draft] generating {len(sequence)} slots, first slot opens at {first_start}")

    slots = []
    for pick_number, (round_num, entry) in enumerate(sequence, start=1):
        if pick_number == 1:
            opens_at = first_start
            closes_at = first_start + timedelta(minutes=SLOT_DURATION_MINUTES)
        else:
            # Will be set dynamically when the previous slot completes
            opens_at = None
            closes_at = None

        slots.append(DraftSlot(
            game=game,
            game_entry=entry,
            round_number=round_num,
            pick_number=pick_number,
            opens_at=opens_at,
            closes_at=closes_at,
        ))

    created = DraftSlot.objects.bulk_create(slots)
    print(f"[draft] created {len(created)} slots")

    # Verify slot 1 has times
    slot1 = DraftSlot.objects.filter(game=game, pick_number=1).first()
    if slot1:
        print(f"[draft] slot 1: opens={slot1.opens_at} closes={slot1.closes_at} active={slot1.is_active}")
    else:
        print("[draft] WARNING: slot 1 not found after bulk_create!")


def advance_draft(game, completed_slot, catchup=False):
    """
    Called after a slot completes (pick made or auto-assigned).
    Sets opens_at/closes_at on the next slot.

    catchup=True: chains from completed_slot.closes_at (historical mode).
    catchup=False: opens from now() so fast pickers move draft along immediately.
    """
    next_slot = (
        DraftSlot.objects
        .filter(game=game, completed=False, opens_at__isnull=True)
        .order_by("pick_number")
        .first()
    )

    if next_slot:
        if catchup and completed_slot.closes_at:
            opens_at = completed_slot.closes_at
        else:
            opens_at = timezone.now()

        next_slot.opens_at = opens_at
        next_slot.closes_at = opens_at + timedelta(minutes=SLOT_DURATION_MINUTES)
        next_slot.save(update_fields=["opens_at", "closes_at"])

    return next_slot


# -------------------------------------------------------
# Available golfers
# -------------------------------------------------------

def get_available_golfers(game):
    picked_ids = DraftPick.objects.filter(game=game).values_list("golfer_id", flat=True)
    return (
        EventEntry.objects
        .filter(event=game.event)
        .exclude(golfer_id__in=picked_ids)
        .select_related("golfer")
        .order_by("golfer__world_ranking")
    )


def get_best_available_for_player(game, game_entry):
    available_golfer_ids = set(
        get_available_golfers(game).values_list("golfer_id", flat=True)
    )

    preferences = (
        UserOrder.objects
        .filter(user=game_entry.user, event=game.event)
        .order_by("selection_rank")
        .select_related("golfer")
    )
    for pref in preferences:
        if pref.golfer_id in available_golfer_ids:
            return pref.golfer

    entry = get_available_golfers(game).first()
    return entry.golfer if entry else None


# -------------------------------------------------------
# Submitting a pick
# -------------------------------------------------------

@transaction.atomic
def submit_pick(game, game_entry, golfer, slot, auto=False, catchup=False):
    """
    Create a DraftPick, mark slot complete, and advance the draft.
    catchup=True chains the next slot from slot.closes_at (historical mode).
    Returns (pick, error_message).
    """
    if DraftPick.objects.filter(game=game, golfer=golfer).exists():
        return None, f"{golfer.full_name} has already been picked."

    if not auto and not slot.is_active:
        return None, "This pick slot is no longer active."

    pick = DraftPick.objects.create(
        game=game,
        game_entry=game_entry,
        slot=slot,
        golfer=golfer,
        round_number=slot.round_number,
        auto_assigned=auto,
    )

    slot.completed = True
    slot.auto_assigned = auto
    slot.save(update_fields=["completed", "auto_assigned"])

    # Open next slot -- catchup chains from closes_at, normal from now()
    advance_draft(game, slot, catchup=catchup)

    return pick, None


# -------------------------------------------------------
# Auto-pick expired slots
# -------------------------------------------------------

def process_expired_slots(game):
    """
    Find the current active slot if it has expired and auto-assign.
    Only processes one slot at a time -- advance_draft() opens the next.
    Called periodically by management command.
    """
    # Only look at slots that have a real time set and have expired
    expired = (
        DraftSlot.objects
        .filter(
            game=game,
            completed=False,
            opens_at__isnull=False,
            closes_at__lte=timezone.now(),
        )
        .order_by("pick_number")
    )

    for slot in expired:
        golfer = get_best_available_for_player(game, slot.game_entry)
        if golfer:
            submit_pick(game, slot.game_entry, golfer, slot, auto=True)
        else:
            slot.completed = True
            slot.auto_assigned = True
            slot.save(update_fields=["completed", "auto_assigned"])
            advance_draft(game, slot)


# -------------------------------------------------------
# Draft lifecycle helpers
# -------------------------------------------------------

def maybe_start_draft(game):
    """Start draft if scheduled time has passed. Returns True if started."""
    if game.status != GolfGame.Status.OPEN:
        return False
    if timezone.now() < game.draft_start_time:
        return False

    game.status = GolfGame.Status.DRAFTING
    game.save(update_fields=["status"])
    # Pass scheduled time so auto-starts open at the right time
    generate_draft_slots(game, start_from=game.draft_start_time)
    return True


def draft_is_complete(game):
    """Returns True if all slots are completed."""
    return not DraftSlot.objects.filter(game=game, completed=False).exists()
