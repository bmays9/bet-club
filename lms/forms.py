# lms/forms.py
from django import forms
from .models import LMSPick, LMSRound, LMSGame

class LMSPickForm(forms.Form):
    team_name = forms.CharField(widget=forms.RadioSelect)  # radio buttons for fixtures
    
    def __init__(self, *args, game, round, entry, **kwargs):
        super().__init__(*args, **kwargs)
        self.game = game
        self.round = round
        self.entry = entry

        # Fetch fixtures for this round
        fixtures = game.rounds.get(id=round.id).picks.none()  # placeholder
        fixtures = round.get_fixtures() if hasattr(round, "get_fixtures") else []  # we’ll define this below

        # Build choices from home and away teams
        choices = []
        for f in fixtures:
            choices.append((f.home_team, f"{f.home_team} vs {f.away_team} (H)"))
            choices.append((f.away_team, f"{f.home_team} vs {f.away_team} (A)"))
        
        self.fields["team_name"].widget.choices = choices
