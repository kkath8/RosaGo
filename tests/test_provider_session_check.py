"""Offline qualification of optional current-session checking; no provider I/O.

Synthetic booleans test coordinator admission only. No factory supplies a real
checker, no protected authority is simulated as production, and no JWT is issued.
"""
from contextlib import contextmanager
import unittest
from unittest.mock import Mock,patch

from flask import Flask
from normal_auth_coordinator import (
    AuthenticationRequired, ClientUnavailable, NormalAuthCoordinator,
)
from normal_auth_store import NormalAuthStore
from session_realms import init_session_realms,SessionStorageUnavailable


class ProviderSessionCheckTests(unittest.TestCase):
    def setUp(self):
        self.clock = Mock(return_value=100.0)
        self.store = NormalAuthStore(clock=self.clock)
        self.handle = self.store.create(
            user_id='synthetic-user', user_email='fixture@example.invalid',
            access_token='synthetic-access', refresh_token='synthetic-refresh',
            access_expires_at=5000.0, session_id='synthetic-session')
        self.before = self.store.resolve(self.handle)
        self.refresh = Mock(side_effect=AssertionError('Unexpected refresh'))
        self.client_entries = []
        self.issuer = 'https://fixture.example.invalid/auth/v1'

        @contextmanager
        def clients(token):
            self.client_entries.append(token)
            yield object()
        self.clients = clients

    def coordinator(self, checker, realm='user'):
        return NormalAuthCoordinator(self.store, refresh_transport=self.refresh,
            client_factory=self.clients, issuer=self.issuer, clock=self.clock,
            realm=realm, provider_session_check=checker)

    def test_each_realm_checks_exact_current_subject_before_client_or_activity(self):
        for realm in ('user', 'admin'):
            with self.subTest(realm=realm):
                self.client_entries.clear()
                calls = []
                def check(record, issuer, selected_realm):
                    self.assertEqual(self.client_entries, [])
                    self.assertEqual(record.session_id, 'synthetic-session')
                    self.assertEqual(record.user_id, 'synthetic-user')
                    self.assertEqual(issuer, self.issuer)
                    self.assertEqual(selected_realm, realm)
                    calls.append(True)
                    return True
                with self.coordinator(check, realm).authenticated(self.handle) as auth:
                    self.assertEqual(auth.realm, realm)
                self.assertEqual(len(calls), 1)
        self.refresh.assert_not_called()

    def test_provider_revocation_denies_still_fresh_local_record_on_next_request(self):
        current = {'active': True}
        checker = Mock(side_effect=lambda *_: current['active'])
        coordinator = self.coordinator(checker)
        with coordinator.authenticated(self.handle):
            pass
        self.client_entries.clear()
        before = self.store.resolve(self.handle)
        self.clock.return_value = 110.0
        current['active'] = False
        with self.assertRaises(AuthenticationRequired):
            with coordinator.authenticated(self.handle):
                self.fail('Revoked provider session admitted')
        self.assertEqual(self.client_entries, [])
        self.assertIsNone(self.store.resolve(self.handle))
        self.assertEqual(checker.call_count, 2)  # No positive result cache.
        self.refresh.assert_not_called()

    def test_unknown_outage_and_malformed_results_fail_closed_without_touch_or_retry(self):
        for outcome in (None, 1, 'active', {}, OSError('synthetic-private-error')):
            with self.subTest(kind=type(outcome).__name__):
                checker = Mock(side_effect=outcome) if isinstance(outcome, Exception) else Mock(return_value=outcome)
                self.clock.return_value = 110.0
                with self.assertRaises(ClientUnavailable) as error:
                    with self.coordinator(checker).authenticated(self.handle):
                        self.fail('Unknown provider result admitted')
                self.assertIsNone(error.exception.__context__)
                self.assertNotIn('synthetic-private-error', str(error.exception))
                self.assertEqual(self.store.resolve(self.handle), self.before)
                self.assertEqual(self.client_entries, [])
                checker.assert_called_once()
        self.refresh.assert_not_called()

    def test_unknown_handle_does_not_call_provider(self):
        checker = Mock(return_value=True)
        with self.assertRaises(AuthenticationRequired):
            with self.coordinator(checker).authenticated('missing'):
                self.fail('Unknown local reference admitted')
        checker.assert_not_called()

    def test_confirmed_provider_denial_with_uncertain_local_revoke_is_unavailable(self):
        with patch.object(self.store,'revoke',side_effect=SessionStorageUnavailable('Synthetic uncertain commit')) as revoke:
            with self.assertRaises(SessionStorageUnavailable):
                with self.coordinator(Mock(return_value=False)).authenticated(self.handle):
                    self.fail('Uncertain local revoke admitted')
            revoke.assert_called_once_with(self.handle)
        self.assertEqual(self.store.resolve(self.handle),self.before)
        self.assertEqual(self.client_entries,[])
        self.refresh.assert_not_called()

    def test_unknown_near_expiry_session_does_not_refresh_or_renew_activity(self):
        handle = self.store.create(user_id='synthetic-near-expiry',
            user_email='fixture@example.invalid', access_token='synthetic-access',
            refresh_token='synthetic-refresh', access_expires_at=130.0,
            session_id='synthetic-session')
        before = self.store.resolve(handle)
        checker = Mock(return_value=None)
        with self.assertRaises(ClientUnavailable):
            with self.coordinator(checker).authenticated(handle):
                self.fail('Unknown provider state admitted near expiry')
        self.assertEqual(self.store.resolve(handle), before)
        self.assertEqual(self.client_entries, [])
        self.refresh.assert_not_called()
        checker.assert_called_once()

    def test_invalid_checker_and_production_startup_remain_closed(self):
        with self.assertRaises(ValueError):
            self.coordinator(True)
        with self.assertRaises(RuntimeError):
            init_session_realms(Flask('still-closed'), mode='production')
