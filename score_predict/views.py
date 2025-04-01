from collections import defaultdict
from django.shortcuts import render
from django.views import generic
from .models import Fixture

# Create your views here.
class FixtureList(generic.ListView):
    # template_name = "score_predict/fixtures.html"
    # queryset = Fixture.objects.all()
    template_name = "score_predict/fixtures.html"
    model = Fixture

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        grouped_fixtures = defaultdict(list)

        for fixture in self.object_list:  # self.object_list contains the queryset
            grouped_fixtures[fixture.league_short_name].append(fixture)  # Grouping by league_short_name

        context["fixture_list"] = dict(grouped_fixtures)  # Convert defaultdict to dict

        print("DEBUG:", context["fixture_list"])  # Check what is being passed
        
        return context