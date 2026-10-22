"""Offline Flask infrastructure tests; no production route activation."""
from asyncio import CancelledError
from contextlib import contextmanager
from dataclasses import FrozenInstanceError, fields, replace
import socket
import unittest
from unittest.mock import Mock, patch

from flask import Flask, g, session

from normal_auth_coordinator import (
    AuthenticationRequired, ClientUnavailable, NormalAuthCoordinator, SessionBusy,
    VerifiedLoginCredentials,
)
from normal_auth_flask import (
    EXTENSION_KEY, NormalAuthEntryError, clear_normal_auth_authority,
    get_normal_auth_dependencies, init_normal_auth, normal_authenticated,
    read_auth_session_id,
    establish_normal_session, SessionEstablishmentError, normal_auth_state,
    normal_auth_redirect_decision, AuthRedirectDecision, AuthStateDecision,
    logout_normal_session, LocalLogoutError,
)


class NormalAuthFlaskTests(unittest.TestCase):
    def setUp(self):
        self.guards = []
        for target, names in (
            (socket, ('create_connection', 'getaddrinfo', 'gethostbyname',
                      'gethostbyname_ex', 'gethostbyaddr')),
            (socket.socket, ('connect', 'connect_ex', 'send', 'sendall', 'sendto')),
        ):
            for name in names:
                guard = patch.object(target, name, side_effect=AssertionError('Live network forbidden.'))
                self.guards.append(guard.start())
                self.addCleanup(guard.stop)
        self.app = self.new_app()

    def tearDown(self):
        for guard in self.guards:
            guard.assert_not_called()

    def new_app(self):
        app = Flask(__name__)
        app.secret_key = 'synthetic-offline-cookie-signing-key'
        init_normal_auth(app, 'https://flask.example.invalid', 'sb_publishable_synthetic_fixture')
        return app

    def credentials(self):
        return dict(user_id='verified-user', user_email='verified@example.invalid',
                    access_token='synthetic-access', refresh_token='synthetic-refresh',
                    access_expires_at=2_000_003_600, session_id='verified-session')

    def prepare_context(self, *, entry_error=None, exit_error=None):
        dependencies = self.app.extensions[EXTENSION_KEY]
        handle = dependencies.store.create(**self.credentials())
        closes = Mock()
        @contextmanager
        def client(token):
            try:
                if entry_error is not None:
                    raise entry_error
                yield object()
            finally:
                closes()
                if exit_error is not None:
                    raise exit_error
        factory = Mock(side_effect=client)
        coordinator = NormalAuthCoordinator(
            dependencies.store, refresh_transport=Mock(side_effect=AssertionError('Unexpected refresh.')),
            client_factory=factory, issuer=dependencies.adapters.issuer, clock=lambda: 2_000_000_000)
        self.app.extensions[EXTENSION_KEY] = replace(dependencies, coordinator=coordinator)
        return handle, factory, closes

    def test_registration_is_per_app_and_does_not_construct_sdk_clients(self):
        with patch('normal_auth_coordinator.SupabaseAdapters._client') as client:
            other = self.new_app()
        client.assert_not_called()
        first = self.app.extensions[EXTENSION_KEY]
        second = other.extensions[EXTENSION_KEY]
        for name in ('store', 'adapters', 'coordinator'):
            self.assertIsNot(getattr(first, name), getattr(second, name))
        handle = first.store.create(**self.credentials())
        self.assertIsNone(second.store.resolve(handle))
        with self.app.app_context():
            self.assertIs(get_normal_auth_dependencies(), first)
            for _ in range(2):
                with self.app.test_request_context():
                    self.assertIs(get_normal_auth_dependencies(), first)
                    self.assertIsNotNone(first.store.resolve(handle))
        with other.app_context():
            self.assertIs(get_normal_auth_dependencies(), second)
        with self.assertRaises(RuntimeError):
            init_normal_auth(self.app, 'https://flask.example.invalid', 'sb_publishable_synthetic_fixture')
        self.assertIs(self.app.extensions[EXTENSION_KEY], first)
        self.assertIs(first.coordinator._store, first.store)
        self.assertEqual(first.coordinator._refresh, first.adapters.refresh)
        self.assertEqual(first.coordinator._clients, first.adapters.database_client)

    def test_reads_only_normal_handle_and_cleanup_preserves_recovery(self):
        with self.app.test_request_context():
            session.update(user_id='legacy', user_email='legacy@example.invalid',
                           pending_recovery_id='pending', password_recovery_id='grant')
            for value in (None, '', ' ', 1, True, [], {}):
                session['auth_session_id'] = value
                self.assertIsNone(read_auth_session_id())
                with self.assertRaises(NormalAuthEntryError) as raised:
                    with normal_authenticated():
                        self.fail('Invalid handle authenticated.')
                self.assertEqual(raised.exception.kind, 'unauthenticated')
                self.assertNotIn('auth', g)
            session.pop('auth_session_id')
            self.assertIsNone(read_auth_session_id())
            session['auth_session_id'] = 'candidate-handle'
            self.assertEqual(read_auth_session_id(), 'candidate-handle')
            clear_normal_auth_authority()
            self.assertEqual(dict(session), {'pending_recovery_id': 'pending', 'password_recovery_id': 'grant'})

    def test_nested_repeated_operations_and_reused_app_context_cleanup(self):
        handle, factory, closes = self.prepare_context()
        with self.app.app_context():
            for _ in range(2):
                with self.app.test_request_context():
                    session['auth_session_id'] = handle
                    with normal_authenticated() as outer:
                        self.assertIs(g.auth, outer)
                        self.assertEqual(set(g), {'auth'})
                        self.assertEqual(outer.user_id, 'verified-user')
                        with normal_authenticated() as inner:
                            self.assertIs(g.auth, inner)
                            self.assertIsNot(inner.client, outer.client)
                        self.assertIs(g.auth, outer)
                        # A nested entry failure preserves the still-active outer scope.
                        session['auth_session_id'] = 'unknown'
                        with self.assertRaises(NormalAuthEntryError):
                            with normal_authenticated():
                                self.fail('Unknown handle authenticated.')
                        self.assertIs(g.auth, outer)
                    self.assertNotIn('auth', g)
                self.assertNotIn('auth', g)
        self.assertEqual(factory.call_count, 4)
        self.assertEqual(closes.call_count, 4)

    def test_entry_failures_are_safely_classified_without_cookie_mutation(self):
        for error_type, kind in ((AuthenticationRequired, 'unauthenticated'),
                                 (SessionBusy, 'busy'), (ClientUnavailable, 'unavailable')):
            with self.subTest(kind=kind), self.app.test_request_context():
                error = error_type()
                error.args = ('private-provider-token-detail',)
                error.__cause__ = RuntimeError('private-provider-token-detail')
                dependencies = self.app.extensions[EXTENSION_KEY]
                coordinator = Mock()
                coordinator.authenticated.side_effect = error
                self.app.extensions[EXTENSION_KEY] = replace(dependencies, coordinator=coordinator)
                session.update(auth_session_id='candidate', pending_recovery_id='pending',
                               password_recovery_id='grant')
                before = dict(session)
                with self.assertRaises(NormalAuthEntryError) as raised:
                    with normal_authenticated():
                        self.fail('Failed entry ran application code.')
                result = raised.exception
                self.assertEqual(result.kind, kind)
                self.assertEqual(result.retryable, kind != 'unauthenticated')
                self.assertEqual(result.may_clear_authority, kind == 'unauthenticated')
                self.assertEqual(result.suggested_status, None if kind == 'unauthenticated' else 503)
                self.assertIsNone(result.__cause__)
                self.assertIsNone(result.__context__)
                self.assertNotIn('private-provider-token-detail', str(result) + repr(result) + repr(vars(result)))
                self.assertNotIn('auth', g)
                self.assertEqual(dict(session), before)
                if result.may_clear_authority:
                    clear_normal_auth_authority()
                    self.assertEqual(dict(session), {'pending_recovery_id': 'pending', 'password_recovery_id': 'grant'})

    def test_actual_client_entry_failure_closes_once(self):
        handle, _, closes = self.prepare_context(entry_error=RuntimeError('private-client-detail'))
        with self.app.test_request_context():
            session['auth_session_id'] = handle
            with self.assertRaises(NormalAuthEntryError) as raised:
                with normal_authenticated():
                    self.fail('Failed client entry yielded.')
            self.assertEqual(raised.exception.kind, 'unavailable')
            self.assertNotIn('auth', g)
            self.assertEqual(session['auth_session_id'], handle)
        closes.assert_called_once_with()

    def test_application_errors_including_auth_types_propagate_unchanged(self):
        for error in (RuntimeError('application sentinel'), AuthenticationRequired(),
                      SessionBusy(), ClientUnavailable()):
            handle, _, closes = self.prepare_context()
            with self.app.test_request_context():
                session['auth_session_id'] = handle
                with self.assertRaises(type(error)) as raised:
                    with normal_authenticated():
                        raise error
                self.assertIs(raised.exception, error)
                self.assertNotIn('auth', g)
            closes.assert_called_once_with()

    def test_teardown_error_propagates_and_g_is_removed(self):
        error = ClientUnavailable()
        handle, _, closes = self.prepare_context(exit_error=error)
        with self.app.test_request_context():
            session['auth_session_id'] = handle
            with self.assertRaises(ClientUnavailable) as raised:
                with normal_authenticated():
                    pass
            self.assertIs(raised.exception, error)
            self.assertNotIn('auth', g)
        closes.assert_called_once_with()

    def test_control_flow_from_entry_and_body_propagates_unchanged(self):
        for stage in ('entry', 'body'):
            signal = CancelledError('synthetic cancellation')
            handle, _, closes = self.prepare_context(entry_error=signal if stage == 'entry' else None)
            with self.app.test_request_context():
                session['auth_session_id'] = handle
                with self.assertRaises(CancelledError) as raised:
                    with normal_authenticated():
                        raise signal
                self.assertIs(raised.exception, signal)
                self.assertNotIn('auth', g)
            closes.assert_called_once_with()

    def test_establishment_maps_verified_credentials_and_cookie_contains_only_handle(self):
        store = self.app.extensions[EXTENSION_KEY].store
        credentials = VerifiedLoginCredentials(**self.credentials())
        with self.app.test_request_context():
            session.update(user_id='legacy', user_email='legacy@example.invalid',
                           pending_recovery_id='pending', password_recovery_id='grant')
            with patch.object(store, 'create', wraps=store.create) as create:
                handle = establish_normal_session(credentials, clock=lambda: 2_000_000_000)
            create.assert_called_once_with(**self.credentials())
            record = store.resolve(handle)
            self.assertIsNotNone(record)
            self.assertEqual(dict(session), dict(auth_session_id=handle,
                             pending_recovery_id='pending', password_recovery_id='grant'))
            serializer = self.app.session_interface.get_signing_serializer(self.app)
            decoded = serializer.loads(serializer.dumps(dict(session)))
            self.assertEqual(decoded, dict(session))
            for secret in (record.access_token, record.refresh_token, record.session_id, record.csrf):
                self.assertNotIn(secret, repr(decoded))
            self.assertNotIn('auth', g)

    def test_establishment_rejects_unverified_or_expired_input_without_changes(self):
        store = self.app.extensions[EXTENSION_KEY].store
        old = store.create(**self.credentials())
        inputs = [self.credentials(), object(), None,
                  VerifiedLoginCredentials(**(self.credentials() | {'access_expires_at': 2_000_000_000})),
                  VerifiedLoginCredentials(**(self.credentials() | {'access_expires_at': 1}))]
        with self.app.test_request_context():
            session.update(auth_session_id=old, pending_recovery_id='pending')
            before = dict(session)
            for value in inputs:
                with patch.object(store, 'create', wraps=store.create) as create, \
                     patch.object(store, 'revoke', wraps=store.revoke) as revoke:
                    with self.assertRaises(SessionEstablishmentError) as raised:
                        establish_normal_session(value, clock=lambda: 2_000_000_000)
                    create.assert_not_called()
                    revoke.assert_not_called()
                self.assertIsNone(raised.exception.__context__)
                self.assertEqual(dict(session), before)
                self.assertIsNotNone(store.resolve(old))

    def test_replacement_revokes_old_browser_only_after_authority_installed(self):
        store = self.app.extensions[EXTENSION_KEY].store
        old, other = store.create(**self.credentials()), store.create(**self.credentials())
        revoke = store.revoke
        with self.app.test_request_context():
            session.update(auth_session_id=old, user_id='legacy', user_email='legacy@example.invalid')
            def ordered_revoke(handle):
                self.assertEqual(handle, old)
                self.assertNotEqual(session['auth_session_id'], old)
                self.assertIsNotNone(store.resolve(session['auth_session_id']))
                self.assertNotIn('user_id', session)
                self.assertNotIn('user_email', session)
                return revoke(handle)
            with patch.object(store, 'revoke', side_effect=ordered_revoke) as revoked:
                new = establish_normal_session(VerifiedLoginCredentials(**self.credentials()),
                                               clock=lambda: 2_000_000_000)
            revoked.assert_called_once_with(old)
            self.assertIsNone(store.resolve(old))
            self.assertIsNotNone(store.resolve(new))
            self.assertIsNotNone(store.resolve(other))

    def test_session_mutation_failure_rolls_back_new_record_and_all_normal_keys(self):
        store = self.app.extensions[EXTENSION_KEY].store
        old = store.create(**self.credentials())
        for failing_step in ('auth_session_id', 'user_id', 'user_email'):
            with self.subTest(step=failing_step), self.app.test_request_context():
                original = dict(auth_session_id=old, user_id='legacy', user_email='legacy@example.invalid',
                                pending_recovery_id='pending', password_recovery_id='grant')
                class FailingSession(dict):
                    failed = False
                    def maybe_fail(self, key):
                        if key == failing_step and not self.failed:
                            self.failed = True
                            raise RuntimeError('synthetic-access synthetic-refresh private-provider-detail')
                    def __setitem__(self, key, value):
                        super().__setitem__(key, value)
                        self.maybe_fail(key)
                    def pop(self, key, default=None):
                        value = super().pop(key, default)
                        self.maybe_fail(key)
                        return value
                simulated = FailingSession(original)
                created = []
                create = store.create
                def capture_create(**kwargs):
                    handle = create(**kwargs)
                    created.append(handle)
                    return handle
                with patch('normal_auth_flask.session', simulated), \
                     patch.object(store, 'create', side_effect=capture_create), \
                     patch.object(store, 'revoke', wraps=store.revoke) as revoke:
                    with self.assertRaises(SessionEstablishmentError) as raised:
                        establish_normal_session(VerifiedLoginCredentials(**self.credentials()),
                                                 clock=lambda: 2_000_000_000)
                self.assertEqual(len(created), 1)
                revoke.assert_called_once_with(created[0])
                self.assertIsNone(store.resolve(created[0]))
                self.assertIsNotNone(store.resolve(old))
                self.assertEqual(simulated, original)
                self.assertIsNone(raised.exception.__cause__)
                self.assertIsNone(raised.exception.__context__)
                self.assertEqual(str(raised.exception), 'Normal authentication session could not be established.')

    def test_state_and_redirect_reject_missing_legacy_recovery_and_invalid_handles(self):
        for data in ({}, {'user_id': 'legacy', 'user_email': 'legacy@example.invalid'},
                     {'pending_recovery_id': 'pending', 'password_recovery_id': 'grant'},
                     *[{'auth_session_id': value} for value in (None, '', ' ', 123, [], {}, 'unknown')]):
            with self.subTest(data=data), self.app.test_request_context():
                session.update(data)
                self.assertEqual(normal_auth_state(), AuthStateDecision('unauthenticated'))
                self.assertEqual(normal_auth_redirect_decision(), AuthRedirectDecision.SHOW_FORM)
                self.assertNotIn('auth_session_id', session)
                self.assertNotIn('user_id', session)
                self.assertNotIn('user_email', session)
                for key in ('pending_recovery_id', 'password_recovery_id'):
                    self.assertEqual(session.get(key), data.get(key))
                self.assertNotIn('auth', g)

    def test_authenticated_state_and_redirect_close_clients_before_return(self):
        handle, _, closes = self.prepare_context()
        with self.app.test_request_context():
            session.update(auth_session_id=handle, user_id='untrusted-cookie-user')
            result = normal_auth_state()
            closes.assert_called_once_with()
            self.assertNotIn('auth', g)
            self.assertEqual(result, AuthStateDecision('authenticated', 'verified-user', 'verified@example.invalid'))
            self.assertEqual({field.name for field in fields(result)}, {'state', 'user_id', 'user_email'})
            with self.assertRaises(FrozenInstanceError):
                result.state = 'unauthenticated'
            self.assertEqual(normal_auth_redirect_decision(), AuthRedirectDecision.REDIRECT_USER)
            self.assertEqual(closes.call_count, 2)
            self.assertNotIn('auth', g)

    def test_temporary_state_and_redirect_decisions_preserve_handle(self):
        for error, state, action in ((SessionBusy(), 'busy', AuthRedirectDecision.RETRYABLE_TEMPORARY),
                                     (ClientUnavailable(), 'unavailable', AuthRedirectDecision.SERVICE_TEMPORARY)):
            with self.subTest(state=state), self.app.test_request_context():
                dependencies = self.app.extensions[EXTENSION_KEY]
                coordinator = Mock()
                coordinator.authenticated.side_effect = error
                self.app.extensions[EXTENSION_KEY] = replace(dependencies, coordinator=coordinator)
                session.update(auth_session_id='candidate', pending_recovery_id='pending')
                before = dict(session)
                self.assertEqual(normal_auth_state(), AuthStateDecision(state))
                self.assertEqual(normal_auth_redirect_decision(), action)
                self.assertEqual(dict(session), before)
                self.assertNotIn('auth', g)

    def block_logout_provider_dependencies(self):
        dependencies = self.app.extensions[EXTENSION_KEY]
        # Any access to coordinator/provider methods is forbidden, not just HTTP.
        coordinator = Mock(spec=[])
        adapters = Mock(spec=[])
        self.app.extensions[EXTENSION_KEY] = replace(
            dependencies, coordinator=coordinator, adapters=adapters)
        self.addCleanup(lambda: self.assertEqual(coordinator.mock_calls, []))
        self.addCleanup(lambda: self.assertEqual(adapters.mock_calls, []))
        return dependencies.store

    def test_logout_handle_cases_are_local_idempotent_and_preserve_recovery(self):
        store = self.block_logout_provider_dependencies()
        original_clock = store._clock
        for case in ('valid', 'revoked', 'expired', 'unknown', 'missing', 'blank', 'malformed'):
            with self.subTest(case=case), self.app.test_request_context():
                store._clock = original_clock
                handle = store.create(**self.credentials())
                if case == 'revoked':
                    store.revoke(handle)
                elif case == 'expired':
                    record = store.resolve(handle)
                    # Deterministic local absolute expiry, without sleeping.
                    store._clock = lambda: record.created_at + 28800
                candidate = {'unknown': 'x' * 43, 'blank': ' ', 'malformed': []}.get(case, handle)
                session.update(user_id='legacy', user_email='legacy@example.invalid',
                               pending_recovery_id='pending', password_recovery_id='grant')
                if case != 'missing':
                    session['auth_session_id'] = candidate
                with patch.object(store, 'revoke', wraps=store.revoke) as revoke:
                    self.assertIsNone(logout_normal_session())
                    self.assertIsNone(logout_normal_session())
                if case in ('missing', 'blank', 'malformed'):
                    revoke.assert_not_called()
                else:
                    revoke.assert_called_once_with(candidate)
                self.assertEqual(dict(session), {'pending_recovery_id': 'pending', 'password_recovery_id': 'grant'})
                if case in ('valid', 'revoked', 'expired'):
                    self.assertIsNone(store.resolve(handle))
                self.assertNotIn('auth', g)

    def test_logout_busy_handle_cannot_resurrect_and_other_browser_survives(self):
        store = self.block_logout_provider_dependencies()
        first, second = store.create(**self.credentials()), store.create(**self.credentials())
        lease, _ = store.reserve_refresh(first)
        with self.app.test_request_context():
            session['auth_session_id'] = first
            logout_normal_session()
            self.assertNotIn('auth_session_id', session)
        self.assertIsNone(store.resolve(first))
        self.assertFalse(store.replace_credentials(first, lease, **self.credentials()))
        self.assertFalse(store.release_refresh(first, lease))
        self.assertIsNone(store.resolve(first))
        self.assertNotIn(first, store._busy)
        with self.app.test_request_context():
            session['auth_session_id'] = second
            self.assertIsNotNone(store.resolve(read_auth_session_id()))

    def test_logout_cookie_failure_leaves_revocation_final_and_error_sanitized(self):
        store = self.block_logout_provider_dependencies()
        for failing_key in ('auth_session_id', 'user_id', 'user_email'):
            with self.subTest(key=failing_key), self.app.test_request_context():
                handle = store.create(**self.credentials())
                class FailingSession(dict):
                    def pop(self, key, default=None):
                        # Prove revocation precedes even the first cookie mutation.
                        self_test.assertIsNone(store.resolve(handle))
                        if key == failing_key:
                            raise RuntimeError('synthetic-access synthetic-refresh private-provider-detail')
                        return super().pop(key, default)
                self_test = self
                simulated = FailingSession(auth_session_id=handle, user_id='legacy',
                    user_email='legacy@example.invalid', pending_recovery_id='pending', password_recovery_id='grant')
                with patch('normal_auth_flask.session', simulated), \
                     patch.object(store, 'create', side_effect=AssertionError('Recreation forbidden.')) as create, \
                     patch.object(store, 'revoke', wraps=store.revoke) as revoke:
                    with self.assertRaises(LocalLogoutError) as raised:
                        logout_normal_session()
                revoke.assert_called_once_with(handle)
                create.assert_not_called()
                self.assertIsNone(store.resolve(handle))
                self.assertIsNone(store.reserve_refresh(handle))
                self.assertEqual(simulated['pending_recovery_id'], 'pending')
                self.assertEqual(simulated['password_recovery_id'], 'grant')
                self.assertEqual(str(raised.exception), 'Local normal-auth logout could not be completed.')
                self.assertIsNone(raised.exception.__cause__)
                self.assertIsNone(raised.exception.__context__)

    def test_state_does_not_classify_body_or_teardown_exceptions(self):
        for stage in ('body', 'teardown'):
            error = NormalAuthEntryError('busy')
            handle, _, closes = self.prepare_context(exit_error=error if stage == 'teardown' else None)
            with self.app.test_request_context():
                session['auth_session_id'] = handle
                if stage == 'body':
                    with patch('normal_auth_flask.AuthStateDecision', side_effect=error):
                        with self.assertRaises(NormalAuthEntryError) as raised:
                            normal_auth_state()
                else:
                    with self.assertRaises(NormalAuthEntryError) as raised:
                        normal_auth_state()
                self.assertIs(raised.exception, error)
                self.assertEqual(session['auth_session_id'], handle)
                self.assertNotIn('auth', g)
            closes.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
