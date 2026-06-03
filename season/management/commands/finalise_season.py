# season/management/commands/finalise_season.py
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.timezone import now
from season.models import (
    Game, PlayerGame, GameLeague, StandingsRow, StandingsBatch,
    PrizePool, PrizePayout, PrizeCategory,
)
from season.utils.payouts import allocate_payouts_for_game
from season.utils.season_helpers import get_latest_batches_map
from bank.services import apply_batch
from player_messages.utils import create_message


class Command(BaseCommand):
    help = "Finalise a season game: verify tables, preview payouts, settle bank."

    def add_arguments(self, parser):
        parser.add_argument("--game_id", type=int, required=True)
        parser.add_argument("--force", action="store_true",
                            help="Skip games-played equality check.")
        parser.add_argument("--dry_run", action="store_true",
                            help="Preview only, no changes.")

    def handle(self, *args, **options):
        game_id = options["game_id"]
        force = options["force"]
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN -- no changes will be made."))

        # -------------------------------------------------------
        # 1. Load game
        # -------------------------------------------------------
        try:
            game = Game.objects.get(id=game_id)
        except Game.DoesNotExist:
            raise CommandError(f"Game {game_id} not found.")

        if game.status == Game.Status.FINISHED:
            raise CommandError(f"Game '{game.name}' is already finished.")

        num_players = game.players.count()
        self.stdout.write(f"\nFinalising: {game.name} | Group: {game.group.name} | Players: {num_players}")

        # -------------------------------------------------------
        # 2. Verify standings
        # -------------------------------------------------------
        batch_map = get_latest_batches_map()
        game_leagues = list(GameLeague.objects.filter(game=game).select_related("league"))

        if not game_leagues:
            raise CommandError("No leagues configured for this game.")

        self.stdout.write(f"\nChecking {len(game_leagues)} league(s)...")
        problems = []

        for gl in game_leagues:
            league = gl.league
            batch = batch_map.get(league.id)
            if not batch:
                problems.append(f"  {league.name}: no standings batch found.")
                continue
            rows = StandingsRow.objects.filter(batch=batch)
            if not rows.exists():
                problems.append(f"  {league.name}: batch has no rows.")
                continue
            played_vals = set(rows.values_list("played", flat=True))
            if len(played_vals) > 1:
                problems.append(
                    f"  {league.name}: unequal games played {played_vals}."
                )
            else:
                played = played_vals.pop()
                expected = league.season_games
                age = now() - batch.taken_at
                status = "OK" if played >= expected else f"only {played}/{expected}"
                freshness = f" [WARNING: {age.days}d old]" if age.days > 3 else ""
                self.stdout.write(f"  {league.name}: {status}{freshness}")

        if problems and not force:
            for p in problems:
                self.stdout.write(self.style.ERROR(p))
            raise CommandError("Fix issues above or use --force.")

        # -------------------------------------------------------
        # 3. Run latest allocation so recipients are up to date
        # -------------------------------------------------------
        self.stdout.write("\nRunning latest payout allocation...")
        allocate_payouts_for_game(game, batch_map)

        # -------------------------------------------------------
        # 4. Build payout plan -- same logic as prize_summary view
        # -------------------------------------------------------
        # Each entry: {description, winner_user, losers, amount, prize_pool}
        # amount = what winner receives = what each loser pays * num_losers
        plan = []
        total_out = Decimal("0")
        total_in = Decimal("0")
        player_net = {}

        def add_to_plan(description, winner_user, losers, prize_amount, fee_per_loser):
            plan.append({
                "description": description,
                "winner": winner_user,
                "losers": losers,
                "prize": prize_amount,
                "fee": fee_per_loser,
            })
            player_net[winner_user.username] = player_net.get(winner_user.username, Decimal("0")) + prize_amount
            for u in losers:
                player_net[u.username] = player_net.get(u.username, Decimal("0")) - fee_per_loser

        all_players = list(
            PlayerGame.objects.filter(game=game).select_related("user")
        )
        all_users = [pg.user for pg in all_players]

        payouts_qs = PrizePayout.objects.filter(
            prize_pool__game=game,
            recipient__isnull=False,
        ).select_related(
            "prize_pool", "prize_pool__league",
            "recipient__user", "winning_pick__team",
        ).order_by("prize_pool__category", "amount")

        for payout in payouts_qs:
            cat = payout.prize_pool.category
            winner_user = payout.recipient.user

            # Calculate prize using same logic as prize_summary view
            if payout.amount is not None:
                prize = abs(payout.amount)
                fee_per_loser = prize / (num_players - 1) if num_players > 1 else prize
                is_penalty = payout.amount < 0
            elif payout.entry_fee_per_player:
                fee_per_loser = payout.entry_fee_per_player
                prize = fee_per_loser * (num_players - 1)
                is_penalty = False
            else:
                continue

            if prize == 0:
                continue

            losers = [u for u in all_users if u != winner_user]

            team_name = ""
            if payout.winning_pick and payout.winning_pick.team:
                team_name = f" ({payout.winning_pick.team.name})"

            if is_penalty:
                # This player PAYS, everyone else receives a share
                description = f"{payout.prize_pool.name} rank {payout.rank} penalty{team_name}"
                # Penalty: winner_user is actually the payer here
                # Flip: payer pays prize, split among others
                payer = winner_user
                receivers = losers
                fee_per_receiver = prize / len(receivers) if receivers else prize
                player_net[payer.username] = player_net.get(payer.username, Decimal("0")) - prize
                for u in receivers:
                    player_net[u.username] = player_net.get(u.username, Decimal("0")) + fee_per_receiver
                plan.append({
                    "description": description,
                    "winner": None,  # no single winner for penalties
                    "payer": payer,
                    "prize": prize,
                    "fee": prize,
                    "is_penalty": True,
                })
            else:
                description = f"{payout.prize_pool.name}{team_name}"
                add_to_plan(description, winner_user, losers, prize, fee_per_loser)

        # -------------------------------------------------------
        # 5. Preview
        # -------------------------------------------------------
        self.stdout.write("\n" + "=" * 65)
        self.stdout.write("PAYOUT PREVIEW")
        self.stdout.write("=" * 65)

        for item in plan:
            if item.get("is_penalty"):
                self.stdout.write(
                    f"  {item['description']:45s} {item['payer'].username:15s} pays GBP{item['prize']:.2f}"
                )
            else:
                self.stdout.write(
                    f"  {item['description']:45s} {item['winner'].username:15s} +GBP{item['prize']:.2f}  "
                    f"(others -GBP{item['fee']:.2f})"
                )

        self.stdout.write("\n-- Player Net Totals --")
        for username, net in sorted(player_net.items()):
            sign = "+" if net >= 0 else ""
            self.stdout.write(f"  {username:20s} {sign}GBP{net:.2f}")

        for net in player_net.values():
            if net >= 0:
                total_out += net
            else:
                total_in += net

        balance = total_out + total_in
        self.stdout.write(f"\n  Total out: +GBP{total_out:.2f}")
        self.stdout.write(f"  Total in:  -GBP{abs(total_in):.2f}")
        if abs(balance) < Decimal("0.10"):
            self.stdout.write(self.style.SUCCESS(
                f"  Zero-sum check: PASSED (balance=GBP{balance:.2f})"
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f"  Zero-sum check: FAILED (balance=GBP{balance:.2f})"
            ))

        self.stdout.write("=" * 65)

        if dry_run:
            self.stdout.write(self.style.SUCCESS("\nDry run complete."))
            return

        # -------------------------------------------------------
        # 6. Confirm
        # -------------------------------------------------------
        self.stdout.write("\nProceed with settlement? [y/N]: ", ending="")
        confirm = input().strip().lower()
        if confirm != "y":
            self.stdout.write(self.style.WARNING("Settlement cancelled."))
            return

        # -------------------------------------------------------
        # 7. Settle -- one apply_batch per payout item
        # -------------------------------------------------------
        self.stdout.write("\nSettling...")

        entrant_users = all_users

        for item in plan:
            try:
                if item.get("is_penalty"):
                    # Charge the payer, nothing paid out (goes to overall winner)
                    apply_batch(
                        group=game.group,
                        entrants=[item["payer"]],
                        winners=[],
                        entry_fee=item["prize"],
                        prize_pool=Decimal("0"),
                        description=f"Season: {item['description']} - {game.name}",
                    )
                else:
                    winner = item["winner"]
                    non_winners = [u for u in entrant_users if u != winner]
                    apply_batch(
                        group=game.group,
                        entrants=non_winners,
                        winners=[winner],
                        entry_fee=item["fee"],
                        prize_pool=item["prize"],
                        description=f"Season: {item['description']} - {game.name}",
                    )
                self.stdout.write(f"  Settled: {item['description']}")
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  FAILED {item['description']}: {e}"))

        # -------------------------------------------------------
        # 8. Overall winner receives collected penalties
        # -------------------------------------------------------
        # Penalties were collected above -- now pay the overall winner
        overall_winner_payout = PrizePayout.objects.filter(
            prize_pool__game=game,
            prize_pool__category="overall",
            rank=1,
            recipient__isnull=False,
        ).select_related("recipient__user").first()

        if overall_winner_payout:
            overall_penalties = PrizePayout.objects.filter(
                prize_pool__game=game,
                prize_pool__category="overall",
                rank__gt=1,
                recipient__isnull=False,
            )
            total_penalty = sum(abs(p.amount) for p in overall_penalties if p.amount)
            if total_penalty > 0:
                winner_user = overall_winner_payout.recipient.user
                try:
                    apply_batch(
                        group=game.group,
                        entrants=[],
                        winners=[winner_user],
                        entry_fee=Decimal("0"),
                        prize_pool=total_penalty,
                        description=f"Season overall winner prize - {game.name}",
                    )
                    self.stdout.write(self.style.SUCCESS(
                        f"  Overall winner {winner_user.username}: +GBP{total_penalty:.2f}"
                    ))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"  Overall winner payment failed: {e}"))

        # -------------------------------------------------------
        # 9. Player messages
        # -------------------------------------------------------
        self.stdout.write("\nSending player messages...")
        for pg in all_players:
            user = pg.user
            net = player_net.get(user.username, Decimal("0"))
            sign = "+" if net >= 0 else ""
            try:
                create_message(
                    code="SE-END",
                    context={
                        "User": user,
                        "game": game.name,
                        "net": f"{sign}GBP{net:.2f}",
                    },
                    group=game.group,
                    receiver=user,
                    actor=user,
                    link="season_overall",
                )
            except Exception:
                pass

        # -------------------------------------------------------
        # 10. Mark finished
        # -------------------------------------------------------
        game.status = Game.Status.FINISHED
        game.end_date = now().date()
        game.save(update_fields=["status", "end_date"])
        self.stdout.write(self.style.SUCCESS(f"\nGame '{game.name}' finalised."))
