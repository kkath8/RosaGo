"""Operation-owned public Supabase clients; no authentication/session integration."""
import base64
import binascii
from contextlib import contextmanager
import json
from urllib.parse import urlsplit

import httpx
from supabase import ClientOptions, create_client


def _configuration(url, key):
    valid = False
    try:
        if type(url) is str and type(key) is str:
            parsed = urlsplit(url)
            valid = bool(
                url == url.strip() and parsed.scheme == 'https' and parsed.hostname
                and not parsed.username and not parsed.password
                and not parsed.query and not parsed.fragment
                and parsed.path in ('', '/')
                and key and not any(c.isspace() for c in key))
            if key.startswith('sb_publishable_'):
                valid = valid and len(key) > len('sb_publishable_')
            else:
                parts = key.split('.')
                if len(parts) != 3 or not all(parts):
                    valid = False
                else:
                    payload = json.loads(base64.urlsafe_b64decode(
                        parts[1] + '=' * (-len(parts[1]) % 4)))
                    valid = valid and isinstance(payload, dict) and payload.get('role') == 'anon'
    except (ValueError, TypeError, binascii.Error):
        valid = False
    # Raise outside parsing handlers: diagnostics must not retain key material.
    if not valid:
        raise ValueError('Invalid places public configuration.') from None
    # Structural classification only; the provider verifies the actual key.
    return url.rstrip('/'), key


class PublicPlacesClient:
    """Inject database_client into PlacesService; construction makes no requests."""

    def __init__(self, url, public_key, *, sdk_factory=create_client,
                 http_factory=httpx.Client):
        self._url, self._key = _configuration(url, public_key)
        self._sdk_factory = sdk_factory
        self._http_factory = http_factory

    def __repr__(self):
        return '<PublicPlacesClient redacted>'

    @contextmanager
    def database_client(self):
        # No caller token/header/session input. The SDK supplies public-key auth.
        http = self._http_factory(timeout=20, follow_redirects=False, trust_env=False)
        primary = None
        try:
            client = self._sdk_factory(self._url, self._key, options=ClientOptions(
                headers={}, persist_session=False, auto_refresh_token=False,
                httpx_client=http, schema='public'))
            yield client
        except BaseException as error:
            primary = error
        # Close outside the primary handler so cleanup cannot retain its chain.
        try:
            http.close()
        except BaseException as error:
            if primary is None:
                primary = error
            elif not isinstance(error, Exception):
                # A new shutdown/cancellation signal must still propagate.
                error.add_note('Places operation also failed before cleanup.')
                primary = error
            else:
                # Preserve the first failure; disclose the secondary failure
                # without retaining potentially sensitive cleanup diagnostics.
                primary.add_note('Places client cleanup also failed.')
        if primary is not None:
            raise primary
