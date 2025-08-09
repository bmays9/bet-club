from django.core.management.base import BaseCommand
from score_predict.models import Fixture, Prediction, GameEntry, GameInstance
from django.contrib.auth.models import User
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
            prediction.score = points
            prediction.save()

        if stdout:
            stdout.write(f"Updated scores for Fixture {fixture.fixture_id}")

    # ✅ Recalculate total scores for all entries
    for entry in GameEntry.objects.all():
        total_points = Prediction.objects.filter(
            game_instance=entry.game,
            player=entry.player
        ).aggregate(total=Sum('score'))['total'] or 0

        entry.total_score = total_points
        entry.save()

        if stdout:
            stdout.write(f"Recalculated total score for {entry.player} in game {entry.game}")

    # ✅ Check for winners, but only if not already set
    for game in GameInstance.objects.filter(winner__isnull=True):
        game_fixtures = Fixture.objects.filter(gametemplate=game.template)
        if not game_fixtures.exists():
            continue  # no fixtures linked, skip

        # Only decide winner if ALL fixtures are finished
        if all(f.status_description == "finished" for f in game_fixtures):
            highest_score = GameEntry.objects.filter(game=game).aggregate(top=Sum('total_score'))['top']
            winners = GameEntry.objects.filter(game=game, total_score=highest_score)

        if winners.exists():
            winner_users = [w.player for w in winners]  # list of User instances
            # If multiple winners, pick the first one (or handle tie logic differently)
            winner_user = winner_users[0]  

            game.winner = winner_user
            game.save()

            winner_names = ", ".join(user.username for user in winner_users)
            if stdout:
                stdout.write(f"Winner for {game} set to: {winner_names}")


def check_for_winners(stdout=None):
    # Only games where all fixtures are finished
    for game in GameInstance.objects.all():
        fixtures = Fixture.objects.filter(game_instance=game)
        if fixtures.exists() and all(f.status_description == "finished" for f in fixtures):
            entries = GameEntry.objects.filter(game=game)
            if entries.exists():
                max_score = entries.aggregate(max_score=Sum('total_score'))['max_score']
                top_entries = entries.filter(total_score=max_score)
                winners = ", ".join(e.player.username for e in top_entries)

                game.winner = winners
                game.save()

                if stdout:
                    stdout.write(f"Updated winner for {game}: {winners}")


class Command(BaseCommand):
    help = "Update scores for predictions of finished fixtures."

    def handle(self, *args, **kwargs):
        update_scores(stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS("Scores updated!"))
