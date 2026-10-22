r"""Manual read-only RLS verification; never imported by Flask or test discovery.

Run from a local interactive terminal:
    .\.venv\Scripts\python.exe tools/verify_profile_reads.py
Only password sign-in POSTs and Auth/profile GETs are permitted. Sign-in creates
Auth sessions, but this script never writes database profiles or persists tokens.
"""
import base64
import getpass
import json
import logging
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit
from uuid import UUID
import warnings

import httpx
from dotenv import dotenv_values


class VerificationError(Exception):
    """Carries only a category from the fixed allowlist below."""


CATEGORIES = frozenset({
    'CONFIG_ERROR: missing project URL', 'CONFIG_ERROR: missing public key',
    'CONFIG_ERROR: invalid project URL', 'CONFIG_ERROR: public key rejected',
    'AUTH_A_FAILED', 'AUTH_B_FAILED',
    'AUTH_A_IDENTITY_VALIDATION_FAILED', 'AUTH_B_IDENTITY_VALIDATION_FAILED',
    'AUTH_NETWORK_ERROR', 'REST_NETWORK_ERROR', 'REST_RESPONSE_INVALID',
    'OWN_PROFILE_RESULT_INVALID', 'OWN_PROFILE_FIXTURE_MISMATCH',
    'CROSS_USER_ISOLATION_FAILED', 'UNFILTERED_ISOLATION_FAILED',
    'ANON_SELECT_UNEXPECTEDLY_ALLOWED', 'ANON_PERMISSION_DENIAL_NOT_CONFIRMED',
    'ANON_CONTEXT_INVALID', 'IDENTITIES_NOT_DISTINCT',
    'HIDDEN_INPUT_UNAVAILABLE', 'REQUEST_NOT_ALLOWED',
    'VERIFIER_INTERRUPTED', 'VERIFIER_INTERNAL_ERROR',
})


def require(condition, category='VERIFIER_INTERNAL_ERROR'):
    if not condition:
        raise VerificationError(category if category in CATEGORIES else 'VERIFIER_INTERNAL_ERROR')


def body(response, category):
    try:
        return response.json()
    except (ValueError, UnicodeError):
        raise VerificationError(category) from None


def configuration():
    config = dotenv_values(Path(__file__).resolve().parents[1] / '.env')
    url = os.environ.get('SUPABASE_URL', config.get('SUPABASE_URL', ''))
    key = os.environ.get('SUPABASE_KEY', config.get('SUPABASE_KEY', ''))
    require(isinstance(url, str) and bool(url.strip()), 'CONFIG_ERROR: missing project URL')
    require(isinstance(key, str) and bool(key.strip()), 'CONFIG_ERROR: missing public key')
    try:
        parsed = urlsplit(url)
        valid_url = (parsed.scheme == 'https' and parsed.hostname
            and parsed.hostname.endswith('.supabase.co')
            and not parsed.username and not parsed.password and not parsed.port
            and parsed.path in ('', '/') and not parsed.query and not parsed.fragment)
    except ValueError:
        valid_url = False
    require(valid_url, 'CONFIG_ERROR: invalid project URL')
    # Only publishable keys or legacy anon keys; never secret/service-role keys.
    if not key.startswith('sb_publishable_'):
        try:
            parts = key.split('.')
            require(len(parts) == 3, 'CONFIG_ERROR: public key rejected')
            payload = json.loads(base64.urlsafe_b64decode(parts[1] + '=' * (-len(parts[1]) % 4)))
            require(isinstance(payload, dict) and payload.get('role') == 'anon',
                    'CONFIG_ERROR: public key rejected')
        except (ValueError, UnicodeError):
            raise VerificationError('CONFIG_ERROR: public key rejected') from None
        # Local classification only; the server validates the key on requests.
    return url.rstrip('/'), key


