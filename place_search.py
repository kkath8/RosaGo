"""Literal destination search over the existing published-only catalog reader."""
import unicodedata

from places_service import PlacesConsistencyError, PlacesValidationError


MAX_QUERY_LENGTH = 200
_CATEGORY_LABELS = {
    'attraction': 'Attractions', 'dining': 'Dining', 'shopping': 'Shopping',
    'accommodation': 'Accommodation', 'nature': 'Nature',
    'heritage': 'Heritage', 'industrial': 'Industrial Tourism',
}


def normalize_query(value):
    if (type(value) is not str or len(value) > MAX_QUERY_LENGTH
            or any(unicodedata.category(c) in ('Cc', 'Cs') for c in value)):
        raise PlacesValidationError()
    return ' '.join(value.split())


def search_published(service, query, *, category=None):
    """Read every published page; never send search text to a database query.

    All words must occur as literal, case-insensitive substrings in the public
    visitor fields. Publication, projection and category checks remain owned by
    PlacesService/RLS. Internal Tourism provenance is deliberately not searched.
    """
    words = normalize_query(query).casefold().split()
    matches, seen, offset = [], set(), 0
    while True:
        page = service.list_published(category=category, limit=50, offset=offset)
        for place in page:
            if place.id in seen:
                raise PlacesConsistencyError()
            seen.add(place.id)
            if place.slug.startswith('rosago-test-v1-'):
                continue
            text = ' '.join(str(getattr(place, field, None) or '') for field in (
                'name', 'category', 'address', 'description', 'tourism_type',
                'tourism_category'))
            text += ' ' + _CATEGORY_LABELS.get(place.category, '')
            if all(word in text.casefold() for word in words):
                matches.append(place)
        if len(page) < 50:
            return tuple(matches)
        offset += 50
