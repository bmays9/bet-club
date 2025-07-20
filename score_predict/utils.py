from itertools import groupby
from datetime import timedelta

def group_fixtures_by_consecutive_days(fixtures):
    fixtures = sorted(fixtures, key=lambda f: f.date)

    def get_group_key(fixture):
        date = fixture.date.date()
        weekday = date.weekday()
        iso_week = date.isocalendar()[1]

        if weekday in [1, 2, 3]:  # Tue–Thu
            return (iso_week, 'midweek')
        elif weekday in [4, 5, 6]:  # Fri–Sun
            return (iso_week, 'weekend')
        else:
            return None  # Skip Mon (0)

    grouped_by_type = []
    for key, group in groupby(fixtures, key=get_group_key):
        if key is None:
            continue  # Skip ungroupable fixtures
        group_list = list(group)

        # Now split into consecutive-day blocks
        current_block = []
        previous_date = None

        for fixture in group_list:
            current_date = fixture.date.date()
            if not previous_date or (current_date - previous_date) <= timedelta(days=1):
                current_block.append(fixture)
            else:
                if len(current_block) >= 2:
                    grouped_by_type.append(current_block)
                current_block = [fixture]
            previous_date = current_date

        if len(current_block) >= 2:
            grouped_by_type.append(current_block)

    return grouped_by_type
