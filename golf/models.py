# golf/models.py
from django.db import models
from django.contrib.auth.models import User

class GolfTour(models.Model):
    active = models.IntegerField()
    season_id = models.IntegerField()
    tour_id = models.IntegerField(unique=True)
    tour_name = models.CharField(max_length=255)

class GolfEvent(models.Model):
    event_id = models.IntegerField(unique=True)
    name = models.CharField(max_length=255)
    start_date = models.DateField()
    end_date = models.DateField()
    course = models.CharField(max_length=255, blank=True)
    tour = models.ForeignKey(GolfTour, on_delete=models.CASCADE)

class Golfer(models.Model):
    golfer_id = models.IntegerField()
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    country = models.CharField(max_length=6)

class EventEntry(models.Model):
    event = models.ForeignKey(GolfEvent, on_delete=models.CASCADE)
    golfer = models.ForeignKey(Golfer, on_delete=models.CASCADE)

class UserPick(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    event = models.ForeignKey(GolfEvent, on_delete=models.CASCADE)
    golfer = models.ForeignKey(Golfer, on_delete=models.CASCADE)

class UserOrder(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    event = models.ForeignKey(GolfEvent, on_delete=models.CASCADE)
    golfer = models.ForeignKey(Golfer, on_delete=models.CASCADE)
    selection_rank = models.IntegerField()

class GolferScore(models.Model):
    golfer = models.ForeignKey(Golfer, on_delete=models.CASCADE)
    event = models.ForeignKey(GolfEvent, on_delete=models.CASCADE)
    round = models.IntegerField()
    score = models.IntegerField(null=True, blank=True)
    thru = models.IntegerField(null=True, blank=True)
    position = models.CharField(max_length=10, blank=True)
