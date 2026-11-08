"""Evaluation-only configuration/transport gates; no hosted service is contacted."""
import base64
import hashlib
import json
import os
import runpy
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from flask import Flask, request, session
from evaluation_config import (validate_evaluation_environment, configure_evaluation_http,
                               validate_evaluation_backend)
from normal_auth_coordinator import _normal_claims

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = 'jfaufpfzfhysqkhcdsrs'


def settings():
    return {
        'ROSAGO_EVALUATION':'true', 'ROSAGO_AUTH_MODE':'production',
        'ROSAGO_EVALUATION_PROJECT_REF':REFERENCE,
        'SUPABASE_URL':'https://' + REFERENCE + '.supabase.co',
        'SUPABASE_KEY':'sb_publishable_synthetic_evaluation_only',
        'ROSAGO_PUBLIC_ORIGIN':'https://evaluation.example',
        'ROSAGO_EVALUATION_EMAIL_MODE':'disabled',
        'ROUTING_PROVIDER':'disabled',
        'FLASK_SECRET_KEY':'synthetic-evaluation-secret-with-more-than-32-characters',
        'ROSAGO_EVALUATION_PROXY_HOPS':'1', 'ROSAGO_PROXY_HEADERS_SANITIZED':'true',
    }


class EvaluationKeyFixture:
    def setUp(self):
        pin = hashlib.sha256(settings()['SUPABASE_KEY'].encode()).hexdigest()
        patched = patch('evaluation_config.EVALUATION_PUBLIC_KEY_SHA256', frozenset({pin}))
        patched.start()
        self.addCleanup(patched.stop)


