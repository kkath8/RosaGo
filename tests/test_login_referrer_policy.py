"""Browser-origin regression: all provider/network operations are mocked."""
import unittest
from test_public_layout import Document
import test_login

class LoginReferrerPolicyTests(unittest.TestCase):
    setUp=test_login.LoginTests.setUp

    def token(self,page):
        return Document(page.get_data(as_text=True)).find('input',name='csrf_token')[0].attrs['value']

    def test_non_token_auth_forms_preserve_same_origin_post_headers(self):
        for path in ('/login','/register','/forgot-password'):
            with self.subTest(path=path):
                page=self.client.get(path)
                self.assertEqual(page.status_code,200)
                self.assertEqual(page.headers['Referrer-Policy'],'same-origin')
                self.assertEqual(page.headers['Cache-Control'],'no-store')
                self.assertEqual(page.headers['X-Frame-Options'],'DENY')
        page=self.client.get('/login')
        self.assertTrue(self.token(page))
        self.assertIn(b'js/login.js',page.data)
        self.assertNotIn(b'js/auth.js',page.data)
        self.login_client.auth.sign_in_with_password.assert_not_called()

    def test_callback_privacy_and_existing_recovery_form_policy_are_preserved(self):
        for path in ('/auth/callback','/auth/reset-callback'):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).headers['Referrer-Policy'],'no-referrer')
        for path in ('/reset-password','/verify-email'):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).headers['Referrer-Policy'],'same-origin')
        self.login_client.auth.sign_in_with_password.assert_not_called()

    def test_null_missing_foreign_origin_still_denied_without_consuming_challenge(self):
        token=self.token(self.client.get('/login'))
        for headers in ({},{'Origin':'null'},{'Origin':'https://foreign.invalid'}):
            with self.subTest(headers=headers):
                response=self.client.post('/login',data={**self.credentials,'csrf_token':token},headers=headers)
                self.assertEqual(response.status_code,403)
                self.assertIn(b'Please reload this page and try again.',response.data)
                self.assertTrue(self.app.extensions['rosago_login_challenges'].valid('user',token))
        self.login_client.auth.sign_in_with_password.assert_not_called()
        response=self.client.post('/login',data={**self.credentials,'csrf_token':token},headers={'Origin':'http://localhost'})
        self.assertEqual(response.status_code,303)
        self.login_client.auth.sign_in_with_password.assert_called_once()

    def test_valid_origin_does_not_bypass_cookie_binding_or_single_use_csrf(self):
        token=self.token(self.client.get('/login'))
        old=self.client.get_cookie('session').value
        other=self.app.test_client()
        response=other.post('/login',data={**self.credentials,'csrf_token':token},headers={'Origin':'http://localhost'})
        self.assertEqual(response.status_code,403)
        self.login_client.auth.sign_in_with_password.assert_not_called()
        response=self.client.post('/login',data={**self.credentials,'csrf_token':token},headers={'Origin':'http://localhost'})
        self.assertEqual(response.status_code,303)
        self.assertFalse(self.app.extensions['rosago_login_challenges'].valid('user',token))
        self.client.set_cookie('session',old)
        response=self.client.post('/login',data={**self.credentials,'csrf_token':token},headers={'Origin':'http://localhost'})
        self.assertEqual(response.status_code,403)
        self.login_client.auth.sign_in_with_password.assert_called_once()
