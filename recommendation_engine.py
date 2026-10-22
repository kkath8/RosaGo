"""Category-only personalized candidates; no itinerary generation or I/O.

Callers supply a validated preference dict and a bounded list/tuple of published
Places. Publication and full structural validation remain caller responsibilities.
Only interests, Place identity, and category are checked here. No other preference
or Place attribute is read, interpreted, or retained in the result.
"""
from dataclasses import dataclass
from uuid import UUID

from place_model import CATEGORIES, Place


POLICY_VERSION = 'category-interest-v1'
# Matches the catalog service's maximum page size; no silent truncation.
MAX_CANDIDATES = 100
CATEGORY_INTEREST_MATCH = 'CATEGORY_INTEREST_MATCH'
UNKNOWN_CONSTRAINTS = (
    'cost', 'operating_hours', 'visit_duration', 'environment',
    'companion_suitability', 'transport_compatibility',
)


class RecommendationInputError(ValueError):
    def __init__(self):
        super().__init__('Invalid recommendation input.')


@dataclass(frozen=True, slots=True)
class MatchedSignal:
    kind: str
    category: str


@dataclass(frozen=True, slots=True)
class RecommendationCandidate:
    place_id: str
    category: str
    deterministic_score: int
    matched_signals: tuple[MatchedSignal, ...]
    unknown_constraints: tuple[str, ...] = UNKNOWN_CONSTRAINTS


@dataclass(frozen=True, slots=True)
class RecommendationResult:
    matched: tuple[RecommendationCandidate, ...]
    unmatched: tuple[RecommendationCandidate, ...]
    policy_version: str = POLICY_VERSION

    @property
    def ranked(self) -> tuple[RecommendationCandidate, ...]:
        return self.matched + self.unmatched

    @property
    def total_candidate_count(self) -> int:
        return len(self.matched) + len(self.unmatched)

    @property
    def match_count(self) -> int:
        return len(self.matched)


def rank_candidates(preferences: dict, places: list[Place] | tuple[Place, ...]) -> RecommendationResult:
    """Rank by category match descending, then canonical UUID ascending.

    Reject invalid interests, noncanonical/missing UUIDs, unsupported categories,
    duplicate identities, and unbounded/oversized collections as one fixed error.
    No partial result, fallback, normalization, or input mutation is performed.
    A valid nonselected category remains an explicitly unmatched alternative.
    """
    if type(preferences) is not dict:
        raise RecommendationInputError()
    interests = preferences.get('interests')
    if (type(interests) is not list or not 1 <= len(interests) <= len(CATEGORIES)
            or any(type(item) is not str or item not in CATEGORIES for item in interests)
            or len(set(interests)) != len(interests)):
        raise RecommendationInputError()
    if type(places) not in (list, tuple) or len(places) > MAX_CANDIDATES:
        raise RecommendationInputError()

    seen = set()
    candidates = []
    for place in places:
        if not isinstance(place, Place):
            raise RecommendationInputError()
        if type(place.id) is not str:
            raise RecommendationInputError()
        try:
            canonical_id = str(UUID(place.id))
        except ValueError:
            raise RecommendationInputError() from None
        if (place.id != canonical_id or canonical_id in seen
                or type(place.category) is not str or place.category not in CATEGORIES):
            raise RecommendationInputError()
        seen.add(canonical_id)
        match = place.category in interests
        signals = (MatchedSignal(CATEGORY_INTEREST_MATCH, place.category),) if match else ()
        candidates.append(RecommendationCandidate(canonical_id, place.category, int(match), signals))

    candidates.sort(key=lambda candidate: (-candidate.deterministic_score, candidate.place_id))
    return RecommendationResult(
        matched=tuple(candidate for candidate in candidates if candidate.deterministic_score == 1),
        unmatched=tuple(candidate for candidate in candidates if candidate.deterministic_score == 0),
    )
