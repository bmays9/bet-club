# season/services/draft.py
from django.db import transaction
from django.utils import timezone
from season.models import (
    SeasonDraft, DraftOrder, DraftSlotSeason,
    PlayerPick, PlayerGame, GameLeague, PickType, Team,
)


# -------------------------------------------------------
# Generate draft slots
# -------------------------------------------------------

def generate_draft_slots(draft):
    """
    Generate all DraftSlotSeason rows for the draft.

    Phase 1 (WIN_LOSE): for each league, each player picks:
      - 1 team to WIN
      - 1 team to LOSE
    All WIN picks happen before LOSE picks.
    Pick order follows draft method (straight or snake).

    Phase 2 (HANDICAP): after all WIN/LOSE picks done, each player
    picks 1 HANDICAP team per league. Win/handicap teams are exclusive
    so available pool is reduced.

    Slot sequence:
      For each league:
        Round 1: all players pick WIN (in draft order)
        Round 2: all players pick LOSE (in draft order or reversed if snake)
      Then for each league:
        Round 3: all players pick HANDICAP
    """
    DraftSlotSeason.objects.filter(draft=draft).delete()

    game = draft.game
    leagues = list(
        GameLeague.objects.filter(game=game, active=True)
        .select_related("league")
        .order_by("league__name")
    )
    ordered_players = list(
        DraftOrder.objects.filter(draft=draft)
        .order_by("position")
        .select_related("player_game")
    )

    if not ordered_players or not leagues:
        return

    slots = []
    pick_number = 1

    def get_order(round_num):
        """Straight or snake order for a round."""
        if draft.method == SeasonDraft.Method.SNAKE and round_num % 2 == 0:
            return list(reversed(ordered_players))
        return list(ordered_players)

    # Phase 1: WIN picks (one per player per league)
    round_num = 1
    for league_gl in leagues:
        for do in get_order(round_num):
            slots.append(DraftSlotSeason(
                draft=draft,
                player_game=do.player_game,
                game_league=league_gl,
                pick_type=PickType.WIN,
                pick_number=pick_number,
                round_number=round_num,
            ))
            pick_number += 1
        round_num += 1

    # Phase 1: LOSE picks (one per player per league)
    for league_gl in leagues:
        for do in get_order(round_num):
            slots.append(DraftSlotSeason(
                draft=draft,
                player_game=do.player_game,
                game_league=league_gl,
                pick_type=PickType.LOSE,
                pick_number=pick_number,
                round_number=round_num,
            ))
            pick_number += 1
        round_num += 1

    # Phase 2: HANDICAP picks (one per player per league)
    # These happen after all win/lose picks
    for league_gl in leagues:
        for do in get_order(round_num):
            slots.append(DraftSlotSeason(
                draft=draft,
                player_game=do.player_game,
                game_league=league_gl,
                pick_type=PickType.HANDICAP,
                pick_number=pick_number,
                round_number=round_num,
            ))
            pick_number += 1
        round_num += 1

    DraftSlotSeason.objects.bulk_create(slots)
    return len(slots)


# -------------------------------------------------------
# Available teams
# -------------------------------------------------------

def get_available_teams(draft, game_league, pick_type, player_game):
    """
    Return teams available for a specific pick slot.

    WIN picks:
      - Must be in this league
      - Not already picked as WIN by ANY player in this game+league

    LOSE picks:
      - Must be in this league
      - Not already picked as LOSE by ANY player in this game+league
      - CAN be picked as WIN by another player (or even this player)
      - But NOT if this player already picked it as WIN
        (player can't have same team twice)

    HANDICAP picks:
      - Must be in this league
      - Not already picked as WIN or HANDICAP by ANY player
        (win+handicap share the same exclusivity pool)
      - Not already picked by THIS player in any type
    """
    game = draft.game
    all_league_teams = Team.objects.filter(league=game_league.league)

    if pick_type == PickType.WIN:
        # Exclude teams already won by any player in this game+league
        used = PlayerPick.objects.filter(
            game_league=game_league,
            pick_type=PickType.WIN,
        ).values_list("team_id", flat=True)
        return all_league_teams.exclude(id__in=used)

    elif pick_type == PickType.LOSE:
        # Exclude teams already picked as LOSE by any player
        used_as_lose = PlayerPick.objects.filter(
            game_league=game_league,
            pick_type=PickType.LOSE,
        ).values_list("team_id", flat=True)
        # Exclude teams this player already picked in any type (no same team twice)
        my_picks = PlayerPick.objects.filter(
            player_game=player_game,
            game_league=game_league,
        ).values_list("team_id", flat=True)
        return all_league_teams.exclude(id__in=used_as_lose).exclude(id__in=my_picks)

    elif pick_type == PickType.HANDICAP:
        # Exclude teams already picked as WIN or HANDICAP by anyone
        used_win_hcp = PlayerPick.objects.filter(
            game_league=game_league,
            pick_type__in=[PickType.WIN, PickType.HANDICAP],
        ).values_list("team_id", flat=True)
        # Exclude teams this player picked in any type
        my_picks = PlayerPick.objects.filter(
            player_game=player_game,
            game_league=game_league,
        ).values_list("team_id", flat=True)
        return all_league_teams.exclude(id__in=used_win_hcp).exclude(id__in=my_picks)

    return all_league_teams.none()


