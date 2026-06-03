# season/prize_config.py
"""
Default prize configuration for a season game.
All amounts are per-player contributions or fixed payouts.
Negative amounts = penalty (that player pays into the pot).
"""
from decimal import Decimal

# -------------------------------------------------------------------
# Teams to Win (win + handicap picks combined, ranked by points)
# Best performers PAY IN to the pot; worst performers RECEIVE
# (i.e. negative ranks are penalties paid by those players)
# -------------------------------------------------------------------
TEAMS_TO_WIN_BEST = [
    {"rank": 1, "amount": Decimal("40.00")},
    {"rank": 2, "amount": Decimal("30.00")},
    {"rank": 3, "amount": Decimal("20.00")},
    {"rank": 4, "amount": Decimal("10.00")},
    {"rank": 5, "amount": Decimal("5.00")},
]
TEAMS_TO_WIN_WORST = [
    {"rank": 1, "amount": Decimal("-40.00")},
    {"rank": 2, "amount": Decimal("-30.00")},
    {"rank": 3, "amount": Decimal("-20.00")},
    {"rank": 4, "amount": Decimal("-10.00")},
    {"rank": 5, "amount": Decimal("-5.00")},
]

# -------------------------------------------------------------------
# Teams to Lose (ranked by fewest points = best loser pick)
# -------------------------------------------------------------------
TEAMS_TO_LOSE_BEST = [
    {"rank": 1, "amount": Decimal("30.00")},
    {"rank": 2, "amount": Decimal("20.00")},
    {"rank": 3, "amount": Decimal("10.00")},
]
TEAMS_TO_LOSE_WORST = [
    {"rank": 1, "amount": Decimal("-30.00")},
    {"rank": 2, "amount": Decimal("-20.00")},
    {"rank": 3, "amount": Decimal("-10.00")},
]

# -------------------------------------------------------------------
# League winners -- per-player contribution, all to winner
# Stored as entry_fee_per_player so it scales with player count
# -------------------------------------------------------------------
LEAGUE_WINNER_PER_PLAYER = Decimal("10.00")

# -------------------------------------------------------------------
# Monthly prize -- per-player per month contribution, all to winner
# -------------------------------------------------------------------
MONTHLY_PER_PLAYER = Decimal("5.00")

# -------------------------------------------------------------------
# Overall standings
# 1st = winner, receives all penalties from 2nd-last
# 2nd pays £20, 3rd pays £30, 4th pays £40, 5th pays £50, 6th pays £60 etc.
# -------------------------------------------------------------------
OVERALL_LOSER_PENALTIES = [
    {"rank": 2, "amount": Decimal("-20.00")},
    {"rank": 3, "amount": Decimal("-30.00")},
    {"rank": 4, "amount": Decimal("-40.00")},
    {"rank": 5, "amount": Decimal("-50.00")},
    {"rank": 6, "amount": Decimal("-60.00")},
    {"rank": 7, "amount": Decimal("-70.00")},
    {"rank": 8, "amount": Decimal("-80.00")},
    {"rank": 9, "amount": Decimal("-90.00")},
    {"rank": 10, "amount": Decimal("-100.00")},
]
