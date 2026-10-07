"""Offline tests only: python -m unittest discover -s tools -p test_verify_profile_writes.py"""
import contextlib
from copy import deepcopy
import io
import json
import socket
import unittest
from unittest.mock import patch

import httpx
import verify_profile_writes as writes


class WriteVerifierTests(unittest.TestCase):
    def setUp(self):
        self.ids = {'A': '00000000-0000-0000-0000-000000000001',
                    'B': '00000000-0000-0000-0000-000000000002'}
        self.records = {
            self.ids['A']: dict(id=self.ids['A'], first_name='Test', last_name='User', created_at='2026-01-01T00:00:00+00:00'),
            self.ids['B']: dict(id=self.ids['B'], first_name='Profile', last_name='Test', created_at='2026-01-01T00:00:00+00:00'),
        }
        self.original = deepcopy(self.records)
        self.fault = None
        self.requests = []
        self.output = io.StringIO()
        self.clients = []
        for name in ('connect', 'connect_ex'):
            guard = patch.object(socket.socket, name, side_effect=AssertionError('Live network forbidden'))
            guard.start()
            self.addCleanup(guard.stop)
        for actor in ('A', 'B', 'anon'):
            headers = {'apikey': 'sb_publishable_test-secret', 'Accept-Profile': 'public'}
            if actor != 'anon':
                headers['Authorization'] = 'Bearer private-token-' + actor
            client = httpx.Client(base_url='https://fixture.invalid', headers=headers,
                                  transport=httpx.MockTransport(self.handler(actor)))
            self.clients.append(client)
            self.addCleanup(client.close)
        self.verifier = writes.WriteVerifier(*self.clients, self.ids['A'], self.ids['B'])

    def deny(self, status=403, code='42501'):
        return httpx.Response(status, json={'code': code, 'message': 'permission denied for table profiles'})

    def handler(self, actor):
        def handle(req):
            self.requests.append((actor, req.method, req.url.path, dict(req.url.params)))
            self.assertEqual(req.headers['apikey'], 'sb_publishable_test-secret')
            self.assertEqual(req.headers.get('Authorization'), None if actor == 'anon' else 'Bearer private-token-' + actor)
            if req.url.path == '/auth/v1/user':
                self.assertEqual(req.method, 'GET')
                return httpx.Response(200, json={'id': self.ids[actor], 'role': 'authenticated',
                    'email_confirmed_at': 'fixture', 'email': 'private-email@example.invalid'})
            self.assertEqual(req.url.path, '/rest/v1/profiles')
            target = req.url.params.get('id', '')[3:]
            if req.method == 'GET':
                data = [row for key, row in self.records.items()
                        if key == self.ids.get(actor) and (not target or target == key)]
                return httpx.Response(200, json=data)
            self.assertEqual(req.headers['Content-Profile'], 'public')
            if req.method == 'POST':
                self.assertEqual(actor, 'A')
                candidate = json.loads(req.content)['id']
                self.assertEqual(candidate, self.verifier.candidate)
                if self.fault == 'insert-success':
                    return httpx.Response(201, json=[])
                if self.fault == 'insert-fk':
                    return self.deny(409, '23503')
                if self.fault == 'insert-duplicate':
                    return self.deny(409, '23505')
                return self.deny()
            self.assertIn(target, self.ids.values())
            if req.method == 'DELETE':
                self.assertEqual(target, self.ids['A'])
                if self.fault == 'delete-success':
                    deleted = self.records.pop(target)
                    return httpx.Response(200, json=[deleted])
                return self.deny()
            self.assertEqual(req.method, 'PATCH')
            payload = json.loads(req.content)
            if (self.fault == 'restore-network' and actor == 'A'
                    and self.verifier.marker not in payload.values()
                    and set(payload) <= {'first_name', 'last_name'}):
                raise httpx.ConnectError('private-secret')
            if actor == 'anon':
                if self.fault == 'anon-success':
                    self.records[target].update(payload)
                    return httpx.Response(200, json=[self.records[target]])
                if self.fault == 'anon-unrelated':
                    return self.deny(401, 'invalid_jwt')
                return self.deny(401)
            if target != self.ids[actor]:
                if self.fault == 'cross-success':
                    self.records[target].update(payload)
                    return httpx.Response(200, text='invalid sensitive response')
                if self.fault == 'cross-network':
                    raise httpx.ConnectError('private-secret')
                return httpx.Response(200, json=[])
            if 'id' in payload or 'created_at' in payload:
                if self.fault == 'id-fk' and 'id' in payload:
                    return self.deny(409, '23503')
                if self.fault == 'timestamp-success' and 'created_at' in payload:
                    self.records[target].update(payload)
                    return httpx.Response(200, json=[self.records[target]])
                if self.fault == 'combined-name-only' and 'first_name' in payload:
                    self.records[target]['first_name'] = payload['first_name']
                    return self.deny()
                if self.fault == 'protected-success-no-change':
                    return httpx.Response(200, json=[self.records[target]])
                return self.deny()
            self.records[target].update(payload)
            is_test_change = self.verifier.marker in payload.values()
            if self.fault == 'lost-response' and is_test_change:
                raise httpx.ReadTimeout('private-secret')
            if self.fault == 'malformed-response' and is_test_change:
                return httpx.Response(200, text='private-secret')
            return httpx.Response(200, json=[self.records[target]])
        return handle

    def run_verifier(self):
        with contextlib.redirect_stdout(self.output):
            self.verifier.run()

    def test_complete_success_and_restoration(self):
        self.run_verifier()
        self.assertEqual(self.records, self.original)
        text = self.output.getvalue()
        self.assertIn('PASS: WRITE RLS verified', text)
        for secret in [*self.ids.values(), 'private-token', 'private-email', 'sb_publishable_test-secret']:
            self.assertNotIn(secret, text)

    def test_unrelated_failures_never_pass_and_names_restored(self):
        for fault in ('insert-fk', 'insert-duplicate', 'id-fk', 'cross-network',
                      'lost-response', 'malformed-response', 'anon-unrelated'):
            with self.subTest(fault=fault):
                self.fault = fault
                self.output = io.StringIO()
                with self.assertRaises(writes.TestFailure):
                    self.run_verifier()
                self.assertEqual(self.records, self.original)
                self.assertNotIn('PASS: WRITE RLS verified', self.output.getvalue())

    def test_forbidden_name_changes_restored_then_stop(self):
        for fault in ('cross-success', 'combined-name-only', 'anon-success'):
            with self.subTest(fault=fault):
                self.fault = fault
                self.output = io.StringIO()
                with self.assertRaises(writes.CriticalFailure):
                    self.run_verifier()
                self.assertEqual(self.records, self.original)
                self.assertNotIn('PASS: WRITE RLS verified', self.output.getvalue())

    def test_unexpected_protected_success_stops(self):
        for fault in ('protected-success-no-change', 'insert-success'):
            with self.subTest(fault=fault):
                self.fault = fault
                with self.assertRaises(writes.CriticalFailure):
                    self.run_verifier()
                self.assertFalse(any(method == 'DELETE' for _, method, _, _ in self.requests))

    def test_delete_success_stops_without_reconstruction(self):
        self.fault = 'delete-success'
        with self.assertRaises(writes.CriticalFailure):
            self.run_verifier()
        index = next(i for i, (_, method, _, _) in enumerate(self.requests) if method == 'DELETE')
        self.assertTrue(all(method == 'GET' for _, method, _, _ in self.requests[index + 1:]))
        self.assertNotIn(self.ids['A'], self.records)

    def test_timestamp_change_stops_without_further_writes(self):
        self.fault = 'timestamp-success'
        with self.assertRaises(writes.CriticalFailure):
            self.run_verifier()
        self.assertNotEqual(self.records[self.ids['A']]['created_at'], self.original[self.ids['A']]['created_at'])
        self.assertFalse(any(method == 'DELETE' for _, method, _, _ in self.requests))

    def test_scope_guard_blocks_other_records_and_operations(self):
        for method in ('PATCH', 'DELETE', 'POST', 'PUT'):
            with self.assertRaises(writes.TestFailure):
                self.verifier.send('A', self.verifier.candidate, method, {'first_name': 'blocked'})
        self.assertEqual(self.requests, [])

    def test_wrong_fixture_prevents_all_writes(self):
        self.records[self.ids['A']]['first_name'] = 'Not designated fixture'
        with self.assertRaises(writes.TestFailure):
            self.run_verifier()
        self.assertTrue(all(method == 'GET' for _, method, _, _ in self.requests))

    def test_failed_restoration_is_reported_and_later_tests_do_not_run(self):
        self.fault = 'restore-network'
        with self.assertRaises(writes.TestFailure):
            self.run_verifier()
        text = self.output.getvalue()
        self.assertIn('Original profile restoration not confirmed', text)
        self.assertNotIn('CHECK: D2', text)
        self.assertNotIn('PASS: WRITE RLS verified', text)

    def test_main_reports_critical_without_sensitive_output(self):
        self.fault = 'delete-success'
        with patch.object(writes.reads, 'configuration', return_value=('https://fixture.invalid', 'sb_publishable_test-secret')), patch.object(writes.reads, 'sign_in', side_effect=[self.ids['A'], self.ids['B']]), patch.object(writes.httpx, 'Client', side_effect=self.clients), patch.object(writes, 'WriteVerifier', return_value=self.verifier), contextlib.redirect_stdout(self.output):
            result = writes.main()
        self.assertEqual(result, 1)
        text = self.output.getvalue()
        self.assertIn('CRITICAL SECURITY FAILURE:', text)
        self.assertNotIn('PASS: WRITE RLS verified', text)
        for secret in [*self.ids.values(), 'private-token', 'private-email', 'sb_publishable_test-secret']:
            self.assertNotIn(secret, text)


if __name__ == '__main__':
    unittest.main()
