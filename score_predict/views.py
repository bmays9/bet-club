from django.shortcuts import render
from django.views import generic
from .models import Fixture

# Create your views here.
class FixtureList(generic.ListView):
    model = Fixture