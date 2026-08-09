# season/services/draft.py
from django.db import transaction
from django.utils import timezone
from season.models import (
    SeasonDraft, DraftOrder, DraftSlotSeason,
    PlayerPick, PlayerGame, GameLeague, PickType, Team,
)


def generate_draft_slots(draft):
    """
    Generate DraftSlotSeason rows -- one per player per pick, in draft order.

    Phase WIN_LOSE: each player gets (num_leagues * 2) slots -- one per
    win pick and one per lose pick across all leagues. They choose which
    league when they pick.

    Phase HANDICAP: each player gets num_leagues slots.

    Straight draft: same order every round.
    Snake draft: order reverses every other round.
    """
    DraftSlotSeason.objects.filter(draft=draft).delete()

    game = draft.game
    num_leagues = GameLeague.objects.filter(game=game, active=True).count()

    ordered_players = list(
        DraftOrder.objects.filter(draft=draft)
        .order_by("position")
        .select_related("player_game")
    )

    if not ordered_players or not num_leagues:
        return 0

    slots = []
    pick_number = 1

    def get_order(round_num):
        if draft.method == SeasonDraft.Method.SNAKE and round_num % 2 == 0:
            return list(reversed(ordered_players))
        return list(ordered_players)

    # Phase 1 WIN_LOSE: num_leagues * 2 rounds (one win + one lose per league)
    num_win_lose_rounds = num_leagues * 2
    for round_num in range(1, num_win_lose_rounds + 1):
        for do in get_order(round_num):
            slots.append(DraftSlotSeason(
                draft=draft,
                player_game=do.player_game,
                pick_number=pick_number,
                phase="win_lose",
            ))
            pick_number += 1

    # Phase 2 HANDICAP: num_leagues rounds
    for round_num in range(1, num_leagues + 1):
        for do in get_order(round_num):
            slots.append(DraftSlotSeason(
                draft=draft,
                player_game=do.player_game,
                pick_number=pick_number,
                phase="handicap",
            ))
            pick_number += 1

    DraftSlotSeason.objects.bulk_create(slots)
    return len(slots)


def get_available_teams(draft, game_league, pick_type, player_game):
    """
    Return teams available for a pick in a specific league.

    WIN picks: not already picked as WIN by anyone in this league
    LOSE picks: not already picked as LOSE by anyone; not picked by this player at all
    HANDICAP picks: not already picked as WIN or HANDICAP by anyone;
                    not picked by this player at all
    """
    all_league_teams = Team.objects.filter(league=game_league.league)

    if pick_type == PickType.WIN:
        used = PlayerPick.objects.filter(
            game_league=game_league,
            pick_type=PickType.WIN,
        ).values_list("team_id", flat=True)
        return all_league_teams.exclude(id__in=used)

    elif pick_type == PickType.LOSE:
        used_as_lose = PlayerPick.objects.filter(
            game_league=game_league,
            pick_type=PickType.LOSE,
        ).values_list("team_id", flat=True)
        my_picks = PlayerPick.objects.filter(
            player_game=player_game,
            game_league=game_league,
        ).values_list("team_id", flat=True)
        return all_league_teams.exclude(id__in=used_as_lose).exclude(id__in=my_picks)

    elif pick_type == PickType.HANDICAP:
        used_win_hcp = PlayerPick.objects.filter(
            game_league=game_league,
            pick_type__in=[PickType.WIN, PickType.HANDICAP],
        ).values_list("team_id", flat=True)
        my_picks = PlayerPick.objects.filter(
            player_game=player_game,
            game_league=game_league,
        ).values_list("team_id", flat=True)
        return all_league_teams.exclude(id__in=used_win_hcp).exclude(id__in=my_picks)

    return all_league_teams.none()


@transaction.atomic
def submit_draft_pick(draft, slot, team, player_game, pick_type, game_league):
    """
    Submit a pick for a slot.
    pick_type and game_league are supplied by the player's choice.
    Returns (PlayerPick, error_message).
    """
    if slot.completed:
        return None, "This slot has already been filled."

    if slot.player_game != player_game:
        return None, "This slot does not belong to you."

    # Validate availability
    available = get_available_teams(draft, game_league, pick_type, player_game)
    if not available.filter(id=team.id).exists():
        return None, f"{team.name} is not available for this pick."

    # Phase check
    if slot.phase == "win_lose" and pick_type == PickType.HANDICAP:
        return None, "Handicap picks are not allowed in this phase."
    if slot.phase == "handicap" and pick_type != PickType.HANDICAP:
        return None, "Only handicap picks are allowed in this phase."

    try:
        pick = PlayerPick.objects.create(
            player_game=player_game,
            game_league=game_league,
            pick_type=pick_type,
            team=team,
            pick_number=slot.pick_number,
        )
    except Exception as e:
        return None, str(e)

    # Record what was chosen on the slot
    slot.completed = True
    slot.game_league = game_league
    slot.pick_type = pick_type
    slot.save(update_fields=["completed", "game_league", "pick_type"])

    # Check if WIN_LOSE phase is complete
    if draft.phase == SeasonDraft.Phase.WIN_LOSE:
        pending = draft.slots.filter(phase="win_lose", completed=False).exists()
        if not pending:
            draft.phase = SeasonDraft.Phase.HANDICAP
            draft.save(update_fields=["phase"])

    # Check if all slots done
    if not draft.slots.filter(completed=False).exists():
        draft.phase = SeasonDraft.Phase.COMPLETE
        draft.completed_at = timezone.now()
        draft.save(update_fields=["phase", "completed_at"])
        from season.models import Game
        game = draft.game
        game.status = Game.Status.ACTIVE
        game.save(update_fields=["status"])

    return pick, None


def get_current_slot(draft, player_game):
    """
    Returns this player's current slot if it's their turn.
    Turn = next incomplete slot globally belongs to this player.
    """
    next_slot = (
        DraftSlotSeason.objects
        .filter(draft=draft, completed=False)
        .order_by("pick_number")
        .first()
    )
    if next_slot and player_game and next_slot.player_game_id == player_game.id:
        return next_slot
    return None


def create_draft(game, method=SeasonDraft.Method.STRAIGHT):
    import random
    draft, created = SeasonDraft.objects.get_or_create(
        game=game,
        defaults={"method": method, "started_at": timezone.now()},
    )
    if not created:
        return draft, False
    players = list(PlayerGame.objects.filter(game=game))
    random.shuffle(players)
    for i, pg in enumerate(players, start=1):
        DraftOrder.objects.get_or_create(
            draft=draft, player_game=pg,
            defaults={"position": i}
        )
    generate_draft_slots(draft)
    return draft, True