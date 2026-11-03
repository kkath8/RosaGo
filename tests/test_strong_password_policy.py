"""Creation/reset policy parity without provider requests or real accounts."""
import json
import string
import hashlib
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
import unittest

from password_policy import PASSWORD_RULES, password_error
import test_password_reset as reset
from test_public_layout import Document


class PasswordPolicyTests(unittest.TestCase):
    def test_required_examples_and_ascii_special_character_definition(self):
        for password in ('abcdefgh', 'Abcdefgh', 'Abcdefg1', 'abcdefg1!', 'ABCDEFG1!',
                         'Ab1!', 'Abcdef1 ', 'Abcdef1🐱'):
            with self.subTest(password=password):
                self.assertTrue(password_error(password))
        for character in string.punctuation:
            self.assertEqual(password_error('Abcdef1' + character), '')
        self.assertEqual(password_error('Abcdef1!'), '')
        self.assertEqual(password_error('🐱Abcde1!'), '')


class StrongResetTests(unittest.TestCase):
    setUp = reset.PasswordResetTests.setUp
    submit = reset.PasswordResetTests.submit

    def test_each_failed_requirement_is_local_and_does_not_consume_grant(self):
        cases = [('abcdefgh', 'uppercase'), ('Abcdefgh', 'number'), ('Abcdefg1', 'special character'),
                 ('abcdefg1!', 'uppercase'), ('ABCDEFG1!', 'lowercase'), ('Ab1!', '8 characters'),
                 ('Abcdef1 ', 'special character'), ('Abcdef1🐱', 'special character')]
        for password, requirement in cases:
            with self.subTest(requirement=requirement):
                response = self.submit(new_password=password, confirm_password=password)
                self.assertEqual(response.status_code, 400)
                page = Document(response.get_data(as_text=True))
                error = page.find('p', id='new-password-error')[0]
                self.assertNotIn('hidden', error.attrs)
                self.assertIn(requirement, error.text)
                self.assertEqual(page.find('p', id='reset-status')[0].text, '')
                self.assertTrue(self.store.valid(self.handle))
                self.assertEqual(self.store.csrf(self.handle), self.csrf)
        self.factory.assert_not_called()
        self.assertEqual(self.submit(new_password='Abcdef1!', confirm_password='Abcdef1!').status_code, 303)
        self.isolated.auth.update_user.assert_called_once_with({'password': 'Abcdef1!'})
        self.assertFalse(self.store.valid(self.handle))
        self.assertEqual(self.submit().status_code, 403)
        self.isolated.auth.update_user.assert_called_once()

    def test_confirmation_mismatch_never_creates_provider_client(self):
        response = self.submit(new_password='Abcdef1!', confirm_password='Abcdef2!')
        self.assertEqual(response.status_code, 400)
        error = Document(response.get_data(as_text=True)).find('p', id='confirm-new-password-error')[0]
        self.assertEqual(error.text, 'Passwords do not match.')
        self.assertNotIn('hidden', error.attrs)
        self.factory.assert_not_called()
        self.assertTrue(self.store.valid(self.handle))

    def test_registration_and_reset_render_identical_server_policy_and_script_order(self):
        for path, controller in (('/register', 'auth.js'), ('/reset-password', 'reset-password.js')):
            page = Document(self.client.get(path).get_data(as_text=True))
            help_node = page.find('div', id='password-help')[0]
            self.assertEqual(json.loads(help_node.attrs['data-password-rules']), list(PASSWORD_RULES))
            items = [n for n in page.find('li') if help_node in n.ancestors]
            self.assertEqual(len(items), 5)
            self.assertTrue(all('Not met' in item.text for item in items))
            scripts = [urlsplit(n.attrs['src']).path for n in page.find('script')]
            self.assertLess(scripts.index('/static/js/password-policy.js'), scripts.index('/static/js/' + controller))

    def test_actual_auth_pages_have_visible_initial_policy_and_current_assets(self):
        root = Path(__file__).resolve().parents[1]
        for path in ('/register', '/reset-password'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            text = response.get_data(as_text=True)
            self.assertNotIn('Use at least 8 characters.', text)
            self.assertEqual(text.count('Password must contain:'), 1)
            page = Document(text)
            for rule in PASSWORD_RULES:
                item = page.find('li', id='password-rule-' + rule['key'])[0]
                self.assertNotIn('hidden', item.attrs)
                self.assertIn(rule['label'], item.text)
                state = page.find('span', id='password-rule-' + rule['key'] + '-state')[0]
                self.assertEqual(state.text, 'Not met')
            assets = [n.attrs['src'] for n in page.find('script')]
            assets += [n.attrs['href'] for n in page.find('link', rel='stylesheet')]
            for url in assets:
                parts = urlsplit(url)
                if parts.netloc:
                    self.assertEqual(parts.netloc, 'fonts.googleapis.com')
                    self.assertEqual(parts.path, '/css2')
                    continue
                self.assertEqual(parts.path[:8], '/static/')
                if parts.path in ('/static/js/theme.js','/static/css/theme.css'):
                    self.assertEqual(self.client.get(url).status_code,200)
                    continue
                expected = hashlib.sha256((root / parts.path.lstrip('/')).read_bytes()).hexdigest()[:12]
                self.assertEqual(parse_qs(parts.query), {'v': [expected]})
                self.assertEqual(self.client.get(url).status_code, 200)
