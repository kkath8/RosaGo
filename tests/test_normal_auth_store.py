"""Offline normal-auth foundation tests. No Flask integration or network."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
import io
import contextlib
import math
from threading import Barrier, Event
import unittest
from unittest.mock import Mock, patch

from normal_auth_store import (
    ABSOLUTE_SECONDS, IDLE_SECONDS, NormalAuthStore, RefreshReservation,
)


class NormalAuthStoreTests(unittest.TestCase):
    def setUp(self):
        self.clock = Mock(return_value=100.0)
        self.store = NormalAuthStore(clock=self.clock)
        self.credentials = dict(user_id='fixture-user', user_email='fixture@example.invalid',
            access_token='fixture-access-secret', refresh_token='fixture-refresh-secret',
            access_expires_at=2000000000.0, session_id='fixture-auth-session')

    def create(self, **changes):
        return self.store.create(**(self.credentials | changes))

    def commit(self, handle, lease, **changes):
        data = self.credentials | dict(access_token='rotated-access-secret',
            refresh_token='rotated-refresh-secret', access_expires_at=2000001000.0)
        return self.store.replace_credentials(handle, lease, **(data | changes))

    def test_create_and_resolve_all_record_fields(self):
        handle = self.create()
        record = self.store.resolve(handle)
        for field, expected in self.credentials.items():
            self.assertTrue(getattr(record, field) == expected, 'Stored field mismatch')
        self.assertEqual(record.created_at, 100.0)
        self.assertEqual(record.last_activity_at, 100.0)
        self.assertEqual(record.generation, 0)
        self.assertFalse(record.revoked)
        self.assertEqual(IDLE_SECONDS, 1800)
        self.assertEqual(ABSOLUTE_SECONDS, 28800)

    def test_random_handles_and_csrf_are_unique_for_same_user(self):
        handles = [self.create() for _ in range(64)]
        csrf_values = [self.store.resolve(handle).csrf for handle in handles]
        self.assertEqual(len(set(handles)), 64)
        self.assertEqual(len(set(csrf_values)), 64)
        self.assertFalse(set(handles) & set(csrf_values))
        for handle in handles:
            self.assertTrue(len(handle) == 43)
            self.assertTrue(all(value not in handle for value in
                (self.credentials['user_id'], self.credentials['user_email'],
                 self.credentials['access_token'], self.credentials['refresh_token'])))

    def test_random_generator_requests_256_bits_for_handle_and_csrf(self):
        with patch('normal_auth_store.secrets.token_urlsafe', side_effect=['h' * 43, 'c' * 43]) as random:
            self.create()
        self.assertEqual([call.args for call in random.call_args_list], [(32,), (32,)])

    def test_handle_collision_retries_without_overwriting_existing_session(self):
        handle = self.create()
        original = self.store.resolve(handle)
        with patch('normal_auth_store.secrets.token_urlsafe', side_effect=[handle, 'n' * 43, 's' * 43]):
            other = self.create(user_id='other-fixture')
        self.assertTrue(other != handle)
        self.assertTrue(self.store.resolve(handle) == original)

    def test_missing_and_invalid_handles_fail_closed(self):
        for handle in (None, '', 'missing', [], {}, 123):
            self.assertIsNone(self.store.resolve(handle))
            self.assertFalse(self.store.touch(handle))
            self.assertIsNone(self.store.reserve_refresh(handle))
            self.assertFalse(self.store.release_refresh(handle, None))
            self.assertFalse(self.store.revoke(handle))
            self.assertFalse(self.commit(handle, None))

    def test_idle_expiry_at_boundary_cannot_be_touched_or_refreshed(self):
        handle = self.create()
        lease, _ = self.store.reserve_refresh(handle)
        self.clock.return_value = 100 + IDLE_SECONDS - 0.001
        self.assertIsNotNone(self.store.resolve(handle))
        self.clock.return_value = 100 + IDLE_SECONDS
        self.assertIsNone(self.store.resolve(handle))
        self.assertFalse(self.store.touch(handle))
        self.assertFalse(self.commit(handle, lease))
        self.assertIsNone(self.store.reserve_refresh(handle))

    def test_absolute_expiry_despite_activity(self):
        self.store = NormalAuthStore(clock=self.clock, idle_seconds=10, absolute_seconds=25)
        handle = self.create()
        for now in (109, 118, 124):
            self.clock.return_value = now
            self.assertTrue(self.store.touch(handle))
        self.clock.return_value = 125
        self.assertIsNone(self.store.resolve(handle))
        self.assertFalse(self.store.touch(handle))

    def test_read_does_not_touch_activity(self):
        handle = self.create()
        self.clock.return_value = 100 + IDLE_SECONDS - 1
        self.assertEqual(self.store.resolve(handle).last_activity_at, 100)
        self.clock.return_value += 1
        self.assertIsNone(self.store.resolve(handle))

    def test_touch_updates_only_activity_and_extends_idle_deadline(self):
        handle = self.create()
        before = self.store.resolve(handle)
        self.clock.return_value = 200
        self.assertTrue(self.store.touch(handle))
        after = self.store.resolve(handle)
        self.assertTrue(after == replace(before, last_activity_at=200))
        self.clock.return_value = 100 + IDLE_SECONDS
        self.assertIsNotNone(self.store.resolve(handle))

    def test_expired_access_token_does_not_expire_local_session(self):
        handle = self.create(access_expires_at=1)
        self.assertIsNotNone(self.store.resolve(handle))
        self.assertIsNotNone(self.store.reserve_refresh(handle))

    def test_revoke_is_idempotent_and_other_browser_unaffected(self):
        first, second = self.create(), self.create()
        self.assertTrue(self.store.revoke(first))
        self.assertFalse(self.store.revoke(first))
        self.assertIsNone(self.store.resolve(first))
        self.assertFalse(self.store.touch(first))
        self.assertIsNotNone(self.store.resolve(second))

    def test_snapshots_are_immutable_and_cannot_mutate_store(self):
        handle = self.create()
        snapshot = self.store.resolve(handle)
        with self.assertRaises(FrozenInstanceError):
            snapshot.revoked = True
        object.__setattr__(snapshot, 'access_token', 'tampered-fixture')
        self.assertTrue(self.store.resolve(handle).access_token == self.credentials['access_token'])
        lease, snapshot = self.store.reserve_refresh(handle)
        object.__setattr__(snapshot, 'generation', 99)
        object.__setattr__(lease, 'generation', 99)
        self.assertFalse(self.commit(handle, lease))
        self.assertEqual(self.store.resolve(handle).generation, 0)

    def test_refresh_reservation_exclusive_until_release(self):
        handle = self.create()
        lease, snapshot = self.store.reserve_refresh(handle)
        self.assertEqual(lease.generation, snapshot.generation)
        self.assertIsNone(self.store.reserve_refresh(handle))
        self.assertFalse(self.store.release_refresh(handle, RefreshReservation('wrong', 0)))
        self.assertIsNone(self.store.reserve_refresh(handle))
        self.assertTrue(self.store.release_refresh(handle, lease))
        self.assertFalse(self.store.release_refresh(handle, lease))
        self.assertIsNotNone(self.store.reserve_refresh(handle))

    def test_released_lease_cannot_replace_or_release_new_reservation(self):
        handle = self.create()
        old, _ = self.store.reserve_refresh(handle)
        self.store.release_refresh(handle, old)
        current, _ = self.store.reserve_refresh(handle)
        self.assertFalse(self.commit(handle, old))
        self.assertFalse(self.store.release_refresh(handle, old))
        self.assertTrue(self.commit(handle, current))

    def test_atomic_replacement_increments_generation_preserves_lifetimes_csrf(self):
        handle = self.create()
        before = self.store.resolve(handle)
        lease, _ = self.store.reserve_refresh(handle)
        self.clock.return_value = 110
        self.store.touch(handle)
        self.assertTrue(self.commit(handle, lease))
        after = self.store.resolve(handle)
        self.assertTrue(after.access_token == 'rotated-access-secret')
        self.assertTrue(after.refresh_token == 'rotated-refresh-secret')
        self.assertEqual(after.access_expires_at, 2000001000)
        self.assertEqual(after.generation, 1)
        self.assertEqual(after.created_at, before.created_at)
        self.assertEqual(after.last_activity_at, 110)
        self.assertTrue(after.csrf == before.csrf)
        self.assertFalse(self.commit(handle, lease))
        next_lease, _ = self.store.reserve_refresh(handle)
        self.assertEqual(next_lease.generation, 1)
        self.assertTrue(self.commit(handle, next_lease))
        self.assertEqual(self.store.resolve(handle).generation, 2)

    def test_identity_and_supabase_session_cannot_change_during_refresh(self):
        handle = self.create()
        lease, before = self.store.reserve_refresh(handle)
        for changes in ({'user_id': 'other'}, {'session_id': 'other'},
                        {'access_token': ''}, {'refresh_token': ''}, {'access_expires_at': math.nan}):
            self.assertFalse(self.commit(handle, lease, **changes))
            self.assertTrue(self.store.resolve(handle) == before)
        self.assertTrue(self.commit(handle, lease, user_email='updated@example.invalid'))

    def test_lease_from_different_session_is_rejected(self):
        first, second = self.create(), self.create()
        lease, _ = self.store.reserve_refresh(first)
        self.store.reserve_refresh(second)
        self.assertFalse(self.commit(second, lease))
        self.assertFalse(self.store.release_refresh(second, lease))

    def test_reservation_does_not_extend_lifetime(self):
        handle = self.create()
        self.clock.return_value += IDLE_SECONDS - 1
        lease, _ = self.store.reserve_refresh(handle)
        self.clock.return_value += 1
        self.assertFalse(self.commit(handle, lease))
        self.assertFalse(self.store.release_refresh(handle, lease))

    def test_revoke_during_inflight_refresh_wins(self):
        handle = self.create()
        reserved, resume = Event(), Event()
        def worker():
            lease, _ = self.store.reserve_refresh(handle)
            reserved.set()
            if not resume.wait(5):
                raise RuntimeError('Test synchronization timeout.')
            return self.commit(handle, lease)
        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(worker)
            try:
                self.assertTrue(reserved.wait(5))
                self.assertTrue(self.store.revoke(handle))
            finally:
                resume.set()
            self.assertFalse(result.result(timeout=5))
        self.assertIsNone(self.store.resolve(handle))

    def test_concurrent_refresh_reservations_have_one_winner(self):
        handle = self.create()
        barrier = Barrier(8)
        def worker(_):
            barrier.wait(timeout=5)
            return self.store.reserve_refresh(handle)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(worker, range(8)))
        self.assertEqual(sum(result is not None for result in results), 1)

    def test_concurrent_duplicate_commits_have_one_winner(self):
        handle = self.create()
        lease, _ = self.store.reserve_refresh(handle)
        barrier = Barrier(8)
        def worker(_):
            barrier.wait(timeout=5)
            return self.commit(handle, lease)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(worker, range(8)))
        self.assertEqual(sum(results), 1)
        self.assertEqual(self.store.resolve(handle).generation, 1)

    def test_different_sessions_can_reserve_independently(self):
        first, second = self.create(), self.create()
        self.assertIsNotNone(self.store.reserve_refresh(first))
        self.assertIsNotNone(self.store.reserve_refresh(second))

    def test_restart_has_no_sessions_and_cannot_restore_old_lease(self):
        handle = self.create()
        lease, _ = self.store.reserve_refresh(handle)
        self.store = NormalAuthStore(clock=self.clock)
        self.assertIsNone(self.store.resolve(handle))
        self.assertFalse(self.commit(handle, lease))

    def test_repr_and_operations_do_not_expose_secrets(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            handle = self.create()
            lease, record = self.store.reserve_refresh(handle)
            self.commit(handle, lease)
            self.store.revoke(handle)
        self.assertEqual(output.getvalue(), '')
        rendered = repr((record, lease, self.store)) + str(record) + str(lease)
        for secret in (record.access_token, record.refresh_token, record.csrf,
                       record.user_email, record.user_id, record.session_id, lease.nonce, handle):
            self.assertTrue(secret not in rendered, 'Representation leaked a protected value')

    def test_invalid_inputs_raise_only_fixed_errors(self):
        for value in (None, '', ' ', [], {}, True):
            with self.assertRaisesRegex(ValueError, '^Invalid normal-session credentials.$'):
                self.create(access_token=value)
        for value in (None, math.nan, math.inf, -math.inf, True, 'secret'):
            with self.assertRaisesRegex(ValueError, '^Invalid normal-session credentials.$'):
                self.create(access_expires_at=value)
        for value in (0, -1, math.nan, math.inf, True, 'secret'):
            for argument in ('idle_seconds', 'absolute_seconds'):
                with self.assertRaisesRegex(ValueError, '^Invalid normal-session lifetime.$'):
                    NormalAuthStore(**{argument: value})


if __name__ == '__main__':
    unittest.main()
