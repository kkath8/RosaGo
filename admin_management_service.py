"""Admin-only RPC contracts. No service key, global client, or private row reads."""
import math
import re
from datetime import datetime

from admin_places_service import _context, _execute, AdminPlacesError
from place_model import CATEGORIES, TOURISM_TYPES, TOURISM_HOURS_STATUSES, ENVIRONMENTS
from admin_photo_service import valid_photo_url
from destination_categories import flexible_catalog_enabled

BASIC_FIELDS = ('name', 'category', 'description', 'address', 'latitude', 'longitude')
TOURISM_FIELDS = ('tourism_type', 'tourism_category', 'tourism_opening_hours_raw',
                  'tourism_closing_hours_raw', 'tourism_hours_status')
ACTIONS = ('publish', 'draft', 'archive', 'restore')
PHOTO_FIELDS = ('image_url',)
ENVIRONMENT_FIELDS = ('environment',)
SCHEDULE_FIELDS = ('operating_days_raw',)
SOURCE_FIELDS = ('tourism_source', 'tourism_source_row')


class DestinationValidationError(ValueError):
    pass


def validate_destination(values, *, tourism_enabled):
    """Validate an exact allowlist; absent optional metadata stays NULL."""
    allowed = set(BASIC_FIELDS + (TOURISM_FIELDS if tourism_enabled else ()))
    optional_fields = PHOTO_FIELDS + ENVIRONMENT_FIELDS + (SCHEDULE_FIELDS + SOURCE_FIELDS if flexible_catalog_enabled() else ())
    if (set(values) - set(optional_fields) != allowed
            or any(type(value) is not str for key, value in values.items() if key not in optional_fields)):
        raise DestinationValidationError('Invalid destination fields. Reload the form.')
    result = {}
    if any(field in values for field in SOURCE_FIELDS):
        if not all(field in values for field in SOURCE_FIELDS):
            raise DestinationValidationError('Source label and source row must be supplied together.')
        label, source_row = (values[field] for field in SOURCE_FIELDS)
        if ((label is None) != (source_row is None)
                or (label is not None and (type(label) is not str or not 1 <= len(label) <= 500 or not label.strip()))
                or (source_row is not None and (type(source_row) is not int or not 2 <= source_row <= 1048576))):
            raise DestinationValidationError('Invalid source provenance.')
        result.update(tourism_source=label, tourism_source_row=source_row)
    if 'operating_days_raw' in values:
        days = values['operating_days_raw']
        if days is not None and (type(days) is not str or not 1 <= len(days) <= 2000 or not days.strip()):
            raise DestinationValidationError('Operating days must contain at most 2000 characters or be blank.')
        result['operating_days_raw'] = days
    if 'environment' in values:
        value = values['environment']
        if value is not None and (type(value) is not str or value not in ENVIRONMENTS):
            raise DestinationValidationError('Choose Indoor, Outdoor, Mix of Both, or Not recorded.')
        result['environment'] = value
    if 'image_url' in values:
        if values['image_url'] is not None and not valid_photo_url(values['image_url']):
            raise DestinationValidationError('The destination photo URL is invalid.')
        result['image_url'] = values['image_url']
    for field, maximum in (('name', 150), ('description', 3000), ('address', 500)):
        value = values[field].strip()
        if not 1 <= len(value) <= maximum or any(ord(c) < 32 and c not in '\n\r\t' for c in value):
            raise DestinationValidationError(f'{field.title()} is required and must be at most {maximum} characters.')
        result[field] = value
    if values['category'] not in CATEGORIES:
        raise DestinationValidationError('Choose an existing RosaGo category.')
    result['category'] = values['category']
    for field, maximum in (('latitude', 90), ('longitude', 180)):
        value = values[field].strip()
        try:
            number = float(value) if value else None
        except ValueError:
            raise DestinationValidationError(f'{field.title()} must be numeric.') from None
        if number is not None and (not math.isfinite(number) or not -maximum <= number <= maximum):
            raise DestinationValidationError(f'{field.title()} must be between {-maximum} and {maximum}.')
        result[field] = number
    if (result['latitude'] is None) != (result['longitude'] is None):
        raise DestinationValidationError('Supply latitude and longitude together.')
    if tourism_enabled:
        for field, choices in (('tourism_type', TOURISM_TYPES), ('tourism_hours_status', TOURISM_HOURS_STATUSES)):
            value = values[field] or None
            if value is not None and value not in choices:
                raise DestinationValidationError('Choose a supported Tourism Type and hours status.')
            result[field] = value
        for field in ('tourism_category', 'tourism_opening_hours_raw', 'tourism_closing_hours_raw'):
            value = values[field] or None  # Preserve raw hours, including whitespace and asterisks.
            if value is not None and (len(value) > 250 or not value.strip()):
                raise DestinationValidationError('Optional Tourism text must contain at most 250 characters.')
            result[field] = value
    return result


