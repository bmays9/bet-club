from __future__ import annotations

from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import Group
from groups.models import UserGroup


# -----------------------------
# Core reference data
# -----------------------------

class League(models.Model):
    """A football league (e.g., Premier League).

    season_games may vary by league (EPL=38). Used to pro‑rate handicaps.
    """

    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True)
    country = models.CharField(max_length=50, blank=True)
    season_games = models.PositiveSmallIntegerField(default=38)

    # External IDs
    tournament_id = models.PositiveIntegerField(unique=True)
    season_id = models.PositiveIntegerField(unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name}"


class Team(models.Model):
    league = models.ForeignKey(League, on_delete=models.CASCADE, related_name="teams")
    name = models.CharField(max_length=100)
    short_name = models.CharField(max_length=40, blank=True)
    sofascore_id = models.PositiveIntegerField(unique=True)

    class Meta:
        unique_together = [("league", "name")]
        ordering = ["league__name", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.league.code})"


# -----------------------------
# Game setup & participation
# -----------------------------

class Game(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        FINISHED = "finished", "Finished"
        ARCHIVED = "archived", "Archived"

    name = models.CharField(max_length=120)
    group = models.ForeignKey(UserGroup, on_delete=models.CASCADE, related_name='season_game')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="season_games_created")

    entry_fee = models.DecimalField(max_digits=9, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)

    start_date = models.DateField()
    end_date = models.DateField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["status"])]
        unique_together = [("group", "name")]  # nice-to-have

    def __str__(self) -> str:
        return f"{self.name} ({self.get_status_display()})"


class GameLeague(models.Model):
    """Leagues configured for a given Game."""

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="game_leagues")
    league = models.ForeignKey(League, on_delete=models.PROTECT, related_name="game_leagues")
    active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("game", "league")]
        ordering = ["game", "league__name"]

    def __str__(self) -> str:
        return f"{self.game.name} – {self.league.name}"


class PlayerGame(models.Model):
    """A user's participation in a Game."""

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="players")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="season_player_games")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("game", "user")]
        ordering = ["game", "user__username"]

    def __str__(self) -> str:
        return f"{self.user} in {self.game.name}"


class Handicap(models.Model):
    """Pre‑season handicap points per team for a specific Game+League.

    Stored as an integer total for the season (e.g., +19), to be pro‑rated over
    the league's season_games when computing current scores.
    """

    game_league = models.ForeignKey(GameLeague, on_delete=models.CASCADE, related_name="handicaps")
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="handicaps")
    points = models.IntegerField()  # may be negative or positive

    class Meta:
        unique_together = [("game_league", "team")]
        ordering = ["game_league", "team__name"]

    def __str__(self) -> str:
        return f"{self.team} HCP {self.points} for {self.game_league}"


# -----------------------------
# Picks & constraints
# -----------------------------

class PickType(models.TextChoices):
    WIN = "win", "Win Team"
    HANDICAP = "handicap", "Handicap Team"
    LOSE = "lose", "Lose Team"


class PlayerPick(models.Model):
    """Each player makes one pick per pick type per league for the whole season.

    Exclusivity rules:
      - For a given Game+League, a specific TEAM can be used by at most ONE player in each pick type.
      - A single player cannot pick the same team twice within the same Game+League (across types).
    """

    player_game = models.ForeignKey(PlayerGame, on_delete=models.CASCADE, related_name="picks")
    game_league = models.ForeignKey(GameLeague, on_delete=models.CASCADE, related_name="picks")
    pick_type = models.CharField(max_length=10, choices=PickType.choices)
    team = models.ForeignKey(Team, on_delete=models.PROTECT, related_name="picks")
    pick_number = models.IntegerField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Team exclusivity per pick type within a Game+League
        constraints = [
            models.UniqueConstraint(
                fields=["game_league", "pick_type", "team"],
                name="unique_team_per_type_in_game_league",
            ),
            models.UniqueConstraint(
                fields=["player_game", "game_league", "pick_type"],
                name="one_pick_per_type_per_league_per_player",
            ),
        ]
        indexes = [models.Index(fields=["game_league", "pick_type"]) ]

    def clean(self):
        # prevent a player selecting the same team more than once across types in a Game+League
        if (
            self.player_game_id
            and self.game_league_id
            and self.team_id
        ):
            exists = (
                PlayerPick.objects.exclude(pk=self.pk)
                .filter(
                    player_game=self.player_game,
                    game_league=self.game_league,
                    team=self.team,
                )
                .exists()
            )
            if exists:
                raise ValidationError("You cannot pick the same team more than once in this league.")

        # ensure team belongs to the same league as game_league
        if self.game_league_id and self.team_id and self.team.league_id != self.game_league.league_id:
            raise ValidationError("Selected team does not belong to this league.")

    def __str__(self) -> str:
        return f"{self.player_game.user} – {self.get_pick_type_display()} – {self.team.name} ({self.game_league.league.code})"


