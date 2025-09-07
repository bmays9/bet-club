import decimal
from django.core.management.base import BaseCommand
from django.db.models import Sum
from season.models import (
    StandingsBatch, StandingsRow,
    PlayerPick, PlayerScoreSnapshot,
    PickType, Handicap,
)

class Command(BaseCommand):
    help = "Update PlayerScoreSnapshot for the latest standings batch"

    def handle(self, *args, **options):
        batch = StandingsBatch.objects.order_by("-taken_at").first()
        if not batch:
            self.stdout.write(self.style.ERROR("No standings batch found"))
            return

        self.stdout.write(f"Scoring batch {batch.taken_at:%Y-%m-%d %H:%M}")

        # Clear old scores for this batch
        PlayerScoreSnapshot.objects.filter(batch=batch).delete()

        # Loop through picks
        picks = PlayerPick.objects.select_related(
            "player_game", "game_league", "team", "game_league__league"
        )

        # Aggregate points per (player, game_league)
        agg = {}

        for pick in picks:
            try:
                row = StandingsRow.objects.get(batch=batch, team=pick.team)
            except StandingsRow.DoesNotExist:
                continue  # skip if no standings for team

            points = row.pure_points

            win_points = 0
            handicap_points = decimal.Decimal("0")
            lose_points = 0

            if pick.pick_type == PickType.WIN:
                win_points = points
            elif pick.pick_type == PickType.HANDICAP:
                try:
                    hcp = Handicap.objects.get(game_league=pick.game_league, team=pick.team)
                    per_game = decimal.Decimal(hcp.points) / pick.game_league.league.season_games
                    handicap_points = decimal.Decimal(points) + per_game * decimal.Decimal(row.played)
                except Handicap.DoesNotExist:
                    handicap_points = decimal.Decimal(points)
            elif pick.pick_type == PickType.LOSE:
                lose_points = points

            key = (pick.player_game_id, pick.game_league_id)
            agg.setdefault(key, {"win": 0, "hcp": decimal.Decimal("0"), "lose": 0})
            agg[key]["win"] += win_points
            agg[key]["hcp"] += handicap_points
            agg[key]["lose"] += lose_points

        # Save snapshots
        snapshots = []
        for (player_game_id, game_league_id), scores in agg.items():
            league_total = decimal.Decimal(scores["win"]) + scores["hcp"] - decimal.Decimal(scores["lose"])
            snap = PlayerScoreSnapshot.objects.create(
                player_game_id=player_game_id,
                game_league_id=game_league_id,
                batch=batch,
                win_points=scores["win"],
                handicap_points=scores["hcp"],
                lose_points=scores["lose"],
                league_total_points=league_total,
                overall_total_points=league_total,  # temporary, will update
            )
            snapshots.append(snap)

        # --- Assign league ranks ---
        for game_league_id in set(k[1] for k in agg.keys()):
            league_snaps = [s for s in snapshots if s.game_league_id == game_league_id]
            league_snaps.sort(key=lambda s: s.league_total_points, reverse=True)
            for rank, snap in enumerate(league_snaps, start=1):
                snap.league_rank = rank
                snap.save(update_fields=["league_rank"])

        # --- Aggregate overall totals per player across leagues ---
        overall_points = (
            PlayerScoreSnapshot.objects.filter(batch=batch)
            .values("player_game_id")
            .annotate(total=Sum("league_total_points"))
        )
        totals = {row["player_game_id"]: row["total"] for row in overall_points}

        # Update each snapshot with the player’s overall total
        for snap in snapshots:
            total = totals.get(snap.player_game_id, snap.league_total_points)
            snap.overall_total_points = total
            snap.save(update_fields=["overall_total_points"])

        # --- Assign overall ranks ---
        all_totals = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
        for rank, (player_game_id, total) in enumerate(all_totals, start=1):
            PlayerScoreSnapshot.objects.filter(
                batch=batch, player_game_id=player_game_id
            ).update(overall_rank=rank)

        self.stdout.write(self.style.SUCCESS("Scoring complete with league + overall ranks."))
