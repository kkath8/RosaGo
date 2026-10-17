"""Draft RPCs on a caller-owned authenticated client; no HTTP or client lifecycle.

Writes are never automatically retried. In particular an ambiguous create may
have committed: callers must not blindly create another draft.
"""
from dataclasses import dataclass
from datetime import date
import json
import re
from uuid import UUID

import httpx
from postgrest.exceptions import APIError

from normal_auth_coordinator import AuthenticatedContext
from places_service import CATEGORIES


MAX_REVISION = 9223372036854775807
REQUIRED = frozenset(('interests', 'companion_type', 'start_date', 'end_date',
                      'daily_start_time', 'daily_end_time', 'transportation'))


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


def _preferences(value):
    if type(value) is not dict or not REQUIRED <= value.keys() or value.keys() - REQUIRED - {'budget_centavos', 'timezone'}:
        raise DraftValidationError()
    interests = value['interests']
    if (type(interests) is not list or not 1 <= len(interests) <= 6
            or any(type(item) is not str or item not in CATEGORIES for item in interests)
            or len(set(interests)) != len(interests)):
        raise DraftValidationError()
    if any(type(value[key]) is not str for key in REQUIRED - {'interests'}):
        raise DraftValidationError()
    if (value['companion_type'] not in ('solo', 'couple', 'family', 'friends', 'group')
            or value['transportation'] not in ('walking', 'private_car', 'public_transport')
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
    # All types/strings are now validated and bounded; no arbitrary JSON objects.
    if len(json.dumps(canonical, ensure_ascii=False).encode('utf-8')) > 16384:
        raise DraftValidationError()
    return canonical


def _call(context, name, params, expected_id, expected_revision):
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
        if (row['state'] != 'editing' or type(row['revision']) is not int
                or row['revision'] != expected_revision
                or (expected_id is not None and draft_id != expected_id)):
            raise DraftConsistencyError()
        return DraftResult(draft_id, row['state'], row['revision'])
    # Outside the handler: provider diagnostics must not survive in exception chains.
    raise failure from None


def create_itinerary_draft(context: AuthenticatedContext) -> DraftResult:
    _context(context)
    return _call(context, 'rosago_itinerary_draft_create', {}, None, 1)


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
