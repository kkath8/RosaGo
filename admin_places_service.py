"""Bounded, read-only Admin catalog access using the request-owned client.

Requires migration 0009. Caller must establish fresh Admin authorization.
RLS independently restricts row visibility; no client or token is created here.
"""
from dataclasses import dataclass
from datetime import datetime
import re

import httpx
from postgrest.exceptions import APIError

from normal_auth_coordinator import AuthenticatedContext
from place_model import CATEGORIES

STATUSES = ('published', 'draft', 'archived')
PAGE_SIZE = 25
MAX_OFFSET = 2147483647 - PAGE_SIZE
PROJECTION = 'name,slug,category,status,address,updated_at'


class AdminPlacesError(Exception):
    def __init__(self):
        super().__init__('Destination information is temporarily unavailable.')


@dataclass(frozen=True)
class AdminPlace:
    name: str
    slug: str
    category: str
    status: str
    address: str
    updated_at: datetime

    @property
    def is_test_record(self):
        return self.slug.startswith('rosago-test-v1-')


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


def list_destinations(context, *, status=None, offset=0):
    _context(context)
    if ((status is not None and (type(status) is not str or status not in STATUSES))
            or type(offset) is not int or not 0 <= offset <= MAX_OFFSET):
        raise AdminPlacesError()
    query = context.client.table('places').select(PROJECTION)
    if status is not None:
        query = query.eq('status', status)
    response = _execute(query.order('slug').range(offset, offset + PAGE_SIZE - 1))
    data = getattr(response, 'data', None)
    if type(data) is not list or len(data) > PAGE_SIZE:
        raise AdminPlacesError()
    rows, slugs = [], set()
    for row in data:
        if type(row) is not dict or set(row) != set(PROJECTION.split(',')):
            raise AdminPlacesError()
        for field, maximum in (('name', 150), ('slug', 120), ('address', 500)):
            value = row[field]
            if type(value) is not str or not 1 <= len(value) <= maximum or value != value.strip():
                raise AdminPlacesError()
        if (not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', row['slug'])
                or row['slug'] in slugs or type(row['category']) is not str or row['category'] not in CATEGORIES
                or type(row['status']) is not str or row['status'] not in STATUSES
                or (status is not None and row['status'] != status)):
            raise AdminPlacesError()
        try:
            updated = datetime.fromisoformat(row['updated_at']) if type(row['updated_at']) is str else None
        except ValueError:
            updated = None
        if updated is None or updated.tzinfo is None or updated.utcoffset() is None:
            raise AdminPlacesError()
        slugs.add(row['slug'])
        rows.append(AdminPlace(row['name'], row['slug'], row['category'], row['status'], row['address'], updated))
    return tuple(rows)
