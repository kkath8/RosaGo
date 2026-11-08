"""Offline composition/transport tests; no provider sign-in or remote requests."""
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
import httpx
from authority_http_transport import AuthorityHTTPTransport
from independent_provider_sessions import IndependentProviderSessions, IndependentProviderAdapters, ISSUER
from normal_auth_coordinator import VerifiedLoginCredentials, ClientUnavailable, SupabaseAdapters, PasswordLoginError
from session_realms import SessionStorageUnavailable


class IndependentProviderTests(unittest.TestCase):
    def setUp(self):
        self.now=1900000000.
        self.credentials=VerifiedLoginCredentials('11111111-1111-4111-8111-111111111111',
            'fixture@example.invalid','synthetic-access','synthetic-refresh',self.now+1000,
            '22222222-2222-4222-8222-222222222222')
        self.revoked=False;self.enrolled=False;self.calls=[]
        def exchange(operation,request):
            self.calls.append(operation)
            if operation=='enroll':self.enrolled=True
            if operation=='revoke':self.revoked=True
            return {**{k:v for k,v in request.items() if k!='deadline'},
                'active':self.enrolled and not self.revoked,'known':self.enrolled or self.revoked,'revoked':self.revoked,'expired':False}
        self.transports={op:Mock(exchange=Mock(side_effect=lambda r,op=op:exchange(op,r))) for op in ('enroll','check','revoke')}
        self.authority=IndependentProviderSessions(authority_id='a'*24,incarnation='b'*24,
            namespace='fixture',transports=self.transports,clock=lambda:self.now)
        self.base=Mock(issuer=ISSUER)
        self.base.password_login.return_value=self.credentials
        self.base.provider_session_check.return_value=True
        self.base.provider_session_present.return_value=True
        self.base.sign_out_current_session.return_value=True
        self.adapter=IndependentProviderAdapters(self.base,self.authority)

    def test_verified_password_login_enrolls_before_membership_query_and_refresh_never_enrolls(self):
        result=self.adapter.password_login('fixture@example.invalid','private-synthetic-password')
        self.assertIs(result,self.credentials);self.assertEqual(self.calls,['enroll'])
        self.adapter.refresh('synthetic-refresh');self.assertEqual(self.calls,['enroll'])
        self.assertTrue(self.adapter.provider_session_check(result,ISSUER,'admin'))

    def test_unverified_expired_wrong_target_admission_rejected(self):
        for c in (SimpleNamespace(**self.credentials.__dict__) if hasattr(self.credentials,'__dict__') else {},
                  replace(self.credentials,access_expires_at=self.now)):
            with self.assertRaises(ClientUnavailable): self.authority.enroll_verified_login(c)
        with self.assertRaises(ValueError): IndependentProviderAdapters(Mock(issuer='https://other.invalid'),self.authority)
        self.assertEqual(self.calls,[])

    def test_logout_revokes_before_provider_and_restored_provider_row_stays_denied(self):
        self.adapter.password_login('synthetic','private')
        def logout(*args):
            self.assertTrue(self.revoked);return True
        self.base.sign_out_current_session.side_effect=logout
        self.assertTrue(self.adapter.sign_out_current_session(self.credentials,ISSUER,'user'))
        self.assertFalse(self.adapter.provider_session_check(self.credentials,ISSUER,'user'))
        self.base.provider_session_check.assert_not_called()
        self.assertTrue(self.adapter.provider_session_present(self.credentials,ISSUER,'user'))

    def test_unknown_and_outage_deny_without_calling_provider_or_destroying_state(self):
        self.assertFalse(self.adapter.provider_session_check(self.credentials,ISSUER,'user'))
        self.transports['check'].exchange.side_effect=OSError('synthetic-private-message')
        self.assertIsNone(self.adapter.provider_session_check(self.credentials,ISSUER,'user'))
        self.base.provider_session_check.assert_not_called()
        self.transports['revoke'].exchange.side_effect=OSError('synthetic-private-message')
        self.assertIsNone(self.adapter.sign_out_current_session(self.credentials,ISSUER,'user'))
        self.base.sign_out_current_session.assert_not_called()

    def test_nonce_identity_clock_boolean_and_inconsistent_response_replays_rejected(self):
        patches=[{'nonce':'old'}, {'uid':'other'}, {'incarnation':'old'}, {'now':self.now-10},{'version':True},
                 {'now':float('nan')},{'active':1},{'active':True,'known':False}]
        for patch in patches:
            def reply(r):return {**r,'active':False,'known':False,'revoked':False,'expired':False,**patch}
            self.transports['check'].exchange.side_effect=reply
            self.assertIsNone(self.authority.current(self.credentials,ISSUER,'user'))

    def test_enrollment_transport_failure_does_not_return_login_credentials(self):
        self.transports['enroll'].exchange.side_effect=OSError('synthetic-private-message')
        with self.assertRaises(PasswordLoginError) as caught:self.adapter.password_login('synthetic','private')
        self.assertNotIn('synthetic-private-message',str(caught.exception))

    def test_each_request_calls_authority_and_checks_provider_when_admitted(self):
        self.adapter.password_login('synthetic','private')
        for realm in ('user','admin'):
            self.assertTrue(self.adapter.provider_session_check(self.credentials,ISSUER,realm))
        self.assertEqual(self.calls,['enroll','check','check']);self.assertEqual(self.base.provider_session_check.call_count,2)

    def test_presence_diagnostic_has_separate_rpc_and_does_not_treat_denial_as_absence(self):
        requests=[]
        def factory(**kwargs):
            return httpx.Client(transport=httpx.MockTransport(lambda r:(requests.append(r),httpx.Response(200,json=True))[1]),**kwargs)
        adapter=SupabaseAdapters(ISSUER.removesuffix('/auth/v1'),'sb_publishable_synthetic',http_factory=factory)
        self.assertTrue(adapter.provider_session_present(self.credentials,ISSUER,'user'))
        self.assertTrue(str(requests[0].url).endswith('/rpc/rosago_provider_session_present'))

    def test_provider_transport_is_https_scoped_no_redirects_proxies_or_sensitive_errors(self):
        options=[]
        def factory(**kwargs):
            options.append(kwargs)
            return httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(307,headers={'Location':'https://other.invalid'})),**kwargs)
        transport=AuthorityHTTPTransport('https://authority.invalid/v1/provider/check','x'*40,
            expected_path='/v1/provider/check',client_factory=factory)
        try:
            with self.assertRaises(SessionStorageUnavailable):transport.exchange({})
            self.assertFalse(options[0]['trust_env']);self.assertFalse(options[0]['follow_redirects'])
        finally:transport.close()
        with self.assertRaises(ValueError):AuthorityHTTPTransport('https://authority.invalid/v1/provider/enroll','x'*40,
            expected_path='/v1/provider/check')

    def test_explicit_runtime_wires_both_login_flows_and_raw_presence_logout_checker(self):
        from flask import Flask
        from normal_auth_store import NormalAuthStore
        from normal_auth_flask import init_normal_auth
        from admin_session_flask import init_admin_auth
        from independent_provider_sessions import evaluation_runtime
        realms={realm:SimpleNamespace(realm=realm,readiness=Mock(return_value={'ready':True}),
            snapshot=Mock(),atomic=Mock(),write=Mock(),now=Mock()) for realm in ('user','admin')}
        factory=Mock(return_value=self.base)
        runtime=evaluation_runtime(realms=realms,model_factory=lambda *_:NormalAuthStore(),
            challenges_factory=Mock(),authority=self.authority,url=ISSUER.removesuffix('/auth/v1'),
            public_key='sb_publishable_synthetic',base_factory=factory)
        app=Flask('explicit-provider-runtime');runtime.install(app)
        init_normal_auth(app,ISSUER.removesuffix('/auth/v1'),'sb_publishable_synthetic')
        init_admin_auth(app,ISSUER.removesuffix('/auth/v1'),'sb_publishable_synthetic')
        for name in ('rosago_normal_auth','rosago_admin_auth'):
            self.assertIsInstance(app.extensions[name].adapters,IndependentProviderAdapters)
            app.extensions[name].adapters.password_login('synthetic','private')
        self.assertEqual(self.calls,['enroll','enroll'])
        self.assertEqual(runtime.logout_handler.session_check.__name__,'provider_session_present')
        with self.assertRaises(ValueError):runtime.adapters_factory('https://other.invalid','sb_publishable_synthetic')

if __name__=='__main__':unittest.main()
