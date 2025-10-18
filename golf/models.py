from django.db import models
from django.contrib.auth.models import User


class GolfTour(models.Model):
    active = models.BooleanField(default=True, null=True, blank=True)
    season_id = models.IntegerField()
    tour_id = models.IntegerField(unique=True)
    tour_name = models.CharField(max_length=255)

    def __str__(self):
        return self.tour_name


class GolfEvent(models.Model):
    tourn_id = models.CharField(max_length=50, unique=True)  # e.g. tournId "475"
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

class Golfer(models.Model):
    golfer_id = models.CharField(max_length=50, unique=True)
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    is_amateur = models.BooleanField(default=False)
    country = models.CharField(max_length=6, blank=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class EventEntry(models.Model):
    event = models.ForeignKey(GolfEvent, on_delete=models.CASCADE)
    golfer = models.ForeignKey(Golfer, on_delete=models.CASCADE)
    status = models.CharField(max_length=50, blank=True)

    class Meta:
        unique_together = ('event', 'golfer')

    def __str__(self):
        return f"{self.golfer} in {self.event}"


class GolferScore(models.Model):
    golfer = models.ForeignKey(Golfer, on_delete=models.CASCADE)
    event = models.ForeignKey(GolfEvent, on_delete=models.CASCADE)
    round = models.IntegerField()
    score = models.IntegerField(null=True, blank=True)
    thru = models.IntegerField(null=True, blank=True)
    position = models.CharField(max_length=10, blank=True)

    class Meta:
        unique_together = ('golfer', 'event', 'round')

    def __str__(self):
        return f"{self.golfer} - R{self.round} ({self.event})"


class UserPick(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    event = models.ForeignKey(GolfEvent, on_delete=models.CASCADE)
    golfer = models.ForeignKey(Golfer, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('user', 'event', 'golfer')


class UserOrder(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    event = models.ForeignKey(GolfEvent, on_delete=models.CASCADE)
    golfer = models.ForeignKey(Golfer, on_delete=models.CASCADE)
    selection_rank = models.IntegerField()

    class Meta:
        unique_together = ('user', 'event', 'selection_rank')
