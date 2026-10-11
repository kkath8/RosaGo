"""Read the caller's own profile inside an existing authenticated context.

The caller owns authentication and client lifetime. This module neither creates
clients nor changes sessions. Explicit ownership filtering supplements database
RLS; an empty result cannot distinguish a missing row from an RLS-hidden row.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

import httpx
from postgrest.exceptions import APIError

from normal_auth_coordinator import AuthenticatedContext


class ProfileServiceError(Exception):
    """Base for the service's fixed public failures."""


class ProfileUnavailableError(ProfileServiceError):
    def __init__(self):
        super().__init__('Profile is temporarily unavailable.')


class ProfileConsistencyError(ProfileServiceError):
    def __init__(self):
        super().__init__('Profile data is inconsistent.')


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


def get_own_profile(context: AuthenticatedContext) -> UserProfile | None:
    """Retrieve one validated own-profile value; never accept a separate ID.

    This checks the server-side calling contract, not authentication. The
    coordinator must have produced the context and its client must still be
    alive. Programming errors and control-flow signals propagate unchanged.
    """
    if (not isinstance(context, AuthenticatedContext)
            or not isinstance(context.user_id, str) or not context.user_id.strip()
            or not callable(getattr(context.client, 'table', None))):
        raise TypeError('An active AuthenticatedContext is required.')

    query = (context.client.table('profiles')
             .select('id,first_name,last_name,created_at')
             .eq('id', context.user_id).limit(2).retry(False))
    try:
        response = query.execute()
    except (APIError, httpx.HTTPError):
        pass
    else:
        data = getattr(response, 'data', None)
        if not isinstance(data, list) or len(data) > 1:
            raise ProfileConsistencyError()
        if not data:
            return None
        row = data[0]
        if (not isinstance(row, Mapping)
                or not {'id', 'first_name', 'last_name', 'created_at'} <= row.keys()
                or not isinstance(row['id'], str) or not row['id'].strip()
                or row['id'] != context.user_id):
            raise ProfileConsistencyError()
        return UserProfile(row['id'], _name(row['first_name']),
                           _name(row['last_name']), _timestamp(row['created_at']))
    # Leaving the handler prevents provider diagnostics in cause/context chains.
    raise ProfileUnavailableError() from None