def request(client, method, path, **kwargs):
    allowed = {('POST', '/auth/v1/token'), ('GET', '/auth/v1/user'),
               ('GET', '/rest/v1/profiles')}
    require((method, path) in allowed, 'REQUEST_NOT_ALLOWED')
    if method == 'POST':
        require(kwargs.get('params') == {'grant_type': 'password'}, 'REQUEST_NOT_ALLOWED')
    prefix = 'REST' if path == '/rest/v1/profiles' else 'AUTH'
    try:
        response = client.request(method, path, **kwargs)
    except httpx.RequestError:
        raise VerificationError(prefix + '_NETWORK_ERROR') from None
    if response.status_code != 200:
        # Only fixed status categories; no reason phrases, headers, or bodies.
        status = response.status_code
        category = f'{prefix}_HTTP_{status}' if status in (400, 401, 403, 404, 422, 429) else prefix + '_UNEXPECTED_STATUS'
        print(category)
    # No status exceptions: they can include URLs or response data.
    return response


def identity(client, label):
    require(label in ('A', 'B'))
    failure = f'AUTH_{label}_IDENTITY_VALIDATION_FAILED'
    response = request(client, 'GET', '/auth/v1/user')
    require(response.status_code == 200, failure)
    user = body(response, failure)
    require(isinstance(user, dict) and user.get('role') == 'authenticated'
            and user.get('email_confirmed_at') and isinstance(user.get('email'), str), failure)
    try:
        user_id = str(UUID(user['id']))
    except (ValueError, TypeError, KeyError, AttributeError):
        raise VerificationError(failure) from None
    return user_id, user['email']


def sign_in(client, label):
    require(label in ('A', 'B'))
    failure = f'AUTH_{label}_FAILED'
    # Refuse getpass's echoing fallback and redirected input.
    require(sys.stdin.isatty(), 'HIDDEN_INPUT_UNAVAILABLE')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            email = getpass.getpass(f'User {label} email (hidden): ').strip()
            password = getpass.getpass(f'User {label} password (hidden): ')
    except (getpass.GetPassWarning, EOFError):
        raise VerificationError('HIDDEN_INPUT_UNAVAILABLE') from None
    require(email and password, failure)
    print(f'CHECK: AUTH_{label}')
    response = request(client, 'POST', '/auth/v1/token',
                       params={'grant_type': 'password'},
                       json={'email': email, 'password': password})
    del password
    require(response.status_code == 200, failure)
    result = body(response, failure)
    require(isinstance(result, dict), failure)
    token = result.get('access_token')
    require(isinstance(token, str) and token, failure)
    require(isinstance(result.get('user'), dict) and isinstance(result['user'].get('id'), str), failure)
    client.headers['Authorization'] = 'Bearer ' + token
    expected_id = result['user']['id']
    del result, response, token
    user_id, verified_email = identity(client, label)
    require(user_id == expected_id and verified_email.casefold() == email.casefold(),
            f'AUTH_{label}_IDENTITY_VALIDATION_FAILED')
    print(f'PASS: AUTH_{label}_IDENTITY_VALIDATED')
    return user_id


def rows(client, user_id=None):
    params = {'select': 'id,first_name,last_name'}
    if user_id is not None:
        params['id'] = 'eq.' + user_id
    response = request(client, 'GET', '/rest/v1/profiles', params=params)
    require(response.status_code == 200, 'REST_RESPONSE_INVALID')
    data = body(response, 'REST_RESPONSE_INVALID')
    require(isinstance(data, list), 'REST_RESPONSE_INVALID')
    return data


