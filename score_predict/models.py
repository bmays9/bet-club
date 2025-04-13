from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal

# Create your models here.
class Fixture(models.Model):
    LEAGUES = [
        ('39', 'Premier League', 'PL'),
        ('40', 'Championship', 'CH'),
        ('41', 'League One', 'L1'),
        ('42', 'League Two', 'L2'),
    ]
     
    RESULT_CHOICES = [
        ('H', 'Home Win'),
        ('D', 'Draw'),
        ('A', 'Away Win'),
        ('N', 'Not Played')
    ]
    
    league_id = models.IntegerField(choices=[(l[0], l[1]) for l in LEAGUES])
    league_short_name = models.CharField(max_length=2, choices=[(l[2], l[2]) for l in LEAGUES])
    fixture_id = models.BigIntegerField(unique=True)
    date = models.DateTimeField()
    home_team = models.CharField(max_length=100)
    away_team = models.CharField(max_length=100)
    home_score = models.IntegerField(null=True, blank=True)
    away_score = models.IntegerField(null=True, blank=True)
    result = models.CharField(max_length=1, choices=RESULT_CHOICES, null=True, blank=True, default='N')
    
    def __str__(self):
        return f"{self.league_short_name}: {self.home_team} vs {self.away_team} - {self.date.strftime('%Y-%m-%d')}"

class Prediction(models.Model):
    player = models.ForeignKey(User, on_delete=models.CASCADE, related_name="score_predictions")
    fixture = models.ForeignKey(Fixture, on_delete=models.CASCADE, related_name="fixture")
    predicted_home_score = models.IntegerField()
    predicted_away_score = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("player", "fixture")

    def __str__(self):
        return f"{self.player.username} - {self.fixture} ({self.predicted_home_score}-{self.predicted_away_score})"


class Game(models.Model):
    week = models.PositiveIntegerField()
    start_date = models.DateField()
    end_date = models.DateField()
    entry_fee = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('5.00'))
    players = models.ManyToManyField(User, related_name='score_games')
    winner = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='won_games')

    def __str__(self):
        return f"Week {self.week} (£{self.entry_fee})"