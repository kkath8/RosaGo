"""Offline MockTransport checks; no live sign-ins/logout or hosted RPC calls."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx
from normal_auth_coordinator import SupabaseAdapters


class ProviderSessionTransportTests(unittest.TestCase):
    def setUp(self):
        self.url = 'https://jfaufpfzfhysqkhcdsrs.supabase.co'
        self.issuer = self.url + '/auth/v1'
        self.record = SimpleNamespace(user_id='synthetic-user',
            session_id='synthetic-session',access_token='synthetic-access')
        self.requests = []
        self.options = []
        self.answer = lambda request: httpx.Response(200, json=True)
        def respond(request):
            self.requests.append(request)
            return self.answer(request)
        def factory(**options):
            self.options.append(options)
            return httpx.Client(transport=httpx.MockTransport(respond), **options)
        self.adapter = SupabaseAdapters(self.url,'sb_publishable_synthetic',http_factory=factory)

    def test_strict_boolean_current_session_read_and_request_scope(self):
        for status in (True,False):
            self.answer = lambda request, status=status: httpx.Response(200,json=status)
            self.assertIs(self.adapter.provider_session_check(self.record,self.issuer,'user'),status)
        for request in self.requests:
            self.assertEqual(str(request.url),self.url+'/rest/v1/rpc/rosago_provider_session_current')
            self.assertEqual(request.method,'POST')
            self.assertEqual(request.content,b'{}')
            self.assertEqual(request.headers['Authorization'],'Bearer synthetic-access')
            self.assertEqual(request.headers['apikey'],'sb_publishable_synthetic')
        self.assertTrue(all(o=={'timeout':2.0,'follow_redirects':False,'trust_env':False} for o in self.options))

    def test_errors_redirects_malformed_and_uninstalled_rpc_are_unknown(self):
        answers=[httpx.Response(404),httpx.Response(401),httpx.Response(503),
                 httpx.Response(302,headers={'Location':'https://forbidden.invalid'}),
                 httpx.Response(200,json=1),httpx.Response(200,json={'active':True}),
                 httpx.Response(200,text='private-invalid-json'),
                 httpx.Response(200,text=' '*129+'true')]
        for answer in answers:
            self.answer=lambda request,answer=answer: answer
            before=len(self.requests)
            self.assertIsNone(self.adapter.provider_session_check(self.record,self.issuer,'admin'))
            self.assertEqual(len(self.requests),before+1)

    def test_issuer_or_subject_errors_make_no_requests(self):
        for issuer,realm,record in ((self.issuer+'-wrong','user',self.record),
                                   (self.issuer,'other',self.record),
                                   (self.issuer,'user',SimpleNamespace())):
            self.assertIsNone(self.adapter.provider_session_check(record,issuer,realm))
            self.assertIsNone(self.adapter.sign_out_current_session(record,issuer,realm))
        self.assertEqual(self.requests,[])

    def test_logout_has_current_session_scope_only(self):
        self.answer=lambda request: httpx.Response(204)
        self.assertIs(self.adapter.sign_out_current_session(self.record,self.issuer,'admin'),True)
        self.assertEqual(str(self.requests[0].url),self.url+'/auth/v1/logout?scope=local')
        self.assertEqual(len(self.requests),1)

    def test_uncertain_logout_is_not_retried_or_claimed_successful(self):
        def uncertain(request):
            raise httpx.ReadTimeout('synthetic token-bearing private detail')
        self.answer=uncertain
        self.assertIsNone(self.adapter.sign_out_current_session(self.record,self.issuer,'user'))
        self.assertEqual(len(self.requests),1)

    def test_logout_does_not_buffer_a_provider_body(self):
        class Unreadable(httpx.SyncByteStream):
            def __iter__(self):raise AssertionError('Acknowledgement must not read the body')
        self.answer=lambda request:httpx.Response(204,stream=Unreadable())
        self.assertIs(self.adapter.sign_out_current_session(self.record,self.issuer,'user'),True)
        self.assertEqual(len(self.requests),1)

    def test_status_stream_is_bounded_and_slow_or_encoded_proof_is_unknown(self):
        observed=[]
        class Chunks(httpx.SyncByteStream):
            def __iter__(self):
                for _ in range(100):observed.append(1);yield b' '*65
        self.answer=lambda request:httpx.Response(200,stream=Chunks())
        self.assertIsNone(self.adapter.provider_session_check(self.record,self.issuer,'user'))
        self.assertEqual(len(observed),2)
        observed.clear()
        self.answer=lambda request:httpx.Response(200,headers={'Content-Encoding':'gzip'},stream=Chunks())
        self.assertIsNone(self.adapter.provider_session_check(self.record,self.issuer,'user'))
        self.assertEqual(observed,[])
        self.answer=lambda request:httpx.Response(200,json=True)
        with patch('normal_auth_coordinator.time.monotonic',side_effect=[0,3]):
            self.assertIsNone(self.adapter.provider_session_check(self.record,self.issuer,'user'))
