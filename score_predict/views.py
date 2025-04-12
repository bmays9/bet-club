from collections import defaultdict, OrderedDict
from django.utils.timezone import now
from django.shortcuts import render
from django.views import generic
from .models import Fixture
from django.utils.timezone import make_aware, localtime
from datetime import datetime

LEAGUE_ORDER = {
    "PL": "Premier League",
    "CH": "Championship",
    "L1": "League One",
    "L2": "League Two"
}

VALID_WEEKDAYS = [4, 5, 6, 0]  # Weekend Fixtures | Friday=4, Saturday=5, Sunday=6, Monday=0

class FixtureList(generic.ListView):
    
    template_name = "score_predict/fixtures.html"
    model = Fixture
    context_object_name = "fixtures"

    def get_queryset(self):
        # Simulated "today" in 2021 season
        today_real = datetime.today()
        today_fake = datetime(2021, today_real.month, today_real.day)

        # Make it timezone-aware if using USE_TZ
        today_fake_aware = make_aware(today_fake)

        return Fixture.objects.filter(
            date__gte=today_fake_aware
        ).order_by("date")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        grouped = defaultdict(list)

        for fixture in self.object_list:
            weekday = fixture.date.weekday()
            if fixture.league_short_name in LEAGUE_ORDER and weekday in VALID_WEEKDAYS:
                grouped[fixture.league_short_name].append(fixture)

        # Use OrderedDict to preserve custom league order
        ordered_grouped = OrderedDict()
        for key in LEAGUE_ORDER.keys():
            if key in grouped:
                ordered_grouped[LEAGUE_ORDER[key]] = grouped[key]

        context["fixture_list"] = ordered_grouped
        return context