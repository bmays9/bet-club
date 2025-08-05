from django.contrib import admin

from .models import LMSEntry, LMSGame, LMSPick, LMSRound

# Register your models here.
admin.site.register(LMSEntry)
admin.site.register(LMSGame)
admin.site.register(LMSPick)
admin.site.register(LMSRound)