# lms/models.py
from django.db import models
from django.contrib.auth.models import User
from groups.models import UserGroup
from score_predict.models import Fixture  # reuse your existing fixture model


class LMSGame(models.Model):
    LEAGUE_CHOICES = [
        ("EPL", "Premier League"),
        ("CH", "Championship"),
        ("L1", "League One"),
        ("L2", "League Two"),
    ]

    name = models.CharField(max_length=100)
    group = models.ForeignKey(UserGroup, on_delete=models.CASCADE, related_name="lms_games")
    league = models.CharField(max_length=3, choices=LEAGUE_CHOICES)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.get_league_display()} - {self.group.name})"


class LMSRound(models.Model):
    game = models.ForeignKey(LMSGame, on_delete=models.CASCADE, related_name="rounds")
    round_number = models.PositiveIntegerField()
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    completed = models.BooleanField(default=False)

    def get_fixtures(self):
        return Fixture.objects.filter(
            league=self.game.league,
            start_time__gte=self.start_date,
            start_time__lte=self.end_date
        ).order_by("start_time")

    def __str__(self):
        return f"{self.game.name} - Round {self.round_number}"


class LMSEntry(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    game = models.ForeignKey(LMSGame, on_delete=models.CASCADE, related_name="entries")
    alive = models.BooleanField(default=True)
    eliminated_round = models.IntegerField(blank=True, null=True)

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
        return f"{self.entry.user.username} - {self.team_name} (Round {self.round.round_number})"
