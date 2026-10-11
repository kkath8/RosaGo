"""Validated public catalog reads, independent of Flask and authentication.

Text is untrusted plain text, never HTML. Python str.strip() uses Unicode
whitespace, which can reject boundaries PostgreSQL's locale-dependent POSIX
[:space:] accepts. This is intentional stricter read validation, not DB repair.
Image URLs receive only the migration baseline check; no URL is fetched.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
import math
import re
from uuid import UUID

import httpx
from postgrest.exceptions import APIError


PROJECTION = 'id,name,slug,description,category,address,latitude,longitude,image_url,created_at,updated_at'
CATEGORIES = frozenset(('attraction', 'dining', 'shopping', 'accommodation', 'nature', 'heritage'))
_SLUG = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')
_FIELDS = frozenset(PROJECTION.split(','))


class PlacesServiceError(Exception):
    """Base for fixed-message public catalog failures."""


class PlacesValidationError(PlacesServiceError):
    def __init__(self):
        super().__init__('Invalid places query.')


class PlacesUnavailableError(PlacesServiceError):
    def __init__(self):
        super().__init__('Places are temporarily unavailable.')


class PlacesConsistencyError(PlacesServiceError):
    def __init__(self):
        super().__init__('Places data is inconsistent.')


@dataclass(frozen=True, slots=True, repr=False)
class Place:
    id: str
    name: str
    slug: str
    description: str
    category: str
    address: str
    latitude: float
    longitude: float
    image_url: str | None
    created_at: datetime
    updated_at: datetime

    def __repr__(self):
        return '<Place redacted>'


def _text(value, maximum):
    if (type(value) is not str or not 1 <= len(value) <= maximum
            or value != value.strip()):
        raise PlacesConsistencyError()
    return value


def _uuid(value):
    if type(value) is str and value and value == value.strip():
        try:
            return str(UUID(value))
        except ValueError:
            pass
    raise PlacesConsistencyError() from None


def _timestamp(value):
    if type(value) is str:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            pass
        else:
            if parsed.tzinfo is not None and parsed.utcoffset() is not None:
                return parsed
    raise PlacesConsistencyError() from None


def _coordinate(value, maximum):
    # Check bounds before float conversion, including arbitrarily large ints.
    if (type(value) not in (int, float) or not -maximum <= value <= maximum
            or not math.isfinite(value)):
        raise PlacesConsistencyError()
    return float(value)


def _place(row):
    if not isinstance(row, Mapping) or not _FIELDS <= row.keys():
        raise PlacesConsistencyError()
    slug = _text(row['slug'], 120)
    if not _SLUG.fullmatch(slug):
        raise PlacesConsistencyError()
    category = row['category']
    if type(category) is not str or category not in CATEGORIES:
        raise PlacesConsistencyError()
    image_url = row['image_url']
    if image_url is not None:
        _text(image_url, 2048)
        if not image_url.startswith('https://') or len(image_url) <= 8:
            raise PlacesConsistencyError()
    return Place(
        id=_uuid(row['id']), name=_text(row['name'], 150), slug=slug,
        description=_text(row['description'], 3000), category=category,
        address=_text(row['address'], 500),
        latitude=_coordinate(row['latitude'], 90),
        longitude=_coordinate(row['longitude'], 180), image_url=image_url,
        created_at=_timestamp(row['created_at']), updated_at=_timestamp(row['updated_at']))


def _rows(response, maximum):
    data = getattr(response, 'data', None)
    if not isinstance(data, list) or len(data) > maximum:
        raise PlacesConsistencyError()
    return data


def _lookup_slug(value):
    if type(value) is not str:
        raise PlacesValidationError()
    value = value.strip()
    if not value.isascii():
        raise PlacesValidationError()
    value = value.lower()
    if not 1 <= len(value) <= 120 or not _SLUG.fullmatch(value):
        raise PlacesValidationError()
    return value


def _unavailable(error):
    failure = PlacesUnavailableError()
    # Carry only our fixed cleanup diagnostic, never arbitrary provider notes.
    if 'Places client cleanup also failed.' in getattr(error, '__notes__', ()):
        failure.add_note('Places client cleanup also failed.')
    return failure


class PlacesService:
    """Factory returns a scoped public client; operations own its entire lifetime.

    Only recognized SDK/transport failures are translated, after cleanup.
    Programming errors and cancellation signals propagate unchanged.
    """

    def __init__(self, public_client_factory):
        if not callable(public_client_factory):
            raise TypeError('A scoped public client factory is required.')
        self._clients = public_client_factory

    def list_published(self, *, category: str | None = None,
                       limit: int = 50, offset: int = 0) -> tuple[Place, ...]:
        if ((category is not None and (type(category) is not str or category not in CATEGORIES))
                or type(limit) is not int or not 1 <= limit <= 100
                or type(offset) is not int or offset < 0):
            raise PlacesValidationError()
        try:
            with self._clients() as client:
                query = client.table('places').select(PROJECTION).eq('status', 'published')
                if category is not None:
                    query = query.eq('category', category)
                response = (query.order('slug', desc=False)
                            .range(offset, offset + limit - 1).retry(False).execute())
                places = tuple(_place(row) for row in _rows(response, limit))
                if (len({p.id for p in places}) != len(places)
                        or len({p.slug for p in places}) != len(places)
                        or (category is not None and any(p.category != category for p in places))):
                    raise PlacesConsistencyError()
            return places
        except (APIError, httpx.HTTPError) as error:
            failure = _unavailable(error)
        except BaseException as error:
            if 'Places operation also failed before cleanup.' not in getattr(error, '__notes__', ()):
                raise
            # contextlib can attach the body exception to a cleanup cancellation.
            # Preserve the signal, but detach that potentially sensitive chain.
            failure = error
            failure.__context__ = None
        raise failure from None

    def get_published_by_slug(self, slug: str) -> Place | None:
        slug = _lookup_slug(slug)
        try:
            with self._clients() as client:
                response = (client.table('places').select(PROJECTION)
                            .eq('status', 'published').eq('slug', slug)
                            .limit(2).retry(False).execute())
                rows = _rows(response, 1)
                place = _place(rows[0]) if rows else None
                if place is not None and place.slug != slug:
                    raise PlacesConsistencyError()
            return place
        except (APIError, httpx.HTTPError) as error:
            failure = _unavailable(error)
        except BaseException as error:
            if 'Places operation also failed before cleanup.' not in getattr(error, '__notes__', ()):
                raise
            failure = error
            failure.__context__ = None
        raise failure from None
