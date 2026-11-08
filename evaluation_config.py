"""Fail-closed preparation for an isolated remote evaluation, never a release bypass."""
import hashlib
import re
from urllib.parse import urlsplit

from public_auth_security import validate_public_origin

PROTECTED_PROJECT_REFS = frozenset({'brnkigrrqdrywahvcbvc'})
EVALUATION_PROJECT_REF = 'jfaufpfzfhysqkhcdsrs'
# Enabled modern publishable key independently inspected through evaluation MCP.
# Fingerprints only: no API keys or signing secrets are embedded in source.
# A provider rotation requires a new read-only inspection and reviewed pin update.
EVALUATION_PUBLIC_KEY_SHA256 = frozenset({
    'c7640668eb470357306772fa6a19ac67b0ab207a64aee24875c3d59e28c561d3',
})


def validate_evaluation_backend(environment):
    """Offline backend binding only; no SDK, dotenv, web startup or network I/O."""
    try:
        project = environment.get('ROSAGO_EVALUATION_PROJECT_REF', '')
        if (environment.get('ROSAGO_EVALUATION') != 'true'
                or project != EVALUATION_PROJECT_REF or project in PROTECTED_PROJECT_REFS):
            raise ValueError()
        expected_url = 'https://' + project + '.supabase.co'
        if environment.get('SUPABASE_URL') not in (expected_url, expected_url + '/'):
            raise ValueError()
        if any(value and name.startswith('SUPABASE_')
               and name not in {'SUPABASE_URL', 'SUPABASE_KEY'}
               for name, value in environment.items()):
            raise ValueError()
        key = environment.get('SUPABASE_KEY', '')
        if (type(key) is not str or not re.fullmatch(r'sb_publishable_[A-Za-z0-9_-]+', key)
                or hashlib.sha256(key.encode('utf-8')).hexdigest() not in EVALUATION_PUBLIC_KEY_SHA256):
            raise ValueError()
        if any(environment.get(name) for name in (
                'GEMINI_API_KEY', 'ORS_API_KEY', 'DATABASE_URL')):
            raise ValueError()
    except (TypeError, ValueError, AttributeError):
        raise ValueError('Isolated evaluation configuration rejected.') from None
    return {'project_ref': project, 'url': expected_url, 'public_key_binding_verified': True}


def validate_evaluation_environment(environment):
    try:
        project = validate_evaluation_backend(environment)['project_ref']
        if environment.get('ROSAGO_AUTH_MODE') != 'production':
            raise ValueError()
        origin = validate_public_origin(environment.get('ROSAGO_PUBLIC_ORIGIN'))
        transport=environment.get('ROSAGO_EVALUATION_TRANSPORT','managed-proxy')
        loopback=urlsplit(origin).hostname in ('localhost', '127.0.0.1', '::1')
        if transport=='managed-proxy':
            if (loopback or environment.get('ROSAGO_EVALUATION_PROXY_HOPS')!='1'
                    or environment.get('ROSAGO_PROXY_HEADERS_SANITIZED')!='true'):
                raise ValueError()
        elif transport=='direct-local-https':
            if (not loopback or environment.get('ROSAGO_EVALUATION_PROXY_HOPS')!='0'
                    or environment.get('ROSAGO_PROXY_HEADERS_SANITIZED') not in (None,'','false')):
                raise ValueError()
        else:
            raise ValueError()
        if any(environment.get(name) for name in (
            'SUPABASE_STORAGE_SECRET_KEY', 'SUPABASE_SERVICE_ROLE_KEY',
            'SUPABASE_JWT_SECRET', 'SUPABASE_ACCESS_TOKEN',
            'GEMINI_API_KEY', 'ORS_API_KEY', 'DATABASE_URL',
        )):
            raise ValueError()
        # Email, paid AI and photo mutation are disabled in this initial profile.
        if environment.get('ROSAGO_EVALUATION_EMAIL_MODE') != 'disabled':
            raise ValueError()
        if environment.get('ROUTING_PROVIDER') != 'disabled':
            raise ValueError()
        if environment.get('OSRM_BASE_URL'):
            raise ValueError()
        secret = environment.get('FLASK_SECRET_KEY', '')
        if len(secret) < 32:
            raise ValueError()
    except (TypeError, ValueError, AttributeError):
        # Never include configuration values, tokens or exception chains.
        raise ValueError('Isolated evaluation configuration rejected.') from None
    return {'project_ref': project, 'origin': origin,
            'email': 'disabled', 'paid_ai': 'disabled', 'photo_mutations': 'disabled',
            'transport':transport}


def configure_evaluation_http(app, environment):
    """Prepare HTTP settings only. Does not qualify any session backend/proxy."""
    from werkzeug.middleware.proxy_fix import ProxyFix
    settings = validate_evaluation_environment(environment)
    host = urlsplit(settings['origin']).hostname
    app.config.update(TRUSTED_HOSTS=[host], SESSION_COOKIE_DOMAIN=None,
                      SESSION_COOKIE_SECURE=True, SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE='Lax')
    # Trust only scheme from the attested single edge hop, never client IP/Host.
    # Operator must verify the actual managed edge overwrites this header.
    if settings['transport']=='managed-proxy':
        app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_for=0, x_host=0,
                                x_port=0, x_prefix=0)

    @app.before_request
    def canonical_evaluation_origin():
        from flask import abort, request
        if request.host_url.rstrip('/') != settings['origin']:
            abort(400)

    @app.after_request
    def evaluation_privacy_headers(response):
        response.headers['Permissions-Policy'] = 'geolocation=(), camera=(), microphone=()'
        response.headers['X-RosaGo-Evaluation'] = 'synthetic-isolated'
        # A second CSP intersects with existing auth policies, never relaxes them.
        evaluation_backend = 'https://' + settings['project_ref'] + '.supabase.co'
        response.headers.add('Content-Security-Policy',
            "connect-src 'self' " + evaluation_backend + "; img-src 'self' data: blob: "
            + evaluation_backend + ' https://tile.openstreetmap.org https://*.tile.openstreetmap.org')
        return response
    return settings

