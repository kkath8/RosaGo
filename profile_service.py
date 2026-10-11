"""Read or update the caller's own profile in an authenticated context.

The caller owns authentication and client lifetime. This module neither creates
clients nor changes sessions. Explicit ownership filtering supplements database
RLS; an empty result cannot distinguish a missing row from an RLS-hidden row.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
import unicodedata

import httpx
from postgrest.exceptions import APIError
from postgrest.types import ReturnMethod

from normal_auth_coordinator import AuthenticatedContext


class ProfileServiceError(Exception):
    """Base for the service's fixed public failures."""


class ProfileUnavailableError(ProfileServiceError):
    def __init__(self):
        super().__init__('Profile is temporarily unavailable.')


class ProfileConsistencyError(ProfileServiceError):
    def __init__(self):
        super().__init__('Profile data is inconsistent.')


class ProfileValidationError(ProfileServiceError):
    def __init__(self):
        super().__init__('Profile names are invalid.')


class ProfileNotFoundError(ProfileServiceError):
    def __init__(self):
        super().__init__('Profile is unavailable for update.')


@dataclass(frozen=True, slots=True, repr=False)
class UserProfile:
    id: str
    first_name: str | None
    last_name: str | None
    created_at: datetime

    def __repr__(self):
        return '<UserProfile redacted>'


def _name(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProfileConsistencyError()
    return value.strip() or None


def _timestamp(value):
    if not isinstance(value, str):
        raise ProfileConsistencyError()
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        pass
    else:
        if parsed.tzinfo is not None and parsed.utcoffset() is not None:
            return parsed
    # Do not retain parsing errors, which may contain raw database values.
    raise ProfileConsistencyError() from None


def _validate_context(context):
    if (not isinstance(context, AuthenticatedContext)
            or not isinstance(context.user_id, str) or not context.user_id.strip()
            or not callable(getattr(context.client, 'table', None))):
        raise TypeError('An active AuthenticatedContext is required.')


def _profile(response, user_id):
    data = getattr(response, 'data', None)
    if not isinstance(data, list) or len(data) > 1:
        raise ProfileConsistencyError()
    if not data:
        return None
    row = data[0]
    if (not isinstance(row, Mapping)
            or not {'id', 'first_name', 'last_name', 'created_at'} <= row.keys()
            or not isinstance(row['id'], str) or not row['id'].strip()
            or row['id'] != user_id):
        raise ProfileConsistencyError()
    return UserProfile(row['id'], _name(row['first_name']),
                       _name(row['last_name']), _timestamp(row['created_at']))


def get_own_profile(context: AuthenticatedContext) -> UserProfile | None:
    """Retrieve one validated own-profile value; never accept a separate ID.

    This checks the server-side calling contract, not authentication. The
    coordinator must have produced the context and its client must still be
    alive. Programming errors and control-flow signals propagate unchanged.
    """
    _validate_context(context)
    query = (context.client.table('profiles')
             .select('id,first_name,last_name,created_at')
             .eq('id', context.user_id).limit(2).retry(False))
    try:
        response = query.execute()
    except (APIError, httpx.HTTPError):
        pass
    else:
        return _profile(response, context.user_id)
    # Leaving the handler prevents provider diagnostics in cause/context chains.
    raise ProfileUnavailableError() from None


def _update_name(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProfileValidationError()
    value = value.strip()
    # Preserve Unicode formatting/joining characters; reject controls and
    # unpaired surrogates that cannot be encoded as valid UTF-8.
    if len(value) > 100 or any(unicodedata.category(c) in ('Cc', 'Cs') for c in value):
        raise ProfileValidationError()
    return value or None


def update_own_profile(context: AuthenticatedContext, *,
                       first_name: str | None, last_name: str | None) -> UserProfile:
    """Update only the verified caller's names using its still-active client.

    Authentication and request/CSRF checks belong to the caller. A transport
    failure may follow a committed write; never retry a mutation automatically.
    """
    _validate_context(context)
    first_name, last_name = _update_name(first_name), _update_name(last_name)
    query = (context.client.table('profiles')
             .update({'first_name': first_name, 'last_name': last_name},
                     returning=ReturnMethod.representation)
             .eq('id', context.user_id)
             .select('id,first_name,last_name,created_at').retry(False))
    try:
        response = query.execute()
    except (APIError, httpx.HTTPError):
        pass
    else:
        profile = _profile(response, context.user_id)
        if profile is None:
            raise ProfileNotFoundError()
        if (profile.first_name, profile.last_name) != (first_name, last_name):
            raise ProfileConsistencyError()
        return profile
    raise ProfileUnavailableError() from None
