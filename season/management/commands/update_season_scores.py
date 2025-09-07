from django.core.management.base import BaseCommand
from django.db.models import Sum, Max
import decimal

from season.models import (
    PlayerPick,
    PlayerScoreSnapshot,
    StandingsRow,
    StandingsBatch,
    Handicap,
    PickType,
)


class Command(BaseCommand):
    help = "Update PlayerScoreSnapshot for the latest standings batches across all leagues"

    def handle(self, *args, **options):
        # --- Get latest batch for each league ---
        latest_batches = (
            StandingsBatch.objects.values("league_id")
            .annotate(latest_taken_at=Max("taken_at"))
        )

        batch_map = {}
        for row in latest_batches:
            batch = StandingsBatch.objects.get(
                league_id=row["league_id"], taken_at=row["latest_taken_at"]
            )
            batch_map[batch.league_id] = batch

        if not batch_map:
            self.stdout.write(self.style.ERROR("No standings batches found"))
            return

        self.stdout.write(f"Scoring {len(batch_map)} leagues")

        # --- Clear old snapshots for these batches ---
        PlayerScoreSnapshot.objects.filter(batch__in=batch_map.values()).delete()

        # --- Loop through all picks ---
        picks = PlayerPick.objects.select_related(
            "player_game", "game_league", "team", "game_league__league"
        )

        agg = {}

        for pick in picks:
            league = pick.game_league.league
            batch = batch_map.get(league.id)
            if not batch:
                continue

            try:
                row = StandingsRow.objects.get(batch=batch, team=pick.team)
            except StandingsRow.DoesNotExist:
                self.stdout.write(
                    f"Skipped pick {pick.id}: no standings row for team {pick.team} in {league}"
                )
                continue

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

            key = (pick.player_game_id, pick.game_league_id, batch.id)
            agg.setdefault(
                key, {"win": 0, "hcp": decimal.Decimal("0"), "lose": 0}
            )
            agg[key]["win"] += win_points
            agg[key]["hcp"] += handicap_points
            agg[key]["lose"] += lose_points

        # --- Save snapshots ---
        snapshots = []
        for (player_game_id, game_league_id, batch_id), scores in agg.items():
            league_total = (
                decimal.Decimal(scores["win"])
                + scores["hcp"]
                - decimal.Decimal(scores["lose"])
            )
            snap = PlayerScoreSnapshot.objects.create(
                player_game_id=player_game_id,
                game_league_id=game_league_id,
                batch_id=batch_id,
                win_points=scores["win"],
                handicap_points=scores["hcp"],
                lose_points=scores["lose"],
                league_total_points=league_total,
                overall_total_points=league_total,  # will update later
            )
            snapshots.append(snap)

        # --- Assign league ranks ---
        for (game_league_id, batch_id) in set((k[1], k[2]) for k in agg.keys()):
            league_snaps = [
                s for s in snapshots if s.game_league_id == game_league_id and s.batch_id == batch_id
            ]
            league_snaps.sort(key=lambda s: s.league_total_points, reverse=True)
            for rank, snap in enumerate(league_snaps, start=1):
                snap.league_rank = rank
                snap.save(update_fields=["league_rank"])

        # --- Aggregate overall totals per player across leagues ---
        overall_points = (
            PlayerScoreSnapshot.objects.filter(batch__in=batch_map.values())
            .values("player_game_id", "batch_id")
            .annotate(total=Sum("league_total_points"))
        )

        totals = {}
        for row in overall_points:
            totals.setdefault(row["player_game_id"], 0)
            totals[row["player_game_id"]] += row["total"]

        # Update each snapshot with the player’s overall total
        for snap in snapshots:
            total = totals.get(snap.player_game_id, snap.league_total_points)
            snap.overall_total_points = total
            snap.save(update_fields=["overall_total_points"])

        # --- Assign overall ranks ---
        all_totals = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
        for rank, (player_game_id, total) in enumerate(all_totals, start=1):
            PlayerScoreSnapshot.objects.filter(
                player_game_id=player_game_id, batch__in=batch_map.values()
            ).update(overall_rank=rank)

        self.stdout.write(self.style.SUCCESS("Scoring complete for all leagues."))
