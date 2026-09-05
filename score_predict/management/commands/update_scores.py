from bank.services import apply_batch
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
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


def _settle_game(game, stdout=None):
    """
    Settle a completed game. Must be called inside select_for_update.
    Checks all fixtures finished and scored before paying out.
    """
    template_fixtures = Fixture.objects.filter(gametemplate=game.template)
    total_fixtures = template_fixtures.count()

    if total_fixtures == 0:
        return

    # Fixtures not yet in a final state
    unfinished = template_fixtures.exclude(status_code__in=[100, 90, 60]).count()

    if stdout:
        stdout.write(f"{game}: {unfinished}/{total_fixtures} fixtures unfinished")

    if unfinished > 0:
        return

    # All finished fixtures must have scores recorded
    missing_scores = template_fixtures.filter(
        status_code=100,
        home_score__isnull=True,
    ).count()

    if missing_scores > 0:
        if stdout:
            stdout.write(f"  {game}: {missing_scores} finished fixtures missing scores, waiting")
        return

    # Find winner
    highest_total = GameEntry.objects.filter(game=game).aggregate(
        top=Max("total_score")
    )["top"]

    if highest_total is None:
        return

    top_entries = GameEntry.objects.filter(game=game, total_score=highest_total)

    if top_entries.count() > 1:
        highest_alt = top_entries.aggregate(top_alt=Max("alt_score"))["top_alt"]
        winners = top_entries.filter(alt_score=highest_alt)
    else:
        winners = top_entries

    if not winners.exists():
        return

    winner_users = [w.player for w in winners]

    # Double-check no winners set yet (inside the lock)
    if game.winners.exists():
        return

    game.winners.set(winner_users)
    game.save()

    winner_names = ", ".join(u.username for u in winner_users)
    if stdout:
        stdout.write(f"Winner(s) for {game}: {winner_names} with {highest_total} pts")

    entrants = [e.player for e in GameEntry.objects.filter(game=game)]
    entry_fee = game.entry_fee
    prize_pool = Decimal(str(entry_fee)) * len(entrants)

    try:
        for w in winners:
            create_message(
                code="SP-WIN",
                context={"User": w.player, "score": w.total_score, "prize": prize_pool},
                receiver=w.player,
                actor=w.player,
                group=game.group,
                link=f"game_detail:{game.id}",
            )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"SP-WIN message failed: {e}")

    apply_batch(
        group=game.group,
        entrants=entrants,
        winners=winner_users,
        entry_fee=Decimal(str(entry_fee)),
        prize_pool=prize_pool,
        description=f"Score Predict - {game.group.name} (#{game.id})",
    )

    if stdout:
        stdout.write(f"Bank settled for {game}. Prize pool: {prize_pool}")


def check_for_winners(stdout=None):
    for game in GameInstance.objects.filter(
        winners__isnull=True,
        gameentry__isnull=False,
    ).distinct():
        # Use select_for_update to prevent duplicate settlement
        # if two updater processes run simultaneously
        try:
            with transaction.atomic():
                locked_game = (
                    GameInstance.objects
                    .select_for_update(nowait=True)
                    .get(id=game.id)
                )
                if locked_game.winners.exists():
                    continue
                _settle_game(locked_game, stdout)
        except Exception as e:
            # nowait raises if another process holds the lock -- skip safely
            if stdout:
                stdout.write(f"  {game}: skipped (locked or error: {e})")


def update_scores(stdout=None):
    # Step 1: Score finished fixture predictions
    active_games = (
        GameInstance.objects
        .filter(winners__isnull=True)
        .filter(gameentry__isnull=False)
        .distinct()
    )

    finished_fixtures = Fixture.objects.filter(
        gametemplate__in=active_games.values_list("template", flat=True),
        status_code=100,
        home_score__isnull=False,
        away_score__isnull=False,
    )

    if stdout:
        stdout.write(f"Found {finished_fixtures.count()} finished fixtures for active games.")

    for fixture in finished_fixtures:
        for prediction in Prediction.objects.filter(fixture=fixture):
            prediction.score = calculate_points(prediction, fixture)
            prediction.alternate_score = calculate_alt_points(prediction, fixture)
            prediction.save(update_fields=["score", "alternate_score"])

    # Step 2: Update totals -- correct path is fixture__gametemplate not game_instance
    for game in active_games:
        for entry in GameEntry.objects.filter(game=game):
            totals = (
                Prediction.objects
                .filter(
                    fixture__gametemplate=game.template,
                    player=entry.player,
                )
                .aggregate(
                    total=Sum("score"),
                    alt_total=Sum("alternate_score"),
                )
            )
            entry.total_score = totals["total"] or 0
            entry.alt_score = totals["alt_total"] or 0
            entry.save(update_fields=["total_score", "alt_score"])

            if stdout:
                stdout.write(
                    f"{entry.player.username} in {game}: "
                    f"{entry.total_score} pts (tie: {entry.alt_score})"
                )

    # Step 3: Check winners ONCE after all totals updated
    check_for_winners(stdout)


class Command(BaseCommand):
    help = "Update scores for predictions of finished fixtures."

    def handle(self, *args, **kwargs):
        update_scores(stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS("Scores updated!"))