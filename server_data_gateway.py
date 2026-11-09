"""INACTIVE local candidate for existing services, with Data API closed.

No environment activation, remote connection factory, service-role key or raw JWT
ingress. An opaque server session handle is resolved against the independent
ledger for EVERY operation. SQL runs under existing anon/authenticated RLS roles.
This library alone does not close the hosted Data API or protect Auth endpoints.
"""
from dataclasses import dataclass
import json
import os
import re
import time
import uuid

from postgrest.exceptions import APIError
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from externally_fenced_postgres import ExternalPgModel
from normal_auth_store import NormalAuthSession

ISSUER='https://jfaufpfzfhysqkhcdsrs.supabase.co/auth/v1'
TABLES=frozenset(('profiles','places','trips','trip_places','itinerary_drafts',
    'trip_itinerary','trip_stop_plans','admin_memberships','admin_destination_audit'))
RPC={
    'rosago_provider_session_current':((),False),
    'rosago_is_admin':((),False),
    'rosago_admin_operational_overview':(('p_query','p_offset'),False),
    'rosago_admin_mutate_destination':(('p_action','p_slug','p_expected_updated_at','p_values'),False),
    'rosago_admin_verify_destination_location':(('p_slug','p_expected_updated_at','p_values','p_evidence_ref'),False),
    'rosago_admin_apply_first_catalog_batch':((),False),
    'rosago_admin_hold_first_catalog_batch':((),False),
    'rosago_itinerary_draft_create':((),True),
    'rosago_itinerary_draft_update_preferences':(('p_draft_id','p_expected_revision','p_preferences'),True),
    'rosago_itinerary_draft_store_preview':(('p_draft_id','p_expected_revision','p_candidate_preview'),True),
    'rosago_itinerary_draft_adjust_preview':(('p_draft_id','p_expected_revision','p_preferences','p_candidate_preview'),True),
    'rosago_itinerary_draft_return_to_editing':(('p_draft_id','p_expected_revision'),True),
}

class GatewayDenied(APIError):
    def __init__(self):super().__init__({'code':'42501','message':'Data access denied.','details':None,'hint':None})

class GatewayUnavailable(APIError):
    def __init__(self):super().__init__({'code':'RG503','message':'Data operation unavailable or unconfirmed. Do not automatically retry changes.','details':None,'hint':None})

def identifier(value):
    if type(value) is not str or not re.fullmatch(r'[a-z][a-z0-9_]{0,62}',value):raise GatewayDenied()
    return sql.Identifier(value)

def parameter(value):return Jsonb(value) if type(value) in (dict,list) else value

def restricted_login(connection):
    attributes=connection.execute('SELECT rolsuper,rolcreatedb,rolcreaterole,rolinherit,rolreplication,rolbypassrls '
        'FROM pg_roles WHERE rolname=session_user').fetchone()
    return bool(attributes) and not any(attributes.values())

@dataclass(frozen=True,repr=False)
class DataResponse:
    data: object

