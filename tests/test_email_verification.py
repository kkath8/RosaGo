"""Signup OTP checkpoint; provider calls and clocks are controlled, no email sent."""
from types import SimpleNamespace as NS
import logging
import time
import unittest
from unittest.mock import Mock

import httpx
from supabase_auth.errors import AuthApiError
from werkzeug.datastructures import MultiDict

from email_verification import PendingEmailStore, EmailVerificationService
from test_public_layout import Document
import test_registration

ORIGIN = {'Origin':'http://localhost'}


class EmailVerificationTests(unittest.TestCase):
    def setUp(self):
        test_registration.RegistrationTests.setUp(self)
        self.now = 100.0
        self.store = PendingEmailStore(clock=lambda:self.now)
        self.provider = Mock()
        self.provider.verify.return_value = True
        self.app.extensions['rosago_email_pending'] = self.store
        self.app.extensions['rosago_email_verification'] = self.provider

    def begin(self):
        response = test_registration.post_public_form(self, '/register', data=self.valid)
        self.assertEqual((response.status_code,response.location), (303,'/verify-email'))
        with self.client.session_transaction() as current:
            self.handle = current['pending_email_verification']
        self.csrf = self.store.get(self.handle).csrf
        return self.client.get(response.location)

    def verify(self, code='123456', **kwargs):
        return self.client.post('/verify-email', data={'csrf_token':self.csrf,'code':code}, headers=ORIGIN, **kwargs)

    def resend(self):
        return self.client.post('/verify-email/resend', data={'csrf_token':self.csrf}, headers=ORIGIN)

    def test_registration_consent_links_and_required_accessible_indicators(self):
        for path, count in [('/register',6),('/login',2),('/forgot-password',1)]:
            page = Document(self.client.get(path).get_data(as_text=True))
            marks = page.find('span', **{'class':'required-mark'})
            self.assertEqual(len(marks),count)
            self.assertTrue(all(m.attrs.get('aria-hidden') == 'true' for m in marks))
            self.assertEqual(len(page.find('span', **{'class':'auth-sr-only'})), count)
        page = Document(self.client.get('/register').get_data(as_text=True))
        self.assertTrue(page.find('a', href='/terms'))
        self.assertTrue(page.find('a', href='/privacy'))
        self.assertNotIn('checked',page.find('input',name='terms')[0].attrs)
        for value in ['', 'false']:
            self.assertEqual(test_registration.post_public_form(self, '/register',data=self.valid|{'terms':value}).status_code,400)
        duplicated = MultiDict(self.valid); duplicated.add('terms','accepted')
        self.assertEqual(test_registration.post_public_form(self, '/register',data=duplicated).status_code,400)
        self.supabase.auth.sign_up.assert_not_called()

    def test_real_terms_and_privacy_content(self):
        for path, texts in [('/terms',[b'Terms of Service',b'academic',b'AI-generated',b'Effective date']),
                            ('/privacy',[b'Privacy Policy',b'Supabase',b'Gemini',b'Open-Meteo',b'OSRM',b'Google Maps',b'Effective date'])]:
            response = self.client.get(path)
            self.assertEqual(response.status_code,200)
            for text in texts:
                self.assertIn(text,response.data)
            self.assertNotIn(b'Coming soon',response.data)

    def test_dedicated_page_cookie_secrecy_and_success_without_login(self):
        response = self.begin()
        page = Document(response.get_data(as_text=True))
        self.assertTrue(page.find('input',name='code',autocomplete='one-time-code'))
        self.assertEqual(page.find('input',type='password'),[])
        self.assertTrue(page.find('span', **{'class':'required-mark'}))
        self.assertIn(b'Resend code in 01:00',response.data)
        self.assertIn(b'does not indicate when your code expires',response.data)
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertEqual(response.headers['Referrer-Policy'],'same-origin')
        self.assertTrue(page.find('meta',name='referrer',content='same-origin'))
        with self.client.session_transaction() as current:
            self.assertEqual(set(current),{'pending_email_verification'})
            self.assertNotIn(self.valid['email'], str(dict(current)))
        verified = self.verify()
        self.assertEqual((verified.status_code,verified.location),(303,'/verify-email'))
        self.provider.verify.assert_called_once_with(self.valid['email'],'123456')
        success = self.client.get(verified.location)
        self.assertIn(b'Email verified',success.data)
        self.assertIn(b'Continue to Login',success.data)
        page = Document(success.get_data(as_text=True))
        self.assertEqual(page.find('form'),[])
        self.assertEqual(page.find('input'),[])
        self.assertEqual(self.client.get('/user').status_code,302)
        self.supabase.auth.verify_otp.assert_not_called()
        self.assertNotIn('123456', repr(self.store.get(self.handle)))

    def test_invalid_and_expired_codes_are_safe_and_not_repopulated(self):
        self.begin()
        for error in [AuthApiError('sensitive-code',403,'otp_expired'),
                      AuthApiError('sensitive-code',403,'otp_disabled')]:
            self.provider.verify.side_effect = error
            response = self.verify()
            self.assertEqual(response.status_code,400)
            self.assertIn(b'invalid or expired',response.data)
            self.assertNotIn(b'sensitive-code',response.data)
            self.assertNotIn(b'123456',response.data)
            self.assertFalse(self.store.get(self.handle).verified)
            self.now += 6
        self.provider.verify.side_effect = None
        self.provider.verify.return_value = False
        self.assertEqual(self.verify().status_code,400)

    def test_verify_throttle_and_numeric_validation(self):
        self.begin()
        for code in ['', 'abcdef', '12345', 'x'*100]:
            self.assertEqual(self.verify(code).status_code,400)
        self.provider.verify.assert_not_called()
        self.provider.verify.return_value = False
        self.assertEqual(self.verify().status_code,400)
        self.assertEqual(self.verify().status_code,429)
        self.assertEqual(self.provider.verify.call_count,1)

    def test_resend_cooldown_success_reset_and_no_arbitrary_email(self):
        self.begin()
        response = self.resend()
        self.assertEqual(response.status_code,429)
        self.assertEqual(response.headers['Retry-After'],'60')
        self.provider.resend.assert_not_called()
        self.now += 61
        response = self.resend()
        self.assertEqual((response.status_code,response.location),(303,'/verify-email'))
        self.provider.resend.assert_called_once_with(self.valid['email'])
        self.assertIn(b'Resend code in 01:00',self.client.get(response.location).data)
        self.assertEqual(self.resend().status_code,429)
        forged = self.client.post('/verify-email/resend',headers=ORIGIN,
            data={'csrf_token':self.csrf,'email':'unrelated@example.invalid'})
        self.assertEqual(forged.status_code,400)
        self.assertEqual(self.provider.resend.call_count,1)

    def test_resend_provider_errors_and_rate_limits_are_truthful(self):
        self.begin()
        for error,status in [(AuthApiError('private-provider',429,'over_email_send_rate_limit'),429),
                             (AuthApiError('private-provider',400,'email_not_found'),400),
                             (RuntimeError('private-provider'),503)]:
            self.now += 61
            self.provider.resend.side_effect = error
            response = self.resend()
            self.assertEqual(response.status_code,status)
            self.assertNotIn(b'private-provider',response.data)
            self.assertNotIn(b'email_not_found',response.data)
            self.assertNotIn(b'Account exists',response.data)
            self.assertEqual(self.resend().status_code,429)
        self.assertFalse(self.store.get(self.handle).verified)

    def test_verify_rate_limit_enforces_provider_backoff(self):
        self.begin()
        self.provider.verify.side_effect = AuthApiError('private-provider',429,'over_request_rate_limit')
        self.assertEqual(self.verify().status_code,429)
        self.now += 6
        self.assertEqual(self.verify().status_code,429)
        self.assertEqual(self.provider.verify.call_count,1)

    def test_verify_resend_csrf_origin_and_strict_forms(self):
        self.begin()
        for path in ['/verify-email','/verify-email/resend']:
            valid = {'csrf_token':self.csrf} | ({'code':'123456'} if path=='/verify-email' else {})
            for token in ['', 'wrong', '\u2603']:
                response = self.client.post(path,headers=ORIGIN,data=valid|{'csrf_token':token})
                self.assertEqual(response.status_code,403)
            for headers in [{},{'Origin':'https://foreign.invalid'},{'Origin':'null'}]:
                self.assertEqual(self.client.post(path,headers=headers,data=valid).status_code,403)
            data = MultiDict(valid); data.add('csrf_token',self.csrf)
            self.assertEqual(self.client.post(path,headers=ORIGIN,data=data).status_code,403)
            self.assertEqual(self.client.post(path,headers=ORIGIN,data=valid|{'unexpected':'x'}).status_code,400)
            self.assertEqual(self.client.post(path,headers=ORIGIN,data=valid|{'extra':'x'*5000}).status_code,413)
        self.provider.verify.assert_not_called(); self.provider.resend.assert_not_called()

    def test_missing_expired_and_server_restart_pending_flows_do_not_assert_success(self):
        self.assertNotIn(b'successfully verified',self.client.get('/verify-email').data)
        self.begin()
        self.now += 1801
        self.assertEqual(self.verify().status_code,400)
        self.assertNotIn(b'successfully verified',self.client.get('/verify-email').data)
        self.provider.verify.assert_not_called()

    def test_verification_preserves_separate_recovery_grant(self):
        self.begin()
        globals_ = self.app.view_functions['reset_password'].__globals__
        grants = globals_['recovery_grants']
        recovery_handle = grants.issue('recovered','recovery-session',time.time()+600,'private-access')
        with self.client.session_transaction() as current:
            current['password_recovery_id'] = recovery_handle
        self.assertEqual(self.verify().status_code,303)
        self.assertTrue(grants.valid(recovery_handle))
        with self.client.session_transaction() as current:
            self.assertEqual(current['password_recovery_id'],recovery_handle)
            self.assertNotIn('auth_session_id',current)

    def test_accidental_query_code_is_redacted_from_access_logs(self):
        for path in ['/verify-email','/verify-email/resend']:
            record = logging.LogRecord('werkzeug',logging.INFO,'',0,'"%s" %s %s',
                ('GET '+path+'?code=private-code HTTP/1.1',200,'-'),None)
            logging.getLogger('werkzeug').filter(record)
            self.assertNotIn('private-code',record.getMessage())
            self.assertIn('?[redacted]',record.getMessage())


