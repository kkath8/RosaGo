"""Inactive bounded HTTPS transport for the independently managed authority.

Explicit dependency injection only; no environment loader, redirects, proxies,
automatic retries or remote bootstrap. Errors never expose bearer credentials.
"""
import json
import os
import time
from urllib.parse import urlsplit

import httpx
from session_realms import SessionStorageUnavailable


class AuthorityHTTPTransport:
    def __init__(self, url, token, *, client_factory=httpx.Client, local_test=False,
                 expected_path='/v1/authority'):
        parsed = urlsplit(url)
        local = local_test is True and parsed.scheme in ('http','https') and parsed.hostname in ('127.0.0.1', 'localhost')
        if (not (parsed.scheme == 'https' or local) or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or expected_path not in ('/v1/authority','/v1/provider/enroll','/v1/provider/check',
                                         '/v1/provider/revoke','/v1/provider/inspect')
                or parsed.path != expected_path
                or (not local and parsed.port not in (None,443))
                or type(token) is not str or not 32 <= len(token) <= 256
                or any(c.isspace() for c in token)):
            raise ValueError('Invalid authority endpoint or credential.')
        self._url, self._token, self._factory = url, token, client_factory
        self._pid=os.getpid()
        self._client=self._factory(timeout=httpx.Timeout(.3), follow_redirects=False, trust_env=False,
            limits=httpx.Limits(max_connections=2,max_keepalive_connections=2,keepalive_expiry=15))

    def close(self):
        self._client.close()

    def exchange(self, request):
        started = time.monotonic()
        try:
            encoded=json.dumps(request, allow_nan=False, separators=(',', ':')).encode()
            if len(encoded)>65536: raise ValueError()
            if self._pid!=os.getpid(): raise ValueError()
            with self._client.stream('POST', self._url, content=encoded,
                                     headers={'Authorization':'Bearer '+self._token,
                                              'Content-Type':'application/json','Accept':'application/json'}) as response:
                if response.status_code != 200 or response.headers.get('Content-Encoding','identity')!='identity': raise ValueError()
                raw=bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw)>65536 or time.monotonic()-started>1: raise ValueError()
                if time.monotonic()-started>1: raise ValueError()
                result=json.loads(raw)
                if type(result) is not dict: raise ValueError()
                return result
        except Exception:
            raise SessionStorageUnavailable('Independent authority transport is unavailable.') from None
