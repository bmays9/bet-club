# lms/models.py
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from groups.models import UserGroup
from decimal import Decimal
from score_predict.models import Fixture  # reuse your existing fixture model


class LMSGame(models.Model):
    LEAGUE_CHOICES = [
        ("EPL", "Premier League"),
        ("ECH", "Championship"),
        ("EL1", "League One"),
        ("EL2", "League Two"),
    ]

    entry_fee = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('5.00'))
    group = models.ForeignKey(UserGroup, on_delete=models.CASCADE, related_name="lms_games")
    league = models.CharField(max_length=3, choices=LEAGUE_CHOICES)
    active = models.BooleanField(default=True) #True is active, live game, False is completed
    created_at = models.DateTimeField(auto_now_add=True)
    winner = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='lms_winner')

    def __str__(self):
        game_id = self.id
        return f"{ game_id } | {self.active} ({self.get_league_display()} - {self.group.name} - {self.winner})"


class LMSRound(models.Model):
    game = models.ForeignKey(LMSGame, on_delete=models.CASCADE, related_name="rounds")
    round_number = models.PositiveIntegerField()
    start_date = models.DateTimeField() # start time of the first fixture
    end_date = models.DateTimeField() # 4 hours after the last fixture
    completed = models.BooleanField(default=False)
    fixtures = models.ManyToManyField(Fixture, related_name="lms_rounds", blank=True)

    @property
    def is_active(self):
        """Round is active if it has started, not completed, and is within its time window."""
        if self.completed:
            return False
        return timezone.now() >= self.start_date

    def __str__(self):
        return f"{self.game} - Round {self.round_number} | Active = { self.is_active } | { self.start_date } - { self.end_date } Completed = { self.completed } "


class LMSEntry(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    game = models.ForeignKey(LMSGame, on_delete=models.CASCADE, related_name="entries")
    alive = models.BooleanField(default=True)
    eliminated_round = models.IntegerField(blank=True, null=True) # 0 = entered but didn't pick round 1

    class Meta:
        unique_together = ("user", "game")

    def __str__(self):
        return f"{self.user.username} in {self.game}"


class LMSPick(models.Model):
    entry = models.ForeignKey(LMSEntry, on_delete=models.CASCADE, related_name="picks")
    round = models.ForeignKey(LMSRound, on_delete=models.CASCADE, related_name="picks")
    fixture = models.ForeignKey(Fixture, on_delete=models.CASCADE)
    team_name = models.CharField(max_length=100)  
    result = models.CharField(max_length=10, choices=[
        ("PENDING", "Pending"),
        ("WIN", "Win"),
        ("LOSE", "Lose"),
        ("DRAW", "Draw"),
    ], default="PENDING")

    class Meta:
        unique_together = ("entry", "round")

    def __str__(self):
        group_name = self.entry.game.group.name
        league_name = self.entry.game.get_league_display()
        return f"{self.entry.user.username} - {league_name} - {self.team_name} (Round {self.round.round_number}) - Group: {group_name}"
