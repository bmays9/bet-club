import os
import requests
from django.core.management.base import BaseCommand
from django.utils.timezone import now
from golf.models import GolfEvent, Golfer, GolferScore, EventEntry

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_GOLF_HOST = "live-golf-data.p.rapidapi.com"

HEADERS = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
    "X-RapidAPI-Host": RAPIDAPI_GOLF_HOST,
}


def fetch_leaderboard(event):
    url = "https://live-golf-data.p.rapidapi.com/leaderboard"
    params = {
        "orgId": str(event.tour.tour_id),
        "tournId": event.tourn_id,
        "year": str(event.year),
    }
    response = requests.get(url, headers=HEADERS, params=params, timeout=30)
    if response.status_code != 200:
        print(f"  Failed ({response.status_code}): {response.text[:200]}")
        return None
    return response.json()


def safe_int(val):
    """Parse any API numeric value to int. Handles dicts, strings, E, +/-."""
    if val is None:
        return None
    if isinstance(val, dict):
        val = (val.get("$numberInt")
               or val.get("$numberLong")
               or val.get("$numberDouble"))
        if val is None:
            return None
    if isinstance(val, (int, float)):
        return int(val)
    val = str(val).strip()
    if not val or val in ("-", ""):
        return None
    if val == "E":
        return 0
    try:
        return int(val)
    except ValueError:
        return None


def safe_str(val, default=""):
    if val is None:
        return default
    if isinstance(val, dict):
        return default
    return str(val).strip() or default


def save_leaderboard(event, data):
    players = data.get("leaderboardRows", [])
    if not players:
        print(f"  No leaderboardRows in response")
        return 0

    current_round = safe_int(data.get("roundId")) or event.current_round or 1
    event_status = safe_str(data.get("status"))

    # ------------------------------------------------------------------
    # 1. Upsert golfers in bulk
    # ------------------------------------------------------------------
    golfer_data = {}
    for p in players:
        gid = safe_str(p.get("playerId"))
        if not gid:
            continue
        golfer_data[gid] = {
            "first_name": safe_str(p.get("firstName")),
            "last_name": safe_str(p.get("lastName")),
            "is_amateur": bool(p.get("isAmateur", False)),
        }

    existing_golfers = {
        g.golfer_id: g
        for g in Golfer.objects.filter(golfer_id__in=golfer_data.keys())
    }

    to_create_golfers = []
    to_update_golfers = []
    for gid, fields in golfer_data.items():
        if gid in existing_golfers:
            g = existing_golfers[gid]
            g.first_name = fields["first_name"]
            g.last_name = fields["last_name"]
            g.is_amateur = fields["is_amateur"]
            to_update_golfers.append(g)
        else:
            to_create_golfers.append(Golfer(golfer_id=gid, **fields))

    if to_create_golfers:
        Golfer.objects.bulk_create(to_create_golfers, ignore_conflicts=True)
    if to_update_golfers:
        Golfer.objects.bulk_update(
            to_update_golfers, ["first_name", "last_name", "is_amateur"]
        )

    # Refresh after bulk create
    golfer_map = {
        g.golfer_id: g
        for g in Golfer.objects.filter(golfer_id__in=golfer_data.keys())
    }

    # ------------------------------------------------------------------
    # 2. Upsert EventEntries in bulk
    # ------------------------------------------------------------------
    existing_entries = {
        e.golfer_id: e
        for e in EventEntry.objects.filter(
            event=event, golfer_id__in=golfer_map.values()
        ).select_related("golfer")
    }

    entry_to_create = []
    entry_to_update = []
    for p in players:
        gid = safe_str(p.get("playerId"))
        golfer = golfer_map.get(gid)
        if not golfer:
            continue
        status = safe_str(p.get("status"))
        made_cut = status.lower() not in ("cut", "wd", "dq")
        if golfer.id in existing_entries:
            e = existing_entries[golfer.id]
            e.status = status
            e.made_cut = made_cut
            entry_to_update.append(e)
        else:
            entry_to_create.append(EventEntry(
                event=event, golfer=golfer,
                status=status, made_cut=made_cut
            ))

    if entry_to_create:
        EventEntry.objects.bulk_create(entry_to_create, ignore_conflicts=True)
    if entry_to_update:
        EventEntry.objects.bulk_update(entry_to_update, ["status", "made_cut"])

    # ------------------------------------------------------------------
    # 3. Upsert GolferScore rows in bulk
    # ------------------------------------------------------------------
    # Load existing scores for this event
    existing_scores = {
        (s.golfer_id, s.round): s
        for s in GolferScore.objects.filter(event=event)
    }

    scores_to_create = []
    scores_to_update = []

    for p in players:
        gid = safe_str(p.get("playerId"))
        golfer = golfer_map.get(gid)
        if not golfer:
            continue

        position = safe_str(p.get("position"))
        total_to_par = safe_int(p.get("total"))
        thru_raw = safe_str(p.get("thru"))
        # Normalise thru: "F" stays "F", numbers stay, else None
        if thru_raw in ("", "-"):
            thru = None
        else:
            thru = thru_raw

        for rd in p.get("rounds", []):
            round_num = safe_int(rd.get("roundId"))
            if not round_num:
                continue
            strokes = safe_int(rd.get("strokes"))
            round_score = safe_int(rd.get("scoreToPar"))
            is_current = (round_num == current_round)

            key = (golfer.id, round_num)
            defaults = {
                "score": strokes,
                "round_score": round_score,
                "thru": thru if is_current else None,
                "position": position if is_current else "",
                "total_score": total_to_par,  # store on all rounds, view uses latest non-None
            }

            if key in existing_scores:
                s = existing_scores[key]
                for k, v in defaults.items():
                    setattr(s, k, v)
                scores_to_update.append(s)
            else:
                scores_to_create.append(GolferScore(
                    golfer=golfer, event=event, round=round_num, **defaults
                ))

    if scores_to_create:
        GolferScore.objects.bulk_create(scores_to_create, ignore_conflicts=True)
    if scores_to_update:
        GolferScore.objects.bulk_update(
            scores_to_update,
            ["score", "round_score", "thru", "position", "total_score"]
        )

    # ------------------------------------------------------------------
    # 4. Update event status and round
    # ------------------------------------------------------------------
    # If we got leaderboard data, tournament is definitely not "Scheduled"
    if event_status:
        event.status = event_status
    elif saved > 0:
        # API didn't return a status but we have scores -- mark as In Progress
        event.status = "In Progress"
    event.current_round = current_round
    event.save(update_fields=["status", "current_round"])

    saved = len(golfer_data)
    print(f"  {saved} golfers | Round {current_round} | Status: {event_status}")
    return saved


