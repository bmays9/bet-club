from django.db import models
from django.contrib.auth.models import User

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

