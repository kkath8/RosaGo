"""Synthetic credential replay and logout-proof regressions; no provider I/O."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from durable_session_logout import DurableLogout
from independent_provider_sessions import IndependentProviderSessions, IndependentProviderAdapters, ISSUER, evaluation_runtime
from normal_auth_coordinator import (VerifiedLoginCredentials, PasswordLoginError,
    NormalAuthCoordinator, AuthenticationRequired, ClientUnavailable)
from normal_auth_store import NormalAuthStore
from session_realms import SessionStorageUnavailable
import test_admin_authorization as foundation
import test_registration


class ReceiptRealm:
    """Tiny local CAS fixture; durable backend fencing has separate regressions."""
    def __init__(self,realm,record):
        self.realm=realm;self.data={f'{realm}:web:web':{'values':{'auth_session_id':'auth'}},
            f'{realm}:auth:auth':{'record':record}}
    def snapshot(self,kind,handle):
        key=f'{self.realm}:{kind}:{handle}'
        return SimpleNamespace(key=key,data=deepcopy(self.data.get(key)),now=100,meta={'expires':10000})
    def atomic(self,reads,updates):
        for key,(value,_,_) in updates.items():self.data[key]=deepcopy(value)
    def write(self,snapshot,value,expires):self.data[snapshot.key]=deepcopy(value)
    def now(self):return 100
    def readiness(self):return {'ready':True}


class IndependentLogoutProofTests(unittest.TestCase):
    def setUp(self):
        self.now=1900000000.
        self.record=VerifiedLoginCredentials('11111111-1111-4111-8111-111111111111',
            'synthetic@example.invalid','synthetic-access','synthetic-refresh',self.now+1000,
            '22222222-2222-4222-8222-222222222222')
        self.realms={r:ReceiptRealm(r,self.record) for r in ('user','admin')}

    def test_missing_provider_row_cannot_confirm_logout_without_independent_tombstone(self):
        signout=Mock(return_value=None);presence=Mock(return_value=False);revoked=Mock(return_value=False)
        logout=DurableLogout(self.realms,issuer=ISSUER,sign_out=signout,
            session_check=presence,revocation_check=revoked)
        self.assertFalse(logout('admin','web'))
        self.assertIsNone(self.realms['admin'].snapshot('auth','auth').data)
        self.assertIsNotNone(self.realms['user'].snapshot('auth','auth').data)
        for outcome in (False,None,OSError('synthetic transport error')):
            revoked.side_effect=outcome if isinstance(outcome,Exception) else None
            revoked.return_value=outcome
            self.assertFalse(logout.reconcile('admin','web'))
            self.assertEqual(self.realms['admin'].snapshot('logout','web').data['state'],'attempted')
        # An Auth-row restore is not accepted as a completed logout either.
        revoked.side_effect=None;revoked.return_value=True;presence.return_value=True
        self.assertFalse(logout.reconcile('admin','web'))
        presence.return_value=False
        self.assertTrue(logout.reconcile('admin','web'))
        self.assertEqual(signout.call_count,1)
        self.assertNotIn('record',self.realms['admin'].snapshot('logout','web').data)

    def test_initial_provider_ack_and_absence_still_require_strict_revocation_proof(self):
        for outcome in (False,None,1,'revoked'):
            with self.subTest(outcome=outcome):
                realms={r:ReceiptRealm(r,self.record) for r in ('user','admin')}
                logout=DurableLogout(realms,issuer=ISSUER,sign_out=Mock(return_value=True),
                    session_check=Mock(return_value=False),revocation_check=Mock(return_value=outcome))
                self.assertFalse(logout('admin','web'))

    def authority(self,status=None,error=None):
        def exchange(request):
            if error:raise error
            return {**request,**status}
        return IndependentProviderSessions(authority_id='a'*24,incarnation='b'*24,
            namespace='synthetic',transports={op:Mock(exchange=Mock(side_effect=exchange))
            for op in ('enroll','check','revoke')},clock=lambda:self.now)

    def test_unknown_expired_and_inactive_admission_are_not_revocation_tombstones(self):
        cases=[(dict(active=False,known=False,revoked=False,expired=False),False),
            (dict(active=False,known=True,revoked=False,expired=True),False),
            (dict(active=True,known=True,revoked=False,expired=False),False),
            (dict(active=False,known=True,revoked=True,expired=True),True)]
        for status,expected in cases:
            with self.subTest(status=status):
                self.assertIs(self.authority(status).revocation_confirmed(self.record,ISSUER,'admin'),expected)
        self.assertIsNone(self.authority(error=OSError()).revocation_confirmed(self.record,ISSUER,'admin'))

    def test_authority_and_login_errors_drop_sensitive_exception_context(self):
        authority=self.authority(error=OSError('synthetic-private-credential'))
        with self.assertRaises(SessionStorageUnavailable) as failure:authority.enroll_verified_login(self.record)
        self.assertIsNone(failure.exception.__context__)
        self.assertNotIn('synthetic-private-credential',str(failure.exception))
        base=Mock(issuer=ISSUER);base.password_login.return_value=self.record
        with self.assertRaises(PasswordLoginError) as login:IndependentProviderAdapters(base,authority).password_login('fixture','private')
        self.assertIsNone(login.exception.__context__)

    def test_evaluation_composition_requires_distinct_independent_revocation_proof(self):
        authority=self.authority(dict(active=True,known=True,revoked=False,expired=False))
        runtime=evaluation_runtime(realms=self.realms,model_factory=Mock(),challenges_factory=Mock(),
            authority=authority,url=ISSUER.removesuffix('/auth/v1'),public_key='sb_publishable_synthetic',
            base_factory=lambda *_:Mock(issuer=ISSUER))
        self.assertIs(runtime.logout_handler.revocation_check.__self__,authority)
        self.assertEqual(runtime.logout_handler.revocation_check.__name__,'revocation_confirmed')

    def test_checker_rejects_replayed_fresh_local_session_after_independent_denial(self):
        clock=lambda:100.
        store=NormalAuthStore(clock=clock)
        handle=store.create(user_id=self.record.user_id,user_email=self.record.user_email,
            access_token='synthetic-old-jwt',refresh_token='synthetic-old-refresh',
            access_expires_at=1000,session_id=self.record.session_id)
        clients=Mock();refresh=Mock();proof=Mock(return_value=False)
        coordinator=NormalAuthCoordinator(store,refresh_transport=refresh,client_factory=clients,
            issuer=ISSUER,realm='admin',clock=clock,provider_session_check=proof)
        for _ in range(2):
            with self.assertRaises(AuthenticationRequired):
                with coordinator.authenticated(handle):self.fail('Replayed authority accepted')
        clients.assert_not_called();refresh.assert_not_called();self.assertIsNone(store.resolve(handle))


class AdminBrowserReplayTests(unittest.TestCase):
    setUp=foundation.AdminBoundaryTests.setUp
    tearDown=foundation.AdminBoundaryTests.tearDown
    protected=foundation.AdminBoundaryTests.protected

    def test_terminated_cookie_and_csrf_replay_never_recreate_admin_authority(self):
        handle=test_registration.seed_admin_session(self);self.value=True
        user=test_registration.seed_normal_session(self)
        interface=self.app.session_interface
        cookie=self.client.get_cookie(interface.cookie_name,path='/admin').value
        csrf=self.dependencies.store.resolve(handle).csrf
        self.protected(self.client.post('/admin/logout',data={'csrf_token':csrf},
            headers={'Origin':'http://localhost'}),303)
        for path in ('/admin','/admin/account','/admin/settings'):
            self.client.set_cookie(interface.cookie_name,cookie,path='/admin')
            self.protected(self.client.get(path),302)
        self.client.set_cookie(interface.cookie_name,cookie,path='/admin')
        self.protected(self.client.post('/admin/logout',data={'csrf_token':csrf},
            headers={'Origin':'http://localhost'}),302)
        self.assertIsNone(self.dependencies.store.resolve(handle))
        self.assertIsNone(interface.store.read(cookie))
        self.assertIsNotNone(self.app.extensions['rosago_normal_auth'].store.resolve(user))

    def test_expired_refresh_replay_revokes_admin_handle_without_changing_user(self):
        handle=test_registration.seed_admin_session(self);self.value=True
        user=test_registration.seed_normal_session(self)
        from unittest.mock import patch
        record=self.dependencies.store._records[handle]
        self.dependencies.store._records[handle]=replace(record,access_expires_at=1.)
        with patch.object(self.dependencies.coordinator,'_refresh',side_effect=AuthenticationRequired()) as refresh:
            self.protected(self.client.get('/admin/account'),302)
            refresh.assert_called_once()
        self.assertIsNone(self.dependencies.store.resolve(handle))
        self.assertIsNotNone(self.app.extensions['rosago_normal_auth'].store.resolve(user))
