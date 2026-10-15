"""Own-trip operations using an already active, caller-owned auth context.

No authentication, client lifetime, or HTTP presentation belongs here. Separate
bounded detail reads are not a snapshot. A failed write may have committed:
never automatically replay it, including after response validation failures.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
import unicodedata
from uuid import UUID

import httpx
from postgrest.exceptions import APIError
from postgrest.types import ReturnMethod

from normal_auth_coordinator import AuthenticatedContext
from places_service import Place, PROJECTION as PLACE_PROJECTION, PlacesConsistencyError, parse_place_row


TRIP_PROJECTION = 'id,user_id,name,visit_date,created_at,updated_at'
MEMBERSHIP_PROJECTION = 'trip_id,place_id,position,created_at'
MAX_POSITION = 2147483647


class TripServiceError(Exception):
    """Base for fixed public failures."""


class TripValidationError(TripServiceError):
    def __init__(self):
        super().__init__('Invalid trip input.')


class TripNotFoundError(TripServiceError):
    def __init__(self):
        super().__init__('Trip not found.')


class TripOperationRejectedError(TripServiceError):
    def __init__(self):
        super().__init__('Trip operation was rejected.')


class TripUnavailableError(TripServiceError):
    def __init__(self):
        super().__init__('Trip operation could not be confirmed.')


class TripConsistencyError(TripServiceError):
    def __init__(self):
        super().__init__('Trip data is inconsistent.')


@dataclass(frozen=True, slots=True, repr=False)
class Trip:
    id: str
    name: str
    visit_date: date | None
    created_at: datetime
    updated_at: datetime

    def __repr__(self):
        return '<Trip redacted>'


@dataclass(frozen=True, slots=True, repr=False)
class TripPlace:
    trip_id: str
    place_id: str
    position: int
    created_at: datetime
    place: Place | None

    def __repr__(self):
        return '<TripPlace redacted>'


@dataclass(frozen=True, slots=True, repr=False)
class TripDetail:
    trip: Trip
    memberships: tuple[TripPlace, ...]
    next_after_position: int | None

    def __repr__(self):
        return '<TripDetail redacted>'


def _uuid(value, error=TripValidationError):
    if type(value) is str and value and value == value.strip():
        try:
            return str(UUID(value))
        except ValueError:
            pass
    raise error() from None


def _context(context):
    if (not isinstance(context, AuthenticatedContext)
            or not callable(getattr(context.client, 'table', None))
            or not callable(getattr(context.client, 'rpc', None))):
        raise TypeError('An active AuthenticatedContext is required.')
    return _uuid(context.user_id, lambda: TypeError('An active AuthenticatedContext is required.'))


def _integer(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def _name(value, error=TripValidationError, *, normalize=True):
    if type(value) is str:
        # Reject controls even when trimming would otherwise remove them.
        if not any(unicodedata.category(c) in ('Cc', 'Cs') for c in value):
            trimmed = value.strip()
            if 1 <= len(trimmed) <= 100 and (normalize or trimmed == value):
                return trimmed
    raise error()


def _input_metadata(name, visit_date):
    name = _name(name)
    if visit_date is not None and type(visit_date) is not date:
        raise TripValidationError()
    return {'name': name, 'visit_date': visit_date.isoformat() if visit_date is not None else None}


def _date(value):
    if value is None:
        return None
    if type(value) is str:
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            pass
        else:
            if parsed.isoformat() == value:
                return parsed
    raise TripConsistencyError() from None


def _timestamp(value):
    if type(value) is str:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            pass
        else:
            if parsed.tzinfo is not None and parsed.utcoffset() is not None:
                return parsed
    raise TripConsistencyError() from None


def _row(row, projection):
    if not isinstance(row, Mapping) or not set(projection.split(',')) <= row.keys():
        raise TripConsistencyError()


def _rows(response, maximum):
    data = getattr(response, 'data', None)
    if not isinstance(data, list) or len(data) > maximum:
        raise TripConsistencyError()
    return data


def _execute(query):
    try:
        return query.retry(False).execute()
    except APIError as error:
        code = getattr(error, 'code', None)
        failure = (TripNotFoundError() if code == 'P0002' else
                   TripOperationRejectedError() if code == '22023' else TripUnavailableError())
    except httpx.HTTPError:
        failure = TripUnavailableError()
    # Outside the handler: do not retain provider diagnostics in context/cause.
    raise failure from None


def _trip(row, owner, trip_id=None):
    _row(row, TRIP_PROJECTION)
    identity = _uuid(row['id'], TripConsistencyError)
    if (_uuid(row['user_id'], TripConsistencyError) != owner
            or (trip_id is not None and identity != trip_id)):
        raise TripConsistencyError()
    return Trip(identity, _name(row['name'], TripConsistencyError, normalize=False),
                _date(row['visit_date']), _timestamp(row['created_at']), _timestamp(row['updated_at']))


def _one_trip(response, owner, trip_id=None):
    rows = _rows(response, 1)
    return _trip(rows[0], owner, trip_id) if rows else None


def list_user_trips(context: AuthenticatedContext, *, limit=50, offset=0) -> tuple[Trip, ...]:
    """Return one metadata page, newest first with an ID tie-breaker."""
    owner = _context(context)
    if not _integer(limit, 1, 100) or not _integer(offset, 0, MAX_POSITION - limit + 1):
        raise TripValidationError()
    response = _execute(context.client.table('trips').select(TRIP_PROJECTION)
                        .eq('user_id', owner).order('created_at', desc=True)
                        .order('id', desc=True).range(offset, offset + limit - 1))
    trips = tuple(_trip(row, owner) for row in _rows(response, limit))
    if (len({trip.id for trip in trips}) != len(trips)
            or list(trips) != sorted(trips, key=lambda trip: (trip.created_at, trip.id), reverse=True)):
        raise TripConsistencyError()
    return trips


def get_user_trip(context: AuthenticatedContext, trip_id, *, membership_limit=50,
                  after_position=0) -> TripDetail | None:
    """Read metadata and one membership page, hydrating only published places.

    A nonempty page exposes its last position as a continuation cursor, not a
    promise of more results. An empty page terminates traversal. Concurrent
    membership edits can change subsequent pages; no snapshot is promised.
    """
    owner = _context(context)
    trip_id = _uuid(trip_id)
    if not _integer(membership_limit, 1, 100) or not _integer(after_position, 0, MAX_POSITION):
        raise TripValidationError()
    trip = _one_trip(_execute(context.client.table('trips').select(TRIP_PROJECTION)
                             .eq('id', trip_id).eq('user_id', owner).limit(2)), owner, trip_id)
    if trip is None:
        return None
    rows = _rows(_execute(context.client.table('trip_places').select(MEMBERSHIP_PROJECTION)
                          .eq('trip_id', trip_id).gt('position', after_position)
                          .order('position', desc=False).limit(membership_limit)), membership_limit)
    memberships = []
    seen = set()
    previous = after_position
    for row in rows:
        _row(row, MEMBERSHIP_PROJECTION)
        place_id = _uuid(row['place_id'], TripConsistencyError)
        position = row['position']
        if (_uuid(row['trip_id'], TripConsistencyError) != trip_id or place_id in seen
                or not _integer(position, 1, MAX_POSITION) or position <= previous):
            raise TripConsistencyError()
        memberships.append(TripPlace(trip_id, place_id, position, _timestamp(row['created_at']), None))
        seen.add(place_id)
        previous = position
    if not memberships:
        return TripDetail(trip, (), None)
    place_rows = _rows(_execute(context.client.table('places').select(PLACE_PROJECTION)
                               .eq('status', 'published')
                               .in_('id', [m.place_id for m in memberships])
                               .limit(len(memberships))), len(memberships))
    places = {}
    slugs = set()
    for row in place_rows:
        try:
            place = parse_place_row(row)
        except PlacesConsistencyError:
            pass
        else:
            if place.id not in seen or place.id in places or place.slug in slugs:
                raise TripConsistencyError()
            places[place.id] = place
            slugs.add(place.slug)
            continue
        raise TripConsistencyError() from None
    return TripDetail(trip, tuple(TripPlace(m.trip_id, m.place_id, m.position, m.created_at,
                                          places.get(m.place_id)) for m in memberships), previous)


def _written_trip(response, owner, payload, trip_id=None):
    trip = _one_trip(response, owner, trip_id)
    if trip is None:
        if trip_id is not None:
            raise TripNotFoundError()
        raise TripConsistencyError()
    if (trip.name != payload['name']
            or (trip.visit_date.isoformat() if trip.visit_date is not None else None) != payload['visit_date']):
        raise TripConsistencyError()
    return trip


def create_trip(context: AuthenticatedContext, *, name, visit_date=None) -> Trip:
    """Insert editable metadata only; auth.uid() supplies ownership in the DB."""
    owner = _context(context)
    payload = _input_metadata(name, visit_date)
    return _written_trip(_execute(context.client.table('trips')
                                  .insert(payload, returning=ReturnMethod.representation)
                                  .select(TRIP_PROJECTION)), owner, payload)


def update_trip(context: AuthenticatedContext, trip_id, *, name, visit_date) -> Trip:
    """Replace both editable fields; None explicitly clears the visit date."""
    owner = _context(context)
    trip_id = _uuid(trip_id)
    payload = _input_metadata(name, visit_date)
    return _written_trip(_execute(context.client.table('trips')
                                  .update(payload, returning=ReturnMethod.representation)
                                  .eq('id', trip_id).eq('user_id', owner).select(TRIP_PROJECTION)),
                         owner, payload, trip_id)


def delete_trip(context: AuthenticatedContext, trip_id) -> None:
    """Delete one owned trip; the database cascades its memberships."""
    owner = _context(context)
    trip_id = _uuid(trip_id)
    rows = _rows(_execute(context.client.table('trips').delete(returning=ReturnMethod.representation)
                          .eq('id', trip_id).eq('user_id', owner).select('id,user_id')), 1)
    if not rows:
        raise TripNotFoundError()
    _row(rows[0], 'id,user_id')
    if (_uuid(rows[0]['id'], TripConsistencyError) != trip_id
            or _uuid(rows[0]['user_id'], TripConsistencyError) != owner):
        raise TripConsistencyError()


def _rpc(context, name, parameters):
    response = _execute(context.client.rpc(name, parameters))
    data = getattr(response, 'data', object())
    if data is not None and not (type(data) is list and not data):
        raise TripConsistencyError()


def add_place(context: AuthenticatedContext, trip_id, place_id) -> None:
    """Append a currently published place atomically through the existing RPC."""
    _context(context)
    _rpc(context, 'rosago_trip_add_place', {'p_trip_id': _uuid(trip_id), 'p_place_id': _uuid(place_id)})


def remove_place(context: AuthenticatedContext, trip_id, place_id) -> None:
    """Remove even an unavailable member; already absent is a successful no-op."""
    _context(context)
    _rpc(context, 'rosago_trip_remove_place', {'p_trip_id': _uuid(trip_id), 'p_place_id': _uuid(place_id)})


def reorder_places(context: AuthenticatedContext, trip_id, place_ids) -> None:
    """Submit a bounded permutation; the RPC validates current membership."""
    _context(context)
    trip_id = _uuid(trip_id)
    if type(place_ids) not in (list, tuple) or len(place_ids) > 1000:
        raise TripValidationError()
    ids = [_uuid(value) for value in place_ids]
    if len(set(ids)) != len(ids):
        raise TripValidationError()
    _rpc(context, 'rosago_trip_reorder_places', {'p_trip_id': trip_id, 'p_place_ids': ids})