class ServerDataGateway:
    def __init__(self,pool,realms):
        if set(realms)!={'user','admin'}:raise ValueError('Two independent realms required.')
        self.pool,self.realms,self.pid=pool,realms,os.getpid()

    def client(self,realm,handle):
        if realm not in self.realms or type(handle) is not str or not handle:raise GatewayDenied()
        return GatewayClient(self,realm,handle)

    def public_client(self):return GatewayClient(self,None,None)

    def claims(self,client):
        if client.realm is None:return {}
        snapshot=self.realms[client.realm].snapshot('auth',client.handle)
        record=snapshot.data.get('record') if snapshot.data else None
        if snapshot.meta is not None and snapshot.meta.get('busy') is not False:raise GatewayUnavailable()
        if snapshot.meta is not None and record is not None and snapshot.meta.get('generation')!=record.generation:raise GatewayUnavailable()
        if not isinstance(record,NormalAuthSession) or record.revoked or record.access_expires_at<=time.time():raise GatewayDenied()
        try:
            if str(uuid.UUID(record.user_id))!=record.user_id or str(uuid.UUID(record.session_id))!=record.session_id:raise ValueError()
        except (ValueError,TypeError,AttributeError):raise GatewayDenied() from None
        # Identity was established by the existing verified password-login flow,
        # then persisted encrypted and independently fenced. Never decode browser
        # headers/cookies into SQL claims or accept a JWT as an auth handle.
        return {'sub':record.user_id,'session_id':record.session_id,'iss':ISSUER,
            'aud':'authenticated','role':'authenticated','exp':int(record.access_expires_at)}

    def execute(self,query):
        try:
            if self.pid!=os.getpid():raise GatewayUnavailable()
            claims=self.claims(query.client)
            role='authenticated' if claims else 'anon'
            if not claims and (query.table_name!='places' or query.operation!='select'):raise GatewayDenied()
            statement,values,many=query.compile()
            with self.pool.connection(timeout=1) as connection:
                with connection.transaction():
                    # Reject privileged or inheriting login credentials before
                    # any role switch or application query. Pool must be post-fork.
                    if not restricted_login(connection):raise GatewayDenied()
                    connection.execute("SET LOCAL statement_timeout='1500ms'")
                    connection.execute("SET LOCAL lock_timeout='400ms'")
                    connection.execute("SET LOCAL idle_in_transaction_session_timeout='2500ms'")
                    connection.execute("SET LOCAL search_path=''")
                    connection.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(role)))
                    connection.execute("SELECT pg_catalog.set_config('request.jwt.claims',%s,true),"
                        "pg_catalog.set_config('request.jwt.claim.sub',%s,true)",(json.dumps(claims),claims.get('sub','')))
                    provider_current = (connection.execute('SELECT public.rosago_provider_session_current() current').fetchone()['current']
                                        if claims else True)
                    if type(provider_current) is not bool:
                        # Unknown is unavailable, not a confirmed revocation.
                        # Deny the operation without destroying valid local state.
                        raise GatewayUnavailable()
                    if provider_current is False:
                        # Match the normal coordinator: observed provider denial
                        # is terminal in the independent store, not a temporary
                        # check that a restored Auth row could later reverse.
                        ExternalPgModel(self.realms[query.client.realm],'auth').revoke(query.client.handle)
                        raise GatewayDenied()
                    # Recheck independent authority immediately before SQL.
                    # Existing RLS/RPC checks still enforce provider/ownership.
                    if claims and self.claims(query.client)!=claims:raise GatewayDenied()
                    rows=connection.execute(statement,values).fetchall()
                    data=[row['data'] for row in rows]
                    return DataResponse(data if many else data[0] if len(data)==1 else None)
        except GatewayDenied:raise
        except psycopg.errors.InsufficientPrivilege:raise GatewayDenied() from None
        except Exception:
            # No SQL diagnostics, DSNs, identities or credentials in exceptions.
            # In particular, never retry an unknown mutation result.
            raise GatewayUnavailable() from None

class SQLProviderSessionCheck:
    """Read-only caller-bound status path when Data API is disabled.

    The record comes only from verified login/encrypted authority-fenced state
    or its logout receipt. It never admits a data operation or accepts a JWT
    directly from an HTTP caller. False is not inferred from an expired JWT.
    """
    def __init__(self,pool):self.pool,self.pid=pool,os.getpid()
    def __call__(self,record,issuer,realm):
        try:
            if self.pid!=os.getpid() or issuer!=ISSUER or realm not in ('user','admin') or not isinstance(record,NormalAuthSession):return None
            if record.access_expires_at<=time.time() or any(str(uuid.UUID(v))!=v for v in (record.user_id,record.session_id)):return None
            claims={'iss':ISSUER,'sub':record.user_id,'session_id':record.session_id,
                'aud':'authenticated','role':'authenticated','exp':int(record.access_expires_at)}
            with self.pool.connection(timeout=1) as connection:
                with connection.transaction():
                    connection.execute('SET TRANSACTION READ ONLY')
                    if not restricted_login(connection):return None
                    connection.execute("SET LOCAL statement_timeout='1000ms'")
                    connection.execute("SET LOCAL lock_timeout='400ms'")
                    connection.execute('SET LOCAL ROLE authenticated')
                    connection.execute("SELECT pg_catalog.set_config('request.jwt.claims',%s,true),"
                        "pg_catalog.set_config('request.jwt.claim.sub',%s,true)",(json.dumps(claims),record.user_id))
                    value=connection.execute('SELECT public.rosago_provider_session_current() current').fetchone()['current']
                    return value if type(value) is bool else None
        except Exception:return None

