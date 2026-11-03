"""Published catalog health using only the caller-owned, authorized read client."""
from dataclasses import dataclass
import math
import re
from types import SimpleNamespace

from admin_places_service import AdminPlacesError, _context, _execute
from destination_weather_metadata import load_weather_catalog
from place_model import CATEGORIES

HEALTH_PROJECTION = 'slug,name,category,address,latitude,longitude'
HEALTH_PAGE_SIZE = 200
MAX_HEALTH_ROWS = 2000


@dataclass(frozen=True)
class CatalogHealth:
    published: int
    with_coordinates: int
    missing_coordinates: int
    local: int | None
    common: int | None
    unclassified: int | None
    weather_classified: int | None
    weather_unknown: int | None


def published_catalog_health(context, *, tourism_metadata_enabled=False):
    """Count a complete bounded published catalog, never a truncated first page.

    Exact counts on each page detect changed totals or server-side truncation.
    Separate reads are not a transactional snapshot. Optional Tourism columns
    follow the same deployment flag as the public catalog; disabled is not NULL.
    No user data, provider calls, client construction or mutations occur here.
    """
    _context(context)
    if type(tourism_metadata_enabled) is not bool:
        raise AdminPlacesError()
    projection = HEALTH_PROJECTION + (',tourism_type' if tourism_metadata_enabled else '')
    rows, seen, expected = [], set(), None
    while expected is None or len(rows) < expected:
        offset = len(rows)
        response = _execute(context.client.table('places').select(projection, count='exact')
                            .eq('status', 'published').order('slug')
                            .range(offset, offset + HEALTH_PAGE_SIZE - 1))
        count, page = getattr(response, 'count', None), getattr(response, 'data', None)
        if (type(count) is not int or not 0 <= count <= MAX_HEALTH_ROWS
                or (expected is not None and count != expected)
                or type(page) is not list
                or len(page) != min(HEALTH_PAGE_SIZE, max(0, count - offset))):
            raise AdminPlacesError()
        expected = count
        for row in page:
            if type(row) is not dict or set(row) != set(projection.split(',')):
                raise AdminPlacesError()
            for key, maximum in (('slug', 120), ('name', 150), ('address', 500)):
                value = row[key]
                if type(value) is not str or not 1 <= len(value) <= maximum or value != value.strip():
                    raise AdminPlacesError()
            if (not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', row['slug'])
                    or row['slug'] in seen
                    or type(row['category']) is not str or row['category'] not in CATEGORIES):
                raise AdminPlacesError()
            lat, lon = row['latitude'], row['longitude']
            if (lat is None) != (lon is None):
                raise AdminPlacesError()
            for value, maximum in ((lat, 90), (lon, 180)):
                if value is not None and (type(value) not in (int, float)
                        or not -maximum <= value <= maximum or not math.isfinite(value)):
                    raise AdminPlacesError()
            tourism_type = row.get('tourism_type')
            if tourism_type is not None and (type(tourism_type) is not str or tourism_type not in ('Local', 'Common')):
                raise AdminPlacesError()
            seen.add(row['slug'])
            rows.append(SimpleNamespace(**row))
        if not expected:
            break
    located = sum(row.latitude is not None for row in rows)
    weather = load_weather_catalog()
    classified = sum(weather.for_place(row).exposure != 'unknown' for row in rows) if weather.available else None
    return CatalogHealth(
        expected, located, expected - located,
        sum(row.tourism_type == 'Local' for row in rows) if tourism_metadata_enabled else None,
        sum(row.tourism_type == 'Common' for row in rows) if tourism_metadata_enabled else None,
        sum(row.tourism_type is None for row in rows) if tourism_metadata_enabled else None,
        classified, expected - classified if classified is not None else None,
    )
