from django.contrib import admin
from .models import Fixture, Prediction, GameTemplate, GameInstance, GameEntry

# Register your models here.
admin.site.register(Fixture)
admin.site.register(Prediction)
admin.site.register(GameTemplate)
admin.site.register(GameInstance)
admin.site.register(GameEntry)