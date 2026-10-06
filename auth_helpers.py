from functools import wraps

from flask import redirect, session, url_for


def login_required(view):
    """Allow access only when the signed Flask session contains a user ID."""
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login", login_required="1"))
        return view(*args, **kwargs)

    return wrapped_view
