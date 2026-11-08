"""Offline composition and lock contention checks; no hosted services."""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock,patch

from flask import Flask
from shared_session_runtime import LocalSessionRuntime
from session_realms import init_session_realms,SessionStorageUnavailable
from protected_session_authority import ProtectedRevisionAuthority,AuthorityBinding
from postgres_session_recovery import RecoveryFence,RecoveryBinding


class SharedRuntimeTests(unittest.TestCase):
    def runtime(self):
        realms={r:NS(realm=r, readiness=Mock(return_value={'ready':True}),
            snapshot=Mock(),atomic=Mock(),write=Mock(),now=Mock()) for r in ('user','admin')}
        return LocalSessionRuntime(realms,Mock(),Mock(),Mock(return_value=True))

    def test_both_backends_checked_before_publishing_and_no_memory_fallback(self):
        runtime=self.runtime();runtime.realms['admin'].readiness.return_value={'ready':False}
        app=Flask('unready');old=app.session_interface
        with self.assertRaises(SessionStorageUnavailable):runtime.install(app)
        self.assertIs(app.session_interface,old)
        self.assertNotIn('rosago_shared_sessions',app.extensions)
        runtime.model_factory.assert_not_called()

    def test_dependencies_cannot_cross_worker_fork_or_bypass_production(self):
        runtime=self.runtime()
        with patch('shared_session_runtime.os.getpid',return_value=runtime.creator_pid+1):
            with self.assertRaises(SessionStorageUnavailable):runtime.install(Flask('forked'))
        with self.assertRaises(RuntimeError):
            init_session_realms(Flask('prod'),mode='production',local_runtime=runtime)
        with self.assertRaises(RuntimeError):
            init_session_realms(Flask('dev'),local_runtime=runtime)

    def test_realm_mapping_and_provider_callback_are_required(self):
        runtime=self.runtime()
        with self.assertRaises(ValueError):
            LocalSessionRuntime(dict(runtime.realms),Mock(),Mock(),None)
        with self.assertRaises(TypeError):runtime.realms['user']=runtime.realms['admin']


class AuthorityContentionTests(unittest.TestCase):
    def assert_bounded(self, authority, action, transport):
        # Hold the lock in this thread; a different thread must deny admission
        # instead of waiting indefinitely or contacting the authority out of order.
        authority._lock.acquire()
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(action)
                with self.assertRaises(SessionStorageUnavailable):future.result(timeout=1)
            transport.assert_not_called()
        finally:
            authority._lock.release()

    def test_protected_metadata_lock_wait_is_bounded(self):
        transport=Mock()
        authority=ProtectedRevisionAuthority(transport,AuthorityBinding('a'*20,'b'*20,0),response_budget=.01)
        self.assert_bounded(authority,lambda:authority.descriptor('fixture'),transport.exchange)

    def test_recovery_fence_lock_wait_is_bounded(self):
        provider=Mock()
        authority=RecoveryFence(provider,RecoveryBinding(*['a'*24,'b'*24,'c'*24,'d'*24]),response_budget=.01)
        self.assert_bounded(authority,lambda:authority.check('fixture'),provider.proof)
