"""Bounded, read-only Admin catalog access using the request-owned client.

Requires migration 0009. Caller must establish fresh Admin authorization.
RLS independently restricts row visibility; no client or token is created here.
"""
from dataclasses import dataclass, field
from datetime import datetime
import math
import re

import httpx
from postgrest.exceptions import APIError

from normal_auth_coordinator import AuthenticatedContext
from place_model import CATEGORIES
from places_service import TOURISM_FIELDS, PlacesConsistencyError, _tourism_metadata

STATUSES = ('published', 'draft', 'archived')
PAGE_SIZE = 25
MAX_OFFSET = 2147483647 - PAGE_SIZE
PROJECTION = 'name,slug,category,status,address,updated_at,latitude,longitude'
DETAIL_PROJECTION = PROJECTION + ',description,image_url,created_at'
LIST_TOURISM_FIELDS = ('tourism_type', 'tourism_category')
CATALOG_PAGE_SIZE = 200
MAX_CATALOG_ROWS = 2000


class AdminPlacesError(Exception):
    def __init__(self):
        super().__init__('Destination information is temporarily unavailable.')


class AdminPlacesFilterError(ValueError):
    def __init__(self):
        super().__init__('Invalid destination filter or search.')


@dataclass(frozen=True)
class AdminPlace:
    name: str
    slug: str
    category: str
    status: str
    address: str
    updated_at: datetime
    latitude: float | None = field(default=None, kw_only=True)
    longitude: float | None = field(default=None, kw_only=True)
    tourism_type: str | None = field(default=None, kw_only=True)
    tourism_category: str | None = field(default=None, kw_only=True)
    tourism_hours_status: str | None = field(default=None, kw_only=True)
    tourism_metadata_available: bool = field(default=False, kw_only=True)

    @property
    def has_coordinates(self):
        return self.latitude is not None and self.longitude is not None

    @property
    def is_test_record(self):
        return self.slug.startswith('rosago-test-v1-')


@dataclass(frozen=True)
class AdminPlaceDetail(AdminPlace):
    description: str
    image_url: str | None
    created_at: datetime
    tourism_opening_hours_raw: str | None = field(default=None, kw_only=True)
    tourism_closing_hours_raw: str | None = field(default=None, kw_only=True)
    tourism_source: str | None = field(default=None, kw_only=True)
    tourism_source_row: int | None = field(default=None, kw_only=True)


def get_destination(context, slug, *, tourism_metadata_enabled=False):
    """Read one exact slug with the request-owned Admin client; never write."""
    _context(context)
    if (type(slug) is not str or not 1 <= len(slug) <= 120
            or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug)):
        return None
    projection = _projection(DETAIL_PROJECTION, TOURISM_FIELDS, tourism_metadata_enabled)
    response = _execute(context.client.table('places').select(projection)
                        .eq('slug', slug).limit(1))
    data = getattr(response, 'data', None)
    if type(data) is not list or len(data) > 1:
        raise AdminPlacesError()
    if not data:
        return None
    row = data[0]
    if type(row) is not dict or set(row) != set(projection.split(',')):
        raise AdminPlacesError()
    for field, maximum in (('name', 150), ('address', 500), ('description', 3000)):
        value = row[field]
        if type(value) is not str or not 1 <= len(value) <= maximum or value != value.strip():
            raise AdminPlacesError()
    if (row['slug'] != slug or type(row['category']) is not str
            or row['category'] not in CATEGORIES or type(row['status']) is not str
            or row['status'] not in STATUSES):
        raise AdminPlacesError()
    _coordinates(row)
    image = row['image_url']
    if image is not None and (type(image) is not str or not 9 <= len(image) <= 2048
            or image != image.strip() or not image.startswith('https://')):
        raise AdminPlacesError()
    timestamps = {}
    for field in ('created_at', 'updated_at'):
        try:
            value = datetime.fromisoformat(row[field]) if type(row[field]) is str else None
        except ValueError:
            value = None
        if value is None or value.tzinfo is None or value.utcoffset() is None:
            raise AdminPlacesError()
        timestamps[field] = value
    return AdminPlaceDetail(**(row | timestamps | _metadata(row)),
                           tourism_metadata_available=tourism_metadata_enabled)


