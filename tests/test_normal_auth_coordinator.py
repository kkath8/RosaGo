"""Offline normal-auth coordinator tests; no Flask or recovery integration."""
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import fields, replace
from asyncio import CancelledError
import io
import secrets
import socket
from threading import Event, Thread
import traceback
import unittest
from unittest.mock import Mock, patch

from normal_auth_coordinator import AuthenticationRequired, ClientUnavailable, NormalAuthCoordinator, SessionBusy, VerifiedRefresh
from normal_auth_store import NormalAuthStore


class NormalAuthCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.network_guards = []
        # Block TCP, UDP, and DNS, including calls through existing sockets.
        for target, names in (
            (socket, ('create_connection', 'getaddrinfo', 'gethostbyname',
                      'gethostbyname_ex', 'gethostbyaddr')),
            (socket.socket, ('connect', 'connect_ex', 'send', 'sendall', 'sendto')),
        ):
            for name in names:
                guard = patch.object(target, name, side_effect=AssertionError(
                    'Live network forbidden in coordinator tests.'))
                self.network_guards.append(guard.start())
                self.addCleanup(guard.stop)

    def test_fresh_normal_session_resolves_without_refresh_and_closes_client(self):
        lifecycle_clock = Mock(return_value=100.0)
        unix_clock = Mock(return_value=2_000_000_000.0)
        # Idle outlasts absolute lifetime so the final check isolates absolute expiry.
        store = NormalAuthStore(clock=lifecycle_clock, idle_seconds=1000,
                                absolute_seconds=300)
        # Fixtures represent credentials already verified by normal sign-in.
        # No recovery store, credential, or grant is supplied to this coordinator.
        credentials = dict(
            user_id='verified-normal-user', user_email='normal@example.invalid',
            access_token='normal-access-secret', refresh_token='normal-refresh-secret',
            access_expires_at=unix_clock.return_value + 3600,
            session_id='verified-normal-session',
        )
        handle = store.create(**credentials)
        before = store.resolve(handle)
        self.assertIsNotNone(before)
        self.assertRegex(handle, r'^[A-Za-z0-9_-]{43}$')
        lifecycle_clock.return_value = 125.0
        unix_clock.return_value += 25.0
        self.assertGreater(before.access_expires_at, unix_clock.return_value + 60)
        refresh = Mock(side_effect=AssertionError('Fresh credentials must not refresh.'))
        client = Mock(spec=['close'])

        @contextmanager
        def request_client(access_token):
            self.assertEqual(access_token, credentials['access_token'])
            # Construction itself must precede the successful-resolution touch.
            self.assertEqual(store.resolve(handle).last_activity_at, 100.0)
            try:
                yield client
            finally:
                client.close()

        client_factory = Mock(side_effect=request_client)
        coordinator = NormalAuthCoordinator(
            store, refresh_transport=refresh, client_factory=client_factory,
            issuer='https://normal-auth.example.invalid/auth/v1',
            clock=unix_clock, refresh_seconds=60,
        )
        with coordinator.authenticated(handle) as context:
            self.assertEqual(context.auth_session_id, handle)
            self.assertEqual(context.user_id, credentials['user_id'])
            self.assertEqual(context.user_email, credentials['user_email'])
            self.assertIs(context.client, client)
            client_factory.assert_called_once_with(credentials['access_token'])
            refresh.assert_not_called()
            client.close.assert_not_called()
            for name in ('access_token', 'refresh_token', 'csrf'):
                self.assertFalse(hasattr(context, name))
            # The client is server-only; context string fields and repr must not
            # expose credentials. This does not serialize a context into a cookie.
            public_strings = [getattr(context, field.name) for field in fields(context)
                              if isinstance(getattr(context, field.name), str)]
            rendered = repr(context) + str(context) + repr(public_strings)
            for secret in (before.access_token, before.refresh_token, before.csrf):
                self.assertNotIn(secret, rendered)
            self.assertEqual(store.resolve(handle), replace(before, last_activity_at=125.0))

        client.close.assert_called_once_with()
        refresh.assert_not_called()
        self.assertEqual(store.resolve(handle), replace(before, last_activity_at=125.0))
        lifecycle_clock.return_value = before.created_at + 300 - 0.001
        self.assertIsNotNone(store.resolve(handle))
        lifecycle_clock.return_value = before.created_at + 300
        self.assertIsNone(store.resolve(handle))
        # Also catch network attempts that production code might have swallowed.
        for guard in self.network_guards:
            guard.assert_not_called()

    def test_unknown_opaque_handle_fails_closed_without_side_effects(self):
        lifecycle_clock = Mock(return_value=100.0)
        unix_clock = Mock(return_value=2_000_000_000.0)
        store = NormalAuthStore(clock=lifecycle_clock)
        # An unrelated normal session detects accidental identity disclosure or
        # activity changes. No recovery credential, store, or grant participates.
        existing_handle = store.create(
            user_id='unrelated-normal-user', user_email='unrelated@example.invalid',
            access_token='unrelated-access-secret', refresh_token='unrelated-refresh-secret',
            access_expires_at=unix_clock.return_value + 3600,
            session_id='unrelated-normal-session',
        )
        existing = store.resolve(existing_handle)
        unknown_handle = secrets.token_urlsafe(32)
        while store.resolve(unknown_handle) is not None:
            unknown_handle = secrets.token_urlsafe(32)
        self.assertRegex(unknown_handle, r'^[A-Za-z0-9_-]{43}$')
        self.assertIsNone(store.resolve(unknown_handle))
        records_before = store._records.copy()
        reservations_before = store._busy.copy()
        lifecycle_clock.return_value = 125.0
        refresh = Mock(side_effect=AssertionError('Unknown handles must not refresh.'))
        client_factory = Mock(side_effect=AssertionError('Unknown handles must not create clients.'))
        coordinator = NormalAuthCoordinator(
            store, refresh_transport=refresh, client_factory=client_factory,
            issuer='https://normal-auth.example.invalid/auth/v1', clock=unix_clock,
        )
        output = io.StringIO()
        context = None
        with (
            patch.object(store, 'create', wraps=store.create) as create,
            patch.object(store, 'touch', wraps=store.touch) as touch,
            redirect_stdout(output), redirect_stderr(output),
            self.assertNoLogs(level='DEBUG'),
        ):
            with self.assertRaises(AuthenticationRequired) as raised:
                with coordinator.authenticated(unknown_handle) as context:
                    self.fail('An unknown handle produced an authenticated context.')
        self.assertIsNone(context)
        refresh.assert_not_called()
        client_factory.assert_not_called()
        create.assert_not_called()
        touch.assert_not_called()
        self.assertTrue(store._records == records_before, 'Session records changed.')
        self.assertTrue(store._busy == reservations_before, 'Refresh reservations changed.')
        self.assertTrue(store.resolve(existing_handle) == existing, 'Unrelated session changed.')
        self.assertIsNone(store.resolve(unknown_handle))
        error = raised.exception
        self.assertTrue(str(error) == 'Normal authentication required.', 'Unexpected error text.')
        self.assertTrue(repr(error) == "AuthenticationRequired('Normal authentication required.')",
                        'Unexpected error representation.')
        self.assertTrue(output.getvalue() == '', 'Resolution emitted unexpected output.')
        for name in ('access_token', 'refresh_token', 'csrf', 'user_id', 'user_email'):
            self.assertFalse(hasattr(error, name))
        rendered = str(error) + repr(error) + output.getvalue()
        for protected in (existing.access_token, existing.refresh_token, existing.csrf,
                          existing.user_id, existing.user_email, existing_handle, unknown_handle):
            self.assertTrue(protected not in rendered, 'Failure exposed a protected value.')
        for guard in self.network_guards:
            guard.assert_not_called()

    def test_revoked_normal_handle_fails_closed_and_cannot_revive(self):
        lifecycle_clock = Mock(return_value=100.0)
        unix_clock = Mock(return_value=2_000_000_000.0)
        store = NormalAuthStore(clock=lifecycle_clock)
        # Only previously verified normal-sign-in fixtures participate; no
        # recovery store, grant, pending record, or credential is involved.
        handle = store.create(
            user_id='revoked-normal-user', user_email='revoked@example.invalid',
            access_token='revoked-access-secret', refresh_token='revoked-refresh-secret',
            access_expires_at=unix_clock.return_value + 3600,
            session_id='revoked-normal-session',
        )
        before = store.resolve(handle)
        self.assertIsNotNone(before)
        self.assertFalse(before.revoked)
        self.assertEqual(before.last_activity_at, 100.0)
        self.assertTrue(store.revoke(handle))
        self.assertIsNone(store.resolve(handle))
        self.assertTrue(store._records == {}, 'Revocation retained a session record.')
        self.assertTrue(store._busy == {}, 'Revocation retained a reservation.')
        lifecycle_clock.return_value = 125.0
        refresh = Mock(side_effect=AssertionError('Revoked handles must not refresh.'))
        client_factory = Mock(side_effect=AssertionError('Revoked handles must not create clients.'))
        coordinator = NormalAuthCoordinator(
            store, refresh_transport=refresh, client_factory=client_factory,
            issuer='https://normal-auth.example.invalid/auth/v1', clock=unix_clock,
        )
        output = io.StringIO()
        context = None
        with (
            patch.object(store, 'create', wraps=store.create) as create,
            patch.object(store, 'touch', wraps=store.touch) as touch,
            patch.object(store, 'reserve_refresh', wraps=store.reserve_refresh) as reserve,
            redirect_stdout(output), redirect_stderr(output),
            self.assertNoLogs(level='DEBUG'),
        ):
            # Replay the exact old handle, as a browser could after revocation.
            with self.assertRaises(AuthenticationRequired) as raised:
                with coordinator.authenticated(handle) as context:
                    self.fail('A revoked handle produced an authenticated context.')
        self.assertIsNone(context)
        refresh.assert_not_called()
        client_factory.assert_not_called()
        create.assert_not_called()
        touch.assert_not_called()
        reserve.assert_not_called()
        self.assertIsNone(store.resolve(handle))
        self.assertTrue(store._records == {}, 'Replay recreated session state or activity.')
        self.assertTrue(store._busy == {}, 'Replay created a refresh reservation.')
        error = raised.exception
        self.assertTrue(str(error) == 'Normal authentication required.', 'Unexpected error text.')
        self.assertTrue(repr(error) == "AuthenticationRequired('Normal authentication required.')",
                        'Unexpected error representation.')
        self.assertTrue(output.getvalue() == '', 'Replay emitted unexpected output.')
        for name in ('access_token', 'refresh_token', 'csrf', 'user_id', 'user_email'):
            self.assertFalse(hasattr(error, name))
        rendered = str(error) + repr(error) + output.getvalue()
        for protected in (before.access_token, before.refresh_token, before.csrf,
                          before.user_id, before.user_email, before.session_id, handle):
            self.assertTrue(protected not in rendered, 'Replay exposed a protected value.')
        for guard in self.network_guards:
            guard.assert_not_called()


    def test_refresh_requires_password_amr_evidence(self):
        now = 2_000_000_000
        issuer = 'https://normal-auth.example.invalid/auth/v1'
        password = {'method': 'password', 'timestamp': now}
        missing = object()
        cases = [
            ('password', [password], True),
            ('missing', missing, False),
            ('null', None, False),
            ('string', 'password', False),
            ('object', password, False),
            ('empty', [], False),
            ('non-object entry', ['password'], False),
            ('missing method', [{'timestamp': now}], False),
            ('blank method', [{'method': ' ', 'timestamp': now}], False),
            ('non-string method', [{'method': 1, 'timestamp': now}], False),
            ('recovery', [{'method': 'recovery', 'timestamp': now}], False),
            ('unknown', [{'method': 'unknown', 'timestamp': now}], False),
            ('password and recovery', [password, {'method': 'recovery', 'timestamp': now}], False),
            ('password and unknown', [password, {'method': 'unknown', 'timestamp': now}], False),
            ('password and unsupported MFA', [password, {'method': 'mfa/totp', 'timestamp': now}], False),
            ('password and malformed', [password, {}], False),
            ('missing timestamp', [{'method': 'password'}], False),
            ('invalid timestamp', [{'method': 'password', 'timestamp': 'invalid'}], False),
            ('boolean timestamp', [{'method': 'password', 'timestamp': True}], False),
        ]
        for label, amr, accepted in cases:
            with self.subTest(amr=label):
                store = NormalAuthStore(clock=lambda: 100.0)
                handle = store.create(
                    user_id='normal-user', user_email='normal@example.invalid',
                    access_token='old-access', refresh_token='old-refresh',
                    access_expires_at=now + 30, session_id='normal-session')
                claims = dict(sub='normal-user', iss=issuer, aud='authenticated',
                              role='authenticated', session_id='normal-session', exp=now + 3600)
                if amr is not missing:
                    claims['amr'] = amr
                result = VerifiedRefresh(
                    'normal-user', 'normal@example.invalid', 'normal-user', 'normal-user',
                    'new-access', 'new-refresh', now + 3600, claims)
                refresh = Mock(return_value=result)

                @contextmanager
                def client(access_token):
                    yield access_token

                clients = Mock(side_effect=client)
                coordinator = NormalAuthCoordinator(
                    store, refresh_transport=refresh, client_factory=clients,
                    issuer=issuer, clock=lambda: now)
                if accepted:
                    with coordinator.authenticated(handle) as context:
                        self.assertEqual(context.client, 'new-access')
                    self.assertEqual(store.resolve(handle).refresh_token, 'new-refresh')
                else:
                    with self.assertRaises(AuthenticationRequired):
                        with coordinator.authenticated(handle):
                            self.fail('Invalid AMR authenticated.')
                    self.assertIsNone(store.resolve(handle))
                    clients.assert_not_called()
                refresh.assert_called_once_with('old-refresh')
                self.assertEqual(store._busy, {})
        for guard in self.network_guards:
            guard.assert_not_called()

    def test_near_expiry_refresh_rotates_credentials_once_and_preserves_session(self):
        lifecycle_clock = Mock(return_value=100.0)
        unix_clock = Mock(return_value=2_000_000_000.0)
        store = NormalAuthStore(clock=lifecycle_clock, idle_seconds=1000,
                                absolute_seconds=300)
        issuer = 'https://normal-auth.example.invalid/auth/v1'
        # Trusted normal-sign-in fixtures only; no recovery or browser credentials.
        handle = store.create(
            user_id='refresh-normal-user', user_email='refresh@example.invalid',
            access_token='old-normal-access-secret', refresh_token='old-normal-refresh-secret',
            access_expires_at=unix_clock.return_value + 55,
            session_id='verified-refresh-session',
        )
        before = store.resolve(handle)
        self.assertIsNotNone(before)
        lifecycle_clock.return_value = 125.0
        unix_clock.return_value += 25.0
        self.assertGreater(before.access_expires_at, unix_clock.return_value)
        self.assertLess(before.access_expires_at, unix_clock.return_value + 60)
        new_expiry = unix_clock.return_value + 3600
        refreshed = VerifiedRefresh(
            user_id=before.user_id, user_email=before.user_email,
            response_user_id=before.user_id, session_user_id=before.user_id,
            access_token='new-normal-access-secret', refresh_token='new-normal-refresh-secret',
            expires_at=new_expiry,
            claims={'sub': before.user_id, 'iss': issuer, 'aud': 'authenticated',
                    'role': 'authenticated', 'session_id': before.session_id,
                    'exp': new_expiry, 'amr': [{'method': 'password', 'timestamp': 2_000_000_000}]},
        )
        rotated = replace(before, access_token=refreshed.access_token,
                          refresh_token=refreshed.refresh_token, access_expires_at=new_expiry,
                          generation=before.generation + 1)

        def refresh_transport(refresh_token):
            self.assertTrue(refresh_token == before.refresh_token, 'Incorrect refresh credential.')
            self.assertTrue(store.resolve(handle) == before, 'State changed before refresh completed.')
            self.assertIsNone(store.reserve_refresh(handle))  # Reservation is exclusive.
            return refreshed

        refresh = Mock(side_effect=refresh_transport)
        client = Mock(spec=['close'])

        @contextmanager
        def request_client(access_token):
            self.assertTrue(access_token == refreshed.access_token, 'Client received wrong credential.')
            # Both tokens, expiry, and generation have changed together, but
            # validation/replacement have not yet advanced activity.
            self.assertTrue(store.resolve(handle) == rotated, 'Incorrect pre-client session state.')
            lifecycle_clock.return_value = 130.0
            try:
                yield client
            finally:
                client.close()

        client_factory = Mock(side_effect=request_client)
        coordinator = NormalAuthCoordinator(
            store, refresh_transport=refresh, client_factory=client_factory,
            issuer=issuer, clock=unix_clock, refresh_seconds=60,
        )
        output = io.StringIO()
        with (
            patch.object(store, 'replace_credentials', wraps=store.replace_credentials) as commit,
            redirect_stdout(output), redirect_stderr(output),
            self.assertNoLogs(level='DEBUG'),
        ):
            with coordinator.authenticated(handle) as context:
                self.assertEqual(context.auth_session_id, handle)
                self.assertEqual(context.user_id, before.user_id)
                self.assertEqual(context.user_email, before.user_email)
                self.assertIs(context.client, client)
                client.close.assert_not_called()
                self.assertTrue(store.resolve(handle) == replace(rotated, last_activity_at=130.0),
                                'Incorrect authenticated session state.')
                for name in ('access_token', 'refresh_token', 'csrf'):
                    self.assertFalse(hasattr(context, name))
                public_strings = [getattr(context, field.name) for field in fields(context)
                                  if isinstance(getattr(context, field.name), str)]
                rendered = repr(context) + str(context) + repr(public_strings) + repr(refreshed)
        refresh.assert_called_once()
        self.assertTrue(refresh.call_args.args == (before.refresh_token,), 'Incorrect refresh input.')
        self.assertEqual(refresh.call_args.kwargs, {})
        client_factory.assert_called_once()
        self.assertTrue(client_factory.call_args.args == (refreshed.access_token,),
                        'Incorrect client credential.')
        self.assertEqual(client_factory.call_args.kwargs, {})
        commit.assert_called_once()
        self.assertTrue(commit.call_args.args[0] == handle, 'Replacement used a different handle.')
        self.assertTrue(commit.call_args.kwargs == dict(
            user_id=before.user_id, user_email=before.user_email,
            access_token=refreshed.access_token, refresh_token=refreshed.refresh_token,
            access_expires_at=new_expiry, session_id=before.session_id),
            'Credentials were not submitted in one replacement.')
        client.close.assert_called_once_with()
        self.assertTrue(store.resolve(handle) == replace(rotated, last_activity_at=130.0),
                        'Session changed after client cleanup.')
        self.assertTrue(store._busy == {}, 'Refresh reservation remained held.')
        self.assertTrue(output.getvalue() == '', 'Refresh emitted unexpected output.')
        for secret in (before.access_token, before.refresh_token, refreshed.access_token,
                       refreshed.refresh_token, before.csrf):
            self.assertTrue(secret not in rendered + output.getvalue(), 'Refresh exposed a secret.')
        # Idle outlasts absolute expiry: rotation/activity must not extend it.
        lifecycle_clock.return_value = before.created_at + 300 - 0.001
        self.assertIsNotNone(store.resolve(handle))
        lifecycle_clock.return_value = before.created_at + 300
        self.assertIsNone(store.resolve(handle))
        for guard in self.network_guards:
            guard.assert_not_called()


    def test_refresh_mismatched_subject_revokes_session_and_replay_fails_closed(self):
        lifecycle_clock = Mock(return_value=100.0)
        unix_clock = Mock(return_value=2_000_000_000.0)
        store = NormalAuthStore(clock=lifecycle_clock, idle_seconds=1000,
                                absolute_seconds=300)
        issuer = 'https://normal-auth.example.invalid/auth/v1'
        # Verified normal-sign-in fixtures only: no recovery store/grant/credential.
        handle = store.create(
            user_id='subject-user-a', user_email='subject-a@example.invalid',
            access_token='subject-old-access-secret',
            refresh_token='subject-old-refresh-secret',
            access_expires_at=unix_clock.return_value + 55,
            session_id='subject-normal-session',
        )
        before = store.resolve(handle)
        self.assertIsNotNone(before)
        lifecycle_clock.return_value = 125.0
        unix_clock.return_value += 25.0
        self.assertGreater(before.access_expires_at, unix_clock.return_value)
        self.assertLess(before.access_expires_at, unix_clock.return_value + 60)
        new_expiry = unix_clock.return_value + 3600
        # Fake the trusted transport's already signature-verified claims boundary;
        # JWT cryptography belongs to the adapter, not this coordinator test.
        valid = VerifiedRefresh(
            user_id=before.user_id, user_email=before.user_email,
            response_user_id=before.user_id, session_user_id=before.user_id,
            access_token='subject-new-access-secret',
            refresh_token='subject-new-refresh-secret', expires_at=new_expiry,
            claims={'sub': before.user_id, 'iss': issuer, 'aud': 'authenticated',
                    'role': 'authenticated', 'session_id': before.session_id,
                    'exp': new_expiry,
                    'amr': [{'method': 'password', 'timestamp': 2_000_000_000}]},
        )
        user_b = 'subject-user-b'
        mismatched = replace(valid, claims={**valid.claims, 'sub': user_b})

        def refresh_transport(refresh_token):
            self.assertTrue(refresh_token == before.refresh_token,
                            'Incorrect refresh credential.')
            self.assertTrue(store.resolve(handle) == before,
                            'Session changed before refresh completed.')
            self.assertTrue(handle in store._busy, 'Refresh was not reserved.')
            return mismatched

        refresh = Mock(side_effect=refresh_transport)
        client_factory = Mock(side_effect=AssertionError('Unexpected client construction.'))
        coordinator = NormalAuthCoordinator(
            store, refresh_transport=refresh, client_factory=client_factory,
            issuer=issuer, clock=unix_clock, refresh_seconds=60,
        )
        # Control: every other field passes the real validator. Only sub changes.
        self.assertEqual(coordinator._validate(valid, before), new_expiry)
        revoke_refresh = store.revoke_refresh

        def revoke_reserved(session_handle, lease):
            self.assertTrue(session_handle == handle, 'Wrong session revoked.')
            self.assertTrue(store.resolve(handle) == before,
                            'Credentials, generation, or activity changed before revocation.')
            self.assertTrue(store._busy.get(handle) == lease,
                            'Revocation did not own the refresh reservation.')
            revoked = revoke_refresh(session_handle, lease)
            self.assertTrue(revoked, 'Reserved session was not revoked.')
            return revoked

        output = io.StringIO()
        rendered_errors = []
        context = None
        with (
            patch.object(store, 'replace_credentials', wraps=store.replace_credentials) as commit,
            patch.object(store, 'touch', wraps=store.touch) as touch,
            patch.object(store, 'create', wraps=store.create) as create,
            patch.object(store, 'reserve_refresh', wraps=store.reserve_refresh) as reserve,
            patch.object(store, 'revoke_refresh', side_effect=revoke_reserved) as revoke,
            patch.object(store, 'release_refresh', wraps=store.release_refresh) as release,
            redirect_stdout(output), redirect_stderr(output),
            self.assertNoLogs(level='DEBUG'),
        ):
            for presentation in range(2):
                with self.assertRaises(AuthenticationRequired) as raised:
                    try:
                        with coordinator.authenticated(handle) as context:
                            self.fail('Identity mismatch produced an authenticated context.')
                    except AuthenticationRequired as error:
                        rendered_errors.append(traceback.format_exc())
                        # Inspect even suppressed exception contexts for leaked values.
                        current = error
                        while current is not None:
                            rendered_errors.append(str(current) + repr(current))
                            current = current.__context__
                        raise
                self.assertIsNone(context)
                self.assertIs(type(raised.exception), AuthenticationRequired)
                self.assertTrue(str(raised.exception) == 'Normal authentication required.',
                                'Unexpected authentication failure text.')
                self.assertTrue(repr(raised.exception) ==
                                "AuthenticationRequired('Normal authentication required.')",
                                'Unexpected authentication failure representation.')
                self.assertIsNone(store.resolve(handle))
                self.assertTrue(store._records == {}, 'Credential or activity state remained.')
                self.assertTrue(store._busy == {}, 'Refresh reservation remained held.')
                # Counts must stay at one when the exact revoked handle is replayed.
                self.assertEqual(refresh.call_count, 1)
                self.assertEqual(reserve.call_count, 1)
                self.assertEqual(revoke.call_count, 1)
                self.assertEqual(release.call_count, 1)
                lifecycle_clock.return_value += 5.0

        self.assertTrue(refresh.call_args.args == (before.refresh_token,),
                        'Refresh did not receive the old stored credential.')
        self.assertEqual(refresh.call_args.kwargs, {})
        self.assertEqual(client_factory.call_count, 0, 'Client factory ran.')
        self.assertEqual(commit.call_count, 0, 'New credentials were submitted to the store.')
        self.assertEqual(touch.call_count, 0, 'Failed refresh advanced activity.')
        self.assertEqual(create.call_count, 0, 'Failed refresh created a session.')
        self.assertTrue(release.call_args == revoke.call_args,
                        'Cleanup used a different refresh reservation.')
        self.assertTrue(output.getvalue() == '', 'Failure emitted unexpected output.')
        rendered = ''.join(rendered_errors) + output.getvalue() + repr(before) + repr(mismatched)
        for protected in (before.access_token, before.refresh_token, mismatched.access_token,
                          mismatched.refresh_token, before.csrf, before.user_email,
                          before.user_id, user_b, before.session_id, handle):
            # Boolean assertions keep protected values out of assertion diagnostics.
            self.assertTrue(protected not in rendered, 'Failure exposed a protected value.')
        for guard in self.network_guards:
            self.assertEqual(guard.call_count, 0, 'Outbound network was attempted.')


    def test_refresh_mismatched_session_id_revokes_session_and_replay_fails_closed(self):
        lifecycle_clock = Mock(return_value=100.0)
        unix_clock = Mock(return_value=2_000_000_000.0)
        store = NormalAuthStore(clock=lifecycle_clock, idle_seconds=1000,
                                absolute_seconds=300)
        issuer = 'https://normal-auth.example.invalid/auth/v1'
        # Verified normal-sign-in fixtures only: no recovery store/grant/credential.
        handle = store.create(
            user_id='session-binding-user-a', user_email='session-binding-a@example.invalid',
            access_token='session-binding-old-access-secret',
            refresh_token='session-binding-old-refresh-secret',
            access_expires_at=unix_clock.return_value + 55,
            session_id='session-binding-session-a',
        )
        before = store.resolve(handle)
        self.assertIsNotNone(before)
        lifecycle_clock.return_value = 125.0
        unix_clock.return_value += 25.0
        self.assertGreater(before.access_expires_at, unix_clock.return_value)
        self.assertLess(before.access_expires_at, unix_clock.return_value + 60)
        new_expiry = unix_clock.return_value + 3600
        # Fake the trusted transport's already signature-verified claims boundary;
        # JWT cryptography belongs to the adapter, not this coordinator test.
        valid = VerifiedRefresh(
            user_id=before.user_id, user_email=before.user_email,
            response_user_id=before.user_id, session_user_id=before.user_id,
            access_token='session-binding-new-access-secret',
            refresh_token='session-binding-new-refresh-secret', expires_at=new_expiry,
            claims={'sub': before.user_id, 'iss': issuer, 'aud': 'authenticated',
                    'role': 'authenticated', 'session_id': before.session_id,
                    'exp': new_expiry,
                    'amr': [{'method': 'password', 'timestamp': 2_000_000_000}]},
        )
        session_b = 'session-binding-session-b'
        mismatched = replace(valid, claims={**valid.claims, 'session_id': session_b})
        self.assertTrue(session_b != before.session_id, 'Session IDs must differ.')
        self.assertTrue(all(value == before.user_id for value in (
            mismatched.user_id, mismatched.response_user_id,
            mismatched.session_user_id, mismatched.claims['sub'])),
            'Identity fields must remain bound to the stored user.')

        def refresh_transport(refresh_token):
            self.assertTrue(refresh_token == before.refresh_token,
                            'Incorrect refresh credential.')
            self.assertTrue(store.resolve(handle) == before,
                            'Session changed before refresh completed.')
            self.assertTrue(handle in store._busy, 'Refresh was not reserved.')
            return mismatched

        refresh = Mock(side_effect=refresh_transport)
        client_factory = Mock(side_effect=AssertionError('Unexpected client construction.'))
        coordinator = NormalAuthCoordinator(
            store, refresh_transport=refresh, client_factory=client_factory,
            issuer=issuer, clock=unix_clock, refresh_seconds=60,
        )
        # Control: every other field passes the real validator. Only session_id changes.
        self.assertEqual(coordinator._validate(valid, before), new_expiry)
        self.assertEqual(before.generation, 0)
        revoke_refresh = store.revoke_refresh

        def revoke_reserved(session_handle, lease):
            self.assertTrue(session_handle == handle, 'Wrong session revoked.')
            current_record = store.resolve(handle)
            self.assertTrue(current_record == before,
                            'Credentials, generation, or activity changed before revocation.')
            self.assertEqual(current_record.generation, 0)
            self.assertEqual(current_record.last_activity_at, 100.0)
            self.assertTrue(store._busy.get(handle) == lease,
                            'Revocation did not own the refresh reservation.')
            revoked = revoke_refresh(session_handle, lease)
            self.assertTrue(revoked, 'Reserved session was not revoked.')
            return revoked

        output = io.StringIO()
        rendered_errors = []
        context = None
        with (
            patch.object(store, 'replace_credentials', wraps=store.replace_credentials) as commit,
            patch.object(store, 'touch', wraps=store.touch) as touch,
            patch.object(store, 'create', wraps=store.create) as create,
            patch.object(store, 'reserve_refresh', wraps=store.reserve_refresh) as reserve,
            patch.object(store, 'revoke_refresh', side_effect=revoke_reserved) as revoke,
            patch.object(store, 'release_refresh', wraps=store.release_refresh) as release,
            redirect_stdout(output), redirect_stderr(output),
            self.assertNoLogs(level='DEBUG'),
        ):
            for _ in range(2):
                with self.assertRaises(AuthenticationRequired) as raised:
                    try:
                        with coordinator.authenticated(handle) as context:
                            self.fail('Session binding mismatch produced an authenticated context.')
                    except AuthenticationRequired as error:
                        rendered_errors.append(traceback.format_exc())
                        # Inspect even suppressed exception contexts for leaked values.
                        current = error
                        while current is not None:
                            rendered_errors.append(str(current) + repr(current))
                            current = current.__context__
                        raise
                self.assertIsNone(context)
                self.assertIs(type(raised.exception), AuthenticationRequired)
                self.assertTrue(str(raised.exception) == 'Normal authentication required.',
                                'Unexpected authentication failure text.')
                self.assertTrue(repr(raised.exception) ==
                                "AuthenticationRequired('Normal authentication required.')",
                                'Unexpected authentication failure representation.')
                self.assertIsNone(store.resolve(handle))
                self.assertTrue(store._records == {}, 'Credential or activity state remained.')
                self.assertTrue(store._busy == {}, 'Refresh reservation remained held.')
                # Counts must stay at one when the exact revoked handle is replayed.
                self.assertEqual(refresh.call_count, 1)
                self.assertEqual(reserve.call_count, 1)
                self.assertEqual(revoke.call_count, 1)
                self.assertEqual(release.call_count, 1)
                lifecycle_clock.return_value += 5.0

        self.assertTrue(refresh.call_args.args == (before.refresh_token,),
                        'Refresh did not receive the old stored credential.')
        self.assertEqual(refresh.call_args.kwargs, {})
        self.assertEqual(client_factory.call_count, 0, 'Client factory ran.')
        self.assertEqual(commit.call_count, 0, 'New credentials were submitted to the store.')
        self.assertEqual(touch.call_count, 0, 'Failed refresh advanced activity.')
        self.assertEqual(create.call_count, 0, 'Failed refresh created a session.')
        self.assertTrue(release.call_args == revoke.call_args,
                        'Cleanup used a different refresh reservation.')
        self.assertTrue(output.getvalue() == '', 'Failure emitted unexpected output.')
        rendered = ''.join(rendered_errors) + output.getvalue() + repr(before) + repr(mismatched)
        for protected in (before.access_token, before.refresh_token, mismatched.access_token,
                          mismatched.refresh_token, before.csrf, before.user_email,
                          before.user_id, session_b, before.session_id, handle):
            # Boolean assertions keep protected values out of assertion diagnostics.
            self.assertTrue(protected not in rendered, 'Failure exposed a protected value.')
        for guard in self.network_guards:
            self.assertEqual(guard.call_count, 0, 'Outbound network was attempted.')


    def test_refresh_recovery_amr_revokes_session_and_replay_fails_closed(self):
        lifecycle_clock = Mock(return_value=100.0)
        unix_clock = Mock(return_value=2_000_000_000.0)
        store = NormalAuthStore(clock=lifecycle_clock, idle_seconds=1000,
                                absolute_seconds=300)
        issuer = 'https://normal-auth.example.invalid/auth/v1'
        # Normal-sign-in fixtures; no actual recovery store, grant, or pending record.
        handle = store.create(
            user_id='recovery-amr-user-a', user_email='recovery-amr-a@example.invalid',
            access_token='recovery-amr-old-access-secret',
            refresh_token='recovery-amr-old-refresh-secret',
            access_expires_at=unix_clock.return_value + 55,
            session_id='recovery-amr-session-a',
        )
        before = store.resolve(handle)
        self.assertIsNotNone(before)
        lifecycle_clock.return_value = 125.0
        unix_clock.return_value += 25.0
        self.assertGreater(before.access_expires_at, unix_clock.return_value)
        self.assertLess(before.access_expires_at, unix_clock.return_value + 60)
        new_expiry = unix_clock.return_value + 3600
        # Fake the trusted transport's already signature-verified claims boundary;
        # JWT cryptography belongs to the adapter, not this coordinator test.
        valid = VerifiedRefresh(
            user_id=before.user_id, user_email=before.user_email,
            response_user_id=before.user_id, session_user_id=before.user_id,
            access_token='recovery-amr-new-access-secret',
            refresh_token='recovery-amr-new-refresh-secret', expires_at=new_expiry,
            claims={'sub': before.user_id, 'iss': issuer, 'aud': 'authenticated',
                    'role': 'authenticated', 'session_id': before.session_id,
                    'exp': new_expiry,
                    'amr': [{'method': 'password', 'timestamp': 2_000_000_000}]},
        )
        recovery_marked = replace(valid, claims={
            **valid.claims,
            'amr': [{**valid.claims['amr'][0], 'method': 'recovery'}],
        })
        self.assertTrue(recovery_marked.claims['session_id'] == before.session_id,
                        'Session binding must remain valid.')
        self.assertTrue(all(value == before.user_id for value in (
            recovery_marked.user_id, recovery_marked.response_user_id,
            recovery_marked.session_user_id, recovery_marked.claims['sub'])),
            'Identity fields must remain bound to the stored user.')

        def refresh_transport(refresh_token):
            self.assertTrue(refresh_token == before.refresh_token,
                            'Incorrect refresh credential.')
            self.assertTrue(store.resolve(handle) == before,
                            'Session changed before refresh completed.')
            self.assertTrue(handle in store._busy, 'Refresh was not reserved.')
            return recovery_marked

        refresh = Mock(side_effect=refresh_transport)
        client_factory = Mock(side_effect=AssertionError('Unexpected client construction.'))
        coordinator = NormalAuthCoordinator(
            store, refresh_transport=refresh, client_factory=client_factory,
            issuer=issuer, clock=unix_clock, refresh_seconds=60,
        )
        # Control: every other field passes the real validator. Only the AMR method changes.
        self.assertEqual(coordinator._validate(valid, before), new_expiry)
        self.assertEqual(before.generation, 0)
        revoke_refresh = store.revoke_refresh

        def revoke_reserved(session_handle, lease):
            self.assertTrue(session_handle == handle, 'Wrong session revoked.')
            current_record = store.resolve(handle)
            self.assertTrue(current_record == before,
                            'Credentials, generation, or activity changed before revocation.')
            self.assertEqual(current_record.generation, 0)
            self.assertEqual(current_record.last_activity_at, 100.0)
            self.assertTrue(store._busy.get(handle) == lease,
                            'Revocation did not own the refresh reservation.')
            revoked = revoke_refresh(session_handle, lease)
            self.assertTrue(revoked, 'Reserved session was not revoked.')
            return revoked

        output = io.StringIO()
        rendered_errors = []
        context = None
        with (
            patch.object(store, 'replace_credentials', wraps=store.replace_credentials) as commit,
            patch.object(store, 'touch', wraps=store.touch) as touch,
            patch.object(store, 'create', wraps=store.create) as create,
            patch.object(store, 'reserve_refresh', wraps=store.reserve_refresh) as reserve,
            patch.object(store, 'revoke_refresh', side_effect=revoke_reserved) as revoke,
            patch.object(store, 'release_refresh', wraps=store.release_refresh) as release,
            redirect_stdout(output), redirect_stderr(output),
            self.assertNoLogs(level='DEBUG'),
        ):
            for _ in range(2):
                with self.assertRaises(AuthenticationRequired) as raised:
                    try:
                        with coordinator.authenticated(handle) as context:
                            self.fail('Recovery authorization produced a normal authenticated context.')
                    except AuthenticationRequired as error:
                        rendered_errors.append(traceback.format_exc())
                        # Inspect even suppressed exception contexts for leaked values.
                        current = error
                        while current is not None:
                            rendered_errors.append(str(current) + repr(current))
                            current = current.__context__
                        raise
                self.assertIsNone(context)
                self.assertIs(type(raised.exception), AuthenticationRequired)
                self.assertTrue(str(raised.exception) == 'Normal authentication required.',
                                'Unexpected authentication failure text.')
                self.assertTrue(repr(raised.exception) ==
                                "AuthenticationRequired('Normal authentication required.')",
                                'Unexpected authentication failure representation.')
                self.assertIsNone(store.resolve(handle))
                self.assertTrue(store._records == {}, 'Credential or activity state remained.')
                self.assertTrue(store._busy == {}, 'Refresh reservation remained held.')
                # Counts must stay at one when the exact revoked handle is replayed.
                self.assertEqual(refresh.call_count, 1)
                self.assertEqual(reserve.call_count, 1)
                self.assertEqual(revoke.call_count, 1)
                self.assertEqual(release.call_count, 1)
                lifecycle_clock.return_value += 5.0

        self.assertTrue(refresh.call_args.args == (before.refresh_token,),
                        'Refresh did not receive the old stored credential.')
        self.assertEqual(refresh.call_args.kwargs, {})
        self.assertEqual(client_factory.call_count, 0, 'Client factory ran.')
        self.assertEqual(commit.call_count, 0, 'New credentials were submitted to the store.')
        self.assertEqual(touch.call_count, 0, 'Failed refresh advanced activity.')
        self.assertEqual(create.call_count, 0, 'Failed refresh created a session.')
        self.assertTrue(release.call_args == revoke.call_args,
                        'Cleanup used a different refresh reservation.')
        self.assertTrue(output.getvalue() == '', 'Failure emitted unexpected output.')
        rendered = ''.join(rendered_errors) + output.getvalue() + repr(before) + repr(recovery_marked)
        for protected in (before.access_token, before.refresh_token, recovery_marked.access_token,
                          recovery_marked.refresh_token, before.csrf, before.user_email,
                          before.user_id, before.session_id, handle):
            # Boolean assertions keep protected values out of assertion diagnostics.
            self.assertTrue(protected not in rendered, 'Failure exposed a protected value.')
        for guard in self.network_guards:
            self.assertEqual(guard.call_count, 0, 'Outbound network was attempted.')


    def test_ambiguous_refresh_timeout_revokes_session_and_replay_fails_closed(self):
        lifecycle_clock = Mock(return_value=100.0)
        unix_clock = Mock(return_value=2_000_000_000.0)
        store = NormalAuthStore(clock=lifecycle_clock, idle_seconds=1000,
                                absolute_seconds=300)
        issuer = 'https://normal-auth.example.invalid/auth/v1'
        # Normal-sign-in fixtures; no actual recovery store, grant, or pending record.
        handle = store.create(
            user_id='ambiguous-refresh-user-a', user_email='ambiguous-refresh-a@example.invalid',
            access_token='ambiguous-refresh-old-access-secret',
            refresh_token='ambiguous-refresh-old-refresh-secret',
            access_expires_at=unix_clock.return_value + 55,
            session_id='ambiguous-refresh-session-a',
        )
        before = store.resolve(handle)
        self.assertIsNotNone(before)
        lifecycle_clock.return_value = 125.0
        unix_clock.return_value += 25.0
        self.assertGreater(before.access_expires_at, unix_clock.return_value)
        self.assertLess(before.access_expires_at, unix_clock.return_value + 60)
        # The provider may have consumed the old token before the response was lost.
        # These synthetic details must never escape via the public error chain.
        fake_new_access = 'ambiguous-provider-new-access-secret'
        fake_new_refresh = 'ambiguous-provider-new-refresh-secret'
        provider_detail = 'private-provider-request-detail'
        timeout_detail = 'refresh response timed out after possible provider rotation'
        sensitive_details = (before.access_token, before.refresh_token, before.csrf,
                             before.user_id, before.user_email, before.session_id,
                             fake_new_access, fake_new_refresh, provider_detail, timeout_detail)

        def refresh_transport(refresh_token):
            self.assertTrue(refresh_token == before.refresh_token,
                            'Incorrect refresh credential.')
            self.assertTrue(store.resolve(handle) == before,
                            'Session changed before refresh completed.')
            self.assertTrue(handle in store._busy, 'Refresh was not reserved.')
            raise TimeoutError(' | '.join(sensitive_details))

        refresh = Mock(side_effect=refresh_transport)
        client_factory = Mock(side_effect=AssertionError('Unexpected client construction.'))
        coordinator = NormalAuthCoordinator(
            store, refresh_transport=refresh, client_factory=client_factory,
            issuer=issuer, clock=unix_clock, refresh_seconds=60,
        )
        self.assertEqual(before.generation, 0)
        revoke_refresh = store.revoke_refresh

        def revoke_reserved(session_handle, lease):
            self.assertTrue(session_handle == handle, 'Wrong session revoked.')
            current_record = store.resolve(handle)
            self.assertTrue(current_record == before,
                            'Credentials, generation, or activity changed before revocation.')
            self.assertEqual(current_record.generation, 0)
            self.assertEqual(current_record.last_activity_at, 100.0)
            self.assertTrue(store._busy.get(handle) == lease,
                            'Revocation did not own the refresh reservation.')
            revoked = revoke_refresh(session_handle, lease)
            self.assertTrue(revoked, 'Reserved session was not revoked.')
            return revoked

        output = io.StringIO()
        rendered_errors = []
        context = None
        with (
            patch.object(store, 'replace_credentials', wraps=store.replace_credentials) as commit,
            patch.object(store, 'touch', wraps=store.touch) as touch,
            patch.object(store, 'create', wraps=store.create) as create,
            patch.object(store, 'reserve_refresh', wraps=store.reserve_refresh) as reserve,
            patch.object(store, 'revoke_refresh', side_effect=revoke_reserved) as revoke,
            patch.object(store, 'release_refresh', wraps=store.release_refresh) as release,
            redirect_stdout(output), redirect_stderr(output),
            self.assertNoLogs(level='DEBUG'),
        ):
            for _ in range(2):
                with self.assertRaises(AuthenticationRequired) as raised:
                    try:
                        with coordinator.authenticated(handle) as context:
                            self.fail('Ambiguous refresh failure produced an authenticated context.')
                    except AuthenticationRequired as error:
                        rendered_errors.append(traceback.format_exc())
                        # Inspect suppressed contexts and explicit causes as well as
                        # the formatted public traceback, without printing their contents.
                        pending = [error]
                        seen = set()
                        while pending:
                            current = pending.pop()
                            if current is None or id(current) in seen:
                                continue
                            seen.add(id(current))
                            rendered_errors.append(str(current) + repr(current))
                            pending.extend((current.__context__, current.__cause__))
                        raise
                self.assertIsNone(context)
                self.assertIs(type(raised.exception), AuthenticationRequired)
                self.assertTrue(str(raised.exception) == 'Normal authentication required.',
                                'Unexpected authentication failure text.')
                self.assertTrue(repr(raised.exception) ==
                                "AuthenticationRequired('Normal authentication required.')",
                                'Unexpected authentication failure representation.')
                self.assertIsNone(store.resolve(handle))
                self.assertTrue(store._records == {}, 'Credential or activity state remained.')
                self.assertTrue(store._busy == {}, 'Refresh reservation remained held.')
                # Counts must stay at one when the exact revoked handle is replayed.
                self.assertEqual(refresh.call_count, 1)
                self.assertEqual(reserve.call_count, 1)
                self.assertEqual(revoke.call_count, 1)
                self.assertEqual(release.call_count, 1)
                lifecycle_clock.return_value += 5.0

        self.assertTrue(refresh.call_args.args == (before.refresh_token,),
                        'Refresh did not receive the old stored credential.')
        self.assertEqual(refresh.call_args.kwargs, {})
        self.assertEqual(client_factory.call_count, 0, 'Client factory ran.')
        self.assertEqual(commit.call_count, 0, 'New credentials were submitted to the store.')
        self.assertEqual(touch.call_count, 0, 'Failed refresh advanced activity.')
        self.assertEqual(create.call_count, 0, 'Failed refresh created a session.')
        self.assertTrue(release.call_args == revoke.call_args,
                        'Cleanup used a different refresh reservation.')
        self.assertTrue(output.getvalue() == '', 'Failure emitted unexpected output.')
        rendered = ''.join(rendered_errors) + output.getvalue() + repr(before)
        for protected in (*sensitive_details, handle):
            # Boolean assertions keep protected values out of assertion diagnostics.
            self.assertTrue(protected not in rendered, 'Failure exposed a protected value.')
        for guard in self.network_guards:
            self.assertEqual(guard.call_count, 0, 'Outbound network was attempted.')


    def test_concurrent_request_is_busy_while_owner_refreshes_once(self):
        lifecycle_clock = Mock(return_value=100.0)
        unix_clock = Mock(return_value=2_000_000_000.0)
        store = NormalAuthStore(clock=lifecycle_clock, idle_seconds=1000,
                                absolute_seconds=300)
        issuer = 'https://normal-auth.example.invalid/auth/v1'
        # Normal-sign-in fixtures only; no recovery store, grant, or credential.
        handle = store.create(
            user_id='concurrent-normal-user', user_email='concurrent@example.invalid',
            access_token='concurrent-old-access-secret',
            refresh_token='concurrent-old-refresh-secret',
            access_expires_at=unix_clock.return_value + 55,
            session_id='concurrent-normal-session',
        )
        before = store.resolve(handle)
        self.assertIsNotNone(before)
        lifecycle_clock.return_value = 125.0
        unix_clock.return_value += 25.0
        self.assertGreater(before.access_expires_at, unix_clock.return_value)
        self.assertLess(before.access_expires_at, unix_clock.return_value + 60)
        new_expiry = unix_clock.return_value + 3600
        refreshed = VerifiedRefresh(
            user_id=before.user_id, user_email=before.user_email,
            response_user_id=before.user_id, session_user_id=before.user_id,
            access_token='concurrent-new-access-secret',
            refresh_token='concurrent-new-refresh-secret', expires_at=new_expiry,
            claims={'sub': before.user_id, 'iss': issuer, 'aud': 'authenticated',
                    'role': 'authenticated', 'session_id': before.session_id,
                    'exp': new_expiry,
                    'amr': [{'method': 'password', 'timestamp': 2_000_000_000}]},
        )
        rotated = replace(before, access_token=refreshed.access_token,
                          refresh_token=refreshed.refresh_token,
                          access_expires_at=new_expiry, generation=1)
        entered_refresh, finish_refresh = Event(), Event()
        worker_errors, contexts, rendered = [], [], []
        clients = [Mock(spec=['close']), Mock(spec=['close'])]

        def refresh_transport(refresh_token):
            self.assertTrue(refresh_token == before.refresh_token, 'Wrong refresh credential.')
            entered_refresh.set()
            if not finish_refresh.wait(timeout=5):
                raise AssertionError('Refresh synchronization timed out.')
            return refreshed

        refresh = Mock(side_effect=refresh_transport)

        @contextmanager
        def request_client(access_token):
            self.assertTrue(access_token == refreshed.access_token, 'Wrong client credential.')
            index = client_factory.call_count - 1
            expected = rotated if index == 0 else replace(rotated, last_activity_at=130.0)
            self.assertTrue(store.resolve(handle) == expected,
                            'Rotation or activity was incorrect before client construction.')
            client = clients[index]
            lifecycle_clock.return_value = 130.0 if index == 0 else 140.0
            try:
                yield client
            finally:
                client.close()

        client_factory = Mock(side_effect=request_client)
        coordinator = NormalAuthCoordinator(
            store, refresh_transport=refresh, client_factory=client_factory,
            issuer=issuer, clock=unix_clock, refresh_seconds=60,
        )

        def request_a():
            try:
                with coordinator.authenticated(handle) as context:
                    contexts.append(context)
                    self.assertIs(context.client, clients[0])
                    self.assertTrue(store.resolve(handle) == replace(rotated, last_activity_at=130.0),
                                    'Incorrect state after successful client construction.')
                    self.assertEqual(clients[0].close.call_count, 0)
            except BaseException as error:
                # Propagate worker failures without printing credentials in diagnostics.
                worker_errors.append(error)

        output = io.StringIO()
        with (
            patch.object(store, 'replace_credentials', wraps=store.replace_credentials) as commit,
            patch.object(store, 'touch', wraps=store.touch) as touch,
            patch.object(store, 'revoke', wraps=store.revoke) as revoke,
            patch.object(store, 'revoke_refresh', wraps=store.revoke_refresh) as revoke_refresh,
            patch.object(store, 'release_refresh', wraps=store.release_refresh) as release,
            redirect_stdout(output), redirect_stderr(output),
            self.assertNoLogs(level='DEBUG'),
        ):
            worker = Thread(target=request_a, daemon=True)
            worker.start()
            try:
                self.assertTrue(entered_refresh.wait(timeout=5), 'Owner did not enter refresh.')
                self.assertTrue(store.resolve(handle) == before, 'Premature session mutation.')
                reservations = store._busy.copy()
                self.assertTrue(handle in reservations, 'Owner has no reservation.')
                lease = reservations[handle]
                context_b = None
                with self.assertRaises(SessionBusy) as raised:
                    with coordinator.authenticated(handle) as context_b:
                        self.fail('Busy request produced an authenticated context.')
                self.assertIsNone(context_b)
                error = raised.exception
                self.assertIs(type(error), SessionBusy)
                self.assertTrue(str(error) == 'Normal authentication is busy; retry resolution later.',
                                'Unexpected busy failure text.')
                self.assertIsNone(error.__context__)
                self.assertIsNone(error.__cause__)
                rendered.extend((str(error), repr(error), repr(lease)))
                self.assertEqual(refresh.call_count, 1)
                self.assertEqual(client_factory.call_count, 0)
                self.assertEqual(commit.call_count, 0)
                self.assertEqual(touch.call_count, 0)
                self.assertEqual(revoke.call_count, 0)
                self.assertEqual(revoke_refresh.call_count, 0)
                self.assertEqual(release.call_count, 0)
                self.assertTrue(store.resolve(handle) == before, 'Busy request changed session state.')
                self.assertTrue(store._busy == reservations, 'Busy request changed reservation ownership.')
            finally:
                finish_refresh.set()
                worker.join(timeout=5)
            self.assertFalse(worker.is_alive(), 'Refresh worker did not finish.')
            self.assertTrue(not worker_errors, 'Request A failed in worker thread.')
            self.assertEqual(len(contexts), 1)
            self.assertTrue(contexts[0].auth_session_id == handle, 'Opaque handle changed.')
            self.assertTrue(contexts[0].user_id == before.user_id and
                            contexts[0].user_email == before.user_email, 'Identity changed.')
            self.assertEqual(client_factory.call_count, 1)
            self.assertEqual(clients[0].close.call_count, 1)
            self.assertEqual(commit.call_count, 1)
            self.assertTrue(commit.call_args.args == (handle, lease), 'Wrong replacement reservation.')
            self.assertTrue(commit.call_args.kwargs == dict(
                user_id=before.user_id, user_email=before.user_email,
                access_token=refreshed.access_token, refresh_token=refreshed.refresh_token,
                access_expires_at=new_expiry, session_id=before.session_id),
                'Credentials were not submitted together for atomic replacement.')
            self.assertTrue(store.resolve(handle) == replace(rotated, last_activity_at=130.0),
                            'Incorrect final owner session state.')
            self.assertTrue(store._busy == {}, 'Reservation remained after owner completion.')
            self.assertEqual(touch.call_count, 1)
            self.assertEqual(release.call_count, 1)
            self.assertTrue(release.call_args.args == (handle, lease), 'Wrong cleanup reservation.')

            # The rotated session supports a later ordinary request without refresh.
            lifecycle_clock.return_value = 135.0
            with coordinator.authenticated(handle) as later:
                self.assertTrue(later.auth_session_id == handle, 'Later request changed handle.')
                self.assertIs(later.client, clients[1])
                self.assertEqual(clients[1].close.call_count, 0)
                rendered.extend((repr(later), repr(contexts[0]), repr(refreshed), repr(before)))
            self.assertEqual(clients[1].close.call_count, 1)
            self.assertEqual(clients[0].close.call_count, 1)
            self.assertEqual(client_factory.call_count, 2)
            self.assertEqual(refresh.call_count, 1)
            self.assertTrue(refresh.call_args.args == (before.refresh_token,), 'Wrong refresh input.')
            self.assertEqual(refresh.call_args.kwargs, {})
            self.assertEqual(commit.call_count, 1)
            self.assertEqual(touch.call_count, 2)
            self.assertEqual(release.call_count, 1)
            self.assertEqual(revoke.call_count, 0)
            self.assertEqual(revoke_refresh.call_count, 0)
            self.assertTrue(store._busy == {}, 'Later request retained a reservation.')
            self.assertTrue(store.resolve(handle) == replace(rotated, last_activity_at=140.0),
                            'Later request changed credentials or lifetimes.')

        self.assertTrue(output.getvalue() == '', 'Concurrency test emitted unexpected output.')
        public = ''.join(rendered) + output.getvalue()
        for protected in (before.access_token, before.refresh_token, refreshed.access_token,
                          refreshed.refresh_token, before.csrf, before.user_id, before.user_email,
                          before.session_id, handle, lease.nonce):
            self.assertTrue(protected not in public, 'Protected value leaked.')
        # Successful refresh and later activity must not extend absolute lifetime.
        lifecycle_clock.return_value = before.created_at + 300 - 0.001
        self.assertIsNotNone(store.resolve(handle))
        lifecycle_clock.return_value = before.created_at + 300
        self.assertIsNone(store.resolve(handle))
        for guard in self.network_guards:
            self.assertEqual(guard.call_count, 0, 'Outbound network was attempted.')


    def test_revocation_during_refresh_prevents_session_resurrection(self):
        lifecycle_clock = Mock(return_value=100.0)
        unix_clock = Mock(return_value=2_000_000_000.0)
        store = NormalAuthStore(clock=lifecycle_clock, idle_seconds=1000,
                                absolute_seconds=300)
        issuer = 'https://normal-auth.example.invalid/auth/v1'
        # Normal-sign-in fixtures only; no recovery store, grant, or credential.
        handle = store.create(
            user_id='revocation-race-normal-user', user_email='concurrent@example.invalid',
            access_token='revocation-race-old-access-secret',
            refresh_token='revocation-race-old-refresh-secret',
            access_expires_at=unix_clock.return_value + 55,
            session_id='revocation-race-normal-session',
        )
        before = store.resolve(handle)
        self.assertIsNotNone(before)
        lifecycle_clock.return_value = 125.0
        unix_clock.return_value += 25.0
        self.assertGreater(before.access_expires_at, unix_clock.return_value)
        self.assertLess(before.access_expires_at, unix_clock.return_value + 60)
        new_expiry = unix_clock.return_value + 3600
        refreshed = VerifiedRefresh(
            user_id=before.user_id, user_email=before.user_email,
            response_user_id=before.user_id, session_user_id=before.user_id,
            access_token='revocation-race-new-access-secret',
            refresh_token='revocation-race-new-refresh-secret', expires_at=new_expiry,
            claims={'sub': before.user_id, 'iss': issuer, 'aud': 'authenticated',
                    'role': 'authenticated', 'session_id': before.session_id,
                    'exp': new_expiry,
                    'amr': [{'method': 'password', 'timestamp': 2_000_000_000}]},
        )
        # Control: the result is valid; rejection must come from revoked state.
        entered_refresh, finish_refresh, returned_refresh = Event(), Event(), Event()
        worker_errors, contexts, rendered, replacement_results = [], [], [], []

        def refresh_transport(refresh_token):
            entered_refresh.set()
            if not finish_refresh.wait(timeout=5):
                raise AssertionError('Refresh synchronization timed out.')
            returned_refresh.set()
            return refreshed

        refresh = Mock(side_effect=refresh_transport)
        client_factory = Mock(side_effect=AssertionError('Unexpected client construction.'))
        coordinator = NormalAuthCoordinator(
            store, refresh_transport=refresh, client_factory=client_factory,
            issuer=issuer, clock=unix_clock, refresh_seconds=60,
        )
        self.assertEqual(coordinator._validate(refreshed, before), new_expiry)
        replace_credentials = store.replace_credentials

        def attempt_replacement(*args, **kwargs):
            result = replace_credentials(*args, **kwargs)
            replacement_results.append(result)
            return result

        def capture_error(error):
            rendered.append(traceback.format_exc())
            pending, seen = [error], set()
            while pending:
                current = pending.pop()
                if current is None or id(current) in seen:
                    continue
                seen.add(id(current))
                rendered.append(str(current) + repr(current))
                pending.extend((current.__context__, current.__cause__))

        def request_a():
            try:
                with coordinator.authenticated(handle) as context:
                    contexts.append(context)
            except BaseException as error:
                capture_error(error)
                worker_errors.append(error)

        output = io.StringIO()
        with (
            patch.object(store, 'replace_credentials', side_effect=attempt_replacement) as commit,
            patch.object(store, 'create', wraps=store.create) as create,
            patch.object(store, 'touch', wraps=store.touch) as touch,
            patch.object(store, 'reserve_refresh', wraps=store.reserve_refresh) as reserve,
            patch.object(store, 'revoke_refresh', wraps=store.revoke_refresh) as revoke_refresh,
            patch.object(store, 'release_refresh', wraps=store.release_refresh) as release,
            redirect_stdout(output), redirect_stderr(output),
            self.assertNoLogs(level='DEBUG'),
        ):
            worker = Thread(target=request_a, daemon=True)
            worker.start()
            try:
                self.assertTrue(entered_refresh.wait(timeout=5), 'Owner did not enter refresh.')
                self.assertTrue(worker.is_alive(), 'Request A ended before revocation.')
                self.assertFalse(returned_refresh.is_set(), 'Refresh returned before revocation.')
                self.assertTrue(store.resolve(handle) == before, 'Premature session mutation.')
                self.assertTrue(handle in store._busy, 'Refresh was not reserved.')
                lease = store._busy[handle]
                self.assertEqual(lease.generation, 0)
                self.assertEqual(commit.call_count, 0)
                lifecycle_clock.return_value = 130.0
                # Supported local revocation, without any Flask/logout integration.
                self.assertTrue(store.revoke(handle), 'In-flight session was not revoked.')
                self.assertIsNone(store.resolve(handle))
                self.assertTrue(store._records == {}, 'Revocation retained credentials.')
                self.assertTrue(store._busy == {}, 'Revocation retained the reservation.')
                self.assertFalse(returned_refresh.is_set(), 'Refresh was not paused during revocation.')
            finally:
                finish_refresh.set()
                worker.join(timeout=5)
            self.assertFalse(worker.is_alive(), 'Refresh worker did not finish.')
            self.assertTrue(returned_refresh.is_set(), 'Valid refresh result was not returned.')
            self.assertEqual(len(worker_errors), 1, 'Request A did not fail exactly once.')
            self.assertIs(type(worker_errors[0]), AuthenticationRequired)
            self.assertTrue(not contexts, 'Revoked session produced an authenticated context.')
            self.assertEqual(refresh.call_count, 1)
            self.assertTrue(refresh.call_args.args == (before.refresh_token,), 'Wrong refresh credential.')
            self.assertEqual(refresh.call_args.kwargs, {})
            self.assertEqual(commit.call_count, 1)
            self.assertTrue(replacement_results == [False], 'Revoked replacement was accepted.')
            self.assertTrue(commit.call_args.args == (handle, lease), 'Wrong replacement reservation.')
            self.assertTrue(commit.call_args.kwargs == dict(
                user_id=before.user_id, user_email=before.user_email,
                access_token=refreshed.access_token, refresh_token=refreshed.refresh_token,
                access_expires_at=new_expiry, session_id=before.session_id),
                'Valid refreshed credentials did not reach the replacement guard.')
            self.assertIsNone(store.resolve(handle))
            self.assertTrue(store._records == {}, 'Refresh resurrected session state.')
            self.assertTrue(store._busy == {}, 'Refresh recreated a reservation.')
            self.assertEqual(release.call_count, 1)
            self.assertEqual(revoke_refresh.call_count, 1)
            self.assertTrue(release.call_args.args == (handle, lease), 'Wrong cleanup reservation.')
            self.assertTrue(revoke_refresh.call_args.args == (handle, lease), 'Wrong revocation reservation.')
            self.assertFalse(store.revoke(handle), 'Repeated revocation was not idempotent.')

            lifecycle_clock.return_value = 140.0
            replay_context = None
            with self.assertRaises(AuthenticationRequired) as replay:
                try:
                    with coordinator.authenticated(handle) as replay_context:
                        self.fail('Revoked handle replay produced an authenticated context.')
                except AuthenticationRequired as error:
                    capture_error(error)
                    raise
            self.assertIsNone(replay_context)
            for error in (worker_errors[0], replay.exception):
                self.assertIs(type(error), AuthenticationRequired)
                self.assertTrue(str(error) == 'Normal authentication required.', 'Unexpected failure text.')
                self.assertTrue(repr(error) == "AuthenticationRequired('Normal authentication required.')",
                                'Unexpected failure representation.')
            self.assertEqual(refresh.call_count, 1)
            self.assertEqual(reserve.call_count, 1)
            self.assertEqual(commit.call_count, 1)
            self.assertEqual(release.call_count, 1)
            self.assertEqual(revoke_refresh.call_count, 1)
            self.assertEqual(client_factory.call_count, 0)
            self.assertEqual(create.call_count, 0)
            self.assertEqual(touch.call_count, 0)
            self.assertIsNone(store.resolve(handle))
            self.assertTrue(store._records == {}, 'Replay recreated credentials, generation, or activity.')
            self.assertTrue(store._busy == {}, 'Replay created a reservation.')

        self.assertTrue(output.getvalue() == '', 'Unexpected captured output.')
        public = ''.join(rendered) + output.getvalue() + repr(before) + repr(refreshed) + repr(lease)
        for protected in (before.access_token, before.refresh_token, refreshed.access_token,
                          refreshed.refresh_token, before.csrf, before.user_id, before.user_email,
                          before.session_id, handle, lease.nonce):
            self.assertTrue(protected not in public, 'Failure exposed a protected value.')
        for guard in self.network_guards:
            self.assertEqual(guard.call_count, 0, 'Outbound network was attempted.')


    def test_client_entry_failure_cleans_up_without_sensitive_exception_chain(self):
        lifecycle_clock = Mock(return_value=100.0)
        unix_clock = Mock(return_value=2_000_000_000.0)
        store = NormalAuthStore(clock=lifecycle_clock)
        # Only trusted normal-sign-in fixtures; no recovery dependencies.
        handle = store.create(
            user_id='client-entry-user', user_email='client-entry@example.invalid',
            access_token='client-entry-access-secret', refresh_token='client-entry-refresh-secret',
            access_expires_at=unix_clock.return_value + 3600,
            session_id='client-entry-session',
        )
        before = store.resolve(handle)
        lifecycle_clock.return_value = 125.0
        provider_detail = 'synthetic-private-provider-detail'
        diagnostic = 'synthetic-private-client-diagnostic'
        sensitive = (before.access_token, before.refresh_token, before.csrf,
                     before.user_id, before.user_email, before.session_id,
                     provider_detail, diagnostic)
        resource = Mock(spec=['close'])

        @contextmanager
        def failing_client(access_token):
            try:
                # Simulate a resource acquired before context-manager entry fails.
                raise RuntimeError(' | '.join(sensitive))
                yield resource
            finally:
                resource.close()

        client_factory = Mock(side_effect=failing_client)
        refresh = Mock(side_effect=AssertionError('Fresh credentials must not refresh.'))
        coordinator = NormalAuthCoordinator(
            store, refresh_transport=refresh, client_factory=client_factory,
            issuer='https://normal-auth.example.invalid/auth/v1', clock=unix_clock,
        )
        output, rendered = io.StringIO(), []
        context = None
        with (
            patch.object(store, 'touch', wraps=store.touch) as touch,
            redirect_stdout(output), redirect_stderr(output), self.assertNoLogs(level='DEBUG'),
        ):
            with self.assertRaises(ClientUnavailable) as raised:
                try:
                    with coordinator.authenticated(handle) as context:
                        self.fail('Failed client entry produced an authenticated context.')
                except ClientUnavailable as error:
                    rendered.append(traceback.format_exc())
                    pending, seen = [error], set()
                    while pending:
                        current = pending.pop()
                        if current is None or id(current) in seen:
                            continue
                        seen.add(id(current))
                        rendered.append(str(current) + repr(current))
                        pending.extend((current.__cause__, current.__context__))
                    raise
        self.assertIsNone(context)
        error = raised.exception
        self.assertIs(type(error), ClientUnavailable)
        self.assertTrue(str(error) == 'Authenticated client unavailable.', 'Unexpected public message.')
        self.assertTrue(repr(error) == "ClientUnavailable('Authenticated client unavailable.')",
                        'Unexpected public representation.')
        self.assertEqual(resource.close.call_count, 1)
        self.assertEqual(client_factory.call_count, 1)
        self.assertTrue(client_factory.call_args.args == (before.access_token,), 'Wrong client credential.')
        self.assertEqual(refresh.call_count, 0)
        self.assertEqual(touch.call_count, 0)
        self.assertTrue(store.resolve(handle) == before, 'Client failure changed session state or identity.')
        self.assertTrue(store._busy == {}, 'Client failure created a refresh reservation.')
        self.assertTrue(output.getvalue() == '', 'Client failure emitted output.')
        public = ''.join(rendered) + output.getvalue()
        for protected in sensitive:
            self.assertTrue(protected not in public, 'Client failure exposed a protected value.')
        # Boolean assertions avoid echoing the sensitive exception on regression.
        self.assertTrue(error.__cause__ is None, 'Public failure retained an exception cause.')
        self.assertTrue(error.__context__ is None, 'Public failure retained an exception context.')
        for guard in self.network_guards:
            self.assertEqual(guard.call_count, 0, 'Outbound network was attempted.')

    def test_application_exception_after_client_entry_propagates_unchanged(self):
        lifecycle_clock = Mock(return_value=100.0)
        store = NormalAuthStore(clock=lifecycle_clock)
        handle = store.create(
            user_id='application-user', user_email='application@example.invalid',
            access_token='application-access-secret', refresh_token='application-refresh-secret',
            access_expires_at=2_000_003_600.0, session_id='application-session',
        )
        before = store.resolve(handle)
        lifecycle_clock.return_value = 125.0
        client = Mock(spec=['close'])

        @contextmanager
        def request_client(access_token):
            try:
                yield client
            finally:
                client.close()

        refresh = Mock(side_effect=AssertionError('Fresh credentials must not refresh.'))
        client_factory = Mock(side_effect=request_client)
        coordinator = NormalAuthCoordinator(
            store, refresh_transport=refresh, client_factory=client_factory,
            issuer='https://normal-auth.example.invalid/auth/v1', clock=lambda: 2_000_000_000.0,
        )
        application_error = RuntimeError('Synthetic application failure.')
        with self.assertRaises(RuntimeError) as raised:
            with coordinator.authenticated(handle) as context:
                self.assertIs(context.client, client)
                self.assertEqual(client.close.call_count, 0)
                raise application_error
        self.assertIs(raised.exception, application_error)
        self.assertEqual(client.close.call_count, 1)
        self.assertEqual(client_factory.call_count, 1)
        self.assertEqual(refresh.call_count, 0)
        self.assertTrue(store.resolve(handle) == replace(before, last_activity_at=125.0),
                        'Application failure changed credentials or successful-resolution activity.')
        for guard in self.network_guards:
            self.assertEqual(guard.call_count, 0, 'Outbound network was attempted.')


    def test_refresh_control_flow_signals_propagate_after_revocation_and_cleanup(self):
        for signal_type in (KeyboardInterrupt, SystemExit, GeneratorExit, CancelledError):
            with self.subTest(signal=signal_type.__name__):
                self.assertFalse(issubclass(signal_type, Exception))
                lifecycle_clock = Mock(return_value=100.0)
                unix_clock = Mock(return_value=2_000_000_000.0)
                store = NormalAuthStore(clock=lifecycle_clock)
                # Normal-auth fixtures only; no recovery state participates.
                handle = store.create(
                    user_id='interrupted-user', user_email='interrupted@example.invalid',
                    access_token='interrupted-access-secret',
                    refresh_token='interrupted-refresh-secret',
                    access_expires_at=unix_clock.return_value + 55,
                    session_id='interrupted-session',
                )
                before = store.resolve(handle)
                lifecycle_clock.return_value = 125.0
                unix_clock.return_value += 25.0
                self.assertGreater(before.access_expires_at, unix_clock.return_value)
                self.assertLess(before.access_expires_at, unix_clock.return_value + 60)
                signal = signal_type('Synthetic private interruption detail.')
                leases = []

                def refresh_transport(refresh_token):
                    self.assertTrue(refresh_token == before.refresh_token, 'Wrong refresh credential.')
                    self.assertTrue(store.resolve(handle) == before, 'Premature session mutation.')
                    leases.append(store._busy[handle])
                    raise signal

                refresh = Mock(side_effect=refresh_transport)
                client_factory = Mock(side_effect=AssertionError('Unexpected client construction.'))
                coordinator = NormalAuthCoordinator(
                    store, refresh_transport=refresh, client_factory=client_factory,
                    issuer='https://normal-auth.example.invalid/auth/v1', clock=unix_clock,
                )
                output = io.StringIO()
                context = None
                with (
                    patch.object(store, 'touch', wraps=store.touch) as touch,
                    patch.object(store, 'create', wraps=store.create) as create,
                    patch.object(store, 'replace_credentials', wraps=store.replace_credentials) as commit,
                    patch.object(store, 'reserve_refresh', wraps=store.reserve_refresh) as reserve,
                    patch.object(store, 'revoke_refresh', wraps=store.revoke_refresh) as revoke,
                    patch.object(store, 'release_refresh', wraps=store.release_refresh) as release,
                    redirect_stdout(output), redirect_stderr(output), self.assertNoLogs(level='DEBUG'),
                ):
                    # Capture any outcome, then assert its exact type/object below.
                    # This keeps the pre-fix failure safe and lets all subtests run.
                    with self.assertRaises(BaseException) as raised:
                        with coordinator.authenticated(handle) as context:
                            self.fail('Interrupted refresh produced an authenticated context.')
                    self.assertIsNone(context)
                    self.assertEqual(len(leases), 1)
                    self.assertEqual(revoke.call_count, 1)
                    self.assertEqual(release.call_count, 1)
                    self.assertTrue(revoke.call_args.args == (handle, leases[0]), 'Wrong revoked lease.')
                    self.assertTrue(release.call_args.args == (handle, leases[0]), 'Wrong released lease.')
                    self.assertIsNone(store.resolve(handle))
                    self.assertTrue(store._records == {}, 'Interruption retained session state.')
                    self.assertTrue(store._busy == {}, 'Interruption retained a reservation.')
                    with self.assertRaises(AuthenticationRequired) as replay:
                        with coordinator.authenticated(handle):
                            self.fail('Replay produced an authenticated context.')
                    self.assertTrue(str(replay.exception) == 'Normal authentication required.',
                                    'Unexpected replay failure.')
                    self.assertEqual(refresh.call_count, 1)
                    self.assertEqual(reserve.call_count, 1)
                    self.assertEqual(revoke.call_count, 1)
                    self.assertEqual(release.call_count, 1)
                    self.assertEqual(client_factory.call_count, 0)
                    self.assertEqual(commit.call_count, 0)
                    self.assertEqual(create.call_count, 0)
                    self.assertEqual(touch.call_count, 0)
                    self.assertTrue(store._records == {}, 'Replay recreated session state.')
                    self.assertTrue(store._busy == {}, 'Replay created a reservation.')
                self.assertTrue(output.getvalue() == '', 'Interruption emitted sensitive output.')
                for guard in self.network_guards:
                    self.assertEqual(guard.call_count, 0, 'Outbound network was attempted.')
                self.assertIs(type(raised.exception), signal_type)
                self.assertTrue(raised.exception is signal, 'Original control-flow signal was replaced.')


if __name__ == '__main__':
    unittest.main()
