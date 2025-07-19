from django.shortcuts import render
from datetime import date, timedelta
from golf.models import GolfEvent

def filtered_events(request):
    today = date.today()
    start_range = today - timedelta(weeks=2)
    end_range = today + timedelta(weeks=4)

    events = GolfEvent.objects.filter(start_date__range=(start_range, end_range)).order_by('start_date')

    return render(request, "golf/event_list.html", {"events": events})