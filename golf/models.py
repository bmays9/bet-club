from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal
from groups.models import UserGroup


# ---------------------------------------------
# Existing models (unchanged)
# ---------------------------------------------

class GolfTour(models.Model):
    active = models.BooleanField(default=True, null=True, blank=True)
    season_id = models.IntegerField()
    tour_id = models.IntegerField(unique=True)
    tour_name = models.CharField(max_length=255)

    def __str__(self):
        return self.tour_name


class GolfEvent(models.Model):
    tourn_id = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    tour = models.ForeignKey(GolfTour, on_delete=models.CASCADE)
    year = models.IntegerField()
    purse = models.BigIntegerField(null=True, blank=True)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    week_number = models.IntegerField(null=True, blank=True)
    playing_format = models.CharField(max_length=25, blank=True)
    status = models.CharField(max_length=50, blank=True)
    current_round = models.IntegerField(null=True, blank=True)
    timezone = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"{self.name} ({self.year})"

    @property
    def draft_opens(self):
        """Draft opens at 09:00 GMT the day before the event starts."""
        from django.utils.timezone import make_aware
        from datetime import datetime, time, timedelta
        day_before = self.start_date.date() - timedelta(days=1)
        return make_aware(datetime.combine(day_before, time(9, 0)))


class Golfer(models.Model):
    golfer_id = models.CharField(max_length=50, unique=True)
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    is_amateur = models.BooleanField(default=False)
    country = models.CharField(max_length=6, blank=True)
    world_ranking = models.IntegerField(default=2999)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class EventEntry(models.Model):
    event = models.ForeignKey(GolfEvent, on_delete=models.CASCADE, related_name="entries")
    golfer = models.ForeignKey(Golfer, on_delete=models.CASCADE, related_name="event_entries")
    status = models.CharField(max_length=50, blank=True)
    made_cut = models.BooleanField(null=True, blank=True)  # None=unknown, True=yes, False=no

    class Meta:
        unique_together = ('event', 'golfer')

    def __str__(self):
        return f"{self.golfer} in {self.event}"


class GolferScore(models.Model):
    golfer = models.ForeignKey(Golfer, on_delete=models.CASCADE)
    event = models.ForeignKey(GolfEvent, on_delete=models.CASCADE)
    round = models.IntegerField()
    score = models.IntegerField(null=True, blank=True)       # strokes this round
    total_score = models.IntegerField(null=True, blank=True) # cumulative vs par
    thru = models.IntegerField(null=True, blank=True)
    position = models.CharField(max_length=10, blank=True)

    class Meta:
        unique_together = ('golfer', 'event', 'round')

    def __str__(self):
        return f"{self.golfer} - R{self.round} ({self.event})"


# ---------------------------------------------
# User preference ordering (pre-draft)
# ---------------------------------------------

class UserOrder(models.Model):
    """Player's preferred golfer ranking before the draft starts."""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    event = models.ForeignKey(GolfEvent, on_delete=models.CASCADE)
    golfer = models.ForeignKey(Golfer, on_delete=models.CASCADE)
    selection_rank = models.IntegerField()  # 1 = most preferred

    class Meta:
        unique_together = ('user', 'event', 'selection_rank')

    def __str__(self):
        return f"{self.user.username} rank {self.selection_rank}: {self.golfer}"


# ---------------------------------------------
# Golf Game (one per group per event)
# ---------------------------------------------

class GolfGame(models.Model):

    class Status(models.TextChoices):
        OPEN = "open", "Open for joining"
        DRAFTING = "drafting", "Draft in progress"
        ACTIVE = "active", "Tournament in progress"
        FINISHED = "finished", "Finished"

    class PickMethod(models.TextChoices):
        STRAIGHT = "straight", "Straight (same order every round)"
        SNAKE = "snake", "Snake (order reverses each round)"

    event = models.ForeignKey(GolfEvent, on_delete=models.CASCADE, related_name="golf_games")
    group = models.ForeignKey(UserGroup, on_delete=models.CASCADE, related_name="golf_games")
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="golf_games_created")

    entry_fee = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("10.00"))
    missed_cut_fine = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("5.00"))
    pick_method = models.CharField(max_length=10, choices=PickMethod.choices, default=PickMethod.STRAIGHT)
    picks_per_player = models.PositiveSmallIntegerField(default=5)
    scoring_picks = models.PositiveSmallIntegerField(default=3)  # best N count

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)

    # Rollover pot from previous event (secondary pot carried forward)
    rollover_amount = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("event", "group")  # one game per group per event

    def __str__(self):
        return f"{self.group.name} - {self.event.name}"

    @property
    def total_main_pot(self):
        player_count = self.game_entries.count()
        return self.entry_fee * player_count

    @property
    def draft_start_time(self):
        return self.event.draft_opens


# ---------------------------------------------
# Players in a Golf Game
# ---------------------------------------------

