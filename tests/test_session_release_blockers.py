"""Deterministic offline CAS-race and shared-rate wiring regressions; no services."""
from copy import deepcopy
from threading import Lock
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
from flask import Flask, session

from record_session_store import RedisModel
from redis_session_flask import shared_logout
from session_authority import RevisionConflict
from session_realms import LoginChallenges, SessionStorageUnavailable
from public_auth_security import email_attempt_allowed


class SyntheticRevocationBackend:
    def __init__(self, conflicts=0, uncertain=False):
        self.conflicts=conflicts
        self.uncertain=uncertain
        self.revision=1
        self.calls=0
        self.reads=0
        self.active=True

    def snapshot(self, kind, handle, revocation_only=False):
        self.reads+=1
        data={'values':{'auth_session_id':'auth-handle'}} if kind=='web' and self.active else None
        return NS(kind=kind,key=kind+':'+handle,meta={'revision':self.revision} if self.active else None,
                  data=data,now=100.0)

    def atomic(self, reads, updates):
        self.calls+=1
        assert all(value[0] is None for value in updates.values())
        if self.uncertain:
            raise SessionStorageUnavailable('Synthetic uncertain commit')
        if self.conflicts:
            self.conflicts-=1
            self.revision+=1
            raise RevisionConflict('Synthetic refresh conflict')
        assert all(s.meta==({'revision':self.revision} if self.active else None) for s in reads.values())
        self.active=False

    def write(self, snap, value, expires):
        self.atomic({snap.key:snap},{snap.key:(value,expires,{})})


class RevocationConflictTests(unittest.TestCase):
    def test_revoke_uses_fresh_snapshot_after_refresh_conflict(self):
        backend=SyntheticRevocationBackend(conflicts=1)
        self.assertTrue(RedisModel(backend,'auth').revoke('auth-handle'))
        self.assertFalse(backend.active)
        self.assertEqual(backend.calls,2)
        self.assertEqual(backend.reads,2)

    def test_shared_logout_retries_fresh_bounded_transition_in_selected_realm(self):
        for realm in ('user','admin'):
            with self.subTest(realm=realm):
                selected=SyntheticRevocationBackend(conflicts=1)
                other=SyntheticRevocationBackend()
                app=Flask(__name__)
                app.secret_key='synthetic-test-secret'
                with app.test_request_context('/admin/logout' if realm=='admin' else '/logout'):
                    session.realm=realm
                    session.handle='web-handle'
                    session['auth_session_id']='auth-handle'
                    with patch('redis_session_flask.shared_interface',return_value=NS(realms={
                        realm:selected,('admin' if realm=='user' else 'user'):other})):
                        shared_logout()
                    self.assertTrue(session.delete_cookie)
                    self.assertEqual(dict(session),{})
                self.assertFalse(selected.active)
                self.assertEqual(selected.calls,2)
                self.assertEqual(other.calls,0)

    def test_exhaustion_never_claims_success_or_clears_browser_authority(self):
        backend=SyntheticRevocationBackend(conflicts=10)
        app=Flask(__name__)
        app.secret_key='synthetic-test-secret'
        with app.test_request_context('/logout'):
            session.realm='user'
            session.handle='web-handle'
            session['auth_session_id']='auth-handle'
            with patch('redis_session_flask.shared_interface',return_value=NS(realms={'user':backend})):
                with self.assertRaises(SessionStorageUnavailable):shared_logout()
            self.assertEqual(session['auth_session_id'],'auth-handle')
            self.assertFalse(getattr(session,'delete_cookie',False))
        self.assertEqual(backend.calls,3)
        self.assertTrue(backend.active)

    def test_uncertain_outcome_is_not_retried(self):
        backend=SyntheticRevocationBackend(uncertain=True)
        with self.assertRaises(SessionStorageUnavailable):
            RedisModel(backend,'auth').revoke('auth-handle')
        self.assertEqual(backend.calls,1)
        app=Flask(__name__)
        app.secret_key='synthetic-test-secret'
        backend=SyntheticRevocationBackend(uncertain=True)
        with app.test_request_context('/logout'):
            session.realm='user';session.handle='web-handle'
            session['auth_session_id']='auth-handle'
            with patch('redis_session_flask.shared_interface',return_value=NS(realms={'user':backend})):
                with self.assertRaises(SessionStorageUnavailable):shared_logout()
            self.assertEqual(session['auth_session_id'],'auth-handle')
        self.assertEqual(backend.calls,1)

    def test_record_revocation_exhaustion_remains_bounded(self):
        backend=SyntheticRevocationBackend(conflicts=20)
        with self.assertRaises(SessionStorageUnavailable):
            RedisModel(backend,'auth').revoke('auth-handle')
        self.assertEqual(backend.calls,3)
        self.assertTrue(backend.active)

    def test_already_missing_reference_is_not_recreated(self):
        backend=SyntheticRevocationBackend()
        backend.active=False
        self.assertFalse(RedisModel(backend,'auth').revoke('auth-handle'))
        self.assertEqual(backend.calls,0)


class SyntheticRateBackend:
    def __init__(self):
        self.lock=Lock()
        self.values={}
        self.available=True
    def snapshot(self,kind,handle):
        if not self.available:raise SessionStorageUnavailable('Synthetic backend down')
        with self.lock:
            value=self.values.get(handle)
            return NS(key=handle,data=value['count'] if value else None,
                      meta=deepcopy(value) if value else None,now=100.0)
    def write(self,snap,value,expires):
        with self.lock:
            if self.values.get(snap.key)!=snap.meta:raise RevisionConflict('Synthetic conflict')
            self.values[snap.key]={'count':value,'expires':expires}


class SharedPublicEmailLimitTests(unittest.TestCase):
    def app(self, backend):
        app=Flask(__name__)
        app.extensions['rosago_public_email_limits']=LoginChallenges()
        app.extensions['rosago_shared_sessions']={'user':backend,'admin':SyntheticRateBackend()}
        return app

    def test_two_workers_share_one_email_limit_and_purposes_are_separate(self):
        backend=SyntheticRateBackend()
        workers=[self.app(backend),self.app(backend)]
        accepted=0
        for index in range(40):
            with workers[index%2].test_request_context('/register'):
                accepted+=bool(email_attempt_allowed('registration'))
        self.assertEqual(accepted,20)
        with workers[0].test_request_context('/forgot-password'):
            self.assertTrue(email_attempt_allowed('recovery'))

    def test_shared_outage_has_no_memory_fallback(self):
        backend=SyntheticRateBackend()
        backend.available=False
        app=self.app(backend)
        with app.test_request_context('/register'),self.assertRaises(SessionStorageUnavailable):
            email_attempt_allowed('registration')
        self.assertEqual(app.extensions['rosago_public_email_limits'].attempts,{})

    def test_concurrent_workers_cannot_multiply_shared_allowances(self):
        backend=SyntheticRateBackend()
        workers=[self.app(backend),self.app(backend)]
        def attempt(index):
            with workers[index%2].test_request_context('/register'):
                try:return bool(email_attempt_allowed('registration'))
                except SessionStorageUnavailable:return False
        with ThreadPoolExecutor(max_workers=4) as pool:
            accepted=sum(pool.map(attempt,range(60)))
        self.assertLessEqual(accepted,20)
        self.assertGreater(accepted,0)
        self.assertEqual(sum(v['count'] for v in backend.values.values()),accepted)

