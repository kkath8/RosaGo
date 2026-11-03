"""Registration field errors and strong password enforcement."""
import unittest

import test_registration as registration
from test_public_layout import Document


class RegistrationValidationTests(unittest.TestCase):
    setUp = registration.RegistrationTests.setUp

    def test_consent_only_error_is_local_and_not_duplicated(self):
        response = self.client.post('/register', data=self.valid | {'terms': ''})
        self.assertEqual(response.status_code, 400)
        page = Document(response.get_data(as_text=True))
        error = page.find('p', id='terms-error')[0]
        self.assertEqual(error.text, 'Please agree to the Terms and Privacy Policy.')
        self.assertNotIn('hidden', error.attrs)
        self.assertEqual(error.ancestors[-1].attrs['class'], 'terms-field')
        terms = page.find('input', id='terms')[0]
        self.assertEqual(terms.attrs['aria-describedby'], 'terms-error')
        self.assertEqual(terms.attrs['aria-invalid'], 'true')
        self.assertEqual(page.find('p', id='form-status')[0].text, '')
        self.assertEqual(response.data.count(b'Please agree to the Terms and Privacy Policy.'), 1)
        self.assertNotIn(b'Please correct the highlighted fields and try again.', response.data)
        self.supabase.auth.sign_up.assert_not_called()

    def test_multiple_errors_remain_field_specific_and_consent_clears_when_checked(self):
        for consent in ('', 'accepted'):
            response = self.client.post('/register', data=self.valid | {'email': 'bad', 'terms': consent})
            self.assertEqual(response.status_code, 400)
            page = Document(response.get_data(as_text=True))
            self.assertNotIn('hidden', page.find('p', id='email-error')[0].attrs)
            self.assertEqual('hidden' in page.find('p', id='terms-error')[0].attrs, consent == 'accepted')
            self.assertEqual(page.find('p', id='form-status')[0].text, '')
        self.supabase.auth.sign_up.assert_not_called()

    def test_short_blank_and_unicode_short_passwords_are_rejected_before_signup(self):
        for password in ('short', '        ', '🐱' * 4):
            with self.subTest(password_length=len(password)):
                response = self.client.post('/register', data=self.valid | {
                    'password': password, 'confirm_password': password})
                self.assertEqual(response.status_code, 400)
                error = Document(response.get_data(as_text=True)).find('p', id='password-error')[0]
                self.assertNotIn('hidden', error.attrs)
                self.assertTrue(error.text)
        self.supabase.auth.sign_up.assert_not_called()

    def test_missing_character_classes_are_rejected_before_signup(self):
        cases = [('abcdefgh', 'uppercase'), ('Abcdefgh', 'number'),
                 ('Abcdefg1', 'special character'), ('abcdefg1!', 'uppercase'),
                 ('ABCDEFG1!', 'lowercase'), ('Abcdef1 ', 'special character'),
                 ('Abcdef1\U0001f431', 'special character')]
        for password, requirement in cases:
            with self.subTest(requirement=requirement):
                response = self.client.post('/register', data=self.valid | {
                    'password': password, 'confirm_password': password})
                self.assertEqual(response.status_code, 400)
                error = Document(response.get_data(as_text=True)).find('p', id='password-error')[0]
                self.assertNotIn('hidden', error.attrs)
                self.assertIn(requirement, error.text)
        self.supabase.auth.sign_up.assert_not_called()

    def test_valid_strong_password_keeps_existing_otp_flow(self):
        password = 'Abcdef1!'
        response = self.client.post('/register', data=self.valid | {
            'password': password, 'confirm_password': password})
        self.assertEqual((response.status_code, response.location), (303, '/verify-email'))
        self.supabase.auth.sign_up.assert_called_once()
        self.assertEqual(self.supabase.auth.sign_up.call_args.args[0]['password'], password)
        with self.client.session_transaction() as session:
            self.assertEqual(set(session), {'pending_email_verification'})
        self.assertIn(b'Verification Code', self.client.get(response.location).data)

    def test_confirmation_mismatch_is_specific_and_never_creates_account(self):
        response = self.client.post('/register', data=self.valid | {'confirm_password': 'other-password'})
        self.assertEqual(response.status_code, 400)
        page = Document(response.get_data(as_text=True))
        self.assertEqual(page.find('p', id='confirm-password-error')[0].text, 'Passwords do not match.')
        self.assertEqual(page.find('p', id='form-status')[0].text, '')
        self.supabase.auth.sign_up.assert_not_called()

    def test_policy_is_visible_before_submission_and_associated_with_password(self):
        page = Document(self.client.get('/register').get_data(as_text=True))
        help_node = page.find('div', id='password-help')[0]
        self.assertIn('Password must contain:', help_node.text)
        items = [n for n in page.find('li') if help_node in n.ancestors]
        self.assertEqual([n.attrs['data-password-requirement'] for n in items], ['length', 'uppercase', 'lowercase', 'number', 'special'])
        self.assertTrue(all('hidden' not in n.attrs for n in items))
        self.assertIn('password-help', page.find('input', id='password')[0].attrs['aria-describedby'])
