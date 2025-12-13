from bank.services import apply_batch
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db.models import Max, Min
from django.urls import reverse
from django.utils import timezone
from django.utils.timezone import now
from datetime import timedelta
from lms.models import LMSPick, LMSRound, LMSEntry, LMSGame
from lms.services.missing_picks import handle_missing_picks
from lms.services.pick_resolution import (assign_missing_picks, handle_unresolved_postponed_picks, round_deadline_passed)
from player_messages.utils import create_message
from score_predict.models import Fixture

from player_messages.utils import create_message
from score_predict.models import Fixture


FINAL_STATUS_CODES = (100,)
CANCELLED_CODE = 90
POSTPONED_CODE = 60


class Command(BaseCommand):
    help = "Update LMS pick results and create the next round if needed"

    def handle(self, *args, **options):
        self.stdout.write("Updating LMS pick results...")

        # ----------------------------------------------------
        # 1️ Find earliest incomplete round per active game
        # ----------------------------------------------------
        earliest_rounds = (
            LMSRound.objects
            .filter(game__active=True, completed=False)
            .values("game")
            .annotate(earliest_round=Min("round_number"))
        )

        print("Earliest Rounds:", earliest_rounds)

        rounds = LMSRound.objects.filter(
            game__active=True,
            completed=False,
            round_number__in=[r["earliest_round"] for r in earliest_rounds],
        ).select_related("game").order_by("game_id", "round_number")

        print("Rounds:", rounds)

        for round_obj in rounds:
            game = round_obj.game
            now_ts = timezone.now()

            self.stdout.write(f"\n➡️ Processing {round_obj}")

            # ----------------------------------------------------
            # 2️ Determine pick deadline
            # ----------------------------------------------------
            first_fixture = round_obj.fixtures.order_by("date").first()

            if game.deadline_mode == "first_game":
                deadline_passed = first_fixture and now_ts >= first_fixture.date
            else:  # extended
                deadline_passed = now_ts >= round_obj.end_date

            print("Deadline Passesd?:", deadline_passed)

            # ----------------------------------------------------
            # 3️ Assign missing picks AFTER deadline
            # ----------------------------------------------------
            if deadline_passed:
                assign_missing_picks(game, round_obj)

            # ----------------------------------------------------
            # 4️ Handle postponed fixtures AFTER round ends
            # ----------------------------------------------------
            if now_ts >= round_obj.end_date:
                handle_unresolved_postponed_picks(game, round_obj)

            # ----------------------------------------------------
            # 5️ Compute results for pending picks
            # ----------------------------------------------------
            for pick in round_obj.picks.filter(result="PENDING"):
                fixture = pick.fixture

                if not fixture or fixture.date > now_ts:
                    continue

                if fixture.status_code in FINAL_STATUS_CODES:
                    if fixture.home_score is None or fixture.away_score is None:
                        continue

                    if fixture.home_score > fixture.away_score:
                        result = "WIN" if fixture.home_team == pick.team_name else "LOSE"
                    elif fixture.away_score > fixture.home_score:
                        result = "WIN" if fixture.away_team == pick.team_name else "LOSE"
                    else:
                        result = "DRAW"

                elif fixture.status_code == CANCELLED_CODE:
                    result = "WIN"   # cancelled = free pass

                elif fixture.status_code == POSTPONED_CODE:
                    continue  # still unresolved

                else:
                    continue

                pick.result = result
                pick.save()

            # ----------------------------------------------------
            # 6️ Eliminate entries
            # ----------------------------------------------------
            for entry in game.entries.all():
                picks = round_obj.picks.filter(entry=entry)

                if not picks.exists():
                    if game.deadline_mode != "first_game":
                        continue

                    entry.alive = False
                    entry.eliminated_round = (
                        0 if round_obj.round_number == 1 else round_obj.round_number
                    )
                    entry.save()
                    continue

                if picks.filter(result__in=["LOSE", "DRAW"]).exists():
                    entry.alive = False
                    entry.eliminated_round = round_obj.round_number
                    entry.save()

            # ----------------------------------------------------
            # 7️ Complete round
            # ----------------------------------------------------
            if not round_obj.picks.filter(result="PENDING").exists():
                round_obj.completed = True
                round_obj.save()

            # ----------------------------------------------------
            # 8️ Check for winner
            # ----------------------------------------------------
            alive = game.entries.filter(alive=True)
            alive_count = alive.count()

            if alive_count == 1:
                winner_entry = alive.first()
                game.winner = winner_entry.user
                game.active = False
                game.save()

                entrants = game.entries.count()
                prize_pool = Decimal(game.entry_fee) * entrants

                apply_batch(
                    group=game.group,
                    entrants=[e.user for e in game.entries.all()],
                    winners=[winner_entry.user],
                    entry_fee=Decimal(game.entry_fee),
                    prize_pool=prize_pool,
                    description=f"LMS {game.get_league_display()}",
                )

            elif alive_count == 0:
                game.active = False
                game.save()

            # ---------------------------------------------------
            # 9️ Create next round
            # ----------------------------------------------------
            latest_round = LMSRound.objects.filter(game=game).aggregate(
                Max("round_number")
            )["round_number__max"]

            if round_obj.completed and round_obj.round_number == latest_round:
                self.create_next_round(round_obj)

        self.stdout.write("✅ LMS pick results update complete.")

    # --------------------------------------------------------
    # Helper: create next round
    # --------------------------------------------------------
    def create_next_round(self, previous_round):
        game = previous_round.game
        today = now().date()

        for days_ahead in range(0, 30):
            current_day = today + timedelta(days=days_ahead)
            weekday = current_day.weekday()

            if weekday == 4:
                start, end = current_day, current_day + timedelta(days=3)
            elif weekday == 1:
                start, end = current_day, current_day + timedelta(days=2)
            else:
                continue

            fixtures = Fixture.objects.filter(
                league_short_name=game.league,
                date__range=(start, end),
            ).order_by("date")

            if fixtures.count() >= 7:
                new_round = LMSRound.objects.create(
                    game=game,
                    round_number=previous_round.round_number + 1,
                    start_date=fixtures.first().date,
                    end_date=fixtures.last().date,
                )
                new_round.fixtures.set(fixtures)
                return new_round


