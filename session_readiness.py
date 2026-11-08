"""Configuration preflight and LOCAL HTTPS qualification. No remote connections.

Successful validation is NOT production activation. The production startup
refusal in session_realms remains unconditional.
"""
import base64
import json
import re
from urllib.parse import urlsplit

from redis_session_flask import validate_https_configuration
from session_crypto import SessionCipher


def validate_settings(app,environ):
    try:
        if environ['ROSAGO_AUTH_MODE']!='production' or environ['ROSAGO_SESSION_BACKEND']!='redis':
            raise ValueError()
        ring=json.loads(environ['ROSAGO_SESSION_KEYRING'])
        SessionCipher({k:base64.b64decode(v,validate=True) for k,v in ring['keys'].items()},ring['current'])
        hops=int(environ['ROSAGO_PROXY_HOPS'])
        validate_https_configuration(app,environ['ROSAGO_PUBLIC_ORIGIN'],hops)
        if hops and environ.get('ROSAGO_PROXY_HEADERS_SANITIZED')!='true':
            raise ValueError()
        for realm in ('USER','ADMIN'):
            parsed=urlsplit(environ[f'ROSAGO_SESSION_REDIS_{realm}_URL'])
            if (parsed.scheme!='rediss' or not parsed.hostname or parsed.query or parsed.fragment
                    or not parsed.username or not parsed.password):
                raise ValueError()
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',environ[f'ROSAGO_{realm}_SESSION_EPOCH']):
                raise ValueError()
        if (app.config.get('SESSION_COOKIE_DOMAIN') or
                not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',environ['ROSAGO_SESSION_NAMESPACE'])):
            raise ValueError()
        if (not app.config.get('SESSION_COOKIE_SECURE') or not app.config.get('SESSION_COOKIE_HTTPONLY')
                or app.config.get('SESSION_COOKIE_SAMESITE')!='Lax'):
            raise ValueError()
    except (KeyError,ValueError,TypeError):
        raise ValueError('Production session configuration preflight failed.') from None
    return {'configuration_valid':True,'production_approved':False,
            'blockers':['Independent protected multi-host authority and failover must be qualified.',
                        'Production startup safeguard remains active.']}


def configure_local_https(app,environ):
    """Opt-in isolated HTTPS/proxy tests only; no production bypass."""
    if environ.get('ROSAGO_LOCAL_HTTPS_QUALIFICATION')!='true':
        return False
    try:
        from public_auth_security import validate_public_origin
        origin=validate_public_origin(environ['ROSAGO_PUBLIC_ORIGIN'])
        hosts=json.loads(environ['ROSAGO_TRUSTED_HOSTS'])
        if hosts != [urlsplit(origin).hostname]:
            raise ValueError()
        app.config['TRUSTED_HOSTS']=hosts
        hops=int(environ['ROSAGO_PROXY_HOPS'])
        validate_https_configuration(app,environ['ROSAGO_PUBLIC_ORIGIN'],hops)
        app.config.update(SESSION_COOKIE_SECURE=True,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax')
        if hops:
            if environ.get('ROSAGO_PROXY_HEADERS_SANITIZED')!='true':
                raise ValueError()
            from werkzeug.middleware.proxy_fix import ProxyFix
            app.wsgi_app=ProxyFix(app.wsgi_app,x_for=0,x_proto=hops,x_host=0,x_port=0,x_prefix=0)
        @app.before_request
        def local_qualification_origin():
            from flask import request,abort
            if request.host_url.rstrip('/') != origin:
                abort(400)
    except (KeyError,ValueError,TypeError):
        raise RuntimeError('Invalid local HTTPS qualification configuration.') from None
    return True
