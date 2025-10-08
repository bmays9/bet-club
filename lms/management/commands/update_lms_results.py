from bank.services import apply_batch
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db.models import Max, Min
from django.utils import timezone
from django.utils.timezone import now
from datetime import timedelta
from lms.models import LMSPick, LMSRound, LMSEntry, LMSGame
from player_messages.utils import create_message
from score_predict.models import Fixture

class Command(BaseCommand):
    help = "Update LMS pick results and create the next round if needed"

    def handle(self, *args, **options):
        self.stdout.write("🔄 Updating LMS pick results...")

        # --- 1️⃣ Process earliest incomplete rounds per game ---
        earliest_incomplete_rounds = (
            LMSRound.objects.filter(game__active=True, completed=False, start_date__lte=timezone.now())   # ✅ only past or current rounds
            .values("game")
            .annotate(earliest_round=Min("round_number"))
        )

        incomplete_rounds = LMSRound.objects.filter(
            game__active=True,
            completed=False,
            start_date__lte=timezone.now(),
            round_number__in=[r["earliest_round"] for r in earliest_incomplete_rounds]
        ).order_by("game_id", "round_number")

        self.stdout.write(f"Processing incomplete rounds: {list(incomplete_rounds)}")

        for round_obj in incomplete_rounds:
            self.stdout.write(f"\n➡️ Processing {round_obj}")

            # --- 1a. Update pending picks ---
            picks_pending = round_obj.picks.filter(result="PENDING")
            for pick in picks_pending:
                fixture = pick.fixture
                self.stdout.write(f"  Processing Pick {pick.id} ({pick.team_name}) "
                                  f"{fixture.home_team} vs {fixture.away_team} "
                                  f"[Score: {fixture.home_score}-{fixture.away_score}, Status: {fixture.status_code}]")
                
                if fixture.status_code in (100, 60, 90):  # Fixture finished
                    if fixture.home_score > fixture.away_score:
                        result = "WIN" if fixture.home_team == pick.team_name else "LOSE"
                    elif fixture.away_score > fixture.home_score:
                        result = "WIN" if fixture.away_team == pick.team_name else "LOSE"
                    else:
                        result = "DRAW"
                    pick.result = result
                    pick.save()
                    self.stdout.write(f"    ✅ Pick result computed: {result}")

            # --- 1b. Eliminate entries with losing/drawing picks or no picks ---
            for entry in round_obj.game.entries.all():
                picks_for_entry = round_obj.picks.filter(entry=entry)

                if not picks_for_entry.exists():
                    # No picks made: eliminated at round 0 only if round 1, otherwise current round
                    if entry.alive:
                        entry.alive = False
                        entry.eliminated_round = 0 if round_obj.round_number == 1 else round_obj.round_number
                        entry.save()
                        self.stdout.write(f"    ❌ Entry {entry.user} eliminated for not picking in round {round_obj.round_number}")

                        # Update messages
                        # Update messages with the losers
                        create_message(
                            code="LM-UKO",
                            context={"User": entry.user, "league": entry.game.get_league_display()},
                            group=entry.game.group,
                            receiver=entry.user,
                            link=f"lms_game_detail:{game.id}"
                        )

                    continue

                if picks_for_entry.filter(result__in=["LOSE", "DRAW"]).exists():
                    if entry.alive:
                        entry.alive = False
                        entry.eliminated_round = round_obj.round_number
                        entry.save()
                        self.stdout.write(f"    ❌ Entry {entry.user} eliminated for incorrect pick(s) in round {round_obj.round_number}")

                        # Update messages with the losers
                        create_message(
                            code="LM-UKO",
                            context={"User": entry.user, "league": entry.game.get_league_display()},
                            group=entry.game.group,
                            receiver=entry.user,
                            link=f"lms_game_detail:{game.id}"
                        )


            # --- 1c. Mark round completed if no pending picks remain ---
            if not round_obj.picks.filter(result="PENDING").exists():
                round_obj.completed = True
                round_obj.save()
                self.stdout.write(f"✅ Round {round_obj.round_number} marked as completed.")

            # --- 1d. Check for winner / no winner ---
            alive_entries = round_obj.game.entries.filter(alive=True)
            alive_count = alive_entries.count()
            loser_entries = round_obj.game.entries.filter(alive=False)
            entrants = loser_entries.count() + 1
            entry_fee = round_obj.game.entry_fee  # stored in LMSGame
            prize_pool = Decimal(entry_fee) * entrants

            if alive_count == 1:
                winner_entry = alive_entries.first()
                round_obj.game.winner = winner_entry.user
                round_obj.game.active = False
                round_obj.game.save()
                self.stdout.write(f"🏆 Game over! Winner: {winner_entry.user} ({round_obj.game})")
                
                # Update messages with the LMS Winner!
                create_message(
                    code="LM-WIN",
                    context={"User": winner_entry.user, "league": round_obj.game.get_league_display(), "prize": prize_pool},
                    group=entry.game.group,
                    receiver=winner_entry.user,
                    link=f"lms_game_detail:{game.id}"
                )

                # --- 💰 Settle Money in Bank app ---
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
                self.stdout.write(f"⚠️ Game over with no winner: {round_obj.game}")
    
                # Update messages with no LMS Winner - rollover!
                create_message(
                    code="LM-OOO",
                    context={"league": round_obj.game.league, "prize": prize_pool},
                    group=round_obj.game.group
                )

            # --- 1e. Create next round if current is completed and latest ---
            latest_round_num = LMSRound.objects.filter(game=round_obj.game).aggregate(Max('round_number'))['round_number__max']
            if round_obj.completed and round_obj.round_number == latest_round_num:
                next_round_num = round_obj.round_number + 1
                if not LMSRound.objects.filter(game=round_obj.game, round_number=next_round_num).exists():
                    created_round = self.create_next_round(round_obj)
                    if created_round:
                        self.stdout.write(f"✅ Created Round {created_round.round_number} for {round_obj.game}")
                    else:
                        self.stdout.write(f"⚠️ Not enough fixtures to create Round {next_round_num} for {round_obj.game}")

        # --- 2️⃣ Final check: active games missing a next round ---
        self.stdout.write("\n🔍 Checking active games for missing next rounds...")
        for game in LMSGame.objects.filter(active=True):
            latest_round = LMSRound.objects.filter(game=game).order_by("-round_number").first()
            if latest_round:
                if latest_round.completed:
                    next_round_num = latest_round.round_number + 1
                    if not LMSRound.objects.filter(game=game, round_number=next_round_num).exists():
                        created_round = self.create_next_round(latest_round)
                        if created_round:
                            self.stdout.write(f"✅ Created Round {created_round.round_number} for {game}")
                        else:
                            self.stdout.write(f"⚠️ No suitable fixtures found for next round of {game}")
                else:
                    self.stdout.write(f"⏳ Latest round {latest_round.round_number} of {game} not yet completed. Skipping.")
            else:
                self.stdout.write(f"❌ No rounds found for {game}")

        self.stdout.write("✅ LMS pick results update complete.")


    def create_next_round(self, previous_round):
        """Create the next LMS round with remaining players if fixtures are available."""
        game = previous_round.game
        today = now().date()

        for days_ahead in range(0, 30):
            current_day = today + timedelta(days=days_ahead)
            weekday = current_day.weekday()

            if weekday == 4:  # Friday → weekend block
                block_start = current_day
                block_end = block_start + timedelta(days=3)
            elif weekday == 1:  # Tuesday → midweek block
                block_start = current_day
                block_end = block_start + timedelta(days=2)
            else:
                continue

            fixtures = Fixture.objects.filter(
                league_short_name=game.league,
                date__range=(block_start, block_end)
            ).order_by("date")

            if fixtures.count() >= 7:
                next_round = LMSRound.objects.create(
                    game=game,
                    round_number=previous_round.round_number + 1,
                    start_date=fixtures.first().date,
                    end_date=fixtures.last().date,
                )
                next_round.fixtures.set(fixtures)

                # Create empty picks for remaining alive players
                #remaining_entries = game.entries.filter(alive=True)
                #for entry in remaining_entries:
                #    LMSPick.objects.create(
                #        entry=entry,
                #        round=next_round,
                #        fixture=fixtures.first(),  # placeholder, will be updated when player picks
                #        team_name="",
                #        result="PENDING"
                #    )

                return next_round

        return None
