from functools import wraps
from contextlib import ExitStack

from flask import make_response, redirect, url_for
from normal_auth_flask import normal_authenticated, NormalAuthEntryError, clear_normal_auth_authority


def login_required(view=None, *, login_endpoint='login'):
    """Execute the view inside a verified, request-owned normal-auth context."""
    if view is None:
        return lambda handler: login_required(handler, login_endpoint=login_endpoint)
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        with ExitStack() as stack:
            try:
                stack.enter_context(normal_authenticated())
            except NormalAuthEntryError as error:
                if error.may_clear_authority:
                    clear_normal_auth_authority()
                    return redirect(url_for(login_endpoint, login_required="1"))
                response = make_response("Authentication is temporarily unavailable. Please try again.", 503)
                response.headers['Cache-Control'] = 'no-store'
                response.headers['Retry-After'] = '1'
                return response
            # Application exceptions must never enter the auth-error handler.
            return view(*args, **kwargs)

    return wrapped_view
