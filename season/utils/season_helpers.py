from season.models import Game, PlayerGame, StandingsBatch
from django.db.models import Max
from groups.models import UserGroup

def get_group_and_game_selection(user, request):
    user_groups = UserGroup.objects.filter(members=user)
    selected_group_id = request.GET.get("group")
    selected_game_id = request.GET.get("game")

    # Auto-select group if only one
    if not selected_group_id and user_groups.count() == 1:
        selected_group = user_groups.first()
    else:
        selected_group = user_groups.filter(id=selected_group_id).first()

    # Games for dropdown
    group_games = Game.objects.filter(group=selected_group) if selected_group else Game.objects.none()

    # Auto-select game if only one
    if not selected_game_id and group_games.count() == 1:
        selected_game = group_games.first()
    else:
        selected_game = group_games.filter(id=selected_game_id).first()

    # PlayerGames for scoring
    player_games = PlayerGame.objects.filter(game__group=selected_group)
    if selected_game:
        player_games = player_games.filter(game=selected_game)

    return {
        "user_groups": user_groups,
        "selected_group": selected_group,
        "group_games": group_games,
        "selected_game": selected_game,
        "player_games": player_games,
    }


def get_latest_batch_ids():
    """
    Returns a list of the latest StandingsBatch IDs, one per league.
    """
    latest_batches = (
        StandingsBatch.objects.values("league_id")
        .annotate(latest_taken_at=Max("taken_at"))
    )

    batch_ids = []
    for row in latest_batches:
        b = StandingsBatch.objects.filter(
            league_id=row["league_id"], taken_at=row["latest_taken_at"]
        ).first()
        if b:
            batch_ids.append(b.id)
    return batch_ids

def get_latest_batches_map():
    """
    Returns a dict of {league_id: latest_batch_object}
    """
    from ..models import StandingsBatch
    from django.db.models import Max

    latest_batches = (
        StandingsBatch.objects.values("league_id")
        .annotate(latest_taken_at=Max("taken_at"))
    )

    league_latest_batch = {}
    for lb in latest_batches:
        batch = StandingsBatch.objects.filter(
            league_id=lb["league_id"], taken_at=lb["latest_taken_at"]
        ).first()
        if batch:
            league_latest_batch[lb["league_id"]] = batch
    return league_latest_batch

