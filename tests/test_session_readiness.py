"""Offline configuration tests. No real URLs, secrets, app imports or sockets."""
import base64
import json
import secrets
import unittest
from flask import Flask
from session_readiness import validate_settings,configure_local_https
from session_realms import init_session_realms


class SessionReadinessTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__)
        self.app.config['TRUSTED_HOSTS']=['fixture.example.invalid']
        self.app.config.update(SESSION_COOKIE_SECURE=True,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax')
        self.env={'ROSAGO_AUTH_MODE':'production','ROSAGO_SESSION_BACKEND':'redis',
            'ROSAGO_SESSION_KEYRING':json.dumps({'current':'test','keys':{'test':base64.b64encode(secrets.token_bytes(32)).decode()}}),
            'ROSAGO_PROXY_HOPS':'1','ROSAGO_PROXY_HEADERS_SANITIZED':'true',
            'ROSAGO_PUBLIC_ORIGIN':'https://fixture.example.invalid',
            'ROSAGO_SESSION_REDIS_USER_URL':'rediss://synthetic-user:synthetic-password@cache.example.invalid:6380/0',
            'ROSAGO_SESSION_REDIS_ADMIN_URL':'rediss://synthetic-admin:synthetic-password@cache.example.invalid:6380/0',
            'ROSAGO_USER_SESSION_EPOCH':'user_epoch','ROSAGO_ADMIN_SESSION_EPOCH':'admin_epoch',
            'ROSAGO_SESSION_NAMESPACE':'fixture'}

    def test_valid_preflight_is_explicitly_not_production_approval(self):
        decision=validate_settings(self.app,self.env)
        self.assertTrue(decision['configuration_valid'])
        self.assertFalse(decision['production_approved'])
        with self.assertRaises(RuntimeError):
            init_session_realms(self.app,mode='production')

    def test_missing_settings_and_insecure_overrides_fail(self):
        for key in self.env:
            changed=self.env.copy()
            changed.pop(key)
            with self.subTest(key=key),self.assertRaises(ValueError):
                validate_settings(self.app,changed)
        for key,value in (
            ('ROSAGO_AUTH_MODE','development'),('ROSAGO_SESSION_BACKEND','memory'),
            ('ROSAGO_PUBLIC_ORIGIN','http://fixture.example.invalid'),
            ('ROSAGO_PUBLIC_ORIGIN','https://evil.invalid'),('ROSAGO_PROXY_HOPS','4'),
            ('ROSAGO_PROXY_HEADERS_SANITIZED','false'),
            ('ROSAGO_SESSION_REDIS_USER_URL','redis://cache.example.invalid'),
            ('ROSAGO_SESSION_REDIS_ADMIN_URL',self.env['ROSAGO_SESSION_REDIS_ADMIN_URL']+'?ssl_cert_reqs=none')):
            with self.subTest(setting=key),self.assertRaises(ValueError):
                validate_settings(self.app,{**self.env,key:value})

    def test_explicit_local_https_proxy_and_trusted_host_policy(self):
        env={**self.env,'ROSAGO_LOCAL_HTTPS_QUALIFICATION':'true',
             'ROSAGO_TRUSTED_HOSTS':'["fixture.example.invalid"]'}
        self.assertTrue(configure_local_https(self.app,env))
        @self.app.get('/probe')
        def probe():
            from flask import request
            return {'scheme':request.scheme,'host':request.host,'remote':request.remote_addr}
        client=self.app.test_client()
        good=client.get('/probe',base_url='http://fixture.example.invalid',headers={'X-Forwarded-Proto':'https',
            'X-Forwarded-Host':'evil.invalid','X-Forwarded-For':'192.0.2.5'})
        self.assertEqual(good.json,{'scheme':'https','host':'fixture.example.invalid','remote':'127.0.0.1'})
        self.assertEqual(client.get('/probe',base_url='http://evil.invalid',headers={
            'X-Forwarded-Host':'fixture.example.invalid','X-Forwarded-Proto':'https'}).status_code,400)
        self.assertEqual(client.get('/probe',base_url='http://fixture.example.invalid').status_code,400)

    def test_authority_refuses_network_and_synchronized_paths(self):
        from session_authority import LocalRevisionAuthority
        from session_realms import SessionStorageUnavailable
        for path in ('\\\\unreachable.invalid\\share','OneDrive-test-authority'):
            with self.subTest(path_type='restricted'),self.assertRaises(SessionStorageUnavailable):
                LocalRevisionAuthority(path,bootstrap=True)
