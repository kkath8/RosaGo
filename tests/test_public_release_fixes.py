"""Focused public-form admission/configuration checks. All providers are mocked."""
import os
import runpy
import unittest
from pathlib import Path
from unittest.mock import patch
from supabase_auth.errors import AuthApiError
import test_registration
from public_auth_security import configured_public_origin


class PublicConfigurationTests(unittest.TestCase):
    def test_canonical_origin_is_configuration_only_and_strict(self):
        self.assertEqual(configured_public_origin({}), 'http://127.0.0.1:5000')
        self.assertEqual(configured_public_origin({'ROSAGO_PUBLIC_ORIGIN':'http://127.0.0.1:5055/'}),'http://127.0.0.1:5055')
        self.assertEqual(configured_public_origin({'ROSAGO_AUTH_MODE':'production','ROSAGO_PUBLIC_ORIGIN':'https://rosago.example/'}),'https://rosago.example')
        for value in ('http://public.example','https://u:p@public.example','https://public.example/path','https://public.example?token=x',' https://public.example','https://public.example\n'):
            with self.subTest(value=value),self.assertRaises(ValueError):
                configured_public_origin({'ROSAGO_AUTH_MODE':'production','ROSAGO_PUBLIC_ORIGIN':value})
        with self.assertRaises(ValueError): configured_public_origin({'ROSAGO_AUTH_MODE':'production'})

    def test_public_entrypoint_rejects_memory_and_experimental_modes_before_import(self):
        for mode in ('development','redis-local',''):
            with patch.dict(os.environ,ROSAGO_AUTH_MODE=mode),self.assertRaises(RuntimeError):
                runpy.run_path(str(Path(__file__).resolve().parents[1]/'production_wsgi.py'))
            with self.assertRaises(ValueError):
                configured_public_origin({'RENDER':'true','ROSAGO_AUTH_MODE':mode,
                                          'ROSAGO_PUBLIC_ORIGIN':'https://rosago.example'})


class PublicEmailAdmissionTests(unittest.TestCase):
    setUp=test_registration.RegistrationTests.setUp

    def test_missing_foreign_null_origin_and_cross_site_fetch_are_denied_before_provider(self):
        for path,data in (('/register',self.valid),('/forgot-password',{'email':'ana@example.com'})):
            for headers in ({},{'Origin':'null'},{'Origin':'https://foreign.invalid'},{'Origin':'http://localhost','Sec-Fetch-Site':'cross-site'}):
                with self.subTest(path=path,headers=headers):
                    response=self.client.open(path,method='POST',data=data,headers=headers)
                    self.assertEqual(response.status_code,403)
        self.supabase.auth.sign_up.assert_not_called()

    def test_public_registration_link_ignores_request_host(self):
        namespace=self.app.view_functions['register'].__globals__
        namespace['PUBLIC_ORIGIN']='https://rosago.example'
        response=self.client.post('/register',base_url='http://untrusted.example',data=self.valid,headers={'Origin':'http://untrusted.example'})
        self.assertEqual(response.status_code,303)
        self.assertEqual(self.supabase.auth.sign_up.call_args.args[0]['options']['email_redirect_to'],'https://rosago.example/auth/callback')

    def test_registration_existing_account_matches_accepted_navigation(self):
        accepted=test_registration.post_public_form(self,'/register',data=self.valid)
        for code in ('user_already_exists','email_exists'):
            self.supabase.auth.sign_up.side_effect=AuthApiError('private-provider-detail',422,code)
            response=test_registration.post_public_form(self,'/register',data=self.valid)
            self.assertEqual((response.status_code,response.location),(accepted.status_code,accepted.location))
            self.assertNotIn(b'already exists',response.data)

    def test_email_throttle_and_browser_headers_and_readiness_remain_closed(self):
        for unused in range(20):
            self.assertEqual(test_registration.post_public_form(self,'/register',data=self.valid).status_code,303)
        response=test_registration.post_public_form(self,'/register',data=self.valid)
        self.assertEqual(response.status_code,429)
        self.assertEqual(self.supabase.auth.sign_up.call_count,20)
        self.assertEqual(response.headers['Retry-After'],'60')
        response=self.client.get('/forgot-password')
        self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')
        self.assertEqual(response.headers['X-Frame-Options'],'DENY')
        self.assertEqual(self.client.get('/health/ready').status_code,503)

