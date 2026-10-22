"""Draft RPCs on a caller-owned authenticated client; no HTTP or client lifecycle.

Writes are never automatically retried. In particular an ambiguous create may
have committed: callers must not blindly create another draft.
"""
from dataclasses import dataclass
from datetime import date, datetime
import json
import re
from uuid import UUID

import httpx
from postgrest.exceptions import APIError

from normal_auth_coordinator import AuthenticatedContext
from places_service import CATEGORIES
from itinerary_preview import PreviewContractError, ValidatedPreview, validate_preview


MAX_REVISION = 9223372036854775807
DRAFT_PROJECTION = 'id,user_id,state,schema_version,revision,preferences,expires_at'
PREVIEW_DRAFT_PROJECTION = DRAFT_PROJECTION + ',preview'
REQUIRED = frozenset(('interests', 'companion_type', 'start_date', 'end_date',
                      'daily_start_time', 'daily_end_time', 'transportation'))
TRANSPORTATION = ('walking', 'bicycle', 'motorcycle', 'private_car',
                  'public_transport', 'ride_hailing', 'mixed_transport')
TRIP_PACES = ('relaxed', 'balanced', 'packed')
ACTIVITIES = ('sightseeing', 'food_trip', 'shopping', 'outdoor_activities',
              'culture_heritage', 'relaxation')
ENVIRONMENTS = ('indoor', 'outdoor', 'mixed')
TEXT_LIMITS = {'other_interests': 200, 'additional_preferences': 500}
EXTENDED_REQUIRED = frozenset(('trip_pace', 'activity_preferences', 'environment_preference'))
EXTENSION_FIELDS = EXTENDED_REQUIRED | TEXT_LIMITS.keys()


class DraftError(Exception):
    """Base for sanitized draft failures."""


class DraftValidationError(DraftError):
    def __init__(self):
        super().__init__('Invalid draft input.')


class DraftRejectedError(DraftError):
    def __init__(self):
        super().__init__('Draft operation rejected. Reload before trying again.')


class DraftUnavailableError(DraftError):
    def __init__(self):
        super().__init__('Draft operation could not be confirmed.')


class DraftConsistencyError(DraftError):
    def __init__(self):
        super().__init__('Draft response is inconsistent.')


@dataclass(frozen=True, slots=True, repr=False)
class DraftResult:
    draft_id: str
    state: str
    revision: int

    def __repr__(self):
        return '<DraftResult redacted>'


@dataclass(frozen=True, slots=True, repr=False)
class ItineraryDraft:
    draft_id: str
    state: str
    revision: int
    preferences: dict | None
    expires_at: datetime

    def __repr__(self):
        return '<ItineraryDraft redacted>'


@dataclass(frozen=True, slots=True, repr=False)
class ItineraryPreviewDraft(ItineraryDraft):
    user_id: str
    schema_version: int
    preview: ValidatedPreview | None

    def __repr__(self):
        return '<ItineraryPreviewDraft redacted>'


def _uuid(value, error=DraftValidationError):
    if type(value) is str and value and value == value.strip():
        try:
            return str(UUID(value))
        except ValueError:
            pass
    raise error() from None


def _context(context):
    if not isinstance(context, AuthenticatedContext) or not callable(getattr(context.client, 'rpc', None)):
        raise TypeError('An active AuthenticatedContext is required.')
    _uuid(context.user_id, lambda: TypeError('An active AuthenticatedContext is required.'))


def preference_text(value, maximum):
    """Untrusted text only: never interpret markup, JSON, SQL, or instructions."""
    if value is None:
        return None
    if type(value) is not str:
        raise DraftValidationError()
    value = value.strip()
    if (len(value) > maximum or '\x00' in value
            or any(0xD800 <= ord(char) <= 0xDFFF for char in value)):
        raise DraftValidationError()
    return value or None


