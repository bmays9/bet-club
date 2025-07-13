# groups/forms.py
from django import forms
from .models import UserGroup

class CreateGroupForm(forms.ModelForm):
    class Meta:
        model = UserGroup
        fields = ['name']

class JoinGroupForm(forms.Form):
    access_code = forms.CharField(max_length=6)