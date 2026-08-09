# lms/services/missing_picks.py
#
# This module previously contained a duplicate assign_missing_picks
# with incorrect field names (auto_pick_team_1 instead of auto_pick_team1).
# All logic is now consolidated in pick_resolution.py.
# This file is kept to avoid breaking any existing imports.

from lms.services.pick_resolution import (
    assign_missing_picks,
    handle_unresolved_postponed_picks,
    round_deadline_passed,
)

__all__ = [
    "assign_missing_picks",
    "handle_unresolved_postponed_picks",
    "round_deadline_passed",
]