def _projection(base, fields, enabled):
    if type(enabled) is not bool:
        raise AdminPlacesError()
    return base + (',' + ','.join(fields) if enabled else '')


def _metadata(row):
    try:
        return _tourism_metadata(row)
    except PlacesConsistencyError:
        pass
    raise AdminPlacesError() from None


def _coordinates(row):
    for key, maximum in (('latitude', 90), ('longitude', 180)):
        value = row[key]
        if value is not None and (type(value) not in (int, float)
                or not -maximum <= value <= maximum or not math.isfinite(value)):
            raise AdminPlacesError()
    if (row['latitude'] is None) != (row['longitude'] is None):
        raise AdminPlacesError()


def _context(context):
    if type(context) is not AuthenticatedContext or context.client is None:
        raise AdminPlacesError()


def _execute(query):
    query = query.retry(False)
    try:
        return query.execute()
    except (APIError, httpx.HTTPError, ValueError):
        # The installed SDK parses Content-Range with int() during execute().
        # Translate malformed response counts without hiding query-building bugs.
        pass
    raise AdminPlacesError() from None


def destination_counts(context):
    """Exact HEAD counts, never inferred from a page. Independent snapshots."""
    _context(context)
    result = {}
    for status in (None, *STATUSES):
        query = context.client.table('places').select('id', count='exact', head=True)
        if status is not None:
            query = query.eq('status', status)
        response = _execute(query)
        count = getattr(response, 'count', None)
        if type(count) is not int or count < 0 or getattr(response, 'data', None) != []:
            raise AdminPlacesError()
        result[status or 'total'] = count
    return result


def _list_row(row, *, tourism_metadata_enabled=False, include_hours=False):
    fields = LIST_TOURISM_FIELDS + (('tourism_hours_status',) if include_hours else ())
    projection = _projection(PROJECTION, fields, tourism_metadata_enabled)
    if type(row) is not dict or set(row) != set(projection.split(',')):
        raise AdminPlacesError()
    for key, maximum in (('name', 150), ('slug', 120), ('address', 500)):
        value = row[key]
        if type(value) is not str or not 1 <= len(value) <= maximum or value != value.strip():
            raise AdminPlacesError()
    if (not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', row['slug'])
            or type(row['category']) is not str or row['category'] not in CATEGORIES
            or type(row['status']) is not str or row['status'] not in STATUSES):
        raise AdminPlacesError()
    try:
        updated = datetime.fromisoformat(row['updated_at']) if type(row['updated_at']) is str else None
    except ValueError:
        updated = None
    if updated is None or updated.tzinfo is None or updated.utcoffset() is None:
        raise AdminPlacesError()
    _coordinates(row)
    metadata = _metadata(row)
    return AdminPlace(**(row | {'updated_at': updated}),
                      **{key: metadata[key] for key in fields if key not in row},
                      tourism_metadata_available=tourism_metadata_enabled)


def list_destinations(context, *, status=None, offset=0, tourism_metadata_enabled=False):
    """Legacy bounded page read retained for existing service callers."""
    _context(context)
    if ((status is not None and (type(status) is not str or status not in STATUSES))
            or type(offset) is not int or not 0 <= offset <= MAX_OFFSET):
        raise AdminPlacesError()
    projection = _projection(PROJECTION, LIST_TOURISM_FIELDS, tourism_metadata_enabled)
    query = context.client.table('places').select(projection)
    if status is not None:
        query = query.eq('status', status)
    response = _execute(query.order('slug').range(offset, offset + PAGE_SIZE - 1))
    data = getattr(response, 'data', None)
    if type(data) is not list or len(data) > PAGE_SIZE:
        raise AdminPlacesError()
    rows = tuple(_list_row(row, tourism_metadata_enabled=tourism_metadata_enabled) for row in data)
    if len({row.slug for row in rows}) != len(rows) or any(status and row.status != status for row in rows):
        raise AdminPlacesError()
    return rows


@dataclass(frozen=True)
class DestinationCatalogPage:
    rows: tuple[AdminPlace, ...]
    total: int
    matching: int
    summary: dict


