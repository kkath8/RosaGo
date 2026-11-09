"""Reusable Admin boundary with independent authentication and fresh membership."""
from functools import wraps

from flask import g, render_template

from admin_session_flask import admin_login_required as login_required
from admin_authorization_service import AdminAuthorizationError, is_current_admin


def admin_required(view):
    """Verify only Admin authentication and fresh membership for each request."""
    @login_required(login_endpoint='admin.login')
    @wraps(view)
    def authorized(*args, **kwargs):
        try:
            allowed = is_current_admin(g.admin_auth)
        except AdminAuthorizationError:
            return render_admin_page('admin/access_error.html',
                message='Admin authorization is temporarily unavailable. Please try again.'), 503
        if not allowed:
            return render_admin_page('admin/access_error.html',
                message='Admin access required.'), 403
        return view(*args, **kwargs)
    return authorized


def render_admin_page(template, **values):
    """Render only display data, with request authority hidden from Jinja."""
    auth = g.pop('admin_auth', None)
    try:
        return render_template(template, **values)
    finally:
        if auth is not None:
            g.admin_auth = auth
