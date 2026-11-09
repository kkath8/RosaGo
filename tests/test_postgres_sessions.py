"""Opt-in local PostgreSQL and isolated Flask integration; no live providers."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict,replace
import json
import os
from pathlib import Path
import runpy
import secrets
import time
from threading import Event
import unittest
from unittest.mock import Mock,patch

import pytest
pytest.importorskip('psycopg')
import psycopg
from psycopg.types.json import Jsonb
from postgres_session_recovery import RecoveryBinding,RecoveryProof,RecoveryFence
from postgres_session_store import PgRealm,PgModel,PgChallenges,isolated_pool
from postgres_session_fixture import TestRecoveryController
from session_crypto import SessionCipher
from session_realms import SessionStorageUnavailable,init_session_realms
from session_authority import RevisionConflict
from normal_auth_coordinator import VerifiedLoginCredentials
from flask import Flask


DSN=os.environ.get('ROSAGO_TEST_POSTGRES_DSN')
OPERATOR=os.environ.get('ROSAGO_TEST_POSTGRES_OPERATOR_DSN')
A='11111111-1111-4111-8111-111111111111'
B='22222222-2222-4222-8222-222222222222'


class RecoveryContractTests(unittest.TestCase):
    def test_missing_or_untrusted_source_denied(self):
        with self.assertRaises(SessionStorageUnavailable):RecoveryFence(None,Mock())
        with self.assertRaises(SessionStorageUnavailable):PgRealm(Mock(),Mock(),'local','user')
    def test_no_production_factory_or_remote_pool(self):
        with self.assertRaises(ValueError):isolated_pool('host=example.invalid dbname=rosago_lab user=fake')
        with self.assertRaises(RuntimeError):init_session_realms(Flask('guard'),mode='production')
    def test_stale_corrupt_replayed_and_uncertain_proof(self):
        binding=RecoveryBinding(*['a'*24,'b'*24,'c'*24,'d'*24])
        controller=TestRecoveryController(binding);fence=RecoveryFence(controller,binding,minimum_revision=1)
        self.assertEqual(fence.check('test').binding,binding)
        original=controller.proof
        for field,value in [('request_id','old'),('revision',0),('issued_at',time.time()-10),('state','BLOCKED'),('freshness','UNKNOWN')]:
            with self.subTest(field=field),patch.object(controller,'proof',side_effect=lambda ns,nonce,f=field,v=value:replace(original(ns,nonce),**{f:v})):
                with self.assertRaises(SessionStorageUnavailable):fence.check('test')


@unittest.skipUnless(DSN and OPERATOR,'Explicit isolated PostgreSQL fixture required')
class PgStoreTests(unittest.TestCase):
    def setUp(self):
        self.namespace='pg_m_'+secrets.token_hex(8)
        self.binding=RecoveryBinding(secrets.token_hex(16),secrets.token_hex(16),secrets.token_hex(16),secrets.token_hex(16))
        self.controller=TestRecoveryController(self.binding)
        self.fence=RecoveryFence(self.controller,self.binding)
        self.pool=isolated_pool(DSN);self.addCleanup(self.pool.close)
        self.operator=psycopg.connect(OPERATOR,autocommit=True);self.addCleanup(self.operator.close)
        self.operator.execute('INSERT INTO rosago_session_m.gate VALUES(%s,1,%s,%s,%s,%s,%s)',
            (self.namespace,self.binding.authority_id,self.binding.incarnation,self.binding.user_epoch,self.binding.admin_epoch,'OPEN'))
        self.addCleanup(self.cleanup)
        self.cipher=SessionCipher({'test':secrets.token_bytes(32)},'test')
        self.realms={r:PgRealm(self.pool,self.cipher,self.namespace,r,recovery=self.fence) for r in ('user','admin')}
    def cleanup(self):
        for table in ('records','revoked','versions','gate'):
            self.operator.execute('DELETE FROM rosago_session_m.'+table+' WHERE namespace=%s',(self.namespace,))
    def credentials(self,realm='user'):
        return VerifiedLoginCredentials(A if realm=='user' else B,realm+'@example.invalid',realm+'-access',realm+'-refresh',time.time()+3600,realm+'-provider-session')
    def store(self,realm='user',kind='auth'):return PgModel(self.realms[realm],kind)
    def short_expiry(self,kind,handle,seconds=.15,realm='user'):
        backend=self.realms[realm];snap=backend.snapshot(kind,handle)
        extra={k:v for k,v in snap.meta.items() if k in ('absolute','activity','generation','busy')}
        backend.write(snap,snap.data,snap.now+seconds,**extra)
    def test_encryption_scope_ttl_and_renewal(self):
        handle=self.store().create(**asdict(self.credentials()));backend=self.realms['user']
        snap=backend.snapshot('auth',handle)
        for plain in (b'user-access',b'user-refresh',A.encode(),handle.encode()):self.assertNotIn(plain,snap.raw)
        self.assertIsNone(self.store('admin').resolve(handle))
        self.assertTrue(self.store().touch(handle,expected_generation=0))
        touched=backend.snapshot('auth',handle)
        self.assertEqual(snap.raw,touched.raw)
        self.assertGreater(touched.meta['revision'],snap.meta['revision'])
        self.assertLessEqual(touched.meta['expires'],touched.meta['absolute'])
        self.short_expiry('auth',handle);time.sleep(.2)
        self.assertIsNone(self.store().resolve(handle))
    def test_terminal_revocation_blocks_record_only_restore(self):
        handle=self.store().create(**asdict(self.credentials()));snap=self.realms['user'].snapshot('auth',handle)
        row=self.operator.execute('SELECT * FROM rosago_session_m.records WHERE key=%s',(snap.key,)).fetchone()
        self.assertTrue(self.store().revoke(handle))
        with self.operator.cursor() as cursor:
            cursor.execute('INSERT INTO rosago_session_m.records VALUES('+','.join(['%s']*9)+')',
                tuple(Jsonb(v) if isinstance(v,dict) else v for v in row))
        self.assertIsNone(self.store().resolve(handle))
        with self.assertRaises(RevisionConflict):self.realms['user'].write(snap,snap.data,snap.meta['expires'],absolute=snap.meta['absolute'],activity=snap.meta['activity'],generation=0,busy=False)
    def test_old_refreshed_record_is_rejected_by_revision_fence(self):
        handle=self.store().create(**asdict(self.credentials()));snap=self.realms['user'].snapshot('auth',handle)
        lease,_=self.store().reserve_refresh(handle)
        self.assertTrue(self.store().replace_credentials(handle,lease,**asdict(self.credentials())))
        self.operator.execute('UPDATE rosago_session_m.records SET revision=%s,metadata=%s,ciphertext=%s WHERE key=%s',
            (snap.meta['revision'],Jsonb({k:v for k,v in snap.meta.items() if k in ('absolute','activity','generation','busy')}),snap.raw,snap.key))
        with self.assertRaises(SessionStorageUnavailable):self.store().resolve(handle)
    def test_concurrent_refresh_and_revocation(self):
        handle=self.store().create(**asdict(self.credentials()))
        with ThreadPoolExecutor(max_workers=2) as pool:answers=list(pool.map(lambda _:self.store().reserve_refresh(handle),range(2)))
        self.assertEqual(sum(answer is not None for answer in answers),1)
        lease,_=next(answer for answer in answers if answer is not None)
        prepared=Event();released=Event();original=self.realms['user'].atomic
        def delayed(snapshots,updates):
            if any(value[2].get('generation')==1 for value in updates.values()):prepared.set();released.wait(5)
            return original(snapshots,updates)
        with patch.object(self.realms['user'],'atomic',side_effect=delayed),ThreadPoolExecutor(max_workers=1) as pool:
            pending=pool.submit(self.store().replace_credentials,handle,lease,**asdict(self.credentials()))
            try:self.assertTrue(prepared.wait(5));self.assertTrue(self.store().revoke(handle))
            finally:released.set()
            with self.assertRaises(RevisionConflict):pending.result(timeout=5)
        self.assertIsNone(self.store().resolve(handle))
    def test_independent_recovery_gate_and_unavailable_authority(self):
        handles={r:self.store(r).create(**asdict(self.credentials(r))) for r in self.realms}
        self.controller.available=False
        with self.assertRaises(SessionStorageUnavailable):self.store().resolve(handles['user'])
        self.controller.available=True
        self.controller.change(freshness='UNCERTAIN')
        with self.assertRaises(SessionStorageUnavailable):self.realms['admin'].readiness()
        new=replace(self.binding,user_epoch=secrets.token_hex(16),admin_epoch=secrets.token_hex(16))
        self.controller.change(new)
        with self.assertRaises(SessionStorageUnavailable):self.store().resolve(handles['user'])
        fresh=PgRealm(self.pool,self.cipher,self.namespace,'user',recovery=RecoveryFence(self.controller,new))
        with self.assertRaises(SessionStorageUnavailable):fresh.now() # DB gate not advanced
    def test_runtime_role_cannot_change_gate_or_history(self):
        for statement in ('UPDATE rosago_session_m.gate SET state=state','DELETE FROM rosago_session_m.revoked','DELETE FROM rosago_session_m.versions'):
            with self.subTest(operation=statement.split()[0]),self.assertRaises(psycopg.errors.InsufficientPrivilege):
                with self.pool.connection() as connection:connection.execute(statement)
    def test_clock_stale_snapshot_and_capacity_fail_closed(self):
        backend=self.realms['user'];handle=self.store().create(**asdict(self.credentials()))
        snap=backend.snapshot('auth',handle);snap.now-=3
        with self.assertRaises(RevisionConflict):backend.write(snap,None,time.time())
        with patch('postgres_session_store.time.time',return_value=time.time()+10):
            with self.assertRaises(SessionStorageUnavailable):backend.now()
        bounded=PgRealm(self.pool,self.cipher,self.namespace,'admin',recovery=self.fence,record_limit=1)
        limited=PgModel(bounded,'auth');first=limited.create(**asdict(self.credentials('admin')))
        with self.assertRaises(SessionStorageUnavailable):limited.create(**asdict(self.credentials('admin')))
        self.assertTrue(limited.revoke(first))
    def test_unknown_post_commit_result_does_not_retry_refresh(self):
        handle=self.store().create(**asdict(self.credentials()))
        lease,_=self.store().reserve_refresh(handle)
        calls=[];original=self.fence.check
        def check(namespace):
            calls.append(True)
            if len(calls)==4:raise SessionStorageUnavailable('Synthetic post-commit control outage')
            return original(namespace)
        with patch.object(self.fence,'check',side_effect=check):
            with self.assertRaises(SessionStorageUnavailable):self.store().replace_credentials(handle,lease,**asdict(self.credentials()))
        self.assertEqual(self.store().resolve(handle).generation,1)
        self.assertFalse(self.store().replace_credentials(handle,lease,**asdict(self.credentials())))
    def test_operator_cleanup_is_bounded_and_not_a_runtime_permission(self):
        backend=self.realms['user'];ref=secrets.token_urlsafe(32);snap=backend.snapshot('web',ref)
        backend.write(snap,{'values':{},'version':0},snap.now+.1)
        time.sleep(.15)
        self.assertIsNone(PgModel(backend,'web').read(ref))
        with self.assertRaises(psycopg.errors.InsufficientPrivilege):
            with self.pool.connection() as connection:connection.execute('SELECT rosago_session_m.cleanup_expired(%s,128)',(self.namespace,))
        time.sleep(2.1)
        self.assertGreaterEqual(self.operator.execute('SELECT rosago_session_m.cleanup_expired(%s,128)',(self.namespace,)).fetchone()[0],2)
    def test_independent_family_expiry_and_fixed_rate_window(self):
        challenges=PgChallenges(self.realms)
        login=challenges.issue('user')
        pending=self.store(kind='pending').create()
        grant=self.store(kind='grant').issue(A,'synthetic-provider',time.time()+300,'synthetic-token')
        email=self.store(kind='email').create('ttl@example.invalid')
        web=self.store(kind='web').create({'preference':'test'})
        self.assertTrue(challenges.allow_attempt('user','127.0.0.1'))
        rate=self.realms['user'].snapshot('rate','login:127.0.0.1')
        self.assertTrue(challenges.allow_attempt('user','127.0.0.1'))
        self.assertEqual(rate.meta['expires'],self.realms['user'].snapshot('rate','login:127.0.0.1').meta['expires'])
        pairs=[('login',login),('pending',pending),('grant',grant),('email',email),('web',web)]
        # Store-specific deadline shortening; no production/provider mutation.
        for kind,ref in pairs:self.short_expiry(kind,ref,seconds=.2)
        admin=self.store('admin').create(**asdict(self.credentials('admin')))
        time.sleep(.25)
        for kind,ref in pairs:
            with self.subTest(family=kind):self.assertIsNone(self.realms['user'].snapshot(kind,ref).data)
        self.assertIsNotNone(self.store('admin').resolve(admin))
        # Recovery replay receipt/email rate have independent original deadlines.
        self.assertTrue(self.realms['user'].snapshot('email_rate','ttl@example.invalid').data)
    def test_pool_and_database_lock_deadlines_fail_closed(self):
        backend=self.realms['user']
        with self.pool.connection(),self.pool.connection():
            started=time.monotonic()
            with self.assertRaises(SessionStorageUnavailable):backend.now()
            self.assertLess(time.monotonic()-started,2)
        with self.operator.transaction():
            self.operator.execute('SELECT * FROM rosago_session_m.gate WHERE namespace=%s FOR UPDATE',(self.namespace,))
            started=time.monotonic()
            with self.assertRaises(SessionStorageUnavailable):backend.now()
            self.assertLess(time.monotonic()-started,2)
        self.assertTrue(backend.readiness()['ready'])


# Reuse ONLY the application behavior methods, not Redis-specific storage tests.
# The synthetic loader injects PG dependencies; active application files stay intact.
if DSN and OPERATOR:
    import test_redis_sessions as contracts
    class PgApplicationTests(PgStoreTests):
        def setUp(self):
            super().setUp();self.workers=[];self.requests=[];self.member=True
            self.provider_state={'user':True,'admin':True}
            from shared_session_runtime import LocalSessionRuntime
            env={'ROSAGO_AUTH_MODE':'redis-local','FLASK_SECRET_KEY':secrets.token_hex(32),
                 'ROSAGO_PUBLIC_ORIGIN':'https://localhost',
                 'SUPABASE_URL':'https://example.supabase.co','SUPABASE_KEY':'sb_publishable_synthetic_fixture'}
            for _ in range(2):
                runtime=LocalSessionRuntime(self.realms,PgModel,PgChallenges,
                    lambda record,issuer,realm:self.provider_state[realm])
                with patch('dotenv.load_dotenv'),patch.dict(os.environ,env),patch('supabase.create_client',return_value=Mock()),\
                     patch('session_realms.init_session_realms',side_effect=lambda app,mode: init_session_realms(app,mode=mode,local_runtime=runtime)):
                    app=runpy.run_path(str(Path(__file__).resolve().parents[1]/'app.py'))['app']
                app.testing=True
                for name in ('rosago_normal_auth','rosago_admin_auth'):
                    deps=app.extensions[name]
                    import httpx
                    deps.adapters._http_factory=lambda **kw:httpx.Client(transport=httpx.MockTransport(self.respond),**kw)
                    deps.coordinator._clients=deps.adapters.database_client
                    deps.adapters.password_login=lambda email,password,r=name:self.credentials('admin' if r=='rosago_admin_auth' else 'user')
                self.workers.append(app)
            self.browser=self.workers[0].test_client();self.other=self.workers[1].test_client()

        def test_explicit_runtime_wires_all_stores_and_provider_checks(self):
            for app in self.workers:
                self.assertIsInstance(app.extensions['rosago_normal_auth'].store,PgModel)
                self.assertIsInstance(app.extensions['rosago_admin_auth'].store,PgModel)
                self.assertIsInstance(app.extensions['rosago_email_pending'],PgModel)
                self.assertIsInstance(app.extensions['rosago_login_challenges'],PgChallenges)
                self.assertIs(app.session_interface.model_factory,PgModel)
                self.assertIsNotNone(app.extensions['rosago_normal_auth'].coordinator._provider_session_check)
                self.assertIsNotNone(app.extensions['rosago_admin_auth'].coordinator._provider_session_check)

        def test_real_routes_enforce_provider_outage_and_terminal_revocation(self):
            self.login('user');self.login('admin')
            old=self.browser.get_cookie('rosago_user_session_dev').value
            parent=PgModel(self.realms['user'],'web').read(old)[0]
            self.provider_state['user']=None
            outage=self.browser.get('/auth/status')
            self.assertEqual(outage.status_code,503)
            self.assertFalse(outage.headers.getlist('Set-Cookie'))
            self.provider_state['user']=True
            self.assert_both(self.browser)
            self.provider_state['user']=False
            revoked=self.browser.get('/auth/status')
            self.assertEqual(revoked.status_code,200)
            self.assertFalse(revoked.json['authenticated'])
            self.assertIsNone(PgModel(self.realms['user'],'auth').resolve(parent['auth_session_id']))
            self.assertEqual(self.browser.get('/admin/account').status_code,200)
            self.other.set_cookie('rosago_user_session_dev',old)
            self.assertFalse(self.other.get('/auth/status').json['authenticated'])
            self.provider_state['admin']=False
            self.assertEqual(self.browser.get('/admin/account').status_code,302)
        respond=contracts.RedisApplicationTests.respond
        sync=contracts.RedisApplicationTests.sync
        login=contracts.RedisApplicationTests.login
        assert_both=contracts.RedisApplicationTests.assert_both
        def test_pg_service_failure_keeps_both_cookies(self):
            self.login('user');self.login('admin')
            before=[self.browser.get_cookie(name,path=path).value for name,path in
                    [('rosago_user_session_dev','/'),('rosago_admin_session_dev','/admin')]]
            self.controller.available=False
            response=self.browser.get('/auth/status')
            self.assertEqual(response.status_code,503)
            self.assertFalse(response.headers.getlist('Set-Cookie'))
            self.controller.available=True
            self.assert_both(self.browser)
            after=[self.browser.get_cookie(name,path=path).value for name,path in
                   [('rosago_user_session_dev','/'),('rosago_admin_session_dev','/admin')]]
            self.assertEqual(before,after)
    for name in dir(contracts.RedisApplicationTests):
        if name.startswith('test_') and name not in dir(contracts.RedisTests) and name not in ('test_fresh_login_recovers_uncertain_credentials_without_touching_admin','test_http_outage_keeps_cookies_and_reconnect'):
            setattr(PgApplicationTests,name,getattr(contracts.RedisApplicationTests,name))
