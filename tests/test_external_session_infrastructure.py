"""Real local PG + independent JS SQLite authority + authenticated loopback HTTP.

Only an explicit disposable lab DSN is allowed; all identity/credentials fake.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import json
import os
from pathlib import Path
import runpy
import secrets
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock,patch

import psycopg
from independent_authority_fixture import IndependentAuthorityFixture
from externally_fenced_postgres import ExternalPgRealm,ExternalPgModel
from postgres_session_store import isolated_pool
from record_session_store import RedisChallenges
from session_crypto import SessionCipher
from session_authority import RevisionConflict
from session_realms import SessionStorageUnavailable,init_session_realms
from durable_session_logout import DurableLogout
from normal_auth_coordinator import VerifiedLoginCredentials
from shared_session_runtime import LocalSessionRuntime

ROOT=Path(__file__).resolve().parents[1]
DSN=os.environ.get('ROSAGO_TEST_POSTGRES_DSN');OPERATOR=os.environ.get('ROSAGO_TEST_POSTGRES_OPERATOR_DSN')

@unittest.skipUnless(DSN and OPERATOR,'Explicit disposable local PostgreSQL required')
class ExternalInfrastructureTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='rosago-independent-');self.addCleanup(self.temp.cleanup)
        self.namespace='external_'+secrets.token_hex(8)
        self.service=IndependentAuthorityFixture(Path(self.temp.name)/'authority.sqlite',self.namespace);self.addCleanup(self.service.close)
        self.pool=isolated_pool(DSN);self.addCleanup(self.pool.close)
        self.operator=psycopg.connect(OPERATOR,autocommit=True);self.addCleanup(self.operator.close)
        self.key=secrets.token_bytes(32);self.cipher=SessionCipher({'test':self.key},'test')
        self.realms={r:ExternalPgRealm(self.pool,self.cipher,self.namespace,r,r+'_epoch',authority=self.service.client()) for r in ('user','admin')}
        self.addCleanup(lambda:self.operator.execute('DELETE FROM rosago_session.payloads WHERE key LIKE %s',(self.namespace+':%',)))

    def credentials(self,realm='user'):
        return VerifiedLoginCredentials('11111111-1111-4111-8111-111111111111' if realm=='user' else '22222222-2222-4222-8222-222222222222',
            realm+'@example.invalid',realm+'-access',realm+'-refresh',time.time()+3600,realm+'-fake-session')

    def model(self,realm='user',kind='auth'):return ExternalPgModel(self.realms[realm],kind)
    def create(self,realm='user'):return self.model(realm).create(**asdict(self.credentials(realm)))
    def web(self,auth,realm='user'):return self.model(realm,'web').create({'auth_session_id':auth})

    def test_encrypted_shared_models_recovery_and_independent_restart(self):
        handle=self.create();snap=self.realms['user'].snapshot('auth',handle)
        for plain in (b'user-access',b'user-refresh',handle.encode()):self.assertNotIn(plain,snap.raw)
        self.assertIsNone(self.model('admin').resolve(handle))
        self.assertTrue(self.model().touch(handle,expected_generation=0))
        self.model('user','pending').create()
        grants=self.model('admin','grants');grant=grants.issue('subject','provider',time.time()+300,'token')
        self.service.restart()
        self.assertIsNotNone(self.model().resolve(handle))
        self.assertTrue(grants.valid(grant))
        grant_snapshot=self.realms['admin'].snapshot('grants',grant)
        self.assertTrue(grants.revoke(grant))
        self.operator.execute('INSERT INTO rosago_session.payloads VALUES(%s,%s,%s) ON CONFLICT(key) DO UPDATE '
            'SET ciphertext=excluded.ciphertext,expires=excluded.expires',
            (grant_snapshot.key,grant_snapshot.raw,grant_snapshot.meta['expires']))
        self.service.restart();self.assertFalse(grants.valid(grant))
        self.assertTrue(self.model().revoke(handle));self.service.restart()
        self.assertIsNone(self.model().resolve(handle))

    def test_entire_cache_snapshot_rollback_cannot_restore_revoked_or_old_revision(self):
        handle=self.create();snap=self.realms['user'].snapshot('auth',handle)
        rows=self.operator.execute('SELECT * FROM rosago_session.payloads WHERE key LIKE %s',(self.namespace+':%',)).fetchall()
        self.assertTrue(self.model().touch(handle,expected_generation=0))
        self.operator.execute('UPDATE rosago_session.payloads SET ciphertext=%s,expires=%s WHERE key=%s',(snap.raw,snap.meta['expires'],snap.key))
        with self.assertRaises(RevisionConflict):self.model().resolve(handle)
        self.assertTrue(self.model().revoke(handle)) # revocation-only does not trust stale ciphertext
        self.operator.execute('DELETE FROM rosago_session.payloads WHERE key LIKE %s',(self.namespace+':%',))
        for row in rows:self.operator.execute('INSERT INTO rosago_session.payloads VALUES(%s,%s,%s)',row)
        self.service.restart()
        self.assertIsNone(self.model().resolve(handle))

    def test_refresh_single_winner_and_stale_completion_cannot_resurrect(self):
        handle=self.create()
        with ThreadPoolExecutor(max_workers=2) as workers:
            results=list(workers.map(lambda _:self.model().reserve_refresh(handle),range(2)))
        winners=[r for r in results if r];self.assertEqual(len(winners),1)
        self.assertTrue(self.model().revoke(handle))
        self.assertFalse(self.model().replace_credentials(handle,winners[0][0],**asdict(self.credentials())))

    def test_lost_publication_and_closed_authority_never_fall_back(self):
        handle=self.create();snap=self.realms['user'].snapshot('auth',handle)
        original=self.realms['user'].transaction
        calls=[0]
        from contextlib import contextmanager
        @contextmanager
        def fail_publication():
            calls[0]+=1
            # now() precedes the independent commit; publication is next.
            if calls[0]>1:raise SessionStorageUnavailable('synthetic publication outage')
            with original() as connection:yield connection
        with patch.object(self.realms['user'],'transaction',fail_publication):
            with self.assertRaises(SessionStorageUnavailable):
                self.realms['user'].write(snap,snap.data,snap.meta['expires'],absolute=snap.meta['absolute'],activity=snap.now,generation=0,busy=False)
        with self.assertRaises(RevisionConflict):self.model().resolve(handle)
        self.service.control('block');self.service.restart()
        with self.assertRaises(SessionStorageUnavailable):self.model().resolve(handle)

    def test_logout_unknown_result_never_retries_and_reconciles_read_only(self):
        user=self.create();admin=self.create('admin');web=self.web(user)
        signout=Mock(return_value=None);check=Mock(return_value=True)
        logout=DurableLogout(self.realms,issuer='https://evaluation.invalid/auth/v1',sign_out=signout,session_check=check)
        self.assertFalse(logout('user',web));signout.assert_called_once()
        self.assertIsNone(self.model().resolve(user));self.assertIsNotNone(self.model('admin').resolve(admin))
        self.service.restart()
        self.assertFalse(logout('user',web));signout.assert_called_once()
        check.return_value=False
        self.assertEqual(logout.reconcile_pending('user')['confirmed'],1);signout.assert_called_once()
        self.assertNotIn('record',self.realms['user'].snapshot('logout',web).data)

    def test_logout_ack_requires_session_absence_and_claimed_call_is_not_replayed(self):
        handle=self.create();web=self.web(handle)
        signout=Mock(return_value=True);check=Mock(return_value=True)
        logout=DurableLogout(self.realms,issuer='https://evaluation.invalid/auth/v1',sign_out=signout,session_check=check)
        self.assertFalse(logout('user',web)) # HTTP acknowledgement alone is insufficient
        signout.assert_called_once();self.assertIsNone(self.model().resolve(handle))
        self.service.restart();check.return_value=False
        self.assertTrue(logout('user',web));signout.assert_called_once()
        # Simulate a process dying after durable claim, before its HTTP call.
        other=self.create();parent=self.web(other)
        record=self.model().resolve(other)
        receipt=self.realms['user'].snapshot('logout',parent)
        self.realms['user'].write(receipt,{'state':'attempted','record':record,'web_handle':parent},receipt.now+28800)
        self.model().revoke(other);self.model('user','web').revoke(parent)
        self.service.restart();check.return_value=True
        self.assertFalse(logout('user',parent));signout.assert_called_once()

    def test_worker_process_and_pool_recreation_preserve_revocation(self):
        handle=self.create()
        source="""
