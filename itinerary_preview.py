"""Pure personalized preview v1; digests are content bindings, not authority.

The adapter receives already validated preferences and selected Places. Explicit
publication_confirmed=True asserts that the caller checked publication for this
exact collection. It does not perform or prove that check. The document parser
checks self-consistency only; a future writer must independently compare draft,
selection and catalog state. Neither JSONB text nor repr is canonical JSON here.
"""
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import re
from uuid import UUID

from place_model import CATEGORIES, Place
from itinerary_builder import (
    ItineraryBuildInputError, ItineraryBuildRequest, ItineraryDay, ItineraryPlan,
    ItineraryStop, PlanningConstraints, SelectedDestination, SourceVersion,
    MAX_DESTINATIONS, build_itinerary,
)
from recommendation_engine import POLICY_VERSION as RECOMMENDATION_POLICY_VERSION


PREVIEW_SCHEMA_VERSION = 1
SOURCE_SCHEMA_VERSION = 1
CATALOG_DOMAIN = b'rosago:catalog:v1:'
SOURCE_DOMAIN = b'rosago:source:v1:'
PREVIEW_DOMAIN = b'rosago:preview:v1:'
MAX_DOCUMENT_BYTES = 262144
MAX_REVISION = 9223372036854775807
_HEX = re.compile(r'[0-9a-f]{64}')
_POLICY = re.compile(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*')
_CONSTRAINT_KEYS = frozenset(('start_date', 'end_date', 'daily_start_time', 'daily_end_time',
                             'transportation', 'trip_pace', 'timezone', 'budget_centavos'))
_SOURCE_KEYS = frozenset(('source_schema_version', 'draft_id', 'draft_revision',
                        'recommendation_policy_version', 'selected_place_ids', 'catalog_fingerprint'))
_PREVIEW_KEYS = frozenset(('preview_schema_version', 'builder_policy_version', 'planning_mode',
                         'source', 'source_version', 'constraints', 'days', 'unresolved_constraints'))


class PreviewContractError(ValueError):
    def __init__(self):
        super().__init__('Invalid itinerary preview contract.')


def canonical_json(value) -> bytes:
    """Bounded JSON: sorted string keys, ordered lists, UTF-8, compact separators.

    Strings retain Unicode code points (no normalization); quote/backslash/control
    escaping follows json.dumps(ensure_ascii=False). Reject NUL, surrogates, floats,
    non-JSON objects, excessive depth/size and integers outside signed 64-bit range.
    Dates/UUIDs are schema-validated strings, never implicitly coerced objects.
    """
    nodes = 0
    string_bytes = 0

    def check(item, depth=0):
        nonlocal nodes, string_bytes
        nodes += 1
        if nodes > 10000 or depth > 16:
            raise PreviewContractError()
        if item is None or type(item) is bool:
            return
        if type(item) is int:
            if not -9223372036854775808 <= item <= MAX_REVISION:
                raise PreviewContractError()
        elif type(item) is str:
            if (len(item) > MAX_DOCUMENT_BYTES or '\x00' in item
                    or any(0xD800 <= ord(char) <= 0xDFFF for char in item)):
                raise PreviewContractError()
            string_bytes += len(item.encode('utf-8'))
            if string_bytes > MAX_DOCUMENT_BYTES:
                raise PreviewContractError()
        elif type(item) is list:
            if len(item) > 10000:
                raise PreviewContractError()
            for child in item:
                check(child, depth + 1)
        elif type(item) is dict:
            if len(item) > 10000:
                raise PreviewContractError()
            for key, child in item.items():
                if type(key) is not str:
                    raise PreviewContractError()
                check(key, depth + 1)
                check(child, depth + 1)
        else:
            raise PreviewContractError()

    check(value)
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':'), allow_nan=False).encode('utf-8')
    if len(encoded) > MAX_DOCUMENT_BYTES:
        raise PreviewContractError()
    return encoded


def _hash(domain, value):
    return hashlib.sha256(domain + canonical_json(value)).hexdigest()


def _uuid(value):
    if type(value) is not str or len(value) != 36:
        raise PreviewContractError()
    try:
        canonical = str(UUID(value))
    except ValueError:
        raise PreviewContractError() from None
    if canonical != value:
        raise PreviewContractError()
    return value


def _ids(values):
    if type(values) is not tuple or not 1 <= len(values) <= MAX_DESTINATIONS:
        raise PreviewContractError()
    for value in values:
        _uuid(value)
    if len(set(values)) != len(values):
        raise PreviewContractError()


def _keys(value, keys):
    if type(value) is not dict or value.keys() != keys:
        raise PreviewContractError()


