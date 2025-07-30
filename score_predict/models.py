from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal
from groups.models import UserGroup


####
#### GameTemplate defines fixtures for a midweek/weekend period.
#### GameInstance links a group to a GameTemplate (1 group = 1 game instance).
#### Prediction stores a user’s predicted score for a fixture in a GameInstance.
#### GameEntry stores the total score for a player in a GameInstance.
####

# Create your models here.
class Fixture(models.Model):
    LEAGUES = [
        (17, 'Premier League', 'EPL'),
        (18, 'Championship', 'ECH'),
        (24, 'League One', 'EL1'),
        (25, 'League Two', 'EL2'),
    ]
     
    RESULT_CHOICES = [
        ('H', 'Home Win'),
        ('D', 'Draw'),
        ('A', 'Away Win'),
        ('N', 'Not Played')
    ]
    
    league_id = models.IntegerField(choices=[(l[0], l[1]) for l in LEAGUES])
    league_short_name = models.CharField(max_length=3, choices=[(l[2], l[2]) for l in LEAGUES])
    fixture_id = models.BigIntegerField(unique=True)
    gametemplate = models.ForeignKey('GameTemplate', on_delete=models.SET_NULL, null=True, blank=True)
    date = models.DateTimeField()
    home_team = models.CharField(max_length=100)
    away_team = models.CharField(max_length=100)
    home_colour = models.CharField(max_length=7, null=True, blank=True)
    home_text = models.CharField(max_length=7, null=True, blank=True)
    away_colour = models.CharField(max_length=7, null=True, blank=True)
    away_text = models.CharField(max_length=7, null=True, blank=True)
    final_result_only = models.BooleanField(default=False, null=True, blank=True)
    status_code = models.IntegerField(null=True, blank=True)
    status_description = models.CharField(max_length=50, null=True, blank=True)
    home_score = models.IntegerField(null=True, blank=True)
    away_score = models.IntegerField(null=True, blank=True)
    result = models.CharField(max_length=1, choices=RESULT_CHOICES, null=True, blank=True, default='N')
    
    def __str__(self):
        return f"{self.league_short_name}: {self.home_team} vs {self.away_team} - {self.date.strftime('%Y-%m-%d')}"

class GameTemplate(models.Model):
    slug = models.SlugField(max_length=30, unique=True)  # e.g. SP1-midweek-2025-wk30
    game_type = models.CharField(max_length=10, choices=[("weekend", "Weekend"), ("midweek", "Midweek")])
    week = models.PositiveIntegerField()
    start_date = models.DateField()
    end_date = models.DateField()
    
    def __str__(self):
        return f"{self.slug} ({self.start_date} to {self.end_date})"

class GameInstance(models.Model):
    template = models.ForeignKey(GameTemplate, on_delete=models.CASCADE, related_name='instances')
    group = models.ForeignKey(UserGroup, on_delete=models.CASCADE, related_name='game_instances')
    entry_fee = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('5.00'))
    players = models.ManyToManyField(User, through='GameEntry', related_name='score_games')
    winner = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='won_games')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("template", "group")

    def __str__(self):
        return f"{self.template.slug} - {self.group.name}"

class Prediction(models.Model):
    RESULT_CHOICES = [
        ('H', 'Home Win'),
        ('D', 'Draw'),
        ('A', 'Away Win'),
        ('N', 'Not Played')
    ]
    ## Individual fixture prediction, 
    game_instance = models.ForeignKey(GameInstance, on_delete=models.CASCADE, related_name="predictions")
    player = models.ForeignKey(User, on_delete=models.CASCADE, related_name="score_predictions")
    fixture = models.ForeignKey(Fixture, on_delete=models.CASCADE, related_name="fixture")
    score = models.IntegerField(default=0)
    alternate_score = models.IntegerField(default=0)
    predicted_home_score = models.IntegerField()
    predicted_away_score = models.IntegerField()
    predicted_result = models.CharField(max_length=1, choices=RESULT_CHOICES, null=True, blank=True, default='N')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("player", "fixture")

    def __str__(self):
        return f"{self.player.username} - {self.fixture} ({self.predicted_home_score}-{self.predicted_away_score})"

class GameEntry(models.Model):
    game = models.ForeignKey(GameInstance, on_delete=models.CASCADE)
    player = models.ForeignKey(User, on_delete=models.CASCADE)
    total_score = models.IntegerField(default=0)

    class Meta:
        unique_together = ('game', 'player')

    def __str__(self):
        return f"{self.player.username} - {self.game} - Score: {self.total_score}"