"""Pure untimed layout for both personalized and manual destination selections.

Callers establish ownership, publication, catalog validity, completeness and source
freshness. Like recommendation_engine, this boundary checks Place identity/category
but does not revalidate unused catalog fields. No source version authorizes a build.
Only explicit input_order and inclusive dates determine arrangement. Equal counts
are a layout policy, never evidence that visits fit the requested daily window.
"""
from dataclasses import dataclass
from datetime import date, timedelta
import re
from uuid import UUID

from place_model import CATEGORIES, Place


POLICY_VERSION = 'preserve-order-equal-count-v1'
# Engineering bound, not a per-day feasibility limit or a database membership cap.
MAX_DESTINATIONS = 100
MAX_INPUT_ORDER = 2147483647
TRANSPORTATION = ('walking', 'bicycle', 'motorcycle', 'private_car',
                  'public_transport', 'ride_hailing', 'mixed_transport')
TRIP_PACES = ('relaxed', 'balanced', 'packed')
# Baseline unanswered visit-plan questions. Cost remains unknown even without a
# supplied budget; budget feasibility is reported separately only when supplied.
UNRESOLVED_CONSTRAINTS = (
    'visit_duration', 'time_feasibility', 'operating_hours', 'cost',
    'transport_compatibility', 'travel_time', 'trip_pace',
)
_TIME = re.compile(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]')
_VERSION = re.compile(r'[A-Za-z0-9_.:-]{1,128}')


class ItineraryBuildInputError(ValueError):
    def __init__(self):
        super().__init__('Invalid itinerary build input.')


@dataclass(frozen=True, slots=True)
class PlanningConstraints:
    start_date: date
    end_date: date
    daily_start_time: str
    daily_end_time: str
    transportation: str
    trip_pace: str
    timezone: str = 'Asia/Manila'
    # PHP centavos per person for the whole plan; None means unspecified.
    budget_centavos: int | None = None


@dataclass(frozen=True, slots=True)
class SelectedDestination:
    place: Place
    input_order: int
    source: str
    keep_place: bool


@dataclass(frozen=True, slots=True)
class SourceVersion:
    """Inert draft/trip identifier plus bounded revision/fingerprint text.

    This is not a credential or proof of freshness. An adapter must compare it
    to current source state later; the builder never interprets its version.
    """
    kind: str
    version: str


@dataclass(frozen=True, slots=True)
class ItineraryBuildRequest:
    constraints: PlanningConstraints
    destinations: tuple[SelectedDestination, ...]
    source_version: SourceVersion


@dataclass(frozen=True, slots=True)
class ItineraryStop:
    place_id: str
    order: int
    source: str
    keep_place: bool


@dataclass(frozen=True, slots=True)
class ItineraryDay:
    date: date
    stops: tuple[ItineraryStop, ...]


@dataclass(frozen=True, slots=True)
class ItineraryPlan:
    policy_version: str
    source_version: SourceVersion
    constraints: PlanningConstraints
    days: tuple[ItineraryDay, ...]
    unresolved_constraints: tuple[str, ...]


def _validate(request):
    if type(request) is not ItineraryBuildRequest or type(request.constraints) is not PlanningConstraints:
        raise ItineraryBuildInputError()
    constraints = request.constraints
    if (type(constraints.start_date) is not date or type(constraints.end_date) is not date
            or not 0 <= (constraints.end_date - constraints.start_date).days <= 6):
        raise ItineraryBuildInputError()
    for value in (constraints.daily_start_time, constraints.daily_end_time):
        if type(value) is not str or not _TIME.fullmatch(value):
            raise ItineraryBuildInputError()
    if (constraints.daily_start_time >= constraints.daily_end_time
            or type(constraints.transportation) is not str or constraints.transportation not in TRANSPORTATION
            or type(constraints.trip_pace) is not str or constraints.trip_pace not in TRIP_PACES
            or type(constraints.timezone) is not str or constraints.timezone != 'Asia/Manila'):
        raise ItineraryBuildInputError()
    if constraints.budget_centavos is not None and (
            type(constraints.budget_centavos) is not int or not 0 <= constraints.budget_centavos <= 10000000):
        raise ItineraryBuildInputError()
    version = request.source_version
    if (type(version) is not SourceVersion or type(version.kind) is not str
            or version.kind not in ('draft', 'trip') or type(version.version) is not str
            or not _VERSION.fullmatch(version.version)):
        raise ItineraryBuildInputError()
    if type(request.destinations) is not tuple or not 1 <= len(request.destinations) <= MAX_DESTINATIONS:
        raise ItineraryBuildInputError()
    ids, orders = set(), set()
    for destination in request.destinations:
        if (type(destination) is not SelectedDestination or type(destination.place) is not Place
                or type(destination.input_order) is not int
                or not 1 <= destination.input_order <= MAX_INPUT_ORDER
                or destination.input_order in orders
                or type(destination.source) is not str or destination.source not in ('manual', 'recommended')
                or type(destination.keep_place) is not bool):
            raise ItineraryBuildInputError()
        place = destination.place
        if type(place.id) is not str:
            raise ItineraryBuildInputError()
        try:
            canonical = str(UUID(place.id))
        except ValueError:
            raise ItineraryBuildInputError() from None
        if (place.id != canonical or canonical in ids
                or type(place.category) is not str or place.category not in CATEGORIES):
            raise ItineraryBuildInputError()
        ids.add(canonical)
        orders.add(destination.input_order)


def build_itinerary(request: ItineraryBuildRequest) -> ItineraryPlan:
    """Validate, preserve every selected Place, and group in explicit input order.

    Reject empty, mutable, oversized, duplicate or inconsistent input; never
    repair, truncate or filter destinations. Source and keep_place are metadata
    only, including when keep_place is false. Output order is global 1..N.
    """
    _validate(request)
    ordered = sorted(request.destinations, key=lambda destination: destination.input_order)
    stops = tuple(ItineraryStop(destination.place.id, index, destination.source, destination.keep_place)
                  for index, destination in enumerate(ordered, 1))
    day_count = (request.constraints.end_date - request.constraints.start_date).days + 1
    base, remainder = divmod(len(stops), day_count)
    days = []
    offset = 0
    for index in range(day_count):
        count = base + int(index < remainder)
        days.append(ItineraryDay(request.constraints.start_date + timedelta(days=index), stops[offset:offset + count]))
        offset += count
    unresolved = UNRESOLVED_CONSTRAINTS
    if request.constraints.budget_centavos is not None:
        unresolved += ('budget_feasibility',)
    return ItineraryPlan(POLICY_VERSION, request.source_version, request.constraints, tuple(days), unresolved)
