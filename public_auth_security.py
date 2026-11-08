"""Trusted deployment origin and admission for public email-triggering forms."""
from urllib.parse import urlsplit
from flask import current_app, request


def validate_public_origin(value, *, allow_loopback_http=False):
    try:
        parsed = urlsplit(value)
        parsed.port
        if (not isinstance(value, str) or value != value.strip()
                or any(c.isspace() for c in value) or '\\' in value or '%' in parsed.netloc
                or parsed.username or parsed.password
                or not parsed.hostname or parsed.path not in ('', '/')
                or parsed.query or parsed.fragment
                or (parsed.scheme != 'https' and not (
                    allow_loopback_http and parsed.scheme == 'http'
                    and parsed.hostname in ('127.0.0.1', 'localhost', '::1')))):
            raise ValueError()
    except (TypeError, ValueError, AttributeError):
        raise ValueError('Invalid ROSAGO_PUBLIC_ORIGIN; use an HTTPS origin without a path.') from None
    return value.rstrip('/')


def configured_public_origin(environment):
    mode = environment.get('ROSAGO_AUTH_MODE', 'development')
    if environment.get('RENDER') == 'true' and mode != 'production':
        raise ValueError('Render requires production mode; local/experimental sessions are forbidden.')
    value = environment.get('ROSAGO_PUBLIC_ORIGIN')
    if not value:
        if mode != 'development':
            raise ValueError('ROSAGO_PUBLIC_ORIGIN is required outside local development.')
        value = 'http://127.0.0.1:5000'
    return validate_public_origin(value, allow_loopback_http=(mode == 'development'))


def email_form_origin_allowed():
    # A cross-site browser cannot forge a same-origin Origin header.
    # Reject missing/null Origin too; never trust forwarded headers here.
    return (request.headers.get('Origin') == request.host_url.rstrip('/')
            and request.headers.get('Sec-Fetch-Site') != 'cross-site'
            and not request.files)


def email_attempt_allowed(purpose):
    if 'rosago_shared_sessions' in current_app.extensions:
        from record_session_store import RedisChallenges
        from session_realms import SessionStorageUnavailable
        realms = current_app.extensions['rosago_shared_sessions']
        if not isinstance(realms, dict) or 'user' not in realms:
            raise SessionStorageUnavailable('Shared email limit backend is unavailable.')
        # Reuse the backend-neutral atomic rate records. Never silently fall
        # back to memory after shared mode has been selected.
        return RedisChallenges(realms).allow_attempt(
            'user', request.remote_addr or 'unknown', purpose='email_' + purpose)
    # Development-only mitigation. This branch is not production qualification.
    return current_app.extensions['rosago_public_email_limits'].allow_attempt(
        purpose, request.remote_addr or 'unknown')