# -----------------------------
# Standings snapshots (from SofaScore) & scoring
# -----------------------------

class StandingsBatch(models.Model):
    """A batch timestamp for a standings import (e.g., weekly)."""

    taken_at = models.DateTimeField(default=timezone.now)
    season_round = models.PositiveSmallIntegerField(blank=True, null=True)
    source = models.CharField(max_length=40, default="sofascore")

    class Meta:
        ordering = ["-taken_at"]

    def __str__(self) -> str:
        return f"Standings batch @ {self.taken_at:%Y-%m-%d %H:%M}"


class StandingsRow(models.Model):
    """Row for a given team at a snapshot point.

    We store wins/draws/losses and recompute points as 3*W + 1*D to ignore any
    off‑pitch deductions, per game rules.
    """

    batch = models.ForeignKey(StandingsBatch, on_delete=models.CASCADE, related_name="rows")
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="standings_rows")

    position = models.PositiveSmallIntegerField()
    played = models.PositiveSmallIntegerField()
    wins = models.PositiveSmallIntegerField()
    draws = models.PositiveSmallIntegerField()
    losses = models.PositiveSmallIntegerField()
    goals_for = models.PositiveSmallIntegerField(default=0)
    goals_against = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = [("batch", "team")]
        ordering = ["batch", "position"]

    @property
    def pure_points(self) -> int:
        return 3 * int(self.wins) + int(self.draws)

    def __str__(self) -> str:
        return f"{self.team} pos {self.position} ({self.pure_points} pts)"


class PlayerScoreSnapshot(models.Model):
    """Computed scores for a player at a specific standings batch.

    Fields store the *points* view. Monetary P/L can be derived via Prize pools
    or via separate transactions when settling.
    """

    player_game = models.ForeignKey(PlayerGame, on_delete=models.CASCADE, related_name="score_snapshots")
    game_league = models.ForeignKey(GameLeague, on_delete=models.CASCADE, related_name="score_snapshots")
    batch = models.ForeignKey(StandingsBatch, on_delete=models.CASCADE, related_name="player_scores")

    # per-type points at this snapshot
    win_points = models.IntegerField(default=0)
    handicap_points = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0.00"))
    lose_points = models.IntegerField(default=0)  # stored as positive magnitude; total will subtract

    # totals
    league_total_points = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    overall_total_points = models.DecimalField(max_digits=9, decimal_places=2, default=Decimal("0.00"))

    # ranks within contexts
    league_rank = models.PositiveIntegerField(blank=True, null=True)
    overall_rank = models.PositiveIntegerField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("player_game", "game_league", "batch")]
        indexes = [
            models.Index(fields=["batch", "game_league"]),
            models.Index(fields=["player_game", "batch"]),
        ]

    def __str__(self) -> str:
        return f"Score {self.player_game} {self.game_league.league.code} @ {self.batch.taken_at:%Y-%m-%d}"


# -----------------------------
# Prize configuration & accounting
# -----------------------------

class PrizeCategory(models.TextChoices):
    OVERALL = "overall", "Overall Position"
    LEAGUE_WINNER = "league_total", "Best League Total"
    TEAMS_TO_WIN = "teams_to_win", "Best Teams to Win (with Handicap)"
    TEAMS_TO_LOSE = "teams_to_lose", "Best Teams to Lose"
    MONTH_WINNER = "monthly_winner", "Monthly Winner"


class PrizePool(models.Model):
    """Configures prize money for a category, optionally scoped to a league.

    Store as rows in PrizePayout with rank and amount (positive for payouts,
    negative for penalties). This lets you mirror 'minus for last' explicitly.
    """

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="prize_pools")
    category = models.CharField(max_length=20, choices=PrizeCategory.choices)
    league = models.ForeignKey(League, on_delete=models.PROTECT, null=True, blank=True, related_name="prize_pools")
    name = models.CharField(max_length=120, help_text="Human label shown to users")
    active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("game", "category", "league")]
        ordering = ["game", "category"]

    def __str__(self) -> str:
        target = self.league.code if self.league_id else "All Leagues"
        return f"{self.game.name}"


class PrizePayout(models.Model):
    prize_pool = models.ForeignKey(PrizePool, on_delete=models.CASCADE, related_name="payouts")
    rank = models.PositiveIntegerField()
    amount = models.DecimalField(max_digits=9, decimal_places=2)

    class Meta:
        unique_together = [("prize_pool", "rank")]
        ordering = ["rank"]

    def __str__(self) -> str:
        return f"{self.prize_pool.name} – Rank {self.rank}: £{self.amount}"