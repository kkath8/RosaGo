import logging
import unittest

import test_registration


class CallbackTests(unittest.TestCase):
    setUp = test_registration.RegistrationTests.setUp

    def test_completion_page_needs_no_credentials(self):
        for suffix in ("", "?code=private-code", "?access_token=private-token"):
            response = self.client.get("/auth/callback" + suffix)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Email verified successfully", response.data)
            self.assertIn(b"Your RosaGO account has been verified. You can now continue to login.", response.data)
            self.assertIn(b"Continue to Login", response.data)
            self.assertIn(b"Login is not available yet.", response.data)
            self.assertNotIn(b"private-", response.data)
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
            self.assertFalse(response.headers.getlist("Set-Cookie"))
        self.assertEqual(self.supabase.mock_calls, [])

    def test_callback_no_longer_accepts_token_posts(self):
        response = self.client.post("/auth/callback", json={"access_token": "private-token"})
        self.assertEqual(response.status_code, 405)
        self.assertEqual(self.supabase.mock_calls, [])

    def test_callback_access_log_redacts_query(self):
        record = logging.LogRecord("werkzeug", logging.INFO, "", 0, '"%s" %s %s',
                                   ("GET /auth/callback?code=private-code&access_token=private-token HTTP/1.1", 200, "-"), None)
        logging.getLogger("werkzeug").filter(record)
        self.assertNotIn("private-", record.getMessage())
        self.assertIn("/auth/callback?[redacted]", record.getMessage())


if __name__ == "__main__":
    unittest.main()