def _preferences(value, *, allow_legacy=False):
    if type(value) is not dict:
        raise DraftValidationError()
    legacy = allow_legacy and not (value.keys() & EXTENSION_FIELDS)
    required = REQUIRED if legacy else REQUIRED | EXTENDED_REQUIRED
    allowed = required | {'budget_centavos', 'timezone'} | (set() if legacy else TEXT_LIMITS.keys())
    if not required <= value.keys() or value.keys() - allowed:
        raise DraftValidationError()
    interests = value['interests']
    if (type(interests) is not list or not 1 <= len(interests) <= 6
            or any(type(item) is not str or item not in CATEGORIES for item in interests)
            or len(set(interests)) != len(interests)):
        raise DraftValidationError()
    if any(type(value[key]) is not str for key in REQUIRED - {'interests'}):
        raise DraftValidationError()
    if (value['companion_type'] not in ('solo', 'couple', 'family', 'friends', 'group')
            or value['transportation'] not in (('walking', 'private_car', 'public_transport') if legacy else TRANSPORTATION)
            or ('timezone' in value and (type(value['timezone']) is not str or value['timezone'] != 'Asia/Manila'))):
        raise DraftValidationError()
    budget = value.get('budget_centavos')
    if budget is not None and (type(budget) is not int or not 0 <= budget <= 10000000):
        raise DraftValidationError()
    dates = []
    for key in ('start_date', 'end_date'):
        parsed = None
        if re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value[key]):
            try:
                parsed = date.fromisoformat(value[key])
            except ValueError:
                pass
        if parsed is None:
            raise DraftValidationError()
        dates.append(parsed)
    if not 0 <= (dates[1] - dates[0]).days <= 6:
        raise DraftValidationError()
    for key in ('daily_start_time', 'daily_end_time'):
        if not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]', value[key]):
            raise DraftValidationError()
    if value['daily_end_time'] <= value['daily_start_time']:
        raise DraftValidationError()
    canonical = dict(value, interests=list(interests), budget_centavos=budget, timezone='Asia/Manila')
    if not legacy:
        if (type(value['trip_pace']) is not str or value['trip_pace'] not in TRIP_PACES
                or type(value['environment_preference']) is not str
                or value['environment_preference'] not in ENVIRONMENTS):
            raise DraftValidationError()
        activities = value['activity_preferences']
        if (type(activities) is not list or not 1 <= len(activities) <= 6
                or any(type(item) is not str or item not in ACTIVITIES for item in activities)
                or len(set(activities)) != len(activities)):
            raise DraftValidationError()
        canonical['activity_preferences'] = list(activities)
        for key, maximum in TEXT_LIMITS.items():
            canonical[key] = preference_text(value.get(key), maximum)
    # All types/strings are now validated and bounded; no arbitrary JSON objects.
    if len(json.dumps(canonical, ensure_ascii=False).encode('utf-8')) > 16384:
        raise DraftValidationError()
    return canonical


def validate_complete_preferences(value):
    """Validate the current expanded snapshot without legacy defaults or I/O."""
    return _preferences(value)


def _call(context, name, params, expected_id, expected_revision, expected_state='editing'):
    try:
        response = context.client.rpc(name, params).retry(False).execute()
    except APIError as error:
        code = getattr(error, 'code', None)
        failure = (DraftValidationError() if code == '22023' else
                   DraftRejectedError() if code in ('P0002', '42501') else DraftUnavailableError())
    except httpx.HTTPError:
        failure = DraftUnavailableError()
    else:
        data = getattr(response, 'data', None)
        if type(data) is not list or len(data) != 1 or type(data[0]) is not dict:
            raise DraftConsistencyError()
        row = data[0]
        if set(row) != {'draft_id', 'state', 'revision'}:
            raise DraftConsistencyError()
        draft_id = _uuid(row['draft_id'], DraftConsistencyError)
        if (row['state'] != expected_state or type(row['revision']) is not int
                or row['revision'] != expected_revision
                or (expected_id is not None and draft_id != expected_id)):
            raise DraftConsistencyError()
        return DraftResult(draft_id, row['state'], row['revision'])
    # Outside the handler: provider diagnostics must not survive in exception chains.
    raise failure from None


def create_itinerary_draft(context: AuthenticatedContext) -> DraftResult:
    _context(context)
    return _call(context, 'rosago_itinerary_draft_create', {}, None, 1)


def get_itinerary_draft(context: AuthenticatedContext, draft_id) -> ItineraryDraft | None:
    """Read one own draft through RLS and explicit ownership; no authority returned."""
    return _get_itinerary_draft(context, draft_id, include_preview=False)


def get_itinerary_preview_draft(context: AuthenticatedContext, draft_id) -> ItineraryPreviewDraft | None:
    """Read the stored contract, not a guarantee of current catalog eligibility."""
    return _get_itinerary_draft(context, draft_id, include_preview=True)


