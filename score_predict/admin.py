from django.contrib import admin
from .models import Fixture, Prediction, Game

# Register your models here.
admin.site.register(Fixture)
admin.site.register(Prediction)
admin.site.register(Game)