def validate_catalog_filters(*, q='', status=None, category=None, tourism_type=None,
                             coordinates=None, offset=0, tourism_metadata_enabled=False):
    """Literal search only; user text never becomes a PostgREST expression."""
    if (type(q) is not str or len(q) > 150
            or any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in q)
            or type(offset) is not int or not 0 <= offset <= MAX_OFFSET
            or type(tourism_metadata_enabled) is not bool):
        raise AdminPlacesFilterError()
    for value, allowed in ((status, STATUSES), (category, CATEGORIES),
                           (tourism_type, ('Local', 'Common', 'unclassified')),
                           (coordinates, ('with', 'missing'))):
        if value is not None and (type(value) is not str or value not in allowed):
            raise AdminPlacesFilterError()
    if tourism_type is not None and not tourism_metadata_enabled:
        raise AdminPlacesFilterError()
    return dict(q=q.strip(), status=status, category=category, tourism_type=tourism_type,
                coordinates=coordinates, offset=offset, tourism_metadata_enabled=tourism_metadata_enabled)


def read_catalog(context, *, tourism_metadata_enabled=False, include_hours=False):
    """Complete bounded Admin catalog read shared by review and insights.

    Optional hours status is projected once per page, never through N+1 detail
    reads. Exact counts, row validation and duplicate checks apply to both callers.
    """
    _context(context)
    if type(include_hours) is not bool:
        raise AdminPlacesError()
    enabled = tourism_metadata_enabled
    fields = LIST_TOURISM_FIELDS + (('tourism_hours_status',) if include_hours else ())
    projection = _projection(PROJECTION, fields, enabled)
    rows, seen, expected = [], set(), None
    while expected is None or len(rows) < expected:
        offset = len(rows)
        response = _execute(context.client.table('places').select(projection, count='exact')
                            .order('slug').range(offset, offset + CATALOG_PAGE_SIZE - 1))
        count, data = getattr(response, 'count', None), getattr(response, 'data', None)
        if (type(count) is not int or not 0 <= count <= MAX_CATALOG_ROWS
                or (expected is not None and count != expected) or type(data) is not list
                or len(data) != min(CATALOG_PAGE_SIZE, max(0, count - offset))):
            raise AdminPlacesError()
        expected = count
        for row in data:
            place = _list_row(row, tourism_metadata_enabled=enabled, include_hours=include_hours)
            if place.slug in seen:
                raise AdminPlacesError()
            seen.add(place.slug)
            rows.append(place)
        if not expected:
            break
    # Stable display independent of database text collation.
    rows.sort(key=lambda place: place.slug)
    return tuple(rows)


def catalog_page(context, **filters):
    """Literal filtering and pagination over the same complete catalog read."""
    filters = validate_catalog_filters(**filters)
    enabled = filters['tourism_metadata_enabled']
    rows = read_catalog(context, tourism_metadata_enabled=enabled)
    summary = {status: sum(place.status == status for place in rows) for status in STATUSES}
    summary.update(local=sum(p.tourism_type == 'Local' for p in rows) if enabled else None,
                   common=sum(p.tourism_type == 'Common' for p in rows) if enabled else None,
                   missing_coordinates=sum(not p.has_coordinates for p in rows))
    selected = []
    needle = filters['q'].casefold()
    for place in rows:
        if filters['status'] is not None and place.status != filters['status']:
            continue
        if filters['category'] is not None and place.category != filters['category']:
            continue
        if filters['tourism_type'] is not None:
            required = None if filters['tourism_type'] == 'unclassified' else filters['tourism_type']
            if place.tourism_type != required:
                continue
        if filters['coordinates'] == 'with' and not place.has_coordinates:
            continue
        if filters['coordinates'] == 'missing' and place.has_coordinates:
            continue
        category_label = 'Industrial Tourism' if place.category == 'industrial' else place.category
        if needle and not any(needle in value.casefold() for value in
                              (place.name, place.address, category_label, place.tourism_category or '')):
            continue
        selected.append(place)
    offset = filters['offset']
    return DestinationCatalogPage(tuple(selected[offset:offset + PAGE_SIZE]), len(rows), len(selected), summary)
