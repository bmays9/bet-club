from django.core.management.base import BaseCommand
from score_predict.models import Fixture, Prediction, GameEntry, GameInstance
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Sum
from django.db.models import Max

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
    fixtures = Fixture.objects.filter(status_description="finished")
    if stdout:
        stdout.write(f"Found {fixtures.count()} finished fixtures.")

    # ✅ Update individual fixture prediction scores
    for fixture in fixtures:
        if stdout:
            stdout.write(
                f"Processing Fixture {fixture.fixture_id}: "
                f"{fixture.home_team} {fixture.home_score} - {fixture.away_score} {fixture.away_team}"
            )

        predictions = Prediction.objects.filter(fixture=fixture)
        for prediction in predictions:
            points = calculate_points(prediction, fixture)
            alt_points = calculate_alt_points(prediction, fixture)
            prediction.score = points
            prediction.alternate_score = alt_points
            prediction.save()

        if stdout:
            stdout.write(f"Updated scores for Fixture {fixture.fixture_id}")

    check_for_winners()


def check_for_winners(stdout=None):
    for game in GameInstance.objects.filter(winner__isnull=True):
        game_fixtures = Fixture.objects.filter(gametemplate=game.template)
        if not game_fixtures.exists():
            continue  # no fixtures linked, skip

        # Only decide winner if ALL fixtures are finished
        if all(f.status_code == 100 for f in game_fixtures):
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
                winner_user = winner_users[0]  # first one if you still want a single "official" winner

                game.winner = winner_user
                game.save()

                winner_names = ", ".join(user.username for user in winner_users)
                if stdout:
                    stdout.write(f"Winner for {game} set to: {winner_names}")


class Command(BaseCommand):
    help = "Update scores for predictions of finished fixtures."

    def handle(self, *args, **kwargs):
        update_scores(stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS("Scores updated!"))
