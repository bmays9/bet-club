# season/utils/season_helpers.py
from season.models import Game, PlayerGame, StandingsBatch
from django.db.models import Max
from groups.models import UserGroup


def get_group_and_game_selection(user, request):
    """
    Determines the selected group and game from request params.
    Auto-selects group if user only has one.
    Auto-selects game if the group only has one game,
    OR if the user is only in one game within the group.
    """
    user_groups = UserGroup.objects.filter(members=user)
    selected_group_id = request.GET.get("group")
    selected_game_id = request.GET.get("game")

    # Auto-select group if only one
    if not selected_group_id and user_groups.count() == 1:
        selected_group = user_groups.first()
    else:
        selected_group = user_groups.filter(id=selected_group_id).first()
        if not selected_group and user_groups.exists():
            selected_group = user_groups.first()

    # Games for this group
    group_games = (
        Game.objects.filter(group=selected_group)
        if selected_group
        else Game.objects.none()
    )

    # Filter to only games this user is in
    user_game_ids = PlayerGame.objects.filter(
        user=user,
        game__in=group_games,
    ).values_list("game_id", flat=True)
    user_games = group_games.filter(id__in=user_game_ids)

    # Auto-select if only one game available to this user
    if selected_game_id:
        selected_game = group_games.filter(id=selected_game_id).first()
    elif user_games.count() == 1:
        selected_game = user_games.first()
    elif group_games.count() == 1:
        selected_game = group_games.first()
    else:
        selected_game = None

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
            league_id=row["league_id"],
            taken_at=row["latest_taken_at"],
        ).first()
        if b:
            batch_ids.append(b.id)
    return batch_ids


def get_month_start_batch_ids():
    """
    Returns list of the latest month-end StandingsBatch IDs, one per league.
    """
    month_batches = (
        StandingsBatch.objects
        .filter(is_month_end=True)
        .values("league_id")
        .annotate(latest_taken_at=Max("taken_at"))
    )
    month_batch_ids = []
    for row in month_batches:
        b = StandingsBatch.objects.filter(
            league_id=row["league_id"],
            taken_at=row["latest_taken_at"],
        ).first()
        if b:
            month_batch_ids.append(b.id)
    return month_batch_ids


def get_latest_batches_map():
    """
    Returns a dict of {league_id: latest_batch_object}
    """
    latest_batches = (
        StandingsBatch.objects.values("league_id")
        .annotate(latest_taken_at=Max("taken_at"))
    )
    result = {}
    for row in latest_batches:
        b = StandingsBatch.objects.filter(
            league_id=row["league_id"],
            taken_at=row["latest_taken_at"],
        ).first()
        if b:
            result[row["league_id"]] = b
    return result


def should_mark_month_end(batch_time=None):
    """
    Check if the batch should be flagged as a month-end batch.
    A month ends when all fixtures in that calendar month are finished
    (status_code=100 for all of them, or their date has passed by 3+ hours).
    """
    from django.utils.timezone import now as tz_now
    from datetime import timedelta
    from score_predict.models import Fixture

    if batch_time is None:
        batch_time = tz_now()

    year = batch_time.year
    month = batch_time.month

    # Get fixtures for this calendar month
    month_fixtures = Fixture.objects.filter(
        date__year=year,
        date__month=month,
    ).exclude(status_code__in=[60, 90])  # exclude postponed/abandoned

    if not month_fixtures.exists():
        return False

    last_fixture = month_fixtures.order_by("-date").first()

    # Must be at least 3 hours after the last fixture
    if batch_time < last_fixture.date + timedelta(hours=3):
        return False

    # All fixtures must be finished
    unfinished = month_fixtures.exclude(status_code=100).exists()
    return not unfinished


def get_previous_month_batch_ids(year, month):
    """
    Get the most recent month-end batch IDs for the given year/month.
    Returns list of batch IDs (one per league).
    """
    from django.utils.timezone import make_aware
    from datetime import datetime, date as date_type
    from calendar import monthrange

    last_day = monthrange(year, month)[1]
    month_end = date_type(year, month, last_day)

    batch_ids = []
    latest = (
        StandingsBatch.objects
        .filter(is_month_end=True, taken_at__date__lte=month_end)
        .values("league_id")
        .annotate(latest_taken_at=Max("taken_at"))
    )
    for row in latest:
        b = StandingsBatch.objects.filter(
            league_id=row["league_id"],
            taken_at=row["latest_taken_at"],
            is_month_end=True,
        ).first()
        if b:
            batch_ids.append(b.id)
    return batch_ids
