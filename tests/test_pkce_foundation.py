"""Offline PKCE foundation tests. All HTTP uses httpx.MockTransport."""
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, fields
from threading import Barrier
from unittest.mock import Mock, patch

import httpx

from recovery_helpers import (
    PendingRecoveries, RECOVERY_SECONDS, generate_pkce_verifier,
    pkce_s256_challenge,
)
from recovery_transport import RecoveryTransportError, send_pkce_recovery


# Public RFC 7636 Appendix B example, not real recovery credentials.
EXAMPLE_VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
EXAMPLE_CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


class PKCEValuesTests(unittest.TestCase):
    def test_verifier_uses_cryptographic_randomness(self):
        with patch("recovery_helpers.secrets.token_urlsafe", return_value=EXAMPLE_VERIFIER) as random:
            self.assertEqual(generate_pkce_verifier(), EXAMPLE_VERIFIER)
        random.assert_called_once_with(32)

    def test_generated_values_are_unique_url_safe_and_unpadded(self):
        values = {generate_pkce_verifier() for _ in range(32)}
        self.assertEqual(len(values), 32)
        for verifier in values:
            self.assertRegex(verifier, r"^[A-Za-z0-9_-]{43}$")
            challenge = pkce_s256_challenge(verifier)
            self.assertRegex(challenge, r"^[A-Za-z0-9_-]{43}$")
            self.assertNotIn("=", verifier + challenge)

    def test_s256_matches_rfc7636_vector(self):
        self.assertEqual(pkce_s256_challenge(EXAMPLE_VERIFIER), EXAMPLE_CHALLENGE)

    def test_invalid_verifiers_are_rejected_without_echoing_them(self):
        for verifier in (None, "", "x" * 42, "x" * 129, "!" * 43, "é" * 43):
            with self.assertRaisesRegex(ValueError, "^Invalid PKCE verifier format.$"):
                pkce_s256_challenge(verifier)


class PendingRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.clock = Mock(return_value=100.0)
        self.store = PendingRecoveries(clock=self.clock)

    def test_creation_lookup_and_minimal_immutable_record(self):
        handle = self.store.create()
        record = self.store.lookup(handle)
        self.assertRegex(handle, r"^[A-Za-z0-9_-]{43}$")
        self.assertNotEqual(handle, record.verifier)
        self.assertEqual(record.created_at, 100.0)
        self.assertEqual(record.expires_at, 100.0 + RECOVERY_SECONDS)
        self.assertEqual({field.name for field in fields(record)}, {"verifier", "created_at", "expires_at"})
        self.assertNotIn(record.verifier, repr(record))
        with self.assertRaises(FrozenInstanceError):
            record.verifier = "changed"
        self.assertIs(self.store.lookup(handle), record)

    def test_separate_requests_have_independent_ids_and_verifiers(self):
        first, second = self.store.create(), self.store.create()
        self.assertNotEqual(first, second)
        self.assertNotEqual(self.store.lookup(first).verifier, self.store.lookup(second).verifier)
        self.store.consume(first)
        self.assertIsNotNone(self.store.lookup(second))

    def test_expiration_boundary_and_consumption(self):
        handle = self.store.create()
        self.clock.return_value = 100.0 + RECOVERY_SECONDS - 0.001
        self.assertIsNotNone(self.store.lookup(handle))
        self.clock.return_value = 100.0 + RECOVERY_SECONDS
        self.assertIsNone(self.store.consume(handle))
        self.assertIsNone(self.store.lookup(handle))

    def test_lookup_rejects_expired_record(self):
        handle = self.store.create()
        self.clock.return_value += RECOVERY_SECONDS
        self.assertIsNone(self.store.lookup(handle))

    def test_consumption_and_replay_rejection(self):
        handle = self.store.create()
        record = self.store.lookup(handle)
        self.assertIs(self.store.consume(handle), record)
        self.assertIsNone(self.store.lookup(handle))
        self.assertIsNone(self.store.consume(handle))

    def test_concurrent_consumers_have_exactly_one_winner(self):
        handle = self.store.create()
        barrier = Barrier(8)

        def consume(_):
            barrier.wait()
            return self.store.consume(handle)

        with ThreadPoolExecutor(max_workers=8) as pool:
            records = list(pool.map(consume, range(8)))
        self.assertEqual(sum(record is not None for record in records), 1)

    def test_unknown_invalid_and_restarted_handles_are_rejected(self):
        for handle in (None, [], {}, "missing"):
            self.assertIsNone(self.store.lookup(handle))
            self.assertIsNone(self.store.consume(handle))
        handle = self.store.create()
        self.assertIsNone(PendingRecoveries(clock=self.clock).lookup(handle))

    def test_reservation_release_retry_and_finalization(self):
        handle = self.store.create()
        lease, record = self.store.reserve(handle)
        self.assertIsNotNone(self.store.lookup(handle))
        self.assertIsNone(self.store.reserve(handle))
        self.assertIsNone(self.store.finalize(handle, "wrong-lease"))
        self.store.release(handle, "wrong-lease")
        self.assertIsNone(self.store.reserve(handle))
        self.store.release(handle, lease)
        new_lease, _ = self.store.reserve(handle)
        self.assertNotEqual(lease, new_lease)
        self.assertIsNone(self.store.finalize(handle, lease))
        self.assertIs(self.store.finalize(handle, new_lease), record)
        self.assertIsNone(self.store.lookup(handle))
        self.assertIsNone(self.store.reserve(handle))
        self.assertIsNone(self.store.finalize(handle, new_lease))

    def test_reserved_record_expiry_or_invalidation_prevents_finalization(self):
        handle = self.store.create()
        lease, _ = self.store.reserve(handle)
        self.clock.return_value += RECOVERY_SECONDS
        self.assertIsNone(self.store.finalize(handle, lease))
        handle = self.store.create()
        lease, _ = self.store.reserve(handle)
        self.store.consume(handle)
        self.assertIsNone(self.store.finalize(handle, lease))

    def test_concurrent_reservations_have_exactly_one_winner(self):
        handle = self.store.create()
        barrier = Barrier(8)

        def reserve(_):
            barrier.wait()
            return self.store.reserve(handle)

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(reserve, range(8)))
        self.assertEqual(sum(result is not None for result in results), 1)


