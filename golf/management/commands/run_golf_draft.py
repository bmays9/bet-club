# golf/management/commands/run_golf_draft.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from golf.models import GolfGame
from golf.services.draft import maybe_start_draft, process_expired_slots, draft_is_complete
from golf.services.scoring import update_pick_scores, check_cut, settle_game


class Command(BaseCommand):
    help = "Process golf draft slots: start drafts, auto-assign expired picks, settle finished games."

    def handle(self, *args, **options):

        # -- 1. Start any drafts whose window has opened ---------------
        open_games = GolfGame.objects.filter(
            status=GolfGame.Status.OPEN
        ).select_related("event", "group")

        for game in open_games:
            if game.game_entries.count() == 0:
                continue
            started = maybe_start_draft(game)
            if started:
                self.stdout.write(
                    self.style.SUCCESS(f"Draft started: {game}")
                )

        # -- 2. Process active drafts ----------------------------------
        drafting_games = GolfGame.objects.filter(
            status=GolfGame.Status.DRAFTING
        ).select_related("event", "group")

        for game in drafting_games:
            process_expired_slots(game)
            self.stdout.write(f"Processed expired slots for: {game}")

            # Advance to ACTIVE once all slots filled
            if draft_is_complete(game):
                game.status = GolfGame.Status.ACTIVE
                game.save(update_fields=["status"])
                self.stdout.write(
                    self.style.SUCCESS(f"Draft complete -- game now ACTIVE: {game}")
                )

        # -- 3. Update scores for active games -------------------------
        active_games = GolfGame.objects.filter(
            status=GolfGame.Status.ACTIVE
        ).select_related("event", "group")

        for game in active_games:
            update_pick_scores(game)
            check_cut(game)
            self.stdout.write(f"Scores updated: {game}")

            # Settle if tournament is finished
            event_status = game.event.status.lower()
            if event_status in ("finished", "complete", "official"):
                settle_game(game)
                self.stdout.write(
                    self.style.SUCCESS(f"Game settled: {game}")
                )

        self.stdout.write(self.style.SUCCESS("Golf draft processing complete."))
