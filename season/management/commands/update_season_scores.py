# season/management/commands/update_season_scores.py
from django.core.management.base import BaseCommand
from django.db.models import Sum, Max
from season.utils.payouts import allocate_payouts_for_game
import decimal

from season.models import (
    Game, PlayerPick, PlayerScoreSnapshot,
    StandingsRow, StandingsBatch, Handicap, PickType,
)


class Command(BaseCommand):
    help = "Update PlayerScoreSnapshot for the latest standings batches."

    def handle(self, *args, **options):
        # --- Get latest batch per league ---
        latest_batches = (
            StandingsBatch.objects.values("league_id")
            .annotate(latest_taken_at=Max("taken_at"))
        )

        batch_map = {}
        for row in latest_batches:
            batch = StandingsBatch.objects.get(
                league_id=row["league_id"],
                taken_at=row["latest_taken_at"],
            )
            batch_map[batch.league_id] = batch

        if not batch_map:
            self.stdout.write(self.style.ERROR("No standings batches found"))
            return

        self.stdout.write(f"Scoring {len(batch_map)} leagues")

        # --- Clear old snapshots for these batches ---
        PlayerScoreSnapshot.objects.filter(batch__in=batch_map.values()).delete()

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
                    f"Skipped pick {pick.id}: no row for {pick.team} in {league}"
                )
                continue

            points = row.pure_points
            win_points = decimal.Decimal("0")
            handicap_points = decimal.Decimal("0")
            lose_points = decimal.Decimal("0")

            if pick.pick_type == PickType.WIN:
                win_points = decimal.Decimal(str(points))
            elif pick.pick_type == PickType.HANDICAP:
                try:
                    hcp = Handicap.objects.get(
                        game_league=pick.game_league, team=pick.team
                    )
                    season_games = pick.game_league.league.season_games
                    per_game = decimal.Decimal(str(hcp.points)) / decimal.Decimal(str(season_games))
                    handicap_points = decimal.Decimal(str(points)) + per_game * decimal.Decimal(str(row.played))
                except Handicap.DoesNotExist:
                    handicap_points = decimal.Decimal(str(points))
            elif pick.pick_type == PickType.LOSE:
                lose_points = decimal.Decimal(str(points))

            key = (pick.player_game_id, pick.game_league_id, batch.id)
            agg.setdefault(key, {
                "win": decimal.Decimal("0"),
                "hcp": decimal.Decimal("0"),
                "lose": decimal.Decimal("0"),
            })
            agg[key]["win"] += win_points
            agg[key]["hcp"] += handicap_points
            agg[key]["lose"] += lose_points

        # --- Save snapshots ---
        snapshots = []
        for (player_game_id, game_league_id, batch_id), scores in agg.items():
            league_total = scores["win"] + scores["hcp"] - scores["lose"]
            snap = PlayerScoreSnapshot.objects.create(
                player_game_id=player_game_id,
                game_league_id=game_league_id,
                batch_id=batch_id,
                win_points=scores["win"],
                handicap_points=scores["hcp"],
                lose_points=scores["lose"],
                league_total_points=league_total,
                overall_total_points=league_total,  # updated below
            )
            snapshots.append(snap)

        # --- League ranks ---
        for (game_league_id, batch_id) in set((k[1], k[2]) for k in agg.keys()):
            league_snaps = [
                s for s in snapshots
                if s.game_league_id == game_league_id and s.batch_id == batch_id
            ]
            league_snaps.sort(key=lambda s: s.league_total_points, reverse=True)
            for rank, snap in enumerate(league_snaps, start=1):
                snap.league_rank = rank
                snap.save(update_fields=["league_rank"])

        # --- Overall totals: sum league_total_points per player across leagues ---
        # Key fix: group by player_game_id ONLY (not batch_id)
        # Each player has one snapshot per league -- sum them
        player_totals = {}
        for snap in snapshots:
            pid = snap.player_game_id
            player_totals[pid] = player_totals.get(pid, decimal.Decimal("0")) + snap.league_total_points

        # Update snapshots with overall total
        for snap in snapshots:
            snap.overall_total_points = player_totals.get(
                snap.player_game_id, snap.league_total_points
            )
            snap.save(update_fields=["overall_total_points"])

        # --- Overall ranks ---
        ranked = sorted(player_totals.items(), key=lambda kv: kv[1], reverse=True)
        batch_id_list = [b.id for b in batch_map.values()]
        for rank, (player_game_id, total) in enumerate(ranked, start=1):
            PlayerScoreSnapshot.objects.filter(
                player_game_id=player_game_id,
                batch_id__in=batch_id_list,
            ).update(overall_rank=rank)

        self.stdout.write(self.style.SUCCESS("Scoring complete."))

        # --- Allocate prize payouts ---
        game_ids = PlayerPick.objects.filter(
            game_league__league__in=batch_map.keys()
        ).values_list("game_league__game", flat=True).distinct()

        for game_id in game_ids:
            try:
                game = Game.objects.get(id=game_id)
                allocate_payouts_for_game(game, batch_map)
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"Payout allocation failed for game {game_id}: {e}")
                )
