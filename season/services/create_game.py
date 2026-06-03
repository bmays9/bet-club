# season/services/create_game.py
"""
Creates a Season Game with all prize pools pre-configured.
Called from the create game view.
"""
from decimal import Decimal
from django.utils.timezone import now
from django.db import transaction
from season.models import (
    Game, GameLeague, PlayerGame, PrizePool, PrizePayout, PrizeCategory,
)
from season.prize_config import (
    TEAMS_TO_WIN_BEST, TEAMS_TO_WIN_WORST,
    TEAMS_TO_LOSE_BEST, TEAMS_TO_LOSE_WORST,
    LEAGUE_WINNER_PER_PLAYER, MONTHLY_PER_PLAYER,
    OVERALL_LOSER_PENALTIES,
)


@transaction.atomic
def create_season_game(
    name,
    group,
    created_by,
    leagues,
    entry_fee=Decimal("0.00"),
    draft_date=None,
    draft_method="straight",
    # Prize overrides (optional -- defaults used if None)
    teams_to_win_best=None,
    teams_to_win_worst=None,
    teams_to_lose_best=None,
    teams_to_lose_worst=None,
    league_winner_per_player=None,
    monthly_per_player=None,
    overall_penalties=None,
):
    """
    Create a Game, attach leagues, configure all prize pools.
    Returns the created Game.
    """
    game = Game.objects.create(
        name=name,
        group=group,
        created_by=created_by,
        entry_fee=entry_fee,
        status=Game.Status.OPEN,
        draft_date=draft_date,
        draft_method=draft_method,
    )

    # Attach leagues
    for league in leagues:
        GameLeague.objects.create(game=game, league=league, active=True)

    # Use defaults or overrides
    tw_best = teams_to_win_best or TEAMS_TO_WIN_BEST
    tw_worst = teams_to_win_worst or TEAMS_TO_WIN_WORST
    tl_best = teams_to_lose_best or TEAMS_TO_LOSE_BEST
    tl_worst = teams_to_lose_worst or TEAMS_TO_LOSE_WORST
    lw_per_player = league_winner_per_player or LEAGUE_WINNER_PER_PLAYER
    m_per_player = monthly_per_player or MONTHLY_PER_PLAYER
    ov_penalties = overall_penalties or OVERALL_LOSER_PENALTIES

    # -------------------------------------------------------------------
    # Teams to Win -- Best
    # -------------------------------------------------------------------
    pool_tw_best = PrizePool.objects.create(
        game=game,
        name="Teams to Win -- Best",
        category=PrizeCategory.TEAMS_TO_WIN,
        active=True,
    )
    for row in tw_best:
        PrizePayout.objects.create(
            prize_pool=pool_tw_best,
            rank=row["rank"],
            amount=row["amount"],
        )

    # -------------------------------------------------------------------
    # Teams to Win -- Worst (penalties)
    # -------------------------------------------------------------------
    pool_tw_worst = PrizePool.objects.create(
        game=game,
        name="Teams to Win -- Worst",
        category=PrizeCategory.TEAMS_TO_WIN,
        active=True,
    )
    for row in tw_worst:
        PrizePayout.objects.create(
            prize_pool=pool_tw_worst,
            rank=row["rank"],
            amount=row["amount"],
        )

    # -------------------------------------------------------------------
    # Teams to Lose -- Best
    # -------------------------------------------------------------------
    pool_tl_best = PrizePool.objects.create(
        game=game,
        name="Teams to Lose -- Best",
        category=PrizeCategory.TEAMS_TO_LOSE,
        active=True,
    )
    for row in tl_best:
        PrizePayout.objects.create(
            prize_pool=pool_tl_best,
            rank=row["rank"],
            amount=row["amount"],
        )

    # -------------------------------------------------------------------
    # Teams to Lose -- Worst (penalties)
    # -------------------------------------------------------------------
    pool_tl_worst = PrizePool.objects.create(
        game=game,
        name="Teams to Lose -- Worst",
        category=PrizeCategory.TEAMS_TO_LOSE,
        active=True,
    )
    for row in tl_worst:
        PrizePayout.objects.create(
            prize_pool=pool_tl_worst,
            rank=row["rank"],
            amount=row["amount"],
        )

    # -------------------------------------------------------------------
    # League winners -- one pool per league, scales with player count
    # -------------------------------------------------------------------
    for league in leagues:
        gl = GameLeague.objects.get(game=game, league=league)
        pool_lw = PrizePool.objects.create(
            game=game,
            name=f"{league.name} Winner",
            category=PrizeCategory.LEAGUE_WINNER,
            league=league,
            active=True,
        )
        PrizePayout.objects.create(
            prize_pool=pool_lw,
            rank=1,
            entry_fee_per_player=lw_per_player,
            amount=Decimal("0.00"),  # calculated at runtime from num_players
        )

    # -------------------------------------------------------------------
    # Monthly winner -- one pool, scales with player count x months
    # -------------------------------------------------------------------
    pool_monthly = PrizePool.objects.create(
        game=game,
        name="Monthly Winner",
        category=PrizeCategory.MONTH_WINNER,
        active=True,
    )
    PrizePayout.objects.create(
        prize_pool=pool_monthly,
        rank=1,
        entry_fee_per_player=m_per_player,
        amount=Decimal("0.00"),
    )

    # -------------------------------------------------------------------
    # Overall standings -- 1st wins all penalties from 2nd+
    # Number of penalty rows = min(len(ov_penalties), num_players - 1)
    # but we create them all upfront; unused ones just won't fire
    # -------------------------------------------------------------------
    pool_overall = PrizePool.objects.create(
        game=game,
        name="Overall Standings",
        category=PrizeCategory.OVERALL,
        active=True,
    )
    # Winner row -- amount calculated at settle time from penalties collected
    PrizePayout.objects.create(
        prize_pool=pool_overall,
        rank=1,
        amount=Decimal("0.00"),  # filled in at finalise time
    )
    for row in ov_penalties:
        PrizePayout.objects.create(
            prize_pool=pool_overall,
            rank=row["rank"],
            amount=row["amount"],
        )

    return game


def calculate_overall_winner_prize(game):
    """
    Calculate how much the overall winner receives.
    = sum of all penalty amounts for ranks 2+ (all negative values)
    Times -1 since penalties are stored as negative.
    """
    from season.models import PrizePayout, PrizeCategory
    penalties = PrizePayout.objects.filter(
        prize_pool__game=game,
        prize_pool__category=PrizeCategory.OVERALL,
        rank__gt=1,
        amount__lt=0,
    )
    total_penalty = sum(abs(p.amount) for p in penalties)
    return total_penalty