class RecoveryTransportTests(unittest.TestCase):
    def send(self, handler, **overrides):
        params = dict(
            email="test@example.com", code_challenge=EXAMPLE_CHALLENGE,
            supabase_url="https://example.supabase.co/", supabase_key="test-placeholder",
        )
        params.update(overrides)
        # MockTransport handles every request locally; no network sockets exist.
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            return send_pkce_recovery(**params, client=client)

    def test_request_structure_fixed_redirect_and_no_verifier(self):
        requests = []

        def handler(request):
            requests.append(request)
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.url.host, "example.supabase.co")
            self.assertEqual(request.url.path, "/auth/v1/recover")
            self.assertEqual(dict(request.url.params), {
                "redirect_to": "http://127.0.0.1:5000/auth/reset-callback",
            })
            self.assertEqual(json.loads(request.content), {
                "email": "test@example.com",
                "code_challenge": EXAMPLE_CHALLENGE,
                "code_challenge_method": "S256",
            })
            self.assertEqual(request.headers["apikey"], "test-placeholder")
            self.assertNotIn(EXAMPLE_VERIFIER.encode(), request.content)
            self.assertNotIn("test-placeholder", str(request.url))
            self.assertEqual(request.extensions["timeout"]["read"], 10.0)
            return httpx.Response(200, json={"internal": "not-returned"})

        self.assertIsNone(self.send(handler))
        self.assertEqual(len(requests), 1)

    def test_provider_errors_are_safe_and_not_retried(self):
        for status in (400, 401, 429, 500):
            handler = Mock(return_value=httpx.Response(status, text="private-provider-detail"))
            with self.assertRaisesRegex(RecoveryTransportError, "^Password recovery request was not accepted.$"):
                self.send(handler)
            handler.assert_called_once()

    def test_network_errors_are_safe(self):
        def handler(request):
            raise httpx.ConnectError("private-provider-detail", request=request)

        with self.assertRaisesRegex(RecoveryTransportError, "^Password recovery request could not be completed.$") as raised:
            self.send(handler)
        self.assertTrue(raised.exception.__suppress_context__)

    def test_redirects_are_not_followed(self):
        handler = Mock(return_value=httpx.Response(307, headers={"Location": "https://untrusted.example"}))
        with self.assertRaises(RecoveryTransportError):
            self.send(handler)
        handler.assert_called_once()

    def test_http_diagnostics_are_fixed_labels_without_sensitive_data(self):
        cases = [(status, "RECOVERY_TRANSPORT_HTTP_" + str(status))
                 for status in (400, 401, 403, 404, 409, 422, 429)]
        cases += [(status, "RECOVERY_TRANSPORT_HTTP_5XX") for status in (500, 503, 599)]
        cases += [(status, "RECOVERY_TRANSPORT_HTTP_OTHER") for status in (302, 418)]
        for status, category in cases:
            with self.subTest(status=status):
                handler = Mock(return_value=httpx.Response(
                    status, text="private-response-body",
                    headers={"X-Private": "private-response-header"},
                ))
                with self.assertLogs("rosago.recovery", level="WARNING") as captured:
                    with self.assertRaises(RecoveryTransportError):
                        self.send(handler)
                self.assertEqual([record.getMessage() for record in captured.records],
                                 ["[RosaGO recovery] " + category])
                self.assertIsNone(captured.records[0].exc_info)
                handler.assert_called_once()

    def test_timeout_and_network_diagnostics_are_distinct_and_safe(self):
        cases = [(error, "RECOVERY_TRANSPORT_TIMEOUT") for error in (
            httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout)]
        cases += [(error, "RECOVERY_TRANSPORT_NETWORK_ERROR") for error in (
            httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError)]
        for error, category in cases:
            with self.subTest(error=error.__name__):
                def handler(request):
                    raise error("private-exception-message", request=request)

                with self.assertLogs("rosago.recovery", level="WARNING") as captured:
                    with self.assertRaises(RecoveryTransportError) as raised:
                        self.send(handler)
                self.assertEqual([record.getMessage() for record in captured.records],
                                 ["[RosaGO recovery] " + category])
                self.assertIsNone(captured.records[0].exc_info)
                self.assertEqual(str(raised.exception), "Password recovery request could not be completed.")

    def test_success_does_not_log_failure_and_diagnostics_can_be_disabled(self):
        with self.assertNoLogs("rosago.recovery", level="WARNING"):
            self.send(lambda request: httpx.Response(200))
        with patch("recovery_diagnostics.ENABLED", False):
            with self.assertNoLogs("rosago.recovery", level="WARNING"):
                with self.assertRaises(RecoveryTransportError):
                    self.send(lambda request: httpx.Response(429))

    def test_invalid_inputs_never_send(self):
        for changes in (
            {"code_challenge": ""}, {"code_challenge": EXAMPLE_CHALLENGE + "="},
            {"email": "invalid"}, {"supabase_key": ""},
            {"supabase_url": "http://example.supabase.co"},
            {"supabase_url": "https://user:secret@example.supabase.co"},
            {"supabase_url": "https://example.supabase.co/?key=private"},
        ):
            handler = Mock()
            with self.assertRaises(ValueError):
                self.send(handler, **changes)
            handler.assert_not_called()


if __name__ == "__main__":
    unittest.main()
