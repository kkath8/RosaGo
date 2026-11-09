"""Pure initial suggestion counts and category diversity, never time feasibility."""
from datetime import date
from uuid import UUID

from itinerary_builder import MAX_DESTINATIONS
from recommendation_engine import MAX_CANDIDATES, RecommendationCandidate
from place_model import CATEGORIES
from destination_categories import category_matches
from itinerary_geography import coordinates, distance_km, visit_order

POLICY_VERSION = 'pace-count-category-tourism-cluster-v3'
DESTINATIONS_PER_DAY = {'relaxed': 2, 'balanced': 3, 'packed': 4}


class SelectionPolicyError(ValueError):
    def __init__(self):
        super().__init__('Invalid automatic selection input.')


def select_destinations(preferences, matched, *, place_count=None, places=()):
    """Select eligible category rounds, tourism tier, then developing cluster.

    Caller establishes publication and complete catalog eligibility.
    Each round represents each available category once. Within a category and
    tourism tier, mean distance to located selected stops breaks geographic ties.
    An unknown baseline candidate keeps its turn; it is never treated as distant.
    Without sufficient distinct locations, retain the previous policy exactly.
    """
    if type(preferences) is not dict or type(matched) is not tuple or len(matched) > MAX_CANDIDATES:
        raise SelectionPolicyError()
    interests = preferences.get('interests')
    pace = preferences.get('trip_pace')
    if (type(interests) is not list or not 1 <= len(interests) <= 7
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
                or type(candidate.category) is not str or not any(category_matches(candidate.category, interest) for interest in interests)
                or type(candidate.deterministic_score) is not int or candidate.deterministic_score != 1
                or type(candidate.tourism_priority) is not int or candidate.tourism_priority not in (0, 1, 2)):
            raise SelectionPolicyError()
        try:
            identity = str(UUID(candidate.place_id))
        except ValueError:
            raise SelectionPolicyError() from None
        if identity != candidate.place_id or identity in seen:
            raise SelectionPolicyError()
        seen.add(identity)
        groups.setdefault(candidate.category, []).append(candidate)
    if place_count is not None and (type(place_count) is not int or not 1 <= place_count <= MAX_DESTINATIONS):
        raise SelectionPolicyError()
    count = min(days * DESTINATIONS_PER_DAY[pace] if place_count is None else place_count,
                len(matched), MAX_DESTINATIONS, MAX_CANDIDATES)
    locations = {place.id: coordinates(place) for place in places
                 if place.id in seen and coordinates(place) is not None}
    if len(set(locations.values())) >= 2 and count:
        remaining = list(matched)
        chosen = []
        visits = {category: 0 for category in groups}
        while len(chosen) < count:
            # Coverage precedes tourism priority and geography. Exhausted
            # categories leave the round, allowing the requested count to fill.
            round_number = min(visits[c.category] for c in remaining)
            pool = [c for c in remaining if visits[c.category] == round_number]
            tier = min(c.tourism_priority for c in pool)
            pool = [c for c in pool if c.tourism_priority == tier]
            baseline = pool[0]
            anchors = [locations[c.place_id] for c in chosen if c.place_id in locations]
            located = [c for c in pool if c.place_id in locations]
            next_candidate = baseline
            if anchors and baseline.place_id in locations and len(located) >= 2:
                next_candidate = min(located, key=lambda c: (
                    sum(distance_km(locations[c.place_id], point) for point in anchors) / len(anchors),
                    c.place_id))
            chosen.append(next_candidate)
            remaining.remove(next_candidate)
            visits[next_candidate.category] += 1
        selected_ids = {c.place_id for c in chosen}
        selected_rank = tuple(c for c in matched if c.place_id in selected_ids)
        return visit_order(selected_rank, locations, identity=lambda c: c.place_id)
    selected = set()
    round_index = 0
    while len(selected) < count:
        for category in sorted((key for key in groups if round_index < len(groups[key])),
                               key=lambda key: (groups[key][round_index].tourism_priority, key)):
            if round_index < len(groups[category]):
                selected.add(groups[category][round_index].place_id)
                if len(selected) == count:
                    break
        round_index += 1
    return tuple(candidate for candidate in matched if candidate.place_id in selected)
