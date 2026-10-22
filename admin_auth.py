"""Reusable Admin boundary layered on normal authentication."""
from functools import wraps

from flask import g, render_template

from auth_helpers import login_required
from admin_authorization_service import AdminAuthorizationError, is_current_admin


def admin_required(view):
    """Verify normal authentication and fresh membership for each request."""
    @login_required(login_endpoint='admin.login')
    @wraps(view)
    def authorized(*args, **kwargs):
        try:
            allowed = is_current_admin(g.auth)
        except AdminAuthorizationError:
            return 'Admin authorization is temporarily unavailable. Please try again.', 503
        if not allowed:
            return 'Admin access required.', 403
        return view(*args, **kwargs)
    return authorized


def render_admin_page(template, **values):
    """Render only display data, with request authority hidden from Jinja."""
    auth = g.pop('auth', None)
    try:
        return render_template(template, **values)
    finally:
        if auth is not None:
            g.auth = auth