class EvaluationIsolationTests(EvaluationKeyFixture, unittest.TestCase):
    def test_distinct_project_profile_returns_no_key_material(self):
        result=validate_evaluation_environment(settings())
        self.assertEqual(result['project_ref'],REFERENCE)
        self.assertNotIn('SUPABASE_KEY',result)
        self.assertEqual(result['paid_ai'],'disabled')

    def test_real_project_and_url_mismatch_are_denied(self):
        for change in (
            {'ROSAGO_EVALUATION_PROJECT_REF':'brnkigrrqdrywahvcbvc',
             'SUPABASE_URL':'https://brnkigrrqdrywahvcbvc.supabase.co'},
            {'SUPABASE_URL':'https://brnkigrrqdrywahvcbvc.supabase.co'},
            {'SUPABASE_URL':'https://'+REFERENCE+'.supabase.co.evil.example'},
            {'SUPABASE_URL':'https://'+REFERENCE+'.supabase.co/rest/v1'},
            {'ROSAGO_EVALUATION_PROJECT_REF':'missing'},
            {'ROSAGO_EVALUATION_PROJECT_REF':'eeeeeeeeeeeeeeeeeeee',
             'SUPABASE_URL':'https://eeeeeeeeeeeeeeeeeeee.supabase.co'},
        ):
            with self.subTest(change=change),self.assertRaises(ValueError):
                validate_evaluation_environment(settings()|change)

    def test_privileged_keys_inherited_secrets_and_paid_integrations_are_denied(self):
        for change in (
            {'SUPABASE_KEY':'sb_secret_fake_secret_marker'},
            {'SUPABASE_SERVICE_ROLE_KEY':'private-marker'},
            {'SUPABASE_STORAGE_SECRET_KEY':'private-marker'},
            {'SUPABASE_JWT_SECRET':'private-marker'},
            {'GEMINI_API_KEY':'private-marker'}, {'ORS_API_KEY':'private-marker'},
            {'DATABASE_URL':'private-marker'}, {'SUPABASE_STORAGE_URL':'private-marker'},
            {'OSRM_BASE_URL':'https://brnkigrrqdrywahvcbvc.supabase.co'},
        ):
            with self.subTest(fields=tuple(change)):
                with self.assertRaises(ValueError) as caught:
                    validate_evaluation_environment(settings()|change)
                self.assertNotIn('private-marker',str(caught.exception))
                self.assertNotIn('fake_secret_marker',str(caught.exception))

    def test_legacy_keys_are_not_enabled_pinned_modern_keys(self):
        for ref in (REFERENCE, 'brnkigrrqdrywahvcbvc'):
            payload=base64.urlsafe_b64encode(json.dumps({'role':'anon','ref':ref}).encode()).decode().rstrip('=')
            candidate=settings()|{'SUPABASE_KEY':'header.'+payload+'.signature'}
            with self.assertRaises(ValueError):validate_evaluation_environment(candidate)

    def test_unknown_modern_key_storage_and_external_routes_are_denied(self):
        for change in ({'SUPABASE_KEY':'sb_publishable_unverified_other_project'},
                       {'SUPABASE_STORAGE_BUCKET':'destination-images'},
                       {'ROUTING_PROVIDER':'osrm'}, {'ROUTING_PROVIDER':''},
                       {'OSRM_BASE_URL':'https://router.project-osrm.org'}):
            with self.subTest(fields=tuple(change)), self.assertRaises(ValueError):
                validate_evaluation_environment(settings()|change)

    def test_backend_only_preflight_needs_no_proxy_secret_or_startup(self):
        environment={k:v for k,v in settings().items()
                     if k in ('ROSAGO_EVALUATION','ROSAGO_EVALUATION_PROJECT_REF','SUPABASE_URL','SUPABASE_KEY')}
        result=validate_evaluation_backend(environment)
        self.assertTrue(result['public_key_binding_verified'])
        self.assertNotIn('SUPABASE_KEY',result)

    def test_public_auth_claims_from_real_project_fail_evaluation_issuer_policy(self):
        claims={'sub':'synthetic-id','session_id':'synthetic-session','iss':'https://brnkigrrqdrywahvcbvc.supabase.co/auth/v1','aud':'authenticated','role':'authenticated','exp':9999999999,'amr':[{'method':'password','timestamp':1}]}
        self.assertFalse(_normal_claims(claims,'https://'+REFERENCE+'.supabase.co/auth/v1'))

    def test_local_modes_non_https_and_missing_proxy_attestation_are_denied(self):
        for change in ({'ROSAGO_EVALUATION':'false'},{'ROSAGO_AUTH_MODE':'development'},
                       {'ROSAGO_AUTH_MODE':'redis-local'},{'ROSAGO_PUBLIC_ORIGIN':'http://evaluation.example'},
                       {'ROSAGO_PUBLIC_ORIGIN':'https://localhost'},
                       {'ROSAGO_PROXY_HEADERS_SANITIZED':''},{'ROSAGO_EVALUATION_PROXY_HOPS':'2'},
                       {'ROSAGO_EVALUATION_EMAIL_MODE':'live'}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                validate_evaluation_environment(settings()|change)

    def test_production_session_guard_remains_and_dotenv_is_never_loaded(self):
        provider=Mock()
        with patch.dict(os.environ,settings(),clear=True), \
             patch('dotenv.load_dotenv') as dotenv, \
             patch('supabase.create_client',return_value=provider), \
             patch('socket.socket.connect',side_effect=AssertionError('Network forbidden')) as connect:
            with self.assertRaisesRegex(RuntimeError,'reviewed shared session backend'):
                runpy.run_path(str(ROOT/'app.py'))
            dotenv.assert_not_called()
            provider.auth.sign_in_with_password.assert_not_called()
            connect.assert_not_called()

    def test_invalid_evaluation_fails_before_dotenv_or_sdk_client_creation(self):
        with patch.dict(os.environ,settings()|{'SUPABASE_URL':'https://brnkigrrqdrywahvcbvc.supabase.co'},clear=True), \
             patch('dotenv.load_dotenv') as dotenv,patch('supabase.create_client') as sdk:
            with self.assertRaises(ValueError):runpy.run_path(str(ROOT/'app.py'))
            dotenv.assert_not_called()
            sdk.assert_not_called()


class EvaluationHttpPreparationTests(EvaluationKeyFixture, unittest.TestCase):
    def test_direct_loopback_https_ignores_all_proxy_headers_and_refuses_plaintext(self):
        env=settings()|{'ROSAGO_EVALUATION_TRANSPORT':'direct-local-https',
            'ROSAGO_PUBLIC_ORIGIN':'https://127.0.0.1:5443',
            'ROSAGO_EVALUATION_PROXY_HOPS':'0','ROSAGO_PROXY_HEADERS_SANITIZED':'false'}
        app=Flask('direct');app.secret_key=env['FLASK_SECRET_KEY']
        configure_evaluation_http(app,env)
        @app.get('/')
        def index():
            session['fixture']=True
            return {'scheme':request.scheme,'host':request.host,'remote':request.remote_addr}
        client=app.test_client()
        headers={'X-Forwarded-Proto':'http','X-Forwarded-Host':'evil.invalid',
                 'X-Forwarded-For':'192.0.2.5','X-Forwarded-Port':'80'}
        good=client.get('/',base_url='https://127.0.0.1:5443',headers=headers)
        self.assertEqual(good.json,{'scheme':'https','host':'127.0.0.1:5443','remote':'127.0.0.1'})
        self.assertIn('Secure',good.headers['Set-Cookie'])
        self.assertEqual(client.get('/',base_url='http://127.0.0.1:5443',
            headers={'X-Forwarded-Proto':'https'}).status_code,400)
        self.assertEqual(client.get('/',base_url='https://127.0.0.1:5444').status_code,400)
        for change in ({'ROSAGO_EVALUATION_PROXY_HOPS':'1'},
                       {'ROSAGO_PROXY_HEADERS_SANITIZED':'true'},
                       {'ROSAGO_PUBLIC_ORIGIN':'https://external.invalid'},
                       {'ROSAGO_PUBLIC_ORIGIN':'http://127.0.0.1:5443'}):
            with self.subTest(fields=tuple(change)),self.assertRaises(ValueError):
                validate_evaluation_environment(env|change)

    def app(self):
        app=Flask(__name__)
        app.secret_key=settings()['FLASK_SECRET_KEY']
        configure_evaluation_http(app,settings())
        @app.get('/')
        def index():
            session['synthetic_probe']=True
            return {'scheme':request.scheme,'host':request.host,'address':request.remote_addr}
        return app

    def test_scheme_only_proxy_host_restriction_and_cookie_settings(self):
        client=self.app().test_client()
        result=client.get('/',base_url='http://evaluation.example',headers={
            'X-Forwarded-Proto':'https','X-Forwarded-Host':'untrusted.example',
            'X-Forwarded-For':'192.0.2.99'})
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json,{'scheme':'https','host':'evaluation.example','address':'127.0.0.1'})
        cookie=result.headers['Set-Cookie']
        for item in ('Secure','HttpOnly','SameSite=Lax'):self.assertIn(item,cookie)
        self.assertNotIn('Domain=',cookie)
        self.assertIn('geolocation=()',result.headers['Permissions-Policy'])
        policies='; '.join(result.headers.getlist('Content-Security-Policy'))
        self.assertIn('https://'+REFERENCE+'.supabase.co',policies)
        self.assertNotIn('brnkigrrqdrywahvcbvc',policies)
        # This verifies HTTP preparation, not real User/Admin session persistence.

    def test_wrong_host_and_unqualified_plain_http_fail_closed(self):
        client=self.app().test_client()
        self.assertEqual(client.get('/',base_url='http://untrusted.example',headers={
            'X-Forwarded-Host':'evaluation.example','X-Forwarded-Proto':'https'}).status_code,400)
        self.assertEqual(client.get('/',base_url='http://evaluation.example').status_code,400)