class PendingEmailStoreTests(unittest.TestCase):
    def test_atomic_reservations_bounds_expiry_and_cross_flow_resend(self):
        now=[0]
        store=PendingEmailStore(clock=lambda:now[0],limit=2)
        first=store.create('test@example.invalid')
        second=store.create('TEST@example.invalid')
        self.assertIsNone(store.create('other@example.invalid'))
        now[0]=61
        record,wait=store.reserve(first,'resend')
        self.assertIsNotNone(record)
        self.assertIsNone(store.reserve(first,'verify')[0])
        self.assertIsNone(store.reserve(second,'resend')[0])
        store.finish(first,resent=True)
        self.assertEqual(store.seconds(store.get(first)),60)
        now[0]=1801
        self.assertIsNone(store.get(first))
        self.assertIsNotNone(store.create('other@example.invalid'))


class EmailProviderTests(unittest.TestCase):
    def test_sdk_verification_and_resend_are_isolated_and_do_not_retain_tokens(self):
        clients=[]
        def http_factory(**options):
            self.assertEqual(options,{'timeout':20,'follow_redirects':False,'trust_env':False})
            http=httpx.Client(transport=httpx.MockTransport(lambda _:self.fail('Network forbidden')))
            clients.append(http)
            return http
        sdk=Mock()
        sdk.auth.verify_otp.return_value=NS(user=NS(email='test@example.invalid',email_confirmed_at='confirmed'),
            session=NS(access_token='private-access',refresh_token='private-refresh'))
        factory=Mock(return_value=sdk)
        service=EmailVerificationService('https://example.supabase.co','sb_publishable_fixture',
            sdk_factory=factory,http_factory=http_factory)
        self.assertTrue(service.verify('test@example.invalid','12345678'))
        sdk.auth.verify_otp.assert_called_once_with({'email':'test@example.invalid','token':'12345678','type':'email'})
        service.resend('test@example.invalid')
        sdk.auth.resend.assert_called_once_with({'type':'signup','email':'test@example.invalid'})
        self.assertEqual(factory.call_count,2)
        for call in factory.call_args_list:
            options=call.kwargs['options']
            self.assertFalse(options.persist_session)
            self.assertFalse(options.auto_refresh_token)
        self.assertTrue(all(c.is_closed for c in clients))
        sdk.auth.sign_in_with_password.assert_not_called()
        sdk.auth.set_session.assert_not_called()

    def test_wrong_email_or_unconfirmed_provider_result_cannot_claim_success(self):
        sdk=Mock()
        service=EmailVerificationService('https://example.supabase.co','sb_publishable_fixture',
            sdk_factory=Mock(return_value=sdk),http_factory=lambda **_:httpx.Client(transport=httpx.MockTransport(lambda _:None)))
        for user in [None,NS(email='other@example.invalid',email_confirmed_at='confirmed'),
                     NS(email='test@example.invalid',email_confirmed_at=None)]:
            sdk.auth.verify_otp.return_value=NS(user=user)
            self.assertFalse(service.verify('test@example.invalid','123456'))
