from django.core.management.base import BaseCommand
from score_predict.models import Fixture, Prediction, GameEntry
from django.db import transaction

def calculate_points(prediction, fixture):
    if prediction.home_score == fixture.home_score and prediction.away_score == fixture.away_score:
        return 10
    elif ((fixture.home_score > fixture.away_score and prediction.home_score > prediction.away_score) or
          (fixture.home_score < fixture.away_score and prediction.home_score < prediction.away_score) or
          (fixture.home_score == fixture.away_score and prediction.home_score == prediction.away_score)):
        return 5
    return 0

def update_scores(stdout=None):
    fixtures = Fixture.objects.filter(status_code="finished")

    for fixture in fixtures:
        predictions = Prediction.objects.filter(fixture=fixture)
        for prediction in predictions:
            points = calculate_points(prediction, fixture)
            prediction.points_awarded = points
            prediction.save()

            entry = GameEntry.objects.get(game=prediction.game, player=prediction.player)
            entry.total_score += points
            entry.save()

        if stdout:
            stdout.write(f"Updated scores for Fixture {fixture.fixture_id}")

class Command(BaseCommand):
    help = "Update scores for predictions of finished fixtures."

    def handle(self, *args, **kwargs):
        update_scores(stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS("Scores updated!"))
