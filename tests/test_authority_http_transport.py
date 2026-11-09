import json
import unittest
import httpx
from authority_http_transport import AuthorityHTTPTransport
from session_realms import SessionStorageUnavailable


class TransportTests(unittest.TestCase):
    def test_rejects_unreviewed_endpoints_and_credentials(self):
        for url in ('http://authority.invalid/v1/authority','https://x.invalid/operator/initialize',
                    'https://a:b@x.invalid/v1/authority','https://x.invalid/v1/authority?q=1'):
            with self.assertRaises(ValueError): AuthorityHTTPTransport(url,'a'*40)

    def transport(self,handler):
        def factory(**options):
            self.assertFalse(options['follow_redirects']);self.assertFalse(options['trust_env'])
            return httpx.Client(transport=httpx.MockTransport(handler),**options)
        return AuthorityHTTPTransport('https://authority.invalid/v1/authority','a'*40,client_factory=factory)

    def test_authenticated_single_request_no_redirect_or_retry(self):
        calls=[]
        def handler(request):
            calls.append(request)
            self.assertEqual(request.headers['Authorization'],'Bearer '+'a'*40)
            return httpx.Response(302,headers={'Location':'https://forbidden.invalid'})
        with self.assertRaises(SessionStorageUnavailable):self.transport(handler).exchange({'operation':'commit'})
        self.assertEqual(len(calls),1)

    def test_bounds_json_errors_and_private_exceptions_are_sanitized(self):
        for response in (httpx.Response(200,content=b'x'*65537),httpx.Response(200,json=[]),httpx.Response(503)):
            with self.assertRaises(SessionStorageUnavailable) as error:
                self.transport(lambda request:response).exchange({})
            self.assertNotIn('aaaa',str(error.exception))
        self.assertEqual(self.transport(lambda request:httpx.Response(200,json={'status':'ok'})).exchange({}),{'status':'ok'})