# -------------------------------------------------------
# Submit a pick
# -------------------------------------------------------

@transaction.atomic
def submit_draft_pick(draft, slot, team, player_game):
    """
    Submit a pick for a slot. Validates exclusivity rules.
    Returns (PlayerPick, error_message).
    """
    if slot.completed:
        return None, "This slot has already been filled."

    if slot.player_game != player_game:
        return None, "This slot does not belong to you."

    available = get_available_teams(draft, slot.game_league, slot.pick_type, player_game)
    if not available.filter(id=team.id).exists():
        return None, f"{team.name} is not available for this pick."

    try:
        pick = PlayerPick.objects.create(
            player_game=player_game,
            game_league=slot.game_league,
            pick_type=slot.pick_type,
            team=team,
            pick_number=slot.pick_number,
        )
    except Exception as e:
        return None, str(e)

    slot.completed = True
    slot.save(update_fields=["completed"])

    # Check if phase 1 is now complete (all WIN+LOSE slots done)
    if draft.phase == SeasonDraft.Phase.WIN_LOSE:
        win_lose_pending = draft.slots.filter(
            pick_type__in=[PickType.WIN, PickType.LOSE],
            completed=False,
        ).exists()
        if not win_lose_pending:
            draft.phase = SeasonDraft.Phase.HANDICAP
            draft.save(update_fields=["phase"])

    # Check if all slots done
    if not draft.slots.filter(completed=False).exists():
        draft.phase = SeasonDraft.Phase.COMPLETE
        draft.completed_at = timezone.now()
        draft.save(update_fields=["phase", "completed_at"])
        # Activate the game
        game = draft.game
        from season.models import Game
        game.status = Game.Status.ACTIVE
        game.save(update_fields=["status"])

    return pick, None


# -------------------------------------------------------
# Get current slot for a player
# -------------------------------------------------------

def get_current_slot(draft, player_game):
    """
    Returns the next incomplete slot for this player, respecting phase.
    During WIN_LOSE phase, only returns WIN or LOSE slots.
    During HANDICAP phase, only returns HANDICAP slots.
    """
    if draft.phase == SeasonDraft.Phase.WIN_LOSE:
        types = [PickType.WIN, PickType.LOSE]
    elif draft.phase == SeasonDraft.Phase.HANDICAP:
        types = [PickType.HANDICAP]
    else:
        return None

    return (
        DraftSlotSeason.objects
        .filter(
            draft=draft,
            player_game=player_game,
            pick_type__in=types,
            completed=False,
        )
        .order_by("pick_number")
        .first()
    )


# -------------------------------------------------------
# Initialise draft
# -------------------------------------------------------

def create_draft(game, method=SeasonDraft.Method.STRAIGHT):
    """
    Create a SeasonDraft for a game and randomise/set the draft order.
    """
    import random

    draft, created = SeasonDraft.objects.get_or_create(
        game=game,
        defaults={
            "method": method,
            "started_at": timezone.now(),
        }
    )
    if not created:
        return draft, False

    # Set draft order: by default randomise
    players = list(PlayerGame.objects.filter(game=game))
    random.shuffle(players)

    for i, pg in enumerate(players, start=1):
        DraftOrder.objects.get_or_create(
            draft=draft, player_game=pg,
            defaults={"position": i}
        )

    generate_draft_slots(draft)
    return draft, True