def apply_missed_cut_fines(event, current_round):
    """
    After round 2 completes, charge missed cut fines to players
    and add them to the secondary pot for each active game.
    Only runs once per game (checks if fines already applied).
    """
    if current_round < 3:
        return  # Cut not yet happened

    from golf.models import GolfGame, DraftPick, GolfGameEntry
    from bank.services import apply_batch
    from decimal import Decimal

    games = GolfGame.objects.filter(
        event=event,
        status=GolfGame.Status.ACTIVE,
    )

    for game in games:
        # Check if fines already applied for this game
        from golf.models import GolfGameEntry
        entries_with_fines = GolfGameEntry.objects.filter(
            game=game, total_fines__gt=0
        )
        # Only apply once - if any entry already has fines, skip
        if entries_with_fines.exists():
            continue

        # Find picks where the golfer missed the cut
        cut_picks = DraftPick.objects.filter(
            game=game,
            game_entry__game=game,
        ).select_related("golfer", "game_entry__user")

        # Update made_cut on picks from EventEntry
        from golf.models import EventEntry
        entry_status = {
            ee.golfer_id: ee.made_cut
            for ee in EventEntry.objects.filter(event=event)
        }

        missed_cut_users = set()
        for pick in cut_picks:
            made_cut = entry_status.get(pick.golfer_id)
            if made_cut is False:  # explicitly missed
                pick.made_cut = False
                pick.save(update_fields=["made_cut"])
                missed_cut_users.add(pick.game_entry.user)

        if not missed_cut_users:
            continue

        # Charge fines and add to secondary pot via apply_batch
        fine_amount = game.missed_cut_fine
        total_fines = fine_amount * len(missed_cut_users)

        apply_batch(
            group=game.group,
            entrants=list(missed_cut_users),
            winners=[],
            entry_fee=fine_amount,
            prize_pool=Decimal("0.00"),
            description=f"Golf missed cut fines - {event.name} (#{game.id})",
        )

        # Record fines on GolfGameEntry
        for pick in cut_picks:
            if pick.game_entry.user in missed_cut_users:
                entry = GolfGameEntry.objects.get(
                    game=game, user=pick.game_entry.user
                )
                entry.total_fines = fine_amount
                entry.save(update_fields=["total_fines"])

        # Add fines to rollover/secondary pot
        from golf.models import RolloverPot
        rollover, _ = RolloverPot.objects.get_or_create(
            group=game.group,
            defaults={"balance": Decimal("0.00")}
        )
        rollover.balance += total_fines
        rollover.save(update_fields=["balance"])

        print(f"  Applied fines: {len(missed_cut_users)} players x GBP{fine_amount} = GBP{total_fines}")


class Command(BaseCommand):
    help = "Fetch live leaderboard scores for active golf events."

    def add_arguments(self, parser):
        parser.add_argument("--event_id", type=str, help="tourn_id to update a single event.")

    def handle(self, *args, **options):
        from datetime import timedelta

        event_id = options.get("event_id")
        if event_id:
            events = GolfEvent.objects.filter(tourn_id=event_id).select_related("tour")
        else:
            today = now()
            events = GolfEvent.objects.filter(
                start_date__lte=today + timedelta(days=1),
                end_date__gte=today,
            ).select_related("tour")

        if not events.exists():
            self.stdout.write("No active events to update.")
            return

        for event in events:
            self.stdout.write(f"Fetching: {event.name} ({event.tourn_id})")
            data = fetch_leaderboard(event)
            if data:
                count = save_leaderboard(event, data)
                self.stdout.write(self.style.SUCCESS(f"  Done: {count} golfers"))
                # Apply missed cut fines after R2
                current_round = safe_int(data.get("roundId")) or event.current_round or 1
                if current_round >= 3:
                    self.stdout.write("  Checking missed cut fines...")
                    apply_missed_cut_fines(event, current_round)

        self.stdout.write(self.style.SUCCESS("Leaderboard update complete."))
