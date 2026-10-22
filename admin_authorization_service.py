"""Current-caller authorization using an existing request-owned client only."""
import httpx
from postgrest.exceptions import APIError

from normal_auth_coordinator import AuthenticatedContext


class AdminAuthorizationError(Exception):
    def __init__(self):
        super().__init__('Admin authorization is temporarily unavailable.')


def is_current_admin(context: AuthenticatedContext) -> bool:
    """Return a strict boolean; never cache, accept a target ID, or mutate.

    The normal-auth scope establishes authority and owns the client's lifetime.
    A valid Python context type alone is not proof of authentication.
    """
    if (type(context) is not AuthenticatedContext
            or type(context.user_id) is not str or not context.user_id.strip()
            or context.client is None):
        raise AdminAuthorizationError()
    try:
        response = context.client.rpc('rosago_is_admin', {}).retry(False).execute()
    except (APIError, httpx.HTTPError):
        pass
    else:
        result = getattr(response, 'data', None)
        if type(result) is bool:
            return result
    # Do not retain provider details in exception chains.
    raise AdminAuthorizationError() from None
