"""Read-only catalog distributions and deterministic data-quality flags.

No weather provider calls, private user/trip reads, inference or mutations.
"""
from collections import Counter
from dataclasses import dataclass

from admin_places_service import read_catalog
from destination_weather_metadata import EXPOSURES, load_weather_catalog
from destination_categories import CATEGORY_LABELS

SCOPES = ('published', 'all', 'draft', 'archived')
ISSUES = {
    'missing_coordinates': 'Missing coordinates',
    'tourism_unclassified': 'Tourism Type unclassified',
    'hours_verify_required': 'Hours require verification',
    'hours_unverified': 'Hours supplied but unverified',
    'hours_not_supplied': 'Hours not supplied',
    'hours_unset': 'Hours status not assigned',
    'weather_unknown': 'Weather exposure unknown',
    'draft': 'Draft destination',
}
ATTENTION_PAGE_SIZE = 10
LIST_PREVIEW_SIZE = 10


@dataclass(frozen=True)
class Distribution:
    key: str
    label: str
    count: int
    percent: float


@dataclass(frozen=True)
class AttentionItem:
    place: object
    issues: tuple[str, ...]


def distribution(counts, labels, total):
    return tuple(Distribution(key, label, counts.get(key, 0),
                              round(counts.get(key, 0) * 100 / total, 1) if total else 0.0)
                 for key, label in labels)


def catalog_insights(context, *, tourism_metadata_enabled=False, scope='published', issue=None, page=1):
    if (type(scope) is not str or scope not in SCOPES
            or (issue is not None and (type(issue) is not str or issue not in ISSUES))
            or type(page) is not int or not 1 <= page <= 200):
        raise ValueError('Invalid catalog insight filter.')
    places = read_catalog(context, tourism_metadata_enabled=tourism_metadata_enabled, include_hours=True)
    return summarize_catalog(places, tourism_metadata_enabled=tourism_metadata_enabled,
                             scope=scope, issue=issue, page=page)


def summarize_catalog(places, *, tourism_metadata_enabled, scope, issue, page):
    """Caller supplies validated rows from the complete authorized catalog read."""
    selected = tuple(p for p in places if scope == 'all' or p.status == scope)
    total = len(selected)
    weather = load_weather_catalog()
    categories = Counter(p.category for p in selected)
    tourism = Counter(p.tourism_type for p in selected) if tourism_metadata_enabled else None
    hours = Counter(p.tourism_hours_status for p in selected) if tourism_metadata_enabled else None
    exposures = Counter()
    known_weather, missing, attention = [], [], []
    issue_counts = Counter()
    map_ready = 0
    for place in selected:
        flags = []
        if not place.has_coordinates:
            missing.append(place)
            flags.append('missing_coordinates')
        elif place.status == 'published' and not place.is_test_record:
            map_ready += 1
        if tourism_metadata_enabled:
            if place.tourism_type is None:
                flags.append('tourism_unclassified')
            flags.append({None: 'hours_unset', 'unverified': 'hours_unverified',
                          'verify_required': 'hours_verify_required',
                          'not_supplied': 'hours_not_supplied'}[place.tourism_hours_status])
        if weather.available:
            exposure = weather.for_place(place).exposure
            exposures[exposure] += 1
            if exposure == 'unknown':
                flags.append('weather_unknown')
            else:
                known_weather.append(dict(place=place, exposure=exposure))
        if place.status == 'draft':
            flags.append('draft')
        if flags:
            attention.append(AttentionItem(place, tuple(flags)))
            issue_counts.update(flags)
    matching = tuple(item for item in attention if issue is None or issue in item.issues)
    offset = (page - 1) * ATTENTION_PAGE_SIZE
    category_keys = sorted(categories, key=lambda key: CATEGORY_LABELS[key])
    category_types = tuple(dict(category=key, label=CATEGORY_LABELS[key],
        local=sum(p.category == key and p.tourism_type == 'Local' for p in selected),
        common=sum(p.category == key and p.tourism_type == 'Common' for p in selected),
        unclassified=sum(p.category == key and p.tourism_type is None for p in selected))
        for key in category_keys) if tourism_metadata_enabled else None
    located = total - len(missing)
    return dict(total=total, all_total=len(places),
        publication=distribution(Counter(p.status for p in places),
            ((s, s.title()) for s in ('published', 'draft', 'archived')), len(places)),
        categories=distribution(categories, ((k, CATEGORY_LABELS[k]) for k in category_keys), total),
        tourism=distribution(tourism, (('Local', 'Local'), ('Common', 'Common'), (None, 'Unclassified')), total)
            if tourism_metadata_enabled else None,
        hours=distribution(hours, (('unverified', 'Unverified'), ('verify_required', 'Verification required'),
                                  ('not_supplied', 'Not supplied'), (None, 'Status not assigned')), total)
            if tourism_metadata_enabled else None,
        category_types=category_types,
        coordinates=distribution({'with': located, 'missing': len(missing)},
                                 (('with', 'With coordinates'), ('missing', 'Missing coordinates')), total),
        located=located, missing_count=len(missing), map_ready=map_ready,
        missing_places=tuple(missing[:LIST_PREVIEW_SIZE]),
        tourism_assigned=(total - tourism.get(None, 0)) if tourism_metadata_enabled else None,
        tourism_unclassified=tourism.get(None, 0) if tourism_metadata_enabled else None,
        weather=distribution(exposures, ((key, key.title()) for key in EXPOSURES), total) if weather.available else None,
        weather_classified=total - exposures.get('unknown', 0) if weather.available else None,
        weather_unknown=exposures.get('unknown', 0) if weather.available else None,
        known_weather=tuple(known_weather[:LIST_PREVIEW_SIZE]),
        known_weather_count=len(known_weather),
        attention=matching[offset:offset + ATTENTION_PAGE_SIZE], attention_total=len(attention),
        attention_matching=len(matching), issue_counts=issue_counts,
        attention_has_next=offset + ATTENTION_PAGE_SIZE < len(matching))
