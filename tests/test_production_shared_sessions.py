"""Production-mode wiring with synthetic signed evidence, never hosted qualification."""
from copy import deepcopy
from dataclasses import replace
import json
import os
from pathlib import Path
import runpy
import socket
import tempfile
import time
import unittest
from unittest.mock import Mock,patch

from cryptography.hazmat.primitives.asymmetric import rsa
import httpx
import jwt
from flask import Flask

import production_session_runtime as production
from session_realms import init_session_realms,SessionStorageUnavailable
from normal_auth_coordinator import VerifiedLoginCredentials
from protected_authority_fixture import TestMetadataService
from production_runtime_fixture import environment,Pool,ProviderTransport
from test_public_layout import Document


class ProductionSessions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.private=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='rosago-prod-unit-');self.addCleanup(self.temp.cleanup)
        self.metadata=TestMetadataService(self.temp.name,'production_fixture');self.addCleanup(self.metadata.close)
        self.metadata.local.configure('production_fixture',dict(user='user_epoch_fixture',admin='admin_epoch_fixture'))
        self.env,self.claims=environment(self.private,self.metadata.binding())
        self.pool=Pool();self.provider={};self.clients=[];self.raw_active=True;self.membership=True;self.worker_list=[]
        self.issued=0;self.provider_tokens={}
        self.real_open_worker=production.open_worker
        self.uid='11111111-1111-4111-8111-111111111111';self.sid='22222222-2222-4222-8222-222222222222'
        for target,name in ((socket,'create_connection'),(socket,'getaddrinfo'),(socket.socket,'connect')):
            guard=patch.object(target,name,side_effect=AssertionError('External network forbidden'))
            guard.start();self.addCleanup(guard.stop)
    def sign(self,claims):return jwt.encode(claims,self.private,algorithm='RS256')
    def transport(self,url,token,**kwargs):
        name=url.rsplit('/',1)[1]
        if name=='authority':client=Mock(exchange=self.metadata.exchange,close=Mock())
        else:client=ProviderTransport(name,self.provider)
        self.clients.append(client);return client
    def response(self,request):
        path=request.url.path
        access=request.headers.get('Authorization','').removeprefix('Bearer ')
        active=self.raw_active and self.provider_tokens.get(access,False)
        if path.endswith('/rosago_is_admin'):return httpx.Response(200,json=self.membership)
        if path.endswith('/rosago_provider_session_current'):return httpx.Response(200,json=active)
        if path.endswith('/rosago_provider_session_present'):return httpx.Response(200,json=active)
        if path.endswith('/logout'):self.provider_tokens[access]=False;return httpx.Response(204)
        if path.endswith('/profiles'):return httpx.Response(200,json=[])
        raise AssertionError('Unexpected synthetic provider route')
    def worker(self,settings):
        worker=self.real_open_worker(settings,pool_factory=lambda _:self.pool,transport_factory=self.transport)
        self.worker_list.append(worker);self.addCleanup(worker.close);return worker
    def application(self):
        with patch.dict(os.environ,self.env,clear=True),patch('production_session_runtime.open_worker',side_effect=self.worker), \
                patch('dotenv.load_dotenv'),patch('supabase.create_client',return_value=Mock()):
            app=runpy.run_path(str(Path(__file__).resolve().parents[1]/'app.py'))['app']
        app.testing=True
        for name in ('rosago_normal_auth','rosago_admin_auth'):
            dep=app.extensions[name]
            dep.adapters.base._http_factory=lambda **kw:httpx.Client(transport=httpx.MockTransport(self.response),**kw)
            dep.adapters.base.password_login=self.credentials
        return app
    def credentials(self,*args):
        self.issued+=1;access='synthetic-access-'+str(self.issued);self.provider_tokens[access]=True
        return VerifiedLoginCredentials(self.uid,'synthetic@example.invalid',access,'synthetic-refresh',time.time()+3600,
            '22222222-2222-4222-8222-'+str(self.issued).zfill(12))
    def login(self,client,path='/login'):
        origin=self.env['ROSAGO_PUBLIC_ORIGIN'];page=client.get(path,base_url=origin)
        self.assertEqual(page.status_code,200,page.data[:100])
        token=Document(page.text).find('input',name='csrf_token')[0].attrs['value']
        return client.post(path,base_url=origin,headers={'Origin':origin},data=dict(email='synthetic@example.invalid',password='synthetic-only',csrf_token=token))
    def test_missing_unsigned_stale_unqualified_or_source_changed_release_never_opens_pool(self):
        cases=[{},self.env|{'ROSAGO_SECURITY_RELEASE_JWT':'unsigned'}]
        for field,value in [('exp',int(time.time())-1),('evidence_level','offline-fixture'),('sources',{}),('checks',{})]:
            claims=deepcopy(self.claims);claims[field]=value;cases.append(self.env|{'ROSAGO_SECURITY_RELEASE_JWT':self.sign(claims)})
        with patch.object(production,'_open_pool') as pool:
            for env in cases:
                with self.subTest(case=len(env)),self.assertRaises(RuntimeError) as error:production.validate_environment(env)
                self.assertIsNone(error.exception.__context__)
            pool.assert_not_called()
    def test_rejects_local_storage_bad_tls_supabase_database_or_wrong_key(self):
        for key,value in (('ROSAGO_SESSION_BACKEND','memory'),('ROSAGO_SESSION_BACKEND','redis'),
                          ('SUPABASE_KEY','sb_secret_private'),('ROSAGO_SESSION_DATABASE_URL','host=127.0.0.1'),
                          ('ROSAGO_AUTH_MODE','redis-local'),('ROSAGO_PROXY_HEADERS_SANITIZED','false')):
            with self.subTest(key=key),self.assertRaises(RuntimeError):production.validate_environment(self.env|{key:value})
        for secret in ('synthetic-database','synthetic-flask'):
            with self.assertRaises(RuntimeError) as error:production.validate_environment(self.env|{'ROSAGO_SECURITY_RELEASE_JWT':secret})
            self.assertNotIn(secret,str(error.exception))
    def test_real_production_branch_installs_shared_secure_realms_and_http_boundary(self):
        app=self.application();worker=app.extensions['rosago_production_sessions']
        self.assertTrue(worker.readiness());self.assertTrue(app.session_interface.secure)
        self.assertIs(app.extensions['rosago_normal_auth'].store.backend,worker.runtime.realms['user'])
        self.assertIs(app.extensions['rosago_admin_auth'].store.backend,worker.runtime.realms['admin'])
        self.assertIs(app.extensions['rosago_email_pending'].backend,worker.runtime.realms['user'])
        self.assertEqual(app.config['SESSION_COOKIE_SAMESITE'],'Lax')
        self.assertEqual(app.test_client().get('/login',base_url='http://fixture.example.invalid').status_code,400)
        with patch.dict(os.environ,self.env,clear=True),self.assertRaises(RuntimeError):
            init_session_realms(Flask('deny-injection'),mode='production',local_runtime=worker.runtime)
    def test_login_cross_worker_restart_logout_and_old_cookie_replay(self):
        app=self.application();browser=app.test_client();self.assertEqual(self.login(browser).status_code,303)
        cookie=browser.get_cookie('__Host-rosago_user_session',domain='fixture.example.invalid').value
        other_app=self.application();other=other_app.test_client();other.set_cookie('__Host-rosago_user_session',cookie,domain='fixture.example.invalid')
        origin=self.env['ROSAGO_PUBLIC_ORIGIN'];self.assertTrue(other.get('/auth/status',base_url=origin).json['authenticated'])
        token=browser.get('/auth/logout-token',base_url=origin).json['csrf_token']
        reply=browser.post('/logout',base_url=origin,headers={'Origin':origin},data={'csrf_token':token})
        self.assertIn(reply.status_code,(302,303))
        # Restored raw provider state cannot undo the independently known tombstone.
        self.raw_active=True;self.provider_tokens={k:True for k in self.provider_tokens}
        self.assertFalse(other.get('/auth/status',base_url=origin).json['authenticated'])
        restarted=self.application().test_client();restarted.set_cookie('__Host-rosago_user_session',cookie,domain='fixture.example.invalid')
        self.assertFalse(restarted.get('/auth/status',base_url=origin).json['authenticated'])
    def test_outage_returns_503_keeps_cookie_and_never_falls_back(self):
        app=self.application();client=app.test_client();self.assertEqual(self.login(client).status_code,303)
        before=client.get_cookie('__Host-rosago_user_session',domain='fixture.example.invalid').value
        self.pool.available=False
        response=client.get('/auth/status',base_url=self.env['ROSAGO_PUBLIC_ORIGIN'])
        self.assertEqual(response.status_code,503);self.assertNotIn('Set-Cookie',response.headers)
        self.assertEqual(client.get_cookie('__Host-rosago_user_session',domain='fixture.example.invalid').value,before)
        self.assertFalse(app.extensions['rosago_production_sessions'].readiness())
    def test_membership_is_required_and_user_admin_cookies_and_logout_are_independent(self):
        app=self.application();client=app.test_client();self.assertEqual(self.login(client).status_code,303)
        self.membership=False;self.assertEqual(self.login(client,'/admin/login').status_code,403)
        self.assertTrue(client.get('/auth/status',base_url=self.env['ROSAGO_PUBLIC_ORIGIN']).json['authenticated'])
        self.membership=True;self.assertEqual(self.login(client,'/admin/login').status_code,303)
        self.assertIsNotNone(client.get_cookie('__Secure-rosago_admin_session',domain='fixture.example.invalid',path='/admin'))
        self.assertEqual(client.get('/admin/account',base_url=self.env['ROSAGO_PUBLIC_ORIGIN']).status_code,200)
        origin=self.env['ROSAGO_PUBLIC_ORIGIN']
        token=client.get('/auth/logout-token',base_url=origin).json['csrf_token']
        self.assertIn(client.post('/logout',base_url=origin,headers={'Origin':origin},data={'csrf_token':token}).status_code,(302,303))
        self.assertEqual(client.get('/admin/account',base_url=origin).status_code,200)
    def test_password_reset_provider_invalidation_denies_preexisting_credentials(self):
        app=self.application();client=app.test_client();self.assertEqual(self.login(client).status_code,303)
        self.raw_active=False # required provider-side reset event, not an inferred password change
        self.assertFalse(client.get('/auth/status',base_url=self.env['ROSAGO_PUBLIC_ORIGIN']).json['authenticated'])
        self.raw_active=True
        self.assertFalse(client.get('/auth/status',base_url=self.env['ROSAGO_PUBLIC_ORIGIN']).json['authenticated'])
    def test_expired_release_storage_role_failure_and_fork_are_closed(self):
        settings=production.validate_environment(self.env)
        with patch.dict(os.environ,{},clear=True):worker=self.worker(settings)
        with patch('production_session_runtime.time.time',return_value=settings.deadline+1):
            self.assertFalse(worker.readiness())
            with self.assertRaises(SessionStorageUnavailable):worker.runtime.realms['user'].now()
        with patch('production_session_runtime.os.getpid',return_value=worker.pid+1):
            with self.assertRaises(SessionStorageUnavailable):worker.current()
        for field,value in (('role','postgres'),('rolbypassrls',True),('public_access',True),('relforcerowsecurity',False)):
            old=self.pool.attributes.copy();self.pool.attributes[field]=value
            with patch.dict(os.environ,{},clear=True),self.assertRaises(SessionStorageUnavailable):self.worker(settings)
            self.pool.attributes=old
    def test_recovery_grants_are_shared_consumed_and_expire_without_new_sessions(self):
        first=self.application();second=self.application()
        one=first.extensions['rosago_local_session_runtime'].model_factory(first.extensions['rosago_shared_sessions']['user'],'grants')
        two=second.extensions['rosago_local_session_runtime'].model_factory(second.extensions['rosago_shared_sessions']['user'],'grants')
        grant=one.issue(self.uid,'test-recovery',time.time()+300,'synthetic-access')
        self.assertTrue(two.valid(grant));self.assertTrue(one.revoke(grant));self.assertFalse(two.valid(grant))

    def test_auth_idle_expiry_denies_even_with_unexpired_provider_credentials(self):
        app=self.application();worker=app.extensions['rosago_production_sessions']
        model=worker.runtime.model_factory(worker.runtime.realms['user'],'auth')
        from dataclasses import asdict
        credentials=VerifiedLoginCredentials(self.uid,'synthetic@example.invalid','synthetic-access',
            'synthetic-refresh',time.time()+3500,self.sid)
        handle=model.create(**asdict(credentials))
        self.assertIsNotNone(model.resolve(handle))
        with patch('production_session_runtime.time.time',return_value=time.time()+1900):
            self.assertIsNone(model.resolve(handle))

    def test_worker_shutdown_closes_owned_clients(self):
        app=self.application();worker=app.extensions['rosago_production_sessions']
        config=runpy.run_path(str(Path(__file__).resolve().parents[1]/'gunicorn.conf.py'))
        config['worker_exit'](None,Mock(wsgi=app))
        self.assertTrue(worker.closed);self.assertFalse(worker.readiness())
        self.pool.close.assert_called_once()


if __name__=='__main__':unittest.main()
