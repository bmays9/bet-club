from bank.services import apply_batch
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Sum
from django.db.models import Max
from player_messages.utils import create_message
from score_predict.models import Fixture, Prediction, GameEntry, GameInstance

def calculate_points(prediction, fixture):
    if prediction.predicted_home_score == fixture.home_score and prediction.predicted_away_score == fixture.away_score:
        return 10
    elif ((fixture.home_score > fixture.away_score and prediction.predicted_home_score > prediction.predicted_away_score) or
          (fixture.home_score < fixture.away_score and prediction.predicted_home_score < prediction.predicted_away_score) or
          (fixture.home_score == fixture.away_score and prediction.predicted_home_score == prediction.predicted_away_score)):
        return 5
    return 0

def calculate_alt_points(prediction, fixture):
    if prediction.predicted_home_score == fixture.home_score and prediction.predicted_away_score == fixture.away_score:
        return 10
    else:
        total_points = 0
        result_points = 0
        if ((fixture.home_score > fixture.away_score and prediction.predicted_home_score > prediction.predicted_away_score) or
            (fixture.home_score < fixture.away_score and prediction.predicted_home_score < prediction.predicted_away_score) or
            (fixture.home_score == fixture.away_score and prediction.predicted_home_score == prediction.predicted_away_score)):
            result_points = 3

        
        home_goals_points = max(0, 3 - abs(fixture.home_score - prediction.predicted_home_score))
        away_goals_points = max(0, 3 - abs(fixture.away_score - prediction.predicted_away_score))

        total_points = result_points + home_goals_points + away_goals_points

        return total_points

    return 0

def update_scores(stdout=None):
    # Get active games with no winner
    active_games = (
        GameInstance.objects
        .filter(winners__isnull=True)
        .filter(gameentry__isnull=False)
        .distinct()
    )

    # Get only finished fixtures linked to these active games' templates
    fixtures = Fixture.objects.filter(
        gametemplate__in=active_games.values_list("template", flat=True),
        status_description="finished"
    )

    if stdout:
        stdout.write(f"Found {fixtures.count()} finished fixtures for active games.")

    # Update prediction scores for relevant fixtures
    for fixture in fixtures:

        predictions = Prediction.objects.filter(fixture=fixture)
        for prediction in predictions:
            points = calculate_points(prediction, fixture)
            alt_points = calculate_alt_points(prediction, fixture)
            prediction.score = points
            prediction.alternate_score = alt_points
            prediction.save()

        # if stdout:
        #    stdout.write(f"Updated scores for Fixture {fixture.fixture_id}")

    # Update total_score and alt_score for each player in each active game
    for game in active_games:
        for entry in GameEntry.objects.filter(game=game):
            totals = Prediction.objects.filter(
                game_instance=game,
                player=entry.player
            ).aggregate(
                total=Sum("score"),
                alt_total=Sum("alternate_score")
            )
            entry.total_score = totals["total"] or 0
            entry.alt_score = totals["alt_total"] or 0
            entry.save()

            if stdout:
                stdout.write(
                    f"Updated totals for {entry.player.username} in {game}: "
                    f"total_score={entry.total_score}, alt_score={entry.alt_score}"
                )

    # Check for winners at the end
    check_for_winners(stdout)


def check_for_winners(stdout=None):
    print("Checking for Winners..")
    for game in GameInstance.objects.filter(winners__isnull=True):
        print("Checking for a winner in game:", game)
        game_fixtures = Fixture.objects.filter(gametemplate=game.template)
        if not game_fixtures.exists():
            continue  # no fixtures linked, skip

        # Only decide winner if ALL fixtures are finished
        if all(f.status_code in [100, 90, 60] for f in game_fixtures):
            # Step 1: highest total_score
            highest_total = GameEntry.objects.filter(game=game).aggregate(
                top_total=Max('total_score')
            )['top_total']

            top_total_entries = GameEntry.objects.filter(
            game=game,
            total_score=highest_total
            )   

            # Step 2: if more than one, check alt_score
            if top_total_entries.count() > 1:
                highest_alt = top_total_entries.aggregate(
                    top_alt=Max('alt_score')
                )['top_alt']

                winners = top_total_entries.filter(alt_score=highest_alt)
            else:
                winners = top_total_entries

            # Step 3: assign winner(s)
            if winners.exists():
                winner_users = [w.player for w in winners]  # list of User instances
                # winner_user = winner_users[0]  # first one if you still want a single "official" winner

                game.winners.set(winner_users)
                game.save()

                winner_names = ", ".join(user.username for user in winner_users)
                if stdout:
                    stdout.write(f"Winner for {game} set to: {winner_names}")


                # --- 💰 Prepare data for message and settlement ---
                entrants = [e.player for e in GameEntry.objects.filter(game=game)]
                entry_fee = game.entry_fee  # stored on GameInstance
                prize_pool = Decimal(entry_fee) * len(entrants)

                # Update messages with the winners
                for w in winners: 
                    # Create messaging for each SP Winner - code SP-WIN
                    create_message(
                        code="SP-WIN",
                        context={"User": w.player, "score": w.total_score, "prize": prize_pool},
                        receiver=w.player,
                        actor=w.player,
                        group=game.group,
                        link=f"game_detail:{game.id}"
                    )


                # --- 💰 Settle Money in Bank app ---

                apply_batch(
                    group=game.group,             # 👈 your UserGroup
                    entrants=entrants,            # all who paid in
                    winners=winner_users,         # one or many winners
                    entry_fee=Decimal(entry_fee),
                    prize_pool=prize_pool,
                    description=f"Settlement for {game.group.name} Score Predict (id #{game.id})"
                )



class Command(BaseCommand):
    help = "Update scores for predictions of finished fixtures."

    def handle(self, *args, **kwargs):
        update_scores(stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS("Scores updated!"))
