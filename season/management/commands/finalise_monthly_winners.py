from django.core.management.base import BaseCommand
from django.db.models import Sum
from django.utils.timezone import now
import calendar
from season.models import PlayerScoreSnapshot, PrizePool, PrizePayout, PrizeCategory

class Command(BaseCommand):
    help = "Finalise monthly winners and create PrizePayout entries."

    def handle(self, *args, **options):
        today = now()
        # Look back at the previous month
        year = today.year
        month = today.month - 1 or 12
        if today.month == 1:
            year -= 1

        # Date range for that month
        _, last_day = calendar.monthrange(year, month)
        start = today.replace(year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = today.replace(year=year, month=month, day=last_day, hour=23, minute=59, second=59, microsecond=999999)

        # Group by player total
        scores = (
            PlayerScoreSnapshot.objects.filter(batch__taken_at__range=(start, end))
            .values("player_game", "player_game__user__username")
            .annotate(total_points=Sum("league_total_points"))
            .order_by("-total_points")
        )

        if not scores:
            self.stdout.write("No scores found for that month.")
            return

        winner = scores[0]
        player_game_id = winner["player_game"]
        username = winner["player_game__user__username"]
        total_points = winner["total_points"]

        # Find the monthly prize pool for this game
        pools = PrizePool.objects.filter(category=PrizeCategory.MONTH_WINNER, active=True)
        for pool in pools:
            # Check if we already recorded this month
            already = pool.payouts.filter(rank=1, created_at__month=month, created_at__year=year).exists()
            if already:
                continue

            PrizePayout.objects.create(
                prize_pool=pool,
                rank=1,
                amount=pool.entry_fee or 0,  # or a fixed amount if that’s your rule
                player_game_id=player_game_id,
            )
            self.stdout.write(f"Recorded monthly winner {username} ({total_points} pts) for {pool.game.name}.")
