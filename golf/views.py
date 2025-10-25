from django.shortcuts import render, get_object_or_404, redirect
from datetime import date, timedelta
from django.contrib.auth.decorators import login_required
from golf.models import GolfEvent, EventEntry, UserOrder
from golf.management.commands.fetch_entries import fetch_entries

def filtered_events(request):
    today = date.today()
    start_range = today - timedelta(weeks=2)
    end_range = today + timedelta(weeks=4)

    events = GolfEvent.objects.filter(start_date__range=(start_range, end_range)).order_by('start_date')

    for event in events:
        # Fetch entries only if none exist yet
        if not EventEntry.objects.filter(event=event).exists():
            print(f"Fetching entries for {event.name}...")
            fetch_entries(event)

        # Add a helper flag for template display
        event.has_entries = EventEntry.objects.filter(event=event).exists()

        return render(request, "golf/event_list.html", {"events": events})


def event_entries_view(request, event_id):
    event = get_object_or_404(GolfEvent, id=event_id)
    entries = EventEntry.objects.filter(event=event).select_related("golfer")

    return render(request, "golf/player_order.html", {
        "event": event,
        "entries": entries,
    })


@login_required
def pick_order_view(request, event_id):
    event = get_object_or_404(GolfEvent, id=event_id)
    entries = EventEntry.objects.filter(event=event).select_related("golfer")

    if request.method == "POST":
        UserOrder.objects.filter(user=request.user, event=event).delete()

        for i, golfer_id in enumerate(request.POST.getlist("golfer_order"), start=1):
            UserOrder.objects.create(
                user=request.user,
                event=event,
                golfer_id=golfer_id,
                selection_rank=i
            )
        return redirect("event_entries", event_id=event.id)

    return render(request, "golf/player_order.html", {
        "event": event,
        "entries": entries,
    })