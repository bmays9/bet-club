# golf/forms.py
from django import forms
from .models import GolfGame
from groups.models import UserGroup


class CreateGolfGameForm(forms.ModelForm):
    group = forms.ModelChoiceField(queryset=None, label="Select Group")

    class Meta:
        model = GolfGame
        fields = ["group", "entry_fee", "missed_cut_fine", "pick_method", "picks_per_player", "scoring_picks"]
        labels = {
            "entry_fee": "Entry Fee (GBP)",
            "missed_cut_fine": "Missed Cut Fine per Golfer (GBP)",
            "pick_method": "Draft Type",
            "picks_per_player": "Golfers per Team",
            "scoring_picks": "Best N Golfers Count for Score",
        }
        widgets = {
            "entry_fee": forms.NumberInput(attrs={"step": "0.50", "min": "0"}),
            "missed_cut_fine": forms.NumberInput(attrs={"step": "0.50", "min": "0"}),
            "picks_per_player": forms.NumberInput(attrs={"min": "1", "max": "10"}),
            "scoring_picks": forms.NumberInput(attrs={"min": "1", "max": "10"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields["group"].queryset = UserGroup.objects.filter(members=user)