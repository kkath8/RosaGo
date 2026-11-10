"""TEST ONLY signing/SQL/authority doubles. Never imported by application code."""
import base64
from contextlib import contextmanager
import hashlib
import json
from threading import RLock
import time
from unittest.mock import Mock

import jwt
from cryptography.hazmat.primitives import serialization
from psycopg.conninfo import make_conninfo
from production_session_runtime import CHECKS,source_hashes,bundle_hash


def environment(private,binding=None):
    env=dict(ROSAGO_AUTH_MODE='production',ROSAGO_SESSION_BACKEND='independent-postgres',
        SUPABASE_URL='https://brnkigrrqdrywahvcbvc.supabase.co',SUPABASE_KEY='sb_publishable_synthetic_fixture',
        FLASK_SECRET_KEY='synthetic-flask-'+('s'*40),ROSAGO_PUBLIC_ORIGIN='https://fixture.example.invalid',
        ROSAGO_PROXY_HOPS='1',ROSAGO_PROXY_HEADERS_SANITIZED='true',
        ROSAGO_SESSION_KEYRING=json.dumps(dict(current='test',keys=dict(test=base64.b64encode(b'x'*32).decode()))),
        ROSAGO_SESSION_NAMESPACE='production_fixture',ROSAGO_USER_SESSION_EPOCH='user_epoch_fixture',
        ROSAGO_ADMIN_SESSION_EPOCH='admin_epoch_fixture',ROSAGO_AUTHORITY_ID='authority_fixture_id',
        ROSAGO_AUTHORITY_INCARNATION='incarnation_fixture',ROSAGO_AUTHORITY_MIN_SEQUENCE='0',
        ROSAGO_AUTHORITY_ORIGIN='https://fixture.example.workers.dev',ROSAGO_AUTHORITY_CLIENT_TOKEN='m'*40,
        ROSAGO_PROVIDER_ENROLL_TOKEN='e'*40,ROSAGO_PROVIDER_CHECK_TOKEN='c'*40,ROSAGO_PROVIDER_REVOKE_TOKEN='r'*40,
        ROSAGO_SESSION_DATABASE_URL=make_conninfo(host='private-db.example.invalid',port=5432,dbname='rosago_sessions',
            user='rosago_session_app',password='synthetic-database-'+('x'*40),sslmode='verify-full',sslrootcert='system'))
    if binding:
        env['ROSAGO_AUTHORITY_ID']=binding['authority_id'];env['ROSAGO_AUTHORITY_INCARNATION']=binding['incarnation']
    env['ROSAGO_SECURITY_RELEASE_VERIFY_KEY']=private.public_key().public_bytes(serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    claims=claims_for(env)
    env['ROSAGO_SECURITY_RELEASE_JWT']=jwt.encode(claims,private,algorithm='RS256')
    return env,claims


def claims_for(env):
    now=int(time.time())
    sha=lambda v:hashlib.sha256(v.encode()).hexdigest()
    return dict(iss='rosago-security-release',aud='rosago-production-sessions-v1',iat=now,nbf=now-1,exp=now+3600,
        jti='synthetic_release_fixture',sub='brnkigrrqdrywahvcbvc',project_ref='brnkigrrqdrywahvcbvc',
        public_origin=env['ROSAGO_PUBLIC_ORIGIN'],
        store=dict(host='private-db.example.invalid',port='5432',database='rosago_sessions',role='rosago_session_app',
            owner='rosago_session_owner',schema='rosago_session',table='payloads'),
        authority=dict(origin=env['ROSAGO_AUTHORITY_ORIGIN'],authority_id=env['ROSAGO_AUTHORITY_ID'],
            incarnation=env['ROSAGO_AUTHORITY_INCARNATION'],minimum_sequence=0,namespace=env['ROSAGO_SESSION_NAMESPACE'],
            epochs=dict(user=env['ROSAGO_USER_SESSION_EPOCH'],admin=env['ROSAGO_ADMIN_SESSION_EPOCH'])),
        key_fingerprints=dict(public_key=sha(env['SUPABASE_KEY']),flask_secret=sha(env['FLASK_SECRET_KEY']),
            keyring=sha(json.dumps(json.loads(env['ROSAGO_SESSION_KEYRING']),sort_keys=True,separators=(',',':')))),
        sources=source_hashes(),bundle_sha256=bundle_hash(),checks={name:True for name in CHECKS},evidence_level='real-provider-qualified')


class Pool:
    def __init__(self):
        self.data={};self.lock=RLock();self.close=Mock();self.available=True;self.queries=[]
        self.attributes=dict(role='rosago_session_app',login='rosago_session_app',owner='rosago_session_owner',
            rolsuper=False,rolbypassrls=False,rolcreaterole=False,rolcreatedb=False,rolreplication=False,rolinherit=False,
            api_access=False,public_access=False,relrowsecurity=True,relforcerowsecurity=True,logged=True,schema_use=True,rw=True,
            can_login=True,no_memberships=True,database_create=False,public_create=False)
    @contextmanager
    def connection(self,**kw):
        if not self.available:raise TimeoutError('synthetic-private-error')
        with self.lock:yield self
    @contextmanager
    def transaction(self):yield self
    def execute(self,sql,args=None):
        self.queries.append(sql);row=None
        if 'pg_roles' in sql:row=self.attributes
        elif 'fsync' in sql:row=dict(fsync='on',standby=False)
        elif 'clock_timestamp' in sql:row=dict(t=time.time())
        elif sql.startswith('SELECT ciphertext,expires'):row=self.data.get(args[0])
        elif sql.startswith('SELECT ciphertext '):row=self.data.get(args[0])
        elif sql.startswith('INSERT INTO rosago_session.payloads'):self.data[args[0]]=dict(ciphertext=args[1],expires=args[2])
        elif sql.startswith('DELETE FROM rosago_session.payloads WHERE key=%s'):
            if self.data.get(args[0],{}).get('ciphertext')==args[1]:self.data.pop(args[0],None)
        return Mock(fetchone=Mock(return_value=row),fetchall=Mock(return_value=[]))


class ProviderTransport:
    def __init__(self,operation,state):self.operation,self.state=operation,state;self.close=Mock()
    def exchange(self,request):
        sid=request['sid'];record=self.state.setdefault(sid,dict(known=False,revoked=False,expired=False))
        if self.operation=='enroll' and not record['revoked']:record['known']=True
        if self.operation=='revoke':record.update(known=True,revoked=True)
        return request|record|dict(active=record['known'] and not record['revoked'] and not record['expired'],now=time.time())