import json,sys
from authority_http_transport import AuthorityHTTPTransport
from protected_session_authority import ProtectedRevisionAuthority,AuthorityBinding
from externally_fenced_postgres import ExternalPgRealm,ExternalPgModel
from postgres_session_store import isolated_pool
from session_crypto import SessionCipher
c=json.load(sys.stdin);pool=isolated_pool(c['dsn'])
try:
 authority=ProtectedRevisionAuthority(AuthorityHTTPTransport(c['url'],c['token'],local_test=True),AuthorityBinding(**c['binding']),response_budget=1.5)
 realm=ExternalPgRealm(pool,SessionCipher({'test':bytes.fromhex(c['key'])},'test'),c['namespace'],'user','user_epoch',authority=authority)
 print(json.dumps({'present':ExternalPgModel(realm,'auth').resolve(c['handle']) is not None}))
finally:pool.close()
"""
        config={'dsn':DSN,'url':self.service.url,'token':self.service.token,'namespace':self.namespace,
            'binding':asdict(self.service.binding),'key':self.key.hex(),'handle':handle}
        env={k:os.environ[k] for k in ('PATH','SystemRoot','TEMP','TMP','PATHEXT') if k in os.environ}
        def child():
            result=subprocess.run([sys.executable,'-c',source],input=json.dumps(config),capture_output=True,text=True,env=env,cwd=ROOT,timeout=15)
            self.assertEqual(result.returncode,0,'Synthetic child failed; private stderr withheld')
            return json.loads(result.stdout)['present']
        self.assertTrue(child());self.model().revoke(handle);self.service.restart();self.assertFalse(child())

    def test_private_role_cannot_read_application_auth_or_change_schema(self):
        with self.pool.connection() as connection:
            for query in ('SELECT * FROM auth.users','CREATE TABLE rosago_session.unapproved(id int)',
                          'SELECT * FROM public.admin_memberships'):
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):connection.execute(query)

    def test_direct_table_and_all_privileged_rpc_replay_denied_after_provider_revocation(self):
        actor='f0000000-0000-4000-8000-000000000002';provider=secrets.token_hex(16)
        claims={'sub':actor,'session_id':str(__import__('uuid').UUID(provider)),'role':'authenticated',
            'aud':'authenticated','iss':'https://jfaufpfzfhysqkhcdsrs.supabase.co/auth/v1','exp':int(time.time()+3600)}
        self.operator.execute('INSERT INTO auth.sessions(id,user_id) VALUES(%s,%s)',(claims['session_id'],actor))
        def configure():
            self.operator.execute('SET LOCAL ROLE authenticated')
            self.operator.execute("SELECT set_config('request.jwt.claim.sub',%s,true)",(actor,))
            self.operator.execute("SELECT set_config('request.jwt.claims',%s,true)",(json.dumps(claims),))
        with self.operator.transaction():
            configure()
            self.assertEqual(self.operator.execute('SELECT count(*) FROM public.places').fetchone()[0],2)
            self.assertTrue(self.operator.execute('SELECT public.rosago_provider_session_current()').fetchone()[0])
        self.operator.execute('DELETE FROM auth.sessions WHERE id=%s',(claims['session_id'],))
        with self.operator.transaction():
            configure()
            for table, in self.operator.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'").fetchall():
                self.assertEqual(self.operator.execute('SELECT count(*) FROM public.'+table).fetchone()[0],0)
        from tools.prepare_provider_guards import NAMES
        calls=list(self.operator.execute("SELECT proname,pronargs FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND proname=ANY(%s)",(list(NAMES),)))
        self.assertEqual(len(calls),7)
        for name,nargs in calls:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                with self.operator.transaction():
                    configure();self.operator.execute('SELECT public.'+name+'('+','.join(['NULL']*nargs)+')')
        with self.operator.transaction():
            self.operator.execute('SET LOCAL ROLE anon')
            self.assertEqual(self.operator.execute('SELECT count(*) FROM public.places').fetchone()[0],1)

    def test_actual_user_admin_routes_use_candidate_and_truthful_logout(self):
        from test_redis_sessions import RedisApplicationTests as Contract
        self.requests=[];self.member=True;self.provider_state={'user':True,'admin':True}
        self.respond=lambda request:Contract.respond(self,request)
        self.workers=[]
        signout=Mock(return_value=None)
        logout=DurableLogout(self.realms,issuer='https://example.supabase.co/auth/v1',sign_out=signout,
            session_check=lambda record,issuer,realm:self.provider_state[realm])
        env={'ROSAGO_AUTH_MODE':'redis-local','FLASK_SECRET_KEY':secrets.token_hex(32),'ROSAGO_PUBLIC_ORIGIN':'https://localhost',
             'SUPABASE_URL':'https://example.supabase.co','SUPABASE_KEY':'sb_publishable_synthetic_fixture'}
        for _ in range(2):
            runtime=LocalSessionRuntime(self.realms,ExternalPgModel,RedisChallenges,
                lambda record,issuer,realm:self.provider_state[realm],logout_handler=logout)
            with patch('dotenv.load_dotenv'),patch.dict(os.environ,env),patch('supabase.create_client',return_value=Mock()),\
                 patch('session_realms.init_session_realms',side_effect=lambda app,mode:init_session_realms(app,mode=mode,local_runtime=runtime)):
                app=runpy.run_path(str(ROOT/'app.py'))['app']
            app.testing=True
            for name in ('rosago_normal_auth','rosago_admin_auth'):
                deps=app.extensions[name]
                import httpx
                deps.adapters._http_factory=lambda **kw:httpx.Client(transport=httpx.MockTransport(self.respond),**kw)
                deps.coordinator._clients=deps.adapters.database_client
                deps.adapters.password_login=lambda email,password,r=name:self.credentials('admin' if r=='rosago_admin_auth' else 'user')
            self.workers.append(app)
        self.browser=self.workers[0].test_client();self.other=self.workers[1].test_client()
        self.login=lambda realm:Contract.login(self,realm)
        self.sync=lambda source,target:Contract.sync(self,source,target)
        self.login('user');self.login('admin');Contract.assert_both(self,self.browser)
        cookie=self.browser.get_cookie('rosago_user_session_dev').value
        self.other.set_cookie('rosago_user_session_dev',cookie)
        token=self.browser.get('/auth/logout-token').json['csrf_token']
        result=self.browser.post('/logout',data={'csrf_token':token},headers={'Origin':'http://localhost'})
        self.assertEqual(result.status_code,503);self.assertIn(b'not yet confirmed',result.data)
        self.assertIsNone(self.browser.get_cookie('rosago_user_session_dev'))
        self.assertFalse(self.other.get('/auth/status').json['authenticated'])
        self.assertEqual(self.browser.get('/admin/account').status_code,200)
        signout.assert_called_once()