def _get_itinerary_draft(context, draft_id, *, include_preview):
    _context(context)
    draft_id = _uuid(draft_id)
    owner = _uuid(context.user_id)
    projection = PREVIEW_DRAFT_PROJECTION if include_preview else DRAFT_PROJECTION
    try:
        response = (context.client.table('itinerary_drafts').select(projection)
                    .eq('id', draft_id).eq('user_id', owner).limit(2).retry(False).execute())
    except (APIError, httpx.HTTPError):
        pass
    else:
        data = getattr(response, 'data', None)
        if type(data) is not list or len(data) > 1:
            raise DraftConsistencyError()
        if not data:
            return None
        row = data[0]
        if type(row) is not dict or set(row) != set(projection.split(',')):
            raise DraftConsistencyError()
        if (_uuid(row['id'], DraftConsistencyError) != draft_id
                or _uuid(row['user_id'], DraftConsistencyError) != owner
                or row['state'] not in ('editing', 'generating', 'preview_ready', 'failed', 'saved', 'expired')
                or type(row['schema_version']) is not int or row['schema_version'] != 1
                or type(row['revision']) is not int or not 1 <= row['revision'] <= MAX_REVISION):
            raise DraftConsistencyError()
        expires = None
        if type(row['expires_at']) is str:
            try:
                expires = datetime.fromisoformat(row['expires_at'])
            except ValueError:
                pass
        if expires is None or expires.tzinfo is None or expires.utcoffset() is None:
            raise DraftConsistencyError()
        snapshot = row['preferences']
        if snapshot is not None:
            try:
                canonical = _preferences(snapshot, allow_legacy=True)
            except DraftValidationError:
                canonical = None
            if canonical is None or canonical != snapshot:
                raise DraftConsistencyError()
            snapshot = canonical
        if include_preview:
            parsed = None
            if row['preview'] is not None:
                try:
                    parsed = validate_preview(row['preview'])
                except (PreviewContractError, ValueError, TypeError):
                    pass
                if parsed is None or parsed.source.draft_id != draft_id:
                    raise DraftConsistencyError()
                if row['state'] == 'preview_ready':
                    constraints = row['preview']['constraints']
                    if (parsed.source.draft_revision != row['revision'] - 1 or snapshot is None
                            or any(snapshot.get(key) != value for key, value in constraints.items())):
                        raise DraftConsistencyError()
            if ((row['state'] == 'preview_ready' and parsed is None)
                    or (row['state'] == 'editing' and parsed is not None)):
                raise DraftConsistencyError()
            return ItineraryPreviewDraft(draft_id, row['state'], row['revision'], snapshot,
                                         expires, owner, row['schema_version'], parsed)
        return ItineraryDraft(draft_id, row['state'], row['revision'], snapshot, expires)
    raise DraftUnavailableError() from None


def update_itinerary_draft_preferences(context: AuthenticatedContext, draft_id,
                                      expected_revision, preferences) -> DraftResult:
    _context(context)
    draft_id = _uuid(draft_id)
    if type(expected_revision) is not int or not 1 <= expected_revision < MAX_REVISION:
        raise DraftValidationError()
    return _call(context, 'rosago_itinerary_draft_update_preferences', {
        'p_draft_id': draft_id, 'p_expected_revision': expected_revision,
        'p_preferences': _preferences(preferences),
    }, draft_id, expected_revision + 1)


def store_itinerary_draft_preview(context: AuthenticatedContext, draft_id,
                                  expected_revision, candidate_preview) -> DraftResult:
    """Submit one candidate once; database independently checks every authority."""
    _context(context)
    draft_id = _uuid(draft_id)
    if type(expected_revision) is not int or not 1 <= expected_revision < MAX_REVISION:
        raise DraftValidationError()
    parsed = None
    try:
        parsed = validate_preview(candidate_preview)
    except (PreviewContractError, ValueError, TypeError):
        pass
    if (parsed is None or parsed.source.draft_id != draft_id
            or parsed.source.draft_revision != expected_revision):
        raise DraftValidationError()
    return _call(context, 'rosago_itinerary_draft_store_preview', {
        'p_draft_id': draft_id, 'p_expected_revision': expected_revision,
        'p_candidate_preview': parsed.to_document(),
    }, draft_id, expected_revision + 1, expected_state='preview_ready')


def return_itinerary_draft_to_editing(context: AuthenticatedContext, draft_id,
                                      expected_revision) -> DraftResult:
    """Invalidate preview and selection; the database preserves preferences/expiry."""
    _context(context)
    draft_id = _uuid(draft_id)
    if type(expected_revision) is not int or not 1 <= expected_revision < MAX_REVISION:
        raise DraftValidationError()
    return _call(context, 'rosago_itinerary_draft_return_to_editing', {
        'p_draft_id': draft_id, 'p_expected_revision': expected_revision,
    }, draft_id, expected_revision + 1)
