# season/management/commands/finalise_monthly_winners.py
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db.models import Sum
from django.utils.timezone import now
from season.models import (
    Game, PlayerScoreSnapshot, PrizePool, PrizePayout,
    PrizeCategory, StandingsBatch, PlayerGame,
)
from bank.services import apply_batch


class Command(BaseCommand):
    help = "Finalise monthly winners and settle bank balances."

    def handle(self, *args, **options):
        # Find most recent month-end batch per league
        month_end_batches = (
            StandingsBatch.objects
            .filter(is_month_end=True)
            .order_by("-taken_at")
        )
        if not month_end_batches.exists():
            self.stdout.write("No month-end batch found.")
            return

        # Use the most recent one
        month_end_batch = month_end_batches.first()
        cutoff_date = month_end_batch.taken_at
        year = cutoff_date.year
        month = cutoff_date.month
        awarded_for = cutoff_date.date().replace(day=1)

        self.stdout.write(
            f"Finalising monthly winner for {year}-{month:02d} "
            f"using batch {month_end_batch.id}"
        )

        # Find monthly prize pools, filter by game so we handle each separately
        pools = PrizePool.objects.filter(
            category=PrizeCategory.MONTH_WINNER,
            active=True,
        ).select_related("game", "game__group")

        for pool in pools:
            game = pool.game

            # Skip if already paid for this month
            already = PrizePayout.objects.filter(
                prize_pool=pool,
                awarded_for_month__year=year,
                awarded_for_month__month=month,
            ).exists()
            if already:
                self.stdout.write(
                    f"  {game.name}: already settled for {year}-{month:02d}, skipping."
                )
                continue

            # Scores for THIS game only at this month-end batch
            scores = (
                PlayerScoreSnapshot.objects
                .filter(
                    batch=month_end_batch,
                    player_game__game=game,
                )
                .values("player_game", "player_game__user__username")
                .annotate(total_points=Sum("league_total_points"))
                .order_by("-total_points")
            )

            if not scores.exists():
                self.stdout.write(f"  {game.name}: no scores found.")
                continue

            top_score = scores[0]["total_points"]
            winners = [s for s in scores if s["total_points"] == top_score]

            num_players = game.players.count()

            # Calculate prize amount
            # PrizePayout template row (rank=None) holds the prize config
            payout_config = pool.payouts.filter(rank__isnull=True).first()
            if payout_config:
                prize_total = payout_config.calculate_prize(num_players)
            else:
                prize_total = Decimal("0.00")

            # Split prize among tied winners
            share = (prize_total / len(winners)).quantize(Decimal("0.01"))

            entrants = list(
                PlayerGame.objects.filter(game=game)
                .values_list("user", flat=True)
            )
            from django.contrib.auth.models import User
            entrant_users = list(User.objects.filter(id__in=entrants))
            winner_users = []

            for winner in winners:
                pg = PlayerGame.objects.get(id=winner["player_game"])
                winner_users.append(pg.user)

                PrizePayout.objects.create(
                    prize_pool=pool,
                    rank=awarded_for.month,  # month number as rank (8=Aug, 9=Sep etc)
                    amount=share,
                    recipient=pg,
                    awarded_for_month=awarded_for,
                    points=winner["total_points"],
                )
                self.stdout.write(
                    f"  {game.name}: winner {pg.user.username} "
                    f"({top_score} pts) gets GBP{share}"
                )

            # Settle bank balances
            if prize_total > 0 and entrant_users and winner_users:
                try:
                    apply_batch(
                        group=game.group,
                        entrants=entrant_users,
                        winners=winner_users,
                        entry_fee=game.entry_fee,
                        prize_pool=prize_total,
                        description=(
                            f"Season monthly prize {year}-{month:02d} "
                            f"- {game.name}"
                        ),
                    )
                    self.stdout.write(
                        f"  {game.name}: bank settled, "
                        f"GBP{prize_total} split {len(winner_users)} way(s)"
                    )
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"  {game.name}: bank settlement failed: {e}")
                    )