def verify(a, b, anonymous, a_id, b_id):
    require(a_id != b_id, 'IDENTITIES_NOT_DISTINCT')
    checks = []
    print('CHECK: USER_A_OWN_PROFILE')
    own_a = rows(a, a_id)
    require(len(own_a) == 1 and isinstance(own_a[0], dict) and own_a[0].get('id') == a_id,
            'OWN_PROFILE_RESULT_INVALID')
    # Confirm the accounts correspond to the designated test fixtures.
    require(own_a == [{'id': a_id, 'first_name': 'Test', 'last_name': 'User'}], 'OWN_PROFILE_FIXTURE_MISMATCH')
    print('CHECK: USER_B_OWN_PROFILE')
    own_b = rows(b, b_id)
    require(len(own_b) == 1 and isinstance(own_b[0], dict) and own_b[0].get('id') == b_id,
            'OWN_PROFILE_RESULT_INVALID')
    require(own_b == [{'id': b_id, 'first_name': 'Profile', 'last_name': 'Test'}], 'OWN_PROFILE_FIXTURE_MISMATCH')
    checks.append(('User A can read own profile', True))
    print('CHECK: USER_A_READ_USER_B')
    require(rows(a, b_id) == [], 'CROSS_USER_ISOLATION_FAILED')
    checks.append(('User A cannot read User B profile', True))
    print('CHECK: USER_A_UNFILTERED')
    require(rows(a) == own_a, 'UNFILTERED_ISOLATION_FAILED')
    checks.append(('User A unfiltered SELECT returns only own profile', True))
    checks.append(('User B can read own profile', True))
    print('CHECK: USER_B_UNFILTERED')
    require(rows(b) == own_b, 'UNFILTERED_ISOLATION_FAILED')
    checks.append(('User B unfiltered SELECT returns only own profile', True))
    print('CHECK: ANONYMOUS_SELECT')
    require('Authorization' not in anonymous.headers and not anonymous.cookies, 'ANON_CONTEXT_INVALID')
    response = request(anonymous, 'GET', '/rest/v1/profiles', params={'select': 'id'})
    require(not 200 <= response.status_code < 300, 'ANON_SELECT_UNEXPECTEDLY_ALLOWED')
    error = body(response, 'ANON_PERMISSION_DENIAL_NOT_CONFIRMED')
    denied = (response.status_code in (401, 403) and isinstance(error, dict)
              and error.get('code') == '42501'
              and error.get('message') == 'permission denied for table profiles')
    require(denied, 'ANON_PERMISSION_DENIAL_NOT_CONFIRMED')
    checks.append(('Anonymous SELECT denied', True))
    # Revalidate user sessions before reporting any successful results.
    print('CHECK: AUTH_IDENTITY_REVALIDATION')
    require(identity(a, 'A')[0] == a_id, 'AUTH_A_IDENTITY_VALIDATION_FAILED')
    require(identity(b, 'B')[0] == b_id, 'AUTH_B_IDENTITY_VALIDATION_FAILED')
    for label, passed in checks:
        print(('PASS: ' if passed else 'FAIL: ') + label)
    return all(passed for _, passed in checks)


def main():
    logging.disable(logging.CRITICAL)
    try:
        url, key = configuration()
        options = dict(base_url=url, headers={'apikey': key}, timeout=20,
                       follow_redirects=False, trust_env=False)
        with httpx.Client(**options) as a, httpx.Client(**options) as b, httpx.Client(**options) as anonymous:
            # Explicit public schema; anonymous context has no user bearer token.
            for client in (a, b, anonymous):
                client.headers['Accept-Profile'] = 'public'
            a_id = sign_in(a, 'A')
            b_id = sign_in(b, 'B')
            passed = verify(a, b, anonymous, a_id, b_id)
        print('PASS: READ RLS verified' if passed else 'FAIL: READ RLS not verified')
        return 0 if passed else 1
    except VerificationError as error:
        category = error.args[0] if error.args else None
        print(category if category in CATEGORIES else 'VERIFIER_INTERNAL_ERROR')
    except KeyboardInterrupt:
        print('VERIFIER_INTERRUPTED')
    except Exception:
        # Never expose unexpected exception messages or tracebacks.
        print('VERIFIER_INTERNAL_ERROR')
    print('FAIL: READ RLS not verified')
    return 1


if __name__ == '__main__':
    sys.exit(main())
