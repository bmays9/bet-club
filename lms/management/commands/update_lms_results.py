from bank.services import apply_batch
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db.models import Max, Min
from django.utils import timezone
from datetime import timedelta, datetime, time
from lms.models import LMSPick, LMSRound, LMSEntry, LMSGame
from lms.services.pick_resolution import (
    assign_missing_picks, handle_unresolved_postponed_picks
)
from lms.utils import get_auto_pick_teams_for_round
from player_messages.utils import create_message
from score_predict.models import Fixture

FINAL_STATUS_CODES = (100,)
CANCELLED_CODE = 90
POSTPONED_CODE = 60
MIN_FIXTURES_PER_ROUND = 7


class Command(BaseCommand):
    help = "Update LMS pick results and create the next round if needed"

    def handle(self, *args, **options):
        self.stdout.write("Updating LMS pick results...")

        # 1. Find earliest incomplete round per active game
        earliest_rounds = (
            LMSRound.objects
            .filter(game__active=True, completed=False)
            .values("game")
            .annotate(earliest_round=Min("round_number"))
        )

        rounds = LMSRound.objects.filter(
            game__active=True,
            completed=False,
            round_number__in=[r["earliest_round"] for r in earliest_rounds],
        ).select_related("game").order_by("game_id", "round_number")

        for round_obj in rounds:
            game = round_obj.game
            now_ts = timezone.now()

            self.stdout.write(f"\nProcessing {round_obj}")

            if round_obj.start_date and now_ts < round_obj.start_date:
                self.stdout.write(f"  Skipping (starts {round_obj.start_date})")
                continue

            first_fixture = round_obj.fixtures.order_by("date").first()

            if game.deadline_mode == "first_game":
                deadline_passed = first_fixture and now_ts >= first_fixture.date
            else:
                deadline_passed = now_ts >= round_obj.end_date

            # 2. Assign missing picks after deadline
            if deadline_passed:
                assign_missing_picks(game, round_obj)

            # 3. Handle postponed fixtures after round ends
            if now_ts >= round_obj.end_date:
                handle_unresolved_postponed_picks(game, round_obj)

            # 4. Compute results for pending picks
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

                    pick.result = result
                    pick.save(update_fields=["result"])
                    self.stdout.write(f"  {pick}: {result}")

            # 5. Eliminate entries that lost or drew
            for entry in game.entries.filter(alive=True):
                picks = round_obj.picks.filter(entry=entry)

                if not picks.exists():
                    if deadline_passed and game.no_pick_rule == "elimination":
                        entry.alive = False
                        entry.eliminated_round = (
                            0 if round_obj.round_number == 1 else round_obj.round_number
                        )
                        entry.save(update_fields=["alive", "eliminated_round"])
                        create_message(
                            code="LM-UKO",
                            context={"User": entry.user, "league": game.get_league_display()},
                            group=game.group,
                            receiver=entry.user,
                            actor=entry.user,
                            link=f"lms_game_detail:{game.id}",
                        )
                    continue

                if picks.filter(result__in=["LOSE", "DRAW"]).exists():
                    entry.alive = False
                    entry.eliminated_round = round_obj.round_number
                    entry.save(update_fields=["alive", "eliminated_round"])
                    create_message(
                        code="LM-UKO",
                        context={"User": entry.user, "league": game.get_league_display()},
                        group=game.group,
                        receiver=entry.user,
                        actor=entry.user,
                        link=f"lms_game_detail:{game.id}",
                    )

            # 6. Complete round if no pending picks remain
            all_resolved = not round_obj.picks.filter(result="PENDING").exists()
            if all_resolved:
                round_obj.completed = True
                round_obj.save(update_fields=["completed"])
                self.stdout.write(f"  Round {round_obj.round_number} completed.")

            # 7. Check for winner/no winner
            alive = game.entries.filter(alive=True)
            alive_count = alive.count()
            entrant_users = [e.user for e in game.entries.all()]
            prize_pool = Decimal(str(game.entry_fee)) * game.entries.count()

            if alive_count == 1:
                winner_entry = alive.first()
                game.winner = winner_entry.user
                game.active = False
                game.save(update_fields=["winner", "active"])
                self.stdout.write(f"  Winner: {winner_entry.user}")

                create_message(
                    code="LM-WIN",
                    context={
                        "User": winner_entry.user,
                        "league": game.get_league_display(),
                        "prize": prize_pool,
                    },
                    group=game.group,
                    actor=winner_entry.user,
                    receiver=winner_entry.user,
                    link=f"lms_game_detail:{game.id}",
                )
                apply_batch(
                    group=game.group,
                    entrants=entrant_users,
                    winners=[winner_entry.user],
                    entry_fee=Decimal(str(game.entry_fee)),
                    prize_pool=prize_pool,
                    description=f"LMS Settlement - {game.get_league_display()} (#{game.id})",
                )

            elif alive_count == 0:
                game.active = False
                game.save(update_fields=["active"])
                self.stdout.write(f"  No winner for {game}")
                create_message(
                    code="LM-OOO",
                    context={"league": game.get_league_display(), "prize": prize_pool},
                    group=game.group,
                    link=f"lms_game_detail:{game.id}",
                )

            # 8. Create next round if this one just completed
            if round_obj.completed:
                latest_round_num = LMSRound.objects.filter(game=game).aggregate(
                    Max("round_number")
                )["round_number__max"]

                if round_obj.round_number == latest_round_num:
                    created = self.create_next_round(game=game, previous_round=round_obj)
                    if created:
                        self.stdout.write(f"  Created Round {created.round_number}")
                    else:
                        self.stdout.write(f"  No fixtures available for next round")

        # Final pass: ensure active games have a next round ready
        self.stdout.write("\nChecking active games for missing next rounds...")
        for game in LMSGame.objects.filter(active=True):
            rounds = LMSRound.objects.filter(game=game).order_by("-round_number")

            if not rounds.exists():
                created = self.create_next_round(game=game, previous_round=None)
                if created:
                    self.stdout.write(f"Created Round 1 for {game}")
                continue

            latest = rounds.first()
            if not latest.completed:
                continue

            next_num = latest.round_number + 1
            if LMSRound.objects.filter(game=game, round_number=next_num).exists():
                continue

            created = self.create_next_round(game=game, previous_round=latest)
            if created:
                self.stdout.write(f"Created Round {created.round_number} for {game}")

        self.stdout.write("LMS update complete.")

    def create_next_round(self, *, game, previous_round=None):
        """
        Find the next valid fixture block for the game's league.

        Improved logic:
        - Scans forward from after the previous round ended
        - Groups fixtures by calendar date
        - Finds the next cluster of dates where each TEAM appears only once
        - Accepts any block of dates with >= MIN_FIXTURES_PER_ROUND unique-team fixtures
        - Works around holidays (Christmas etc.) by not enforcing Fri-Mon/Tue-Thu windows
        """
        search_after = max(
            previous_round.end_date if previous_round else timezone.now(),
            timezone.now(),
        )
        lookahead_limit = timezone.now() + timedelta(days=60)

        self.stdout.write(f"Searching for next round for {game} after {search_after.date()}")

        # Get all upcoming fixtures for this league
        upcoming = (
            Fixture.objects
            .filter(
                league_short_name=game.league,
                date__gt=search_after,
                date__lt=timezone.make_aware(
                    datetime.combine(lookahead_limit.date(), time.max)
                ),
            )
            .exclude(status_code__in=[CANCELLED_CODE, POSTPONED_CODE])
            .order_by("date")
        )

        if not upcoming.exists():
            self.stdout.write(f"  No upcoming fixtures for {game.league}")
            return None

        # Group fixtures by date
        from collections import defaultdict
        by_date = defaultdict(list)
        for fx in upcoming:
            by_date[fx.date.date()].append(fx)

        sorted_dates = sorted(by_date.keys())

        # Find natural fixture clusters:
        # A cluster is a group of consecutive dates where no more than 1 day
        # gap exists between them. This handles Fri-Mon AND holiday schedules.
        clusters = []
        current_cluster_dates = []

        for i, d in enumerate(sorted_dates):
            if not current_cluster_dates:
                current_cluster_dates = [d]
            else:
                gap = (d - current_cluster_dates[-1]).days
                if gap <= 2:  # allow up to 2-day gap within a cluster
                    current_cluster_dates.append(d)
                else:
                    clusters.append(current_cluster_dates)
                    current_cluster_dates = [d]

        if current_cluster_dates:
            clusters.append(current_cluster_dates)

        # Find first cluster with enough unique-team fixtures
        for cluster_dates in clusters:
            cluster_fixtures = []
            seen_teams = set()
            valid = True

            for d in cluster_dates:
                for fx in by_date[d]:
                    # Each team can only appear once in a round
                    if fx.home_team in seen_teams or fx.away_team in seen_teams:
                        continue  # skip duplicate team fixture
                    seen_teams.add(fx.home_team)
                    seen_teams.add(fx.away_team)
                    cluster_fixtures.append(fx)

            if len(cluster_fixtures) < MIN_FIXTURES_PER_ROUND:
                self.stdout.write(
                    f"  Cluster {cluster_dates[0]} - {cluster_dates[-1]}: "
                    f"{len(cluster_fixtures)} usable fixtures (need {MIN_FIXTURES_PER_ROUND}) -- skipping"
                )
                continue

            # Valid cluster found
            self.stdout.write(
                f"  Using cluster {cluster_dates[0]} - {cluster_dates[-1]} "
                f"({len(cluster_fixtures)} fixtures)"
            )

            # Sort fixtures by date
            cluster_fixtures.sort(key=lambda f: f.date)

            round_number = (previous_round.round_number + 1) if previous_round else 1

            from django.utils.timezone import make_aware
            block_start_dt = make_aware(
                datetime.combine(cluster_dates[0], time.min)
            )
            block_end_dt = make_aware(
                datetime.combine(cluster_dates[-1], time.max)
            )

            new_round = LMSRound.objects.create(
                game=game,
                round_number=round_number,
                start_date=cluster_fixtures[0].date,
                end_date=cluster_fixtures[-1].date + timedelta(hours=4),
            )
            new_round.fixtures.set(cluster_fixtures)

            # Auto-picks
            auto_picks = get_auto_pick_teams_for_round(
                game, new_round, cluster_fixtures, count=4
            )
            if auto_picks:
                new_round.auto_pick_team1 = auto_picks[0]
                new_round.auto_pick_team2 = auto_picks[1] if len(auto_picks) > 1 else None
                new_round.auto_pick_team3 = auto_picks[2] if len(auto_picks) > 2 else None
                new_round.auto_pick_team = auto_picks[3] if len(auto_picks) > 3 else None
                new_round.save(update_fields=[
                    "auto_pick_team1", "auto_pick_team2",
                    "auto_pick_team3", "auto_pick_team",
                ])

            return new_round

        self.stdout.write(f"  No valid cluster found within 60 days for {game}")
        return None
