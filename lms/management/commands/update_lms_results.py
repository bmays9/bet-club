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
from lms.utils import get_auto_pick_teams_for_round
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
                print("Handling this pick now:", pick)
                print("which is this fixture", fixture)
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
                    continue   # unresolved

                elif fixture.status_code == POSTPONED_CODE:
                    continue  # still unresolved

                else:
                    continue

                pick.result = result
                pick.save()
                self.stdout.write(f"Pick result computed: {result}")

            # ----------------------------------------------------
            # 6️ Eliminate entries that lost or drew
            # ----------------------------------------------------
            for entry in round_obj.game.entries.all():
                picks = round_obj.picks.filter(entry=entry)

                if not picks.exists():
                    if game.deadline_mode != "first_game":
                        continue

                    entry.alive = False
                    entry.eliminated_round = 0 if round_obj.round_number == 1 else round_obj.round_number
                    entry.save()
                    self.stdout.write(f"Entry {entry.user} eliminated for not picking in round {round_obj.round_number}")

                    # Update messages with the losers
                    create_message(
                        code="LM-UKO",
                        context={"User": entry.user, "league": entry.game.get_league_display()},
                        group=entry.game.group,
                        receiver=entry.user,
                        actor=entry.user,
                        link=f"lms_game_detail:{entry.game.id}"
                       # link= reverse ("lms_game_detail", args=[entry.game.id])
                    )
                    continue

                if picks.filter(result__in=["LOSE", "DRAW"]).exists():
                    entry.alive = False
                    entry.eliminated_round = round_obj.round_number
                    entry.save()
                    self.stdout.write(f"Entry {entry.user} eliminated for incorrect pick(s) in round {round_obj.round_number}")

                    # Update messages with the losers
                    create_message(
                        code="LM-UKO",
                        context={"User": entry.user, "league": entry.game.get_league_display()},
                        group=entry.game.group,
                        receiver=entry.user,
                        actor=entry.user,
                        link=f"lms_game_detail:{entry.game.id}"
                        # link=reverse ("lms_game_detail", args=[entry.game.id])
                    )

            # ----------------------------------------------------
            # 7️ Complete round
            # ----------------------------------------------------
            if not round_obj.picks.filter(result="PENDING").exists():
                round_obj.completed = True
                round_obj.save()
                self.stdout.write(f"Round {round_obj.round_number} marked as completed.")

            # ----------------------------------------------------
            # 8️ Check for winner
            # ----------------------------------------------------
            alive = game.entries.filter(alive=True)
            alive_count = alive.count()
            entry_fee = round_obj.game.entry_fee  # stored in LMSGame
            entrants = game.entries.count()
            prize_pool = Decimal(entry_fee) * entrants

            if alive_count == 1:
                winner_entry = alive.first()
                game.winner = winner_entry.user
                game.active = False
                game.save()
                self.stdout.write(f" Game over! Winner: {winner_entry.user} ({round_obj.game})")

                # Update messages with the LMS Winner!
                create_message(
                    code="LM-WIN",
                    context={"User": winner_entry.user, "league": round_obj.game.get_league_display(), "prize": prize_pool},
                    group=entry.game.group,
                    actor=winner_entry.user,
                    receiver=winner_entry.user,
                    link=f"lms_game_detail:{entry.game.id}"
                    # link = reverse ("lms_game_detail", args=[entry.game.id])
                    )

                 # --- Settle Money in Bank app ---
                entrants = [e.user for e in round_obj.game.entries.all()]  # all users who joined this game
                winners = [winner_entry.user]                              # the single winner
                
                apply_batch(
                    group=round_obj.game.group, 
                    entrants=entrants,
                    winners=winners,
                    entry_fee=Decimal(entry_fee),
                    prize_pool=prize_pool,
                    description=f"Settlement for LMS {round_obj.game.get_league_display()}"
                    )

            elif alive_count == 0:
                round_obj.game.active = False
                round_obj.game.save()
                self.stdout.write(f"Game over with no winner: {round_obj.game}")

                # Update messages with no LMS Winner - rollover!
                create_message(
                    code="LM-OOO",
                    context={"league": round_obj.game.league, "prize": prize_pool},
                    link=f"lms_game_detail:{entry.game.id}",
                    group=round_obj.game.group
                )


            # ---------------------------------------------------
            # 9️ Create next round
            # ----------------------------------------------------
            latest_round = LMSRound.objects.filter(game=game).aggregate(
                Max("round_number")
                )["round_number__max"]

            if round_obj.completed and round_obj.round_number == latest_round:
                next_round_num = round_obj.round_number + 1
                created_round = self.create_next_round(round_obj)
                if created_round:
                    self.stdout.write(f"Created Round {created_round.round_number} for {round_obj.game}")
                else:
                    self.stdout.write(f" Not enough fixtures to create Round {next_round_num} for {round_obj.game}")
        
                    
        # --- Final check: active games missing a next round ---
        self.stdout.write("\nChecking active games for missing next rounds...")
        for game in LMSGame.objects.filter(active=True):
            latest_round = LMSRound.objects.filter(game=game).order_by("-round_number").first()
            if latest_round:
                if latest_round.completed:
                    next_round_num = latest_round.round_number + 1
                    if not LMSRound.objects.filter(game=game, round_number=next_round_num).exists():
                        created_round = self.create_next_round(latest_round)
                        if created_round:
                            self.stdout.write(f"Created Round {created_round.round_number} for {game}")
                        else:
                            self.stdout.write(f"No suitable fixtures found for next round of {game}")
                else:
                    self.stdout.write(f"Latest round {latest_round.round_number} of {game} not yet completed. Skipping.")
            else:
                self.stdout.write(f"No rounds found for {game}")            
                    
        self.stdout.write(" LMS pick results update complete.")

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
                auto_picks = get_auto_pick_teams_for_round(game, new_round, fixtures, count=4)
                print("auto", auto_picks)

                if auto_picks:
                    new_round.auto_pick_team = auto_picks[3]
                    new_round.auto_pick_team1 = auto_picks[0]
                    new_round.auto_pick_team2 = auto_picks[1] if len(auto_picks) > 1 else None
                    new_round.auto_pick_team3 = auto_picks[2] if len(auto_picks) > 2 else None
                    new_round.save()

                    print("Auto-pick teams set:", auto_picks[0],auto_picks[1] )
                return new_round


