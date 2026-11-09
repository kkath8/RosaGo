"""Disposable local database + actual workerd. No real JWTs/accounts/provider."""
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from unittest.mock import Mock,patch

import psycopg
from externally_fenced_postgres import ExternalPgRealm,ExternalPgModel
from independent_authority_fixture import IndependentAuthorityFixture
from postgres_session_store import isolated_pool
from session_crypto import SessionCipher
from server_data_gateway import ServerDataGateway,GatewayDenied,GatewayUnavailable,SQLProviderSessionCheck,ISSUER
from normal_auth_coordinator import AuthenticatedContext,SupabaseAdapters
from durable_session_logout import DurableLogout

DSN=os.environ.get('ROSAGO_TEST_POSTGRES_DSN');OPERATOR=os.environ.get('ROSAGO_TEST_POSTGRES_OPERATOR_DSN');GATEWAY=os.environ.get('ROSAGO_TEST_GATEWAY_DSN')
ACTORS={'user':'f0000000-0000-4000-8000-000000000001','admin':'f0000000-0000-4000-8000-000000000002'}

@unittest.skipUnless(DSN and OPERATOR and GATEWAY,'Explicit owned local lab required')
class GatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory(prefix='rosago-gateway-authority-')
        cls.service=IndependentAuthorityFixture(Path(cls.temporary.name)/'authority.sqlite','gateway_lab')
        cls.session_pool=isolated_pool(DSN);cls.gateway_pool=isolated_pool(GATEWAY)
        cls.operator=psycopg.connect(OPERATOR,autocommit=True)
        cls.key=secrets.token_bytes(32);cipher=SessionCipher({'test':cls.key},'test')
        cls.realms={r:ExternalPgRealm(cls.session_pool,cipher,'gateway_lab',r,r+'_epoch',authority=cls.service.client()) for r in ('user','admin')}
        cls.gateway=ServerDataGateway(cls.gateway_pool,cls.realms)
    @classmethod
    def tearDownClass(cls):
        cls.gateway_pool.close();cls.session_pool.close();cls.operator.close();cls.service.close();cls.temporary.cleanup()
    def setUp(self):
        self.handles={};self.records={};self.clients={}
        for realm,actor in ACTORS.items():
            sid=str(uuid.uuid4());self.operator.execute('INSERT INTO auth.sessions(id,user_id) VALUES(%s,%s)',(sid,actor))
            model=ExternalPgModel(self.realms[realm],'auth')
            handle=model.create(user_id=actor,user_email=realm+'@example.invalid',access_token='synthetic-'+realm,
                refresh_token='synthetic-refresh',access_expires_at=time.time()+3600,session_id=sid)
            self.handles[realm]=handle;self.records[realm]=model.resolve(handle);self.clients[realm]=self.gateway.client(realm,handle)
        self.check=SQLProviderSessionCheck(self.gateway_pool)
    def test_existing_profile_admin_services_and_published_visibility_keep_rls(self):
        from profile_service import get_own_profile,update_own_profile
        from admin_places_service import get_destination
        context=AuthenticatedContext(self.handles['user'],ACTORS['user'],'user@example.invalid',self.clients['user'])
        self.assertEqual(get_own_profile(context).id,ACTORS['user'])
        self.assertEqual(update_own_profile(context,first_name='Synthetic',last_name='User').first_name,'Synthetic')
        self.assertEqual(self.clients['user'].table('places').select('slug').order('slug').execute().data,[{'slug':'evaluation-garden'}])
        admin=AuthenticatedContext(self.handles['admin'],ACTORS['admin'],'admin@example.invalid',self.clients['admin'],'admin')
        self.assertEqual(get_destination(admin,'evaluation-draft').status,'draft')
        self.assertTrue(self.clients['admin'].rpc('rosago_is_admin').execute().data)
        self.assertFalse(self.clients['user'].rpc('rosago_is_admin').execute().data)
        self.assertEqual(self.clients['admin'].rpc('rosago_admin_operational_overview',{'p_query':'','p_offset':0}).execute().data['users_total'],2)
        public=self.gateway.public_client()
        self.assertEqual(public.table('places').select('slug').execute().data,[{'slug':'evaluation-garden'}])
        with self.assertRaises(GatewayDenied):public.table('profiles').select('id').execute()
    def test_privileged_rpc_and_profile_ownership_stay_enforced(self):
        self.assertEqual(self.clients['user'].table('profiles').select('id').eq('id',ACTORS['admin']).execute().data,[])
        self.assertEqual(self.clients['user'].table('profiles').update({'first_name':'Cannot change'}).select('id').eq('id',ACTORS['admin']).execute().data,[])
        with self.assertRaises(GatewayDenied):self.clients['user'].rpc('rosago_admin_operational_overview',{'p_query':'','p_offset':0}).execute()
        with self.assertRaises(GatewayDenied):self.clients['admin'].rpc('rosago_admin_mutate_destination_unlogged',{}).execute()
        self.assertTrue(self.clients['user'].rpc('rosago_itinerary_draft_create').execute().data)
    def test_auth_row_restore_reproduces_current_sql_vulnerability_but_cannot_revive_gateway_handle(self):
        record=self.records['user'];model=ExternalPgModel(self.realms['user'],'auth')
        self.assertTrue(self.check(record,ISSUER,'user'))
        self.operator.execute('DELETE FROM auth.sessions WHERE id=%s',(record.session_id,))
        self.assertFalse(self.check(record,ISSUER,'user'))
        model.revoke(self.handles['user'])
        self.operator.execute('INSERT INTO auth.sessions(id,user_id) VALUES(%s,%s)',(record.session_id,record.user_id))
        # Explicit negative finding: current SQL accepts this resurrected row.
        self.assertTrue(self.check(record,ISSUER,'user'))
        with self.assertRaises(GatewayDenied):self.clients['user'].table('profiles').select('id').execute()
        self.service.restart()
        with self.assertRaises(GatewayDenied):self.clients['user'].table('profiles').select('id').execute()
        with self.assertRaises(GatewayDenied):self.gateway.client('user','synthetic.old.jwt').table('profiles').select('id').execute()
        self.assertTrue(self.clients['admin'].rpc('rosago_is_admin').execute().data)
    def test_provider_logout_journal_uses_status_sql_with_data_api_unavailable(self):
        import httpx
        requests=[]
        def provider(request):
            requests.append(request)
            self.assertEqual(request.url.path,'/auth/v1/logout');self.assertEqual(request.url.params['scope'],'local')
            self.operator.execute('DELETE FROM auth.sessions WHERE id=%s',(self.records['user'].session_id,))
            return httpx.Response(204)
        adapter=SupabaseAdapters(ISSUER.removesuffix('/auth/v1'),'sb_publishable_synthetic',
            http_factory=lambda **kw:httpx.Client(transport=httpx.MockTransport(provider),**kw))
        handle=self.handles['user'];web=ExternalPgModel(self.realms['user'],'web').create({'auth_session_id':handle})
        logout=DurableLogout(self.realms,issuer=ISSUER,sign_out=adapter.sign_out_current_session,session_check=self.check)
        self.assertTrue(logout('user',web));self.assertEqual(len(requests),1)
        self.assertTrue(logout('user',web));self.assertEqual(len(requests),1)
        with self.assertRaises(GatewayDenied):self.clients['user'].table('profiles').select('id').execute()
        self.operator.execute('INSERT INTO auth.sessions(id,user_id) VALUES(%s,%s)',(self.records['user'].session_id,ACTORS['user']))
        self.assertTrue(self.check(self.records['user'],ISSUER,'user')) # still a direct-provider recovery blocker
        with self.assertRaises(GatewayDenied):self.clients['user'].table('profiles').select('id').execute()

    def test_observed_provider_denial_is_terminal_even_when_auth_row_returns(self):
        record=self.records['user']
        self.operator.execute('DELETE FROM auth.sessions WHERE id=%s',(record.session_id,))
        with self.assertRaises(GatewayDenied):self.clients['user'].table('profiles').select('id').execute()
        self.operator.execute('INSERT INTO auth.sessions(id,user_id) VALUES(%s,%s)',(record.session_id,record.user_id))
        self.assertTrue(self.check(record,ISSUER,'user'))
        self.assertIsNone(ExternalPgModel(self.realms['user'],'auth').resolve(self.handles['user']))
        self.service.restart()
        with self.assertRaises(GatewayDenied):self.clients['user'].table('profiles').select('id').execute()
    def test_pool_identity_isolation_and_no_api_private_storage_access(self):
        self.clients['admin'].table('profiles').select('id').execute()
        self.assertEqual(self.clients['user'].table('profiles').select('id').execute().data,[{'id':ACTORS['user']}])
        with self.gateway_pool.connection() as c:
            self.assertEqual(c.execute('SELECT current_user u').fetchone()['u'],'rosago_gateway_lab')
            for statement in ('SELECT * FROM rosago_session.payloads','SELECT * FROM auth.users','SELECT * FROM public.profiles'):
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):c.execute(statement)
        with patch('server_data_gateway.os.getpid',return_value=self.gateway.pid+1):
            with self.assertRaises(GatewayUnavailable):self.clients['user'].table('profiles').select('id').execute()
    def test_bad_scope_unknown_operation_and_expired_record_deny(self):
        with self.assertRaises(GatewayDenied):self.gateway.client('admin',self.handles['user']).table('profiles').select('id').execute()
        for name in ('auth.users','places;DROP TABLE profiles'):
            with self.assertRaises(GatewayDenied):self.clients['admin'].table(name)
        with self.assertRaises(GatewayDenied):self.clients['user'].table('profiles').select('id').eq('id OR true','x')
        self.assertIsNone(self.check(replace(self.records['user'],access_expires_at=time.time()-1),ISSUER,'user'))
        self.assertIsNone(self.check(self.records['user'],'https://other.invalid','user'))
        model=ExternalPgModel(self.realms['user'],'auth');lease,record=model.reserve_refresh(self.handles['user'])
        with self.assertRaises(GatewayUnavailable):self.clients['user'].table('profiles').select('id').execute()
        self.assertTrue(model.release_refresh(self.handles['user'],lease))
        with patch.object(self.gateway,'claims',side_effect=RuntimeError('synthetic private failure')):
            with self.assertRaises(GatewayUnavailable) as error:self.clients['user'].table('profiles').select('id').execute()
            self.assertNotIn('private failure',str(error.exception))

    def test_cryptographically_valid_old_jwt_is_not_revoked_by_row_deletion(self):
        import jwt
        record=self.records['user'];key=secrets.token_bytes(64)
        claims={'sub':record.user_id,'session_id':record.session_id,'iss':ISSUER,
            'aud':'authenticated','role':'authenticated','exp':int(record.access_expires_at)}
        token=jwt.encode(claims,key,algorithm='HS256') # synthetic key; no provider signing secret
        def verified():return jwt.decode(token,key,algorithms=['HS256'],audience='authenticated',issuer=ISSUER)
        self.assertEqual(verified()['session_id'],record.session_id)
        self.operator.execute('DELETE FROM auth.sessions WHERE id=%s',(record.session_id,))
        self.assertEqual(verified()['session_id'],record.session_id)
        self.assertFalse(self.check(record,ISSUER,'user'))
        ExternalPgModel(self.realms['user'],'auth').revoke(self.handles['user'])
        self.operator.execute('INSERT INTO auth.sessions(id,user_id) VALUES(%s,%s)',(record.session_id,record.user_id))
        self.assertEqual(verified()['session_id'],record.session_id)
        self.assertTrue(self.check(record,ISSUER,'user'))
        with self.assertRaises(GatewayDenied):self.gateway.client('user',token).table('profiles').select('id').execute()
        with self.assertRaises(jwt.InvalidSignatureError):
            jwt.decode(token,secrets.token_bytes(64),algorithms=['HS256'],audience='authenticated',issuer=ISSUER)

    def test_two_independent_processes_recreate_pools_and_preserve_terminal_revocation(self):
        source="""
import json,sys
from externally_fenced_postgres import ExternalPgRealm
from postgres_session_store import isolated_pool
from session_crypto import SessionCipher
from authority_http_transport import AuthorityHTTPTransport
from protected_session_authority import ProtectedRevisionAuthority,AuthorityBinding
from server_data_gateway import ServerDataGateway,GatewayDenied
c=json.load(sys.stdin);sp=isolated_pool(c['session_dsn']);gp=isolated_pool(c['gateway_dsn'])
t=AuthorityHTTPTransport(c['url'],c['token'],local_test=True)
try:
 a=ProtectedRevisionAuthority(t,AuthorityBinding(**c['binding']),response_budget=1.5)
 cipher=SessionCipher({'test':bytes.fromhex(c['key'])},'test')
 realms={r:ExternalPgRealm(sp,cipher,'gateway_lab',r,r+'_epoch',authority=a) for r in ('user','admin')}
 g=ServerDataGateway(gp,realms)
 try:result={'allowed':True,'rows':g.client('user',c['handle']).table('profiles').select('id').execute().data}
 except GatewayDenied:result={'allowed':False}
 print(json.dumps(result))
finally:t.close();sp.close();gp.close()
"""
        from dataclasses import asdict
        config={'session_dsn':DSN,'gateway_dsn':GATEWAY,'url':self.service.url,'token':self.service.token,
            'binding':asdict(self.service.binding),'key':self.key.hex(),'handle':self.handles['user']}
        env={k:os.environ[k] for k in ('PATH','SystemRoot','TEMP','TMP','PATHEXT') if k in os.environ}
        def child(_):
            run=subprocess.run([sys.executable,'-c',source],input=json.dumps(config),capture_output=True,text=True,
                env=env,cwd=Path(__file__).resolve().parents[1],timeout=20)
            self.assertEqual(run.returncode,0,'Synthetic worker failed; private output withheld')
            return json.loads(run.stdout)
        with ThreadPoolExecutor(max_workers=2) as workers:
            self.assertEqual(list(workers.map(child,range(2))),[{'allowed':True,'rows':[{'id':ACTORS['user']}]}]*2)
        ExternalPgModel(self.realms['user'],'auth').revoke(self.handles['user'])
        self.service.restart()
        with ThreadPoolExecutor(max_workers=2) as workers:
            self.assertEqual(list(workers.map(child,range(2))),[{'allowed':False}]*2)