class GatewayClient:
    def __init__(self,gateway,realm,handle):self.gateway,self.realm,self.handle=gateway,realm,handle
    def table(self,name):
        if name not in TABLES:raise GatewayDenied()
        return Query(self,table_name=name)
    def rpc(self,name,params=None):
        if name not in RPC:raise GatewayDenied()
        return Query(self,rpc_name=name,params={} if params is None else params)

class Query:
    def __init__(self,client,*,table_name=None,rpc_name=None,params=None):
        self.client,self.table_name,self.rpc_name=client,table_name,rpc_name
        self.operation='rpc' if rpc_name else 'select';self.params=params
        self.columns=[];self.filters=[];self.ordering=[];self.maximum=200;self.offset=0;self.changes=None
    def select(self,projection):
        if type(projection) is not str:raise GatewayDenied()
        self.columns=projection.split(',')
        for name in self.columns:identifier(name)
        if not 1<=len(self.columns)<=40:raise GatewayDenied()
        return self
    def eq(self,name,value):identifier(name);self.filters.append((name,value));return self
    def limit(self,count):
        if type(count) is not int or not 1<=count<=2000:raise GatewayDenied()
        self.maximum=count;return self
    def range(self,start,end):
        if type(start) is not int or type(end) is not int or not 0<=start<=end<=2147483646:raise GatewayDenied()
        self.offset=start;return self.limit(end-start+1)
    def order(self,name,*,desc=False):
        identifier(name)
        if type(desc) is not bool:raise GatewayDenied()
        self.ordering.append((name,desc));return self
    def retry(self,enabled):
        if enabled is not False:raise GatewayDenied()
        return self
    def update(self,changes,*,returning=None):
        if self.table_name!='profiles' or type(changes) is not dict or not changes or set(changes)-{'first_name','last_name'}:raise GatewayDenied()
        self.operation='update';self.changes=dict(changes);return self
    def execute(self):return self.client.gateway.execute(self)
    def compile(self):
        if self.rpc_name:
            names,many=RPC[self.rpc_name]
            if type(self.params) is not dict or set(self.params)!=set(names):raise GatewayDenied()
            args=sql.SQL(',').join(sql.SQL('{} => %s').format(identifier(name)) for name in names)
            function=sql.SQL('{}({})').format(sql.Identifier('public',self.rpc_name),args)
            text=(sql.SQL('SELECT pg_catalog.to_jsonb(result) data FROM {} result').format(function) if many
                  else sql.SQL('SELECT pg_catalog.to_jsonb({}) data').format(function))
            return text,[parameter(self.params[name]) for name in names],many
        if not self.columns or len(self.filters)>8 or len(self.ordering)>4:raise GatewayDenied()
        projection=sql.SQL(',').join(identifier(name) for name in self.columns)
        where=sql.SQL(' AND ').join(sql.SQL('{} IS NOT DISTINCT FROM %s').format(identifier(name)) for name,_ in self.filters)
        values=[parameter(value) for _,value in self.filters]
        if self.operation=='update':
            if not self.filters:raise GatewayDenied()
            changes=sql.SQL(',').join(sql.SQL('{}=%s').format(identifier(name)) for name in self.changes)
            inner=sql.SQL('UPDATE {} SET {} WHERE {} RETURNING {}').format(sql.Identifier('public',self.table_name),changes,where,projection)
            return sql.SQL('WITH changed AS ({}) SELECT pg_catalog.to_jsonb(changed) data FROM changed').format(inner),[parameter(v) for v in self.changes.values()]+values,True
        inner=sql.SQL('SELECT {} FROM {}').format(projection,sql.Identifier('public',self.table_name))
        if self.filters:inner+=sql.SQL(' WHERE ')+where
        if self.ordering:inner+=sql.SQL(' ORDER BY ')+sql.SQL(',').join(sql.SQL('{} {}').format(identifier(name),sql.SQL('DESC' if desc else 'ASC')) for name,desc in self.ordering)
        inner+=sql.SQL(' LIMIT %s OFFSET %s');values.extend((self.maximum,self.offset))
        return sql.SQL('SELECT pg_catalog.to_jsonb(result) data FROM ({}) result').format(inner),values,True
