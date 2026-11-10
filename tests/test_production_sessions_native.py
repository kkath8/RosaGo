"""Real local PostgreSQL/SQLite persistence, synthetic provider and signed release.

Requires the exact throwaway fixture supplied by qualify_production_sessions_local.
No TLS or managed-provider qualification is claimed by a numeric-loopback test pool.
"""
from dataclasses import asdict
import os
from pathlib import Path
import secrets
import json
import subprocess
import sys
import re
import tempfile
import time
import unittest
from unittest.mock import patch

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from cryptography.hazmat.primitives.asymmetric import rsa
from production_runtime_fixture import environment,ProviderTransport
from independent_authority_fixture import IndependentAuthorityFixture
from normal_auth_coordinator import VerifiedLoginCredentials
import production_session_runtime as production

DSN=os.environ.get('ROSAGO_PRODUCTION_TEST_STORE_DSN')
OPERATOR=os.environ.get('ROSAGO_PRODUCTION_TEST_OPERATOR_DSN')


class LongEpochAuthority(IndependentAuthorityFixture):
    def control(self,operation,**arguments):
        if operation=='initialize':arguments['config']['epochs']=dict(user='user_epoch_fixture',admin='admin_epoch_fixture')
        return super().control(operation,**arguments)


@unittest.skipUnless(DSN and OPERATOR,'Owned disposable PostgreSQL fixture required')
class NativeProductionSessions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.private=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='rosago-production-native-');self.addCleanup(self.temp.cleanup)
        self.namespace='production_'+secrets.token_hex(8)
        self.authority=LongEpochAuthority(Path(self.temp.name)/'authority.sqlite',self.namespace);self.addCleanup(self.authority.close)
        self.operator=psycopg.connect(OPERATOR,autocommit=True);self.addCleanup(self.operator.close)
        self.env,self.claims=environment(self.private,dict(authority_id=self.authority.binding.authority_id,incarnation=self.authority.binding.incarnation))
        self.env['ROSAGO_SESSION_NAMESPACE']=self.namespace;self.claims['authority']['namespace']=self.namespace
        import jwt
        self.env['ROSAGO_SECURITY_RELEASE_JWT']=jwt.encode(self.claims,self.private,algorithm='RS256')
        self.settings=production.validate_environment(self.env)
        self.provider={};self.workers=[];self.addCleanup(lambda:self.operator.execute('DELETE FROM rosago_session.payloads WHERE key LIKE %s',(self.namespace+':%',)))
    def pool(self,settings):
        # Hard-restricted by the owning harness; this injection never exists in env.
        from psycopg.conninfo import conninfo_to_dict
        assert conninfo_to_dict(DSN)['host']=='127.0.0.1'
        value=ConnectionPool(DSN,min_size=1,max_size=2,timeout=1,open=False,
            kwargs={'autocommit':True,'prepare_threshold':None,'row_factory':dict_row,'client_encoding':'UTF8'})
        value.open(wait=True,timeout=2)
        return value
    def transport(self,url,token,**kwargs):
        operation=url.rsplit('/',1)[1]
        return self.authority.client().transport if operation=='authority' else ProviderTransport(operation,self.provider)
    def worker(self):
        with patch.dict(os.environ,{},clear=True):
            worker=production.open_worker(self.settings,pool_factory=self.pool,transport_factory=self.transport)
        self.workers.append(worker);self.addCleanup(worker.close);return worker
    def model(self,worker,kind='auth',realm='user'):return worker.runtime.model_factory(worker.runtime.realms[realm],kind)
    def credentials(self):return VerifiedLoginCredentials('11111111-1111-4111-8111-111111111111','synthetic@example.invalid',
        'synthetic-access','synthetic-refresh',time.time()+3600,'22222222-2222-4222-8222-222222222222')
    def test_encrypted_cross_worker_and_new_worker_after_authority_restart(self):
        first=self.worker();handle=self.model(first).create(**asdict(self.credentials()))
        snap=first.runtime.realms['user'].snapshot('auth',handle)
        self.assertNotIn(b'synthetic-access',snap.raw);self.assertNotIn(b'synthetic-refresh',snap.raw)
        second=self.worker();self.assertIsNotNone(self.model(second).resolve(handle));first.close()
        child_code='''import json,sys,os
from unittest.mock import Mock
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row
import production_session_runtime as p
from authority_http_transport import AuthorityHTTPTransport
v=json.load(sys.stdin)
# The subprocess already inherits only PATH/SystemRoot/temp variables. Windows
# libpq needs SystemRoot on its first connection; do not erase OS prerequisites.
diagnostic={}
original_verify=p._verify_pool
def verify(pool):
 try:return original_verify(pool)
 except Exception as error:
  diagnostic['failure_type']=type(error).__name__
  tb=error.__traceback__
  while tb:
   row=tb.tb_frame.f_locals.get('row') if tb.tb_frame.f_code.co_name=='_verify_pool' else None
   if isinstance(row,dict):
    diagnostic['flags']={k:val for k,val in row.items() if type(val) is bool}
    diagnostic['identity_types']={k:type(row.get(k)).__name__ for k in ('role','login','owner')}
   tb=tb.tb_next
  raise
p._verify_pool=verify
try:s=p.validate_environment(v['environment'])
except Exception:
 print(json.dumps({'stage':'configuration'}));raise SystemExit(1)
def pool(_):
 value=ConnectionPool(v['dsn'],min_size=1,max_size=2,open=False,kwargs={'autocommit':True,'prepare_threshold':None,'row_factory':dict_row,'client_encoding':'UTF8'})
 value.open(wait=True,timeout=2)
 return value
def transport(url,token,**kw):
 if url.endswith('/authority'):return AuthorityHTTPTransport(v['authority_url'],v['authority_token'],local_test=True)
 return Mock(exchange=Mock(side_effect=AssertionError('Provider not used by storage-only test')),close=Mock())
try:w=p.open_worker(s,pool_factory=pool,transport_factory=transport)
except Exception:
 print(json.dumps({'stage':'infrastructure',**diagnostic}));raise SystemExit(2)
try:print(json.dumps({'visible':w.runtime.model_factory(w.runtime.realms['user'],'auth').resolve(v['handle']) is not None}))
finally:w.close()
'''
        private_env={k:os.environ[k] for k in ('PATH','SystemRoot','TEMP','TMP','PATHEXT') if k in os.environ}
        child=subprocess.run([sys.executable,'-c',child_code],input=json.dumps(dict(environment=self.env,dsn=DSN,
            authority_url=self.authority.url,authority_token=self.authority.token,handle=handle)),
            capture_output=True,text=True,env=private_env,cwd=Path(__file__).resolve().parents[1],timeout=20)
        diagnostic=json.loads(child.stdout) if child.stdout.startswith('{"stage":') else {'stage':'before_report'}
        diagnostic['phases']=re.findall(r'production_session_startup stage=([a-z_]+)',child.stderr)
        self.assertEqual(child.returncode,0,json.dumps(diagnostic))
        self.assertTrue(json.loads(child.stdout)['visible'])
        self.authority.restart()
        restarted=self.worker();self.assertIsNotNone(self.model(restarted).resolve(handle))
        self.assertIsNone(self.model(restarted,realm='admin').resolve(handle))
    def test_revocation_survives_restored_ciphertext_and_new_worker(self):
        first=self.worker();handle=self.model(first).create(**asdict(self.credentials()))
        snap=first.runtime.realms['user'].snapshot('auth',handle)
        self.assertTrue(self.model(first).revoke(handle))
        self.operator.execute('INSERT INTO rosago_session.payloads VALUES(%s,%s,%s) ON CONFLICT(key) DO UPDATE '
            'SET ciphertext=excluded.ciphertext,expires=excluded.expires',(snap.key,snap.raw,snap.meta['expires']))
        self.authority.restart();self.assertIsNone(self.model(self.worker()).resolve(handle))
    def test_shared_recovery_consumption_and_database_runtime_role_denial(self):
        first=self.worker();second=self.worker()
        grants=self.model(first,'grants');handle=grants.issue('subject','synthetic-reset',time.time()+300,'synthetic-token')
        self.assertTrue(self.model(second,'grants').valid(handle));grants.revoke(handle)
        self.authority.restart();self.assertFalse(self.model(self.worker(),'grants').valid(handle))
        with first.pool.connection() as connection:
            with self.assertRaises(psycopg.Error):connection.execute('ALTER TABLE rosago_session.payloads DISABLE ROW LEVEL SECURITY')
            with self.assertRaises(psycopg.Error):connection.execute('SET ROLE rosago_session_owner')
    def test_independent_authority_closure_and_short_record_expiry(self):
        worker=self.worker();backend=worker.runtime.realms['user']
        handle='synthetic-short-record';snap=backend.snapshot('web',handle)
        backend.write(snap,{'values':{},'version':0},snap.now+2)
        time.sleep(2.2)
        self.assertIsNone(self.model(worker,'web').read(handle))
        self.authority.control('block');self.assertFalse(worker.readiness())


if __name__=='__main__':unittest.main()