@dataclass(frozen=True, slots=True)
class SourceManifest:
    draft_id: str
    draft_revision: int
    recommendation_policy_version: str
    selected_place_ids: tuple[str, ...]
    catalog_fingerprint: str
    source_schema_version: int = SOURCE_SCHEMA_VERSION

    def __post_init__(self):
        _uuid(self.draft_id)
        _ids(self.selected_place_ids)
        if (type(self.source_schema_version) is not int or self.source_schema_version != SOURCE_SCHEMA_VERSION
                or type(self.draft_revision) is not int or not 1 <= self.draft_revision <= MAX_REVISION
                or type(self.recommendation_policy_version) is not str
                or not 1 <= len(self.recommendation_policy_version) <= 64
                or not _POLICY.fullmatch(self.recommendation_policy_version)
                or type(self.catalog_fingerprint) is not str or not _HEX.fullmatch(self.catalog_fingerprint)):
            raise PreviewContractError()


def _source_document(source):
    if type(source) is not SourceManifest:
        raise PreviewContractError()
    source.__post_init__()
    return dict(source_schema_version=source.source_schema_version, draft_id=source.draft_id,
                draft_revision=source.draft_revision,
                recommendation_policy_version=source.recommendation_policy_version,
                selected_place_ids=list(source.selected_place_ids), catalog_fingerprint=source.catalog_fingerprint)


def compute_source_version(source: SourceManifest) -> SourceVersion:
    return SourceVersion('draft', 'v1:' + _hash(SOURCE_DOMAIN, _source_document(source)))


