from bank.services import apply_batch
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db.models import Sum, Max
from player_messages.utils import create_message
from score_predict.models import Fixture, Prediction, GameEntry, GameInstance


def calculate_points(prediction, fixture):
    if (prediction.predicted_home_score == fixture.home_score
            and prediction.predicted_away_score == fixture.away_score):
        return 10
    elif (
        (fixture.home_score > fixture.away_score and prediction.predicted_home_score > prediction.predicted_away_score)
        or (fixture.home_score < fixture.away_score and prediction.predicted_home_score < prediction.predicted_away_score)
        or (fixture.home_score == fixture.away_score and prediction.predicted_home_score == prediction.predicted_away_score)
    ):
        return 5
    return 0


def calculate_alt_points(prediction, fixture):
    if (prediction.predicted_home_score == fixture.home_score
            and prediction.predicted_away_score == fixture.away_score):
        return 10

    result_points = 0
    if (
        (fixture.home_score > fixture.away_score and prediction.predicted_home_score > prediction.predicted_away_score)
        or (fixture.home_score < fixture.away_score and prediction.predicted_home_score < prediction.predicted_away_score)
        or (fixture.home_score == fixture.away_score and prediction.predicted_home_score == prediction.predicted_away_score)
    ):
        result_points = 3

    home_goals_points = max(0, 3 - abs(fixture.home_score - prediction.predicted_home_score))
    away_goals_points = max(0, 3 - abs(fixture.away_score - prediction.predicted_away_score))
    return result_points + home_goals_points + away_goals_points


def update_scores(stdout=None):
    # Active games with entries but no winner yet
    active_games = (
        GameInstance.objects
        .filter(winners__isnull=True)
        .filter(gameentry__isnull=False)
        .distinct()
    )

    # Finished fixtures for these games' templates
    # status_description stores the API "type" field: "finished"
    fixtures = Fixture.objects.filter(
        gametemplate__in=active_games.values_list("template", flat=True),
    ).filter(
        status_code=100  # 100 = finished in SofaScore
    )

    if stdout:
        stdout.write(f"Found {fixtures.count()} finished fixtures for active games.")

    for fixture in fixtures:
        predictions = Prediction.objects.filter(fixture=fixture)
        for prediction in predictions:
            points = calculate_points(prediction, fixture)
            alt_points = calculate_alt_points(prediction, fixture)
            # Always update to ensure scores are current
            prediction.score = points
            prediction.alternate_score = alt_points
            prediction.save(update_fields=["score", "alternate_score"])

    # Update totals for each player in each active game
    # Also recalculate for recently finished games to keep history accurate
    games_to_score = GameInstance.objects.filter(
        gameentry__isnull=False
    ).distinct()
    for game in games_to_score:
        for entry in GameEntry.objects.filter(game=game):
            totals = Prediction.objects.filter(
                game_instance=game,
                player=entry.player,
            ).aggregate(
                total=Sum("score"),
                alt_total=Sum("alternate_score"),
            )
            entry.total_score = totals["total"] or 0
            entry.alt_score = totals["alt_total"] or 0
            entry.save(update_fields=["total_score", "alt_score"])

        check_for_winners(stdout)


def check_for_winners(stdout=None):
    for game in GameInstance.objects.filter(winners__isnull=True).filter(gameentry__isnull=False).distinct():
        # Guard: re-check winners haven't been set since query ran (prevent double settlement)
        game.refresh_from_db()
        if game.winners.exists():
            if stdout:
                stdout.write(f"  {game}: already has winners, skipping")
            continue

        # FIX: was using fixture__game_instance which doesn't exist.
        # Correct path: fixtures linked to this game's template,
        # excluding those that are finished/abandoned/postponed.
        template_fixtures = Fixture.objects.filter(gametemplate=game.template)
        total_fixtures = template_fixtures.count()

        if total_fixtures == 0:
            continue

        # Any fixture not yet in a final state
        unfinished = template_fixtures.exclude(
            status_code__in=[100, 90, 60]
        ).count()

        if stdout:
            stdout.write(f"{game}: {unfinished}/{total_fixtures} fixtures unfinished")

        if unfinished > 0:
            continue

        # All fixtures done -- find the winner
        highest_total = GameEntry.objects.filter(game=game).aggregate(
            top=Max("total_score")
        )["top"]

        if highest_total is None:
            continue

        top_entries = GameEntry.objects.filter(game=game, total_score=highest_total)

        if top_entries.count() > 1:
            highest_alt = top_entries.aggregate(top_alt=Max("alt_score"))["top_alt"]
            winners = top_entries.filter(alt_score=highest_alt)
        else:
            winners = top_entries

        if not winners.exists():
            continue

        winner_users = [w.player for w in winners]
        game.winners.set(winner_users)
        game.save()

        winner_names = ", ".join(u.username for u in winner_users)
        if stdout:
            stdout.write(f"Winner(s) for {game}: {winner_names}")

        entrants = [e.player for e in GameEntry.objects.filter(game=game)]
        entry_fee = game.entry_fee
        prize_pool = Decimal(str(entry_fee)) * len(entrants)

        for w in winners:
            create_message(
                code="SP-WIN",
                context={"User": w.player, "score": w.total_score, "prize": prize_pool},
                receiver=w.player,
                actor=w.player,
                group=game.group,
                link=f"game_detail:{game.id}",
            )

        apply_batch(
            group=game.group,
            entrants=entrants,
            winners=winner_users,
            entry_fee=Decimal(str(entry_fee)),
            prize_pool=prize_pool,
            description=f"Score Predict settlement - {game.group.name} (#{game.id})",
        )

        if stdout:
            stdout.write(f"Bank settled for {game}. Prize pool: {prize_pool}")


class Command(BaseCommand):
    help = "Update scores for predictions of finished fixtures."

    def handle(self, *args, **kwargs):
        update_scores(stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS("Scores updated!"))