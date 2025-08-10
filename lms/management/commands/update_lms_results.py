from django.core.management.base import BaseCommand
from django.utils.timezone import now
from datetime import timedelta
from lms.models import LMSPick, LMSRound, LMSEntry
from score_predict.models import Fixture
from django.db.models import Max


class Command(BaseCommand):
    help = "Update LMS pick results and create the next round if needed"

    def handle(self, *args, **options):
        self.stdout.write("Updating LMS pick results...")

        # Consider only rounds not yet completed
        incomplete_rounds = LMSRound.objects.filter(completed=False)
        self.stdout.write(f"Processing incomplete rounds {incomplete_rounds}...")

        for round_obj in incomplete_rounds:
            self.stdout.write(f"Processing {round_obj}...")

            # 1️⃣ Update all picks that are still pending
            picks_pending = round_obj.picks.filter(result="PENDING")
            for pick in picks_pending:
                fixture = pick.fixture
                print(f"\n[DEBUG] Processing Pick ID: {pick.id}")
                print(f"  Picked Team: {pick.team_name}")
                print(f"  Fixture: {fixture.home_team} vs {fixture.away_team}")
                print(f"  Scores: {fixture.home_score}-{fixture.away_score}")
                print(f"  Status Code: {fixture.status_code}")

                if fixture.status_code == 100:  # Fixture finished
                    if fixture.home_score > fixture.away_score:
                        result = "WIN" if fixture.home_team == pick.team_name else "LOSE"
                    elif fixture.away_score > fixture.home_score:
                        result = "WIN" if fixture.away_team == pick.team_name else "LOSE"
                    else:
                        result = "DRAW"
                    print(f"  Computed Result: {result}")
                    pick.result = result
                    pick.save()

            # 2️⃣ Eliminate losing/drawing entries and those who didn't pick
            entries = round_obj.game.entries.all()
            for entry in entries:
                picks_for_entry = round_obj.picks.filter(entry=entry)
                if not picks_for_entry.exists():
                    # No picks made at all → eliminated round 0
                    if entry.alive:
                        entry.alive = False
                        entry.eliminated_round = 0
                        entry.save()
                    continue

                # If any pick is LOSE or DRAW → eliminate this entry
                if picks_for_entry.filter(result__in=["LOSE", "DRAW"]).exists():
                    if entry.alive:
                        entry.alive = False
                        entry.eliminated_round = round_obj.round_number
                        entry.save()

            # 3️⃣ If no picks pending, mark round completed
            if not round_obj.picks.filter(result="PENDING").exists():
                round_obj.completed = True
                round_obj.save()
                self.stdout.write(f"Round {round_obj.round_number} marked as completed.")

            # 4️⃣ Create next round if this one is the latest and completed
            latest_round_num = LMSRound.objects.filter(game=round_obj.game).aggregate(Max('round_number'))['round_number__max']

            if round_obj.round_number == latest_round_num and round_obj.completed:
                next_round_num = round_obj.round_number + 1

                # Ensure no existing next round
                if not LMSRound.objects.filter(game=round_obj.game, round_number=next_round_num).exists():
                    self.stdout.write(f"Attempting to create Round {next_round_num} for {round_obj.game}")
                    created_round = self.create_next_round(round_obj)
                    if created_round:
                        self.stdout.write(f"✅ Created Round {created_round.round_number} for {round_obj.game}")
                    else:
                        self.stdout.write(f"⚠️ Not enough fixtures available yet for Round {next_round_num}")

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