def compute_catalog_fingerprint(selected_places: tuple[Place, ...], *, publication_confirmed: bool) -> str:
    """Hash exactly the selected collection; caller asserts current publication.

    A slug is used only for the application's exact case-sensitive test-prefix
    rule. Slug text itself and other irrelevant Place fields are never hashed.
    """
    if publication_confirmed is not True or type(selected_places) is not tuple:
        raise PreviewContractError()
    if not 1 <= len(selected_places) <= MAX_DESTINATIONS:
        raise PreviewContractError()
    records = []
    for place in selected_places:
        if type(place) is not Place:
            raise PreviewContractError()
        _uuid(place.id)
        if (type(place.category) is not str or place.category not in CATEGORIES
                or type(place.slug) is not str or not 1 <= len(place.slug) <= 120
                or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', place.slug)):
            raise PreviewContractError()
        for value, maximum in ((place.name, 150), (place.address, 500)):
            if type(value) is not str or not 1 <= len(value) <= maximum or value != value.strip():
                raise PreviewContractError()
        records.append(dict(id=place.id, category=place.category, status='published', name=place.name,
                            address=place.address, is_test_record=place.slug.startswith('rosago-test-v1-')))
    _ids(tuple(record['id'] for record in records))
    return _hash(CATALOG_DOMAIN, sorted(records, key=lambda record: record['id']))


def _constraints_document(constraints):
    if (type(constraints) is not PlanningConstraints or type(constraints.start_date) is not date
            or type(constraints.end_date) is not date):
        raise PreviewContractError()
    return dict(start_date=constraints.start_date.isoformat(), end_date=constraints.end_date.isoformat(),
                daily_start_time=constraints.daily_start_time, daily_end_time=constraints.daily_end_time,
                transportation=constraints.transportation, trip_pace=constraints.trip_pace,
                timezone=constraints.timezone, budget_centavos=constraints.budget_centavos)


def _read_constraints(value):
    _keys(value, _CONSTRAINT_KEYS)
    dates = []
    for key in ('start_date', 'end_date'):
        if type(value[key]) is not str:
            raise PreviewContractError()
        try:
            parsed = date.fromisoformat(value[key])
        except ValueError:
            raise PreviewContractError() from None
        if parsed.isoformat() != value[key]:
            raise PreviewContractError()
        dates.append(parsed)
    return PlanningConstraints(*dates, **{key: value[key] for key in _CONSTRAINT_KEYS - {'start_date', 'end_date'}})


def _reference_plan(source, constraints):
    """Replay ONLY the existing builder for structural validation, without I/O.

    IDs-only documents cannot supply real Places. These private sentinel Places
    exist solely to exercise the builder's ID/order/date contract. Their constant
    unused fields are never exposed, fingerprinted or asserted as catalog facts.
    Actual catalog verification remains a separate adapter/writer responsibility.
    """
    stamp = datetime(2000, 1, 1, tzinfo=timezone.utc)
    destinations = tuple(SelectedDestination(
        Place(identity, 'Validation sentinel', 'validation-sentinel', 'Unused', 'nature',
              'Unused', 0.0, 0.0, None, stamp, stamp), index, 'recommended', True)
        for index, identity in enumerate(source.selected_place_ids, 1))
    try:
        return build_itinerary(ItineraryBuildRequest(constraints, destinations, compute_source_version(source)))
    except ItineraryBuildInputError:
        raise PreviewContractError() from None


def _document(source, plan):
    if (type(plan) is not ItineraryPlan or type(plan.source_version) is not SourceVersion
            or type(plan.days) is not tuple or not 1 <= len(plan.days) <= 7
            or type(plan.unresolved_constraints) is not tuple):
        raise PreviewContractError()
    days = []
    for day in plan.days:
        if type(day) is not ItineraryDay or type(day.date) is not date or type(day.stops) is not tuple:
            raise PreviewContractError()
        if len(day.stops) > MAX_DESTINATIONS:
            raise PreviewContractError()
        stops = []
        for stop in day.stops:
            if type(stop) is not ItineraryStop:
                raise PreviewContractError()
            stops.append(dict(place_id=stop.place_id, order=stop.order, source=stop.source, keep_place=stop.keep_place))
        days.append(dict(date=day.date.isoformat(), stops=stops))
    return dict(preview_schema_version=PREVIEW_SCHEMA_VERSION, builder_policy_version=plan.policy_version,
                planning_mode='personalized', source=_source_document(source),
                source_version=dict(kind=plan.source_version.kind, version=plan.source_version.version),
                constraints=_constraints_document(plan.constraints), days=days,
                unresolved_constraints=list(plan.unresolved_constraints))


@dataclass(frozen=True, slots=True)
class ValidatedPreview:
    source: SourceManifest
    plan: ItineraryPlan

    def to_document(self) -> dict:
        """Return a fresh JSON-compatible document; validate even forged models."""
        document = _document(self.source, self.plan)
        validate_preview(document)
        return document


def validate_preview(document: dict) -> ValidatedPreview:
    """Strict self-consistency parser, not proof of ownership/catalog freshness.

    Exact canonical-byte comparison to builder replay rejects bool/int coercion,
    unknown fields at every level and every noncanonical or fabricated plan field.
    """
    actual = canonical_json(document)
    _keys(document, _PREVIEW_KEYS)
    source_data = document['source']
    _keys(source_data, _SOURCE_KEYS)
    if type(source_data['selected_place_ids']) is not list:
        raise PreviewContractError()
    source = SourceManifest(**(source_data | {'selected_place_ids': tuple(source_data['selected_place_ids'])}))
    constraints = _read_constraints(document['constraints'])
    expected = _reference_plan(source, constraints)
    if actual != canonical_json(_document(source, expected)):
        raise PreviewContractError()
    return ValidatedPreview(source, expected)


def preview_from_plan(source: SourceManifest, plan: ItineraryPlan) -> ValidatedPreview:
    """Validate an arbitrary builder output before allowing its serialization."""
    return validate_preview(_document(source, plan))


def build_personalized_preview(*, preferences: dict, selected_places: tuple[Place, ...],
                               selected_place_ids: tuple[str, ...], draft_id: str, draft_revision: int,
                               publication_confirmed: bool,
                               recommendation_policy_version: str = RECOMMENDATION_POLICY_VERSION) -> ValidatedPreview:
    """Adapt already validated preferences and explicit, server-normalized order.

    No recommendation ranking/allowlist/auth checks occur here. The caller must
    supply exactly the selected published Places, never an entire catalog page.
    Unused personalized fields remain outside the shared builder and preview.
    """
    _ids(selected_place_ids)
    fingerprint = compute_catalog_fingerprint(selected_places, publication_confirmed=publication_confirmed)
    by_id = {place.id: place for place in selected_places}
    if set(selected_place_ids) != by_id.keys() or type(preferences) is not dict or not _CONSTRAINT_KEYS <= preferences.keys():
        raise PreviewContractError()
    constraints = _read_constraints({key: preferences[key] for key in _CONSTRAINT_KEYS})
    source = SourceManifest(draft_id, draft_revision, recommendation_policy_version, selected_place_ids, fingerprint)
    destinations = tuple(SelectedDestination(by_id[identity], index, 'recommended', True)
                         for index, identity in enumerate(selected_place_ids, 1))
    try:
        plan = build_itinerary(ItineraryBuildRequest(constraints, destinations, compute_source_version(source)))
    except ItineraryBuildInputError:
        raise PreviewContractError() from None
    if type(plan) is not ItineraryPlan or canonical_json(_constraints_document(plan.constraints)) != canonical_json(_constraints_document(constraints)):
        raise PreviewContractError()
    return preview_from_plan(source, plan)


def compute_preview_digest(validated_preview: ValidatedPreview | dict) -> str:
    """Revalidate the complete document before hashing; never embed its digest."""
    document = (validated_preview.to_document() if type(validated_preview) is ValidatedPreview
                else validated_preview)
    validate_preview(document)
    return _hash(PREVIEW_DOMAIN, document)
