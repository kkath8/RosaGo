"""Pure initial suggestion counts and category diversity, never time feasibility."""
from datetime import date
from uuid import UUID

from itinerary_builder import MAX_DESTINATIONS
from recommendation_engine import MAX_CANDIDATES, RecommendationCandidate
from place_model import CATEGORIES

POLICY_VERSION = 'pace-count-category-round-robin-v1'
DESTINATIONS_PER_DAY = {'relaxed': 2, 'balanced': 3, 'packed': 4}


class SelectionPolicyError(ValueError):
    def __init__(self):
        super().__init__('Invalid automatic selection input.')


def select_destinations(preferences, matched):
    """Select from verified matched candidates; preserve their original order.

    Caller establishes publication and complete catalog eligibility. Only dates,
    pace, interests and candidate identity/category/score are used here.
    """
    if type(preferences) is not dict or type(matched) is not tuple or len(matched) > MAX_CANDIDATES:
        raise SelectionPolicyError()
    interests = preferences.get('interests')
    pace = preferences.get('trip_pace')
    if (type(interests) is not list or not 1 <= len(interests) <= len(CATEGORIES)
            or any(type(item) is not str or item not in CATEGORIES for item in interests)
            or len(set(interests)) != len(interests)
            or type(pace) is not str or pace not in DESTINATIONS_PER_DAY):
        raise SelectionPolicyError()
    dates = []
    for key in ('start_date', 'end_date'):
        value = preferences.get(key)
        try:
            parsed = date.fromisoformat(value) if type(value) is str else None
        except ValueError:
            parsed = None
        if parsed is None or parsed.isoformat() != value:
            raise SelectionPolicyError()
        dates.append(parsed)
    days = (dates[1] - dates[0]).days + 1
    if not 1 <= days <= 7:
        raise SelectionPolicyError()
    groups, seen = {}, set()
    for candidate in matched:
        if (type(candidate) is not RecommendationCandidate
                or type(candidate.place_id) is not str
                or type(candidate.category) is not str or candidate.category not in interests
                or type(candidate.deterministic_score) is not int or candidate.deterministic_score != 1):
            raise SelectionPolicyError()
        try:
            identity = str(UUID(candidate.place_id))
        except ValueError:
            raise SelectionPolicyError() from None
        if identity != candidate.place_id or identity in seen:
            raise SelectionPolicyError()
        seen.add(identity)
        groups.setdefault(candidate.category, []).append(candidate)
    count = min(days * DESTINATIONS_PER_DAY[pace], len(matched), MAX_DESTINATIONS, MAX_CANDIDATES)
    selected = set()
    round_index = 0
    while len(selected) < count:
        for category in sorted(groups):
            if round_index < len(groups[category]):
                selected.add(groups[category][round_index].place_id)
                if len(selected) == count:
                    break
        round_index += 1
    return tuple(candidate for candidate in matched if candidate.place_id in selected)
