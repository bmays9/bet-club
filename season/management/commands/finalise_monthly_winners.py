from django.core.management.base import BaseCommand
from django.db.models import Sum
from django.utils.timezone import now
from season.models import PlayerScoreSnapshot, PrizePool, PrizePayout, PrizeCategory, StandingsBatch

class Command(BaseCommand):
    help = "Finalise monthly winners and create PrizePayout entries."

    def handle(self, *args, **options):
        today = now()

        # 1. Find the most recent month-end batch
        month_end_batch = StandingsBatch.objects.filter(is_month_end=True).order_by("-taken_at").first()
        if not month_end_batch:
            self.stdout.write("No month-end batch found.")
            return

        # 2. Work out which month that batch closes
        cutoff_date = month_end_batch.taken_at
        year = cutoff_date.year
        month = cutoff_date.month

        self.stdout.write(f"Finalising monthly winner for {year}-{month:02d} using batch {month_end_batch.id}")

        # 3. Group scores up to that batch
        scores = (
            PlayerScoreSnapshot.objects.filter(batch=month_end_batch)
            .values("player_game", "player_game__user__username")
            .annotate(total_points=Sum("league_total_points"))
            .order_by("-total_points")
        )

        if not scores:
            self.stdout.write("No scores found for that cutoff.")
            return

        # Winner = highest total points
        winner = scores[0]
        player_game_id = winner["player_game"]
        username = winner["player_game__user__username"]
        total_points = winner["total_points"]
        print ("winner", winner)
        print ("username", username)
        print ("totalpoints", total_points)

        # 4. Find the monthly prize pools
        pools = PrizePool.objects.filter(category=PrizeCategory.MONTH_WINNER, active=True)
        print ("pools", pools)
        for pool in pools:
            # Prevent duplicate payouts for same month
            already = pool.payouts.filter(awarded_for_month__year=year, awarded_for_month__month=month).exists()
            if already:
                continue

            PrizePayout.objects.create(
                prize_pool=pool,
                rank=1,
                amount=pool.amount or 0,  # assumes you've precalculated amount on pool/payout rule
                recipient_id=player_game_id,
                awarded_for_month=cutoff_date.date().replace(day=1),  # store first day of that month
                points=total_points,
            )
            self.stdout.write(f"Recorded monthly winner {username} ({total_points} pts) for {pool.game.name}.")