def mutate_destination(context, *, action, values=None, slug=None, expected_updated_at=None,
                       tourism_enabled=False):
    _context(context)
    if action not in ('create', 'edit', *ACTIONS):
        raise DestinationValidationError('Unsupported destination action.')
    payload = validate_destination(values, tourism_enabled=tourism_enabled) if action in ('create', 'edit') else {}
    if action != 'create':
        if type(slug) is not str or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug) or len(slug) > 120:
            raise DestinationValidationError('Invalid destination identity.')
        try:
            version = datetime.fromisoformat(expected_updated_at)
            if version.tzinfo is None:
                raise ValueError()
        except (TypeError, ValueError):
            raise DestinationValidationError('Reload the destination before saving.') from None
    response = _execute(context.client.rpc('rosago_admin_mutate_destination', {
        'p_action': action, 'p_slug': slug, 'p_expected_updated_at': expected_updated_at,
        'p_values': payload}))
    result = getattr(response, 'data', None)
    if (type(result) is not dict or set(result) != {'slug', 'status'}
            or type(result['slug']) is not str or len(result['slug']) > 120
            or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', result['slug'])
            or result['status'] not in ('draft', 'published', 'archived')):
        raise AdminPlacesError()
    return result


def operational_overview(context, *, q='', page=1):
    """One protected, bounded snapshot: safe user projection and trip aggregates."""
    _context(context)
    if (type(q) is not str or len(q) > 150 or any(ord(c) < 32 for c in q)
            or type(page) is not int or not 1 <= page <= 100000):
        raise ValueError('Invalid user search or page.')
    data = getattr(_execute(context.client.rpc('rosago_admin_operational_overview', {
        'p_query': q.strip(), 'p_offset': (page - 1) * 25})), 'data', None)
    keys = {'users_total', 'users_matching', 'users', 'trips_total', 'upcoming_trips',
            'destinations_in_trips', 'popular', 'categories'}
    if type(data) is not dict or set(data) != keys:
        raise AdminPlacesError()
    for key in ('users_total', 'users_matching', 'trips_total', 'upcoming_trips', 'destinations_in_trips'):
        if type(data[key]) is not int or data[key] < 0:
            raise AdminPlacesError()
    if data['users_matching'] > data['users_total']:
        raise AdminPlacesError()
    schemas = {
        'users': ({'identifier', 'email', 'name', 'created_at'}, 25),
        'popular': ({'name', 'slug', 'trips'}, 10),
        'categories': ({'category', 'trips'}, len(CATEGORIES)),
    }
    for key, (fields, maximum) in schemas.items():
        rows = data[key]
        if type(rows) is not list or len(rows) > maximum:
            raise AdminPlacesError()
        for row in rows:
            if type(row) is not dict or set(row) != fields:
                raise AdminPlacesError()
            if key == 'users':
                if (any(row[k] is not None and (type(row[k]) is not str or len(row[k]) > 320)
                        for k in fields) or not row['identifier'] or not row['created_at']):
                    raise AdminPlacesError()
            else:
                if type(row['trips']) is not int or row['trips'] < 1:
                    raise AdminPlacesError()
                if key == 'categories' and row['category'] not in CATEGORIES:
                    raise AdminPlacesError()
                if key == 'popular' and (type(row['name']) is not str or not 1 <= len(row['name']) <= 150
                        or type(row['slug']) is not str or len(row['slug']) > 120
                        or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', row['slug'])):
                    raise AdminPlacesError()
    return data
