from django.core.management.base import BaseCommand
from score_predict.models import Fixture, Prediction, GameEntry
from django.db import transaction
from django.db.models import Sum

def calculate_points(prediction, fixture):
    if prediction.predicted_home_score == fixture.home_score and prediction.predicted_away_score == fixture.away_score:
        return 10
    elif ((fixture.home_score > fixture.away_score and prediction.predicted_home_score > prediction.predicted_away_score) or
          (fixture.home_score < fixture.away_score and prediction.predicted_home_score < prediction.predicted_away_score) or
          (fixture.home_score == fixture.away_score and prediction.predicted_home_score == prediction.predicted_away_score)):
        return 5
    return 0

def update_scores(stdout=None):
    fixtures = Fixture.objects.filter(status_description="finished")
    if stdout:
        stdout.write(f"Found {fixtures.count()} finished fixtures.")

    for fixture in fixtures:
        if stdout:
            stdout.write(
                f"Processing Fixture {fixture.fixture_id}: "
                f"{fixture.home_team} {fixture.home_score} - {fixture.away_score} {fixture.away_team}"
            )

        predictions = Prediction.objects.filter(fixture=fixture)
        for prediction in predictions:
            points = calculate_points(prediction, fixture)
            prediction.score = points
            prediction.save()
        
        if stdout:
            stdout.write(f"Updated scores for Fixture {fixture.fixture_id}")

            # ✅ Now update total scores for all game entries
    for entry in GameEntry.objects.all():
        total_points = Prediction.objects.filter(
            game_instance=entry.game,  
            player=entry.player
        ).aggregate(total=Sum('score'))['total'] or 0

        entry.total_score = total_points
        entry.save()

        if stdout:
            stdout.write(f"Recalculated total score for {entry.player} in game {entry.game}")


class Command(BaseCommand):
    help = "Update scores for predictions of finished fixtures."

    def handle(self, *args, **kwargs):
        update_scores(stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS("Scores updated!"))