class GolfGameEntry(models.Model):
    """A player's participation in a GolfGame."""
    game = models.ForeignKey(GolfGame, on_delete=models.CASCADE, related_name="game_entries")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="golf_game_entries")
    joined_at = models.DateTimeField(auto_now_add=True)

    # Draft order position (1 = picks first in round 1)
    draft_position = models.PositiveSmallIntegerField(null=True, blank=True)

    # Final team score (best N golfers combined), set at tournament end
    final_score = models.IntegerField(null=True, blank=True)
    final_rank = models.PositiveSmallIntegerField(null=True, blank=True)

    # Fines: total missed cut fines owed by this player
    total_fines = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        unique_together = ("game", "user")
        ordering = ["draft_position"]

    def __str__(self):
        return f"{self.user.username} in {self.game}"

    @property
    def picks(self):
        return DraftPick.objects.filter(game_entry=self).select_related("golfer")


# ---------------------------------------------
# Draft slot schedule
# ---------------------------------------------

class DraftSlot(models.Model):
    """
    Scheduled pick slot for one player in one draft round.
    Generated when the draft starts (status moves to DRAFTING).
    """
    game = models.ForeignKey(GolfGame, on_delete=models.CASCADE, related_name="draft_slots")
    game_entry = models.ForeignKey(GolfGameEntry, on_delete=models.CASCADE, related_name="draft_slots")
    round_number = models.PositiveSmallIntegerField()   # 1-5
    pick_number = models.PositiveSmallIntegerField()    # global order within game

    opens_at = models.DateTimeField(null=True, blank=True)    # when this player's window starts
    closes_at = models.DateTimeField(null=True, blank=True)  # opens_at + 1 hour

    completed = models.BooleanField(default=False)
    auto_assigned = models.BooleanField(default=False)

    class Meta:
        unique_together = ("game", "round_number", "game_entry")
        ordering = ["pick_number"]

    def __str__(self):
        return (
            f"Round {self.round_number} - {self.game_entry.user.username} "
            f"[{self.opens_at.strftime('%H:%M') if self.opens_at else 'TBD'}-{self.closes_at.strftime('%H:%M') if self.closes_at else 'TBD'}]"
        )

    @property
    def is_active(self):
        if self.completed or self.opens_at is None or self.closes_at is None:
            return False
        now = timezone.now()
        return self.opens_at <= now < self.closes_at

    @property
    def is_expired(self):
        if self.completed or self.closes_at is None:
            return False
        return timezone.now() >= self.closes_at

    @property
    def is_pending(self):
        """Slot is queued but not yet timed (waiting for previous pick)."""
        return not self.completed and self.opens_at is None


# ---------------------------------------------
# Draft picks (the actual selections)
# ---------------------------------------------

class DraftPick(models.Model):
    """A golfer selected by a player during the draft."""
    game = models.ForeignKey(GolfGame, on_delete=models.CASCADE, related_name="draft_picks")
    game_entry = models.ForeignKey(GolfGameEntry, on_delete=models.CASCADE, related_name="draft_picks")
    slot = models.OneToOneField(DraftSlot, on_delete=models.CASCADE, related_name="pick")
    golfer = models.ForeignKey(Golfer, on_delete=models.CASCADE, related_name="draft_picks")

    round_number = models.PositiveSmallIntegerField()
    auto_assigned = models.BooleanField(default=False)
    picked_at = models.DateTimeField(auto_now_add=True)

    # Scores populated during/after tournament
    made_cut = models.BooleanField(null=True, blank=True)
    total_strokes = models.IntegerField(null=True, blank=True)  # sum of all rounds
    is_tournament_winner = models.BooleanField(default=False)

    class Meta:
        unique_together = ("game", "golfer")  # no two players can pick same golfer
        ordering = ["round_number"]

    def __str__(self):
        flag = " (auto)" if self.auto_assigned else ""
        return f"{self.game_entry.user.username} - {self.golfer}{flag} R{self.round_number}"


# ---------------------------------------------
# Rollover pot tracking
# ---------------------------------------------

class RolloverPot(models.Model):
    """
    Tracks the secondary pot balance per group across events.
    Created/updated when fines are collected or pot is won/rolled.
    """
    group = models.OneToOneField(UserGroup, on_delete=models.CASCADE, related_name="golf_rollover")
    balance = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    last_updated = models.DateTimeField(auto_now=True)
    last_event = models.ForeignKey(
        GolfEvent, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="rollover_updates"
    )

    def __str__(self):
        return f"{self.group.name} rollover pot: GBP{self.balance}"


# ---------------------------------------------
# Historical finishing positions (for draft order)
# ---------------------------------------------

class GolfGameResult(models.Model):
    """
    Stores final rank per player per game.
    Used to determine draft order for the next event.
    """
    game = models.ForeignKey(GolfGame, on_delete=models.CASCADE, related_name="results")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="golf_results")
    final_rank = models.PositiveSmallIntegerField()
    final_score = models.IntegerField(null=True, blank=True)
    main_pot_won = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    secondary_pot_won = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    fines_paid = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        unique_together = ("game", "user")
        ordering = ["final_rank"]

    def __str__(self):
        return f"{self.user.username} - Rank {self.final_rank} in {self.game}"
