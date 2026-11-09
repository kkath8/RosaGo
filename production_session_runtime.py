"""Durable production composition. No bootstrap, migrations or memory fallback.

Ciphertext lives in a separate PostgreSQL service. The independent HTTPS ledger
owns revisions, revocation and recovery fencing. A signed, source-bound security
release is required; neither a config flag nor risk acknowledgement replaces it.
"""
import base64
from dataclasses import dataclass
import hashlib
import ipaddress
import json
import logging
import os
from pathlib import Path
import re
import time
from types import MappingProxyType
from urllib.parse import urlsplit

import jwt
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from psycopg.conninfo import conninfo_to_dict,make_conninfo
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from authority_http_transport import AuthorityHTTPTransport
from protected_session_authority import AuthorityBinding,ProtectedRevisionAuthority
from externally_fenced_postgres import ExternalPgRealm,ExternalPgModel
from record_session_store import RedisChallenges
from independent_provider_sessions import IndependentProviderSessions,IndependentProviderAdapters
from durable_session_logout import DurableLogout
from normal_auth_coordinator import SupabaseAdapters
from session_crypto import SessionCipher
from session_realms import SessionStorageUnavailable
from shared_session_runtime import LocalSessionRuntime
from public_auth_security import validate_public_origin

ROOT=Path(__file__).resolve().parent
PROJECTS=frozenset(('brnkigrrqdrywahvcbvc','jfaufpfzfhysqkhcdsrs'))
SOURCES=('production_session_runtime.py','session_realms.py','production_wsgi.py','app.py',
    'shared_session_runtime.py','externally_fenced_postgres.py','record_session_store.py',
    'redis_session_flask.py','session_crypto.py','protected_session_authority.py',
    'authority_http_transport.py','independent_provider_sessions.py','durable_session_logout.py',
    'normal_auth_coordinator.py','normal_auth_flask.py','admin_session_flask.py',
    'admin_authorization_service.py','public_auth_security.py','recovery_helpers.py',
    'recovery_transport.py','email_verification.py','user_csrf.py','gunicorn.conf.py',
    'requirements.txt','requirements-render.txt')
CHECKS=frozenset(('durable_shared_store','realm_isolation','expiry','logout_revocation',
    'password_reset_invalidation','provider_revocation','direct_api_replay',
    'auth_restore_quarantine','recovery_fencing','multi_worker_restart','proxy_tls','admin_authorization'))


def source_hashes():
    return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in SOURCES}


def bundle_hash():
    paths=set(ROOT.glob('*.py'))
    paths.update((ROOT/'templates').rglob('*.html'))
    paths.update((ROOT/'static/js').rglob('*.js'))
    values={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
    return _hash(json.dumps(values,sort_keys=True,separators=(',',':')))


def _object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError()
        result[key]=value
    return result


def _hash(value):return hashlib.sha256(value.encode()).hexdigest()


@dataclass(frozen=True,repr=False)
class ProductionSettings:
    url: str
    public_key: str
    origin: str
    conninfo: str
    cipher: object
    namespace: str
    epochs: object
    binding: AuthorityBinding
    authority_origin: str
    tokens: object
    deadline: int
    not_before: int
    release_id: str
    max_connections: int


def validate_environment(environment):
    """Offline checks only. Never logs inputs or retains a secret-bearing cause."""
    try:
        if (environment.get('ROSAGO_AUTH_MODE')!='production'
                or environment.get('ROSAGO_SESSION_BACKEND')!='independent-postgres'
                or environment.get('FLASK_DEBUG') not in (None,'','0','false')
                or environment.get('FLASK_ENV')
                or environment.get('ROSAGO_LOCAL_HTTPS_QUALIFICATION')=='true'
                or environment.get('ROSAGO_CATALOG_PREVIEW')=='true'
                or any(v and (k.startswith('PG') or k in ('GUNICORN_CMD_ARGS','LOCAL_TEST_ONLY')) for k,v in environment.items())):
            raise ValueError()
        pem=environment['ROSAGO_SECURITY_RELEASE_VERIFY_KEY'].encode()
        key=load_pem_public_key(pem)
        if not isinstance(key,RSAPublicKey) or key.key_size<2048:raise ValueError()
        token=environment['ROSAGO_SECURITY_RELEASE_JWT']
        if len(token)>32768:raise ValueError()
        claims=jwt.decode(token,key,algorithms=['RS256'],audience='rosago-production-sessions-v1',
            issuer='rosago-security-release',leeway=0,
            options={'require':['iat','nbf','exp','jti','sub','project_ref','public_origin','store',
                'authority','key_fingerprints','sources','bundle_sha256','checks','evidence_level']})
        if (any(type(claims[k]) is not int for k in ('iat','nbf','exp'))
                or not 0<claims['exp']-claims['iat']<=604800 or claims['nbf']>claims['iat']
                or not re.fullmatch(r'[A-Za-z0-9_-]{16,128}',claims['jti'])
                or claims['evidence_level']!='real-provider-qualified'
                or set(claims['checks'])!=CHECKS or any(v is not True for v in claims['checks'].values())
                or claims['sources']!=source_hashes() or claims['bundle_sha256']!=bundle_hash()):raise ValueError()
        project=claims['project_ref'];url=environment['SUPABASE_URL']
        public_key=environment['SUPABASE_KEY']
        if (project not in PROJECTS or claims['sub']!=project or url!='https://'+project+'.supabase.co'
                or not re.fullmatch(r'sb_publishable_[A-Za-z0-9_-]+',public_key)
                or claims['key_fingerprints']['public_key']!=_hash(public_key)):
            raise ValueError()
        origin=validate_public_origin(environment['ROSAGO_PUBLIC_ORIGIN'])
        host=urlsplit(origin).hostname
        if host in ('localhost','127.0.0.1','::1') or origin!=claims['public_origin']:raise ValueError()
        if environment.get('ROSAGO_PROXY_HOPS')!='1' or environment.get('ROSAGO_PROXY_HEADERS_SANITIZED')!='true':raise ValueError()
        secret=environment['FLASK_SECRET_KEY']
        if len(secret)<32 or claims['key_fingerprints']['flask_secret']!=_hash(secret):raise ValueError()
        ring=json.loads(environment['ROSAGO_SESSION_KEYRING'],object_pairs_hook=_object)
        if set(ring)!={'keys','current'} or not 1<=len(ring['keys'])<=4:raise ValueError()
        if claims['key_fingerprints']['keyring']!=_hash(json.dumps(ring,sort_keys=True,separators=(',',':'))):raise ValueError()
        cipher=SessionCipher({k:base64.b64decode(v,validate=True) for k,v in ring['keys'].items()},ring['current'])
        namespace=environment['ROSAGO_SESSION_NAMESPACE']
        prefix='production_' if project=='brnkigrrqdrywahvcbvc' else 'evaluation_'
        if not re.fullmatch(prefix+r'[A-Za-z0-9_-]{1,53}',namespace):raise ValueError()
        epochs={r:environment['ROSAGO_'+r.upper()+'_SESSION_EPOCH'] for r in ('user','admin')}
        if len(set(epochs.values()))!=2 or any(not re.fullmatch(r'[A-Za-z0-9_-]{16,64}',v) for v in epochs.values()):raise ValueError()
        binding=AuthorityBinding(environment['ROSAGO_AUTHORITY_ID'],environment['ROSAGO_AUTHORITY_INCARNATION'],
            int(environment['ROSAGO_AUTHORITY_MIN_SEQUENCE']))
        authority_origin=environment['ROSAGO_AUTHORITY_ORIGIN'];parsed=urlsplit(authority_origin)
        if (parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None,443)
                or parsed.path or parsed.query or parsed.fragment or parsed.hostname in ('localhost','127.0.0.1','::1')
                or authority_origin!='https://'+parsed.hostname):raise ValueError()
        expected_authority=dict(origin=authority_origin,authority_id=binding.authority_id,incarnation=binding.incarnation,
            minimum_sequence=binding.minimum_sequence,namespace=namespace,epochs=epochs)
        if claims['authority']!=expected_authority:raise ValueError()
        tokens={n:environment[k] for n,k in dict(metadata='ROSAGO_AUTHORITY_CLIENT_TOKEN',enroll='ROSAGO_PROVIDER_ENROLL_TOKEN',
            check='ROSAGO_PROVIDER_CHECK_TOKEN',revoke='ROSAGO_PROVIDER_REVOKE_TOKEN').items()}
        if (len(set(tokens.values()))!=4 or any(not 32<=len(v)<=256 or any(not 0x21<=ord(c)<=0x7e for c in v) for v in tokens.values())
                or any(environment.get(k) for k in ('ROSAGO_AUTHORITY_OPERATOR_TOKEN','CLOUDFLARE_API_TOKEN'))):raise ValueError()
        values=conninfo_to_dict(environment['ROSAGO_SESSION_DATABASE_URL'])
        if set(values)-{'host','port','dbname','user','password','sslmode','sslrootcert','connect_timeout','application_name'}:raise ValueError()
        dbhost=values['host']
        try:ipaddress.ip_address(dbhost)
        except ValueError:pass
        else:raise ValueError()
        if (not re.fullmatch(r'[a-z0-9][a-z0-9.-]*\.[a-z]{2,}',dbhost)
                or dbhost.endswith(('.supabase.co','.supabase.com')) or dbhost=='localhost'
                or values.get('port','5432')!='5432' or values.get('user')!='rosago_session_app'
                or not re.fullmatch(r'rosago_sessions(?:_[a-z0-9_]+)?',values.get('dbname',''))
                or not 32<=len(values.get('password',''))<=256 or values.get('sslmode')!='verify-full'
                or values.get('sslrootcert')!='system' or values.get('connect_timeout','2') not in ('1','2')):raise ValueError()
        if claims['store']!=dict(host=dbhost,port='5432',database=values['dbname'],role='rosago_session_app',
            owner='rosago_session_owner',schema='rosago_session',table='payloads'):raise ValueError()
        values.update(connect_timeout='2',application_name='rosago-production-sessions')
        maximum=environment.get('ROSAGO_SESSION_MAX_CONNECTIONS','2')
        if maximum not in ('1','2'):raise ValueError()
        return ProductionSettings(url,public_key,origin,make_conninfo(**values),cipher,namespace,MappingProxyType(epochs),
            binding,authority_origin,MappingProxyType(tokens),claims['exp'],claims['nbf'],claims['jti'],int(maximum))
    except Exception:
        pass
    raise RuntimeError('Production authentication requires a reviewed shared session backend, qualified infrastructure and a valid security release.') from None


class BoundProviderSessions(IndependentProviderSessions):
    def __init__(self,issuer,**kwargs):
        super().__init__(**kwargs)
        self.binding=MappingProxyType({**self.binding,'issuer':issuer})
    def current(self,record,issuer,realm):
        if issuer!=self.binding['issuer'] or realm not in ('user','admin'):return None
        try:return self._exchange('check',record)['active']
        except SessionStorageUnavailable:return None
    def revoke(self,record,issuer,realm):
        if issuer!=self.binding['issuer'] or realm not in ('user','admin'):return None
        try:
            result=self._exchange('revoke',record)
            return True if result['known'] and result['revoked'] and not result['active'] else None
        except SessionStorageUnavailable:return None
    def revocation_confirmed(self,record,issuer,realm):
        if issuer!=self.binding['issuer'] or realm not in ('user','admin'):return None
        try:
            result=self._exchange('check',record)
            return result['known'] and result['revoked'] and not result['active']
        except SessionStorageUnavailable:return None


class BoundProviderAdapters(IndependentProviderAdapters):
    def __init__(self,base,authority):
        if base.issuer!=authority.binding['issuer']:raise ValueError('Provider issuer mismatch.')
        self.base,self.authority=base,authority


def _open_pool(settings):
    pool=ConnectionPool(settings.conninfo,min_size=1,max_size=settings.max_connections,max_waiting=8,timeout=1,open=False,
        kwargs={'autocommit':True,'prepare_threshold':None,'row_factory':dict_row,'client_encoding':'UTF8'},check=ConnectionPool.check_connection)
    try:pool.open(wait=True,timeout=2)
    except Exception:
        pool.close()
        raise SessionStorageUnavailable('Private production store unavailable.') from None
    return pool


def _verify_pool(pool):
    with pool.connection(timeout=1) as conn:
        with conn.transaction():
            conn.execute('SET LOCAL transaction_read_only=on')
            row=conn.execute("""SELECT current_user AS role,session_user AS login,
                r.rolsuper,r.rolbypassrls,r.rolcreaterole,r.rolcreatedb,r.rolreplication,r.rolinherit,
                r.rolcanlogin AS can_login,
                NOT EXISTS(SELECT 1 FROM pg_auth_members m WHERE m.member=r.oid) AS no_memberships,
                has_database_privilege(current_user,current_database(),'CREATE') AS database_create,
                has_schema_privilege(current_user,'public','CREATE') AS public_create,
                c.relrowsecurity,c.relforcerowsecurity,(c.relpersistence='p' AND c.relkind='r') AS logged,
                pg_get_userbyid(c.relowner) AS owner,
                has_schema_privilege(current_user,'rosago_session','USAGE') AS schema_use,
                (has_table_privilege(current_user,c.oid,'SELECT') AND has_table_privilege(current_user,c.oid,'INSERT')
                 AND has_table_privilege(current_user,c.oid,'UPDATE') AND has_table_privilege(current_user,c.oid,'DELETE')) AS rw,
                EXISTS(SELECT 1 FROM pg_roles api WHERE api.rolname IN ('anon','authenticated','service_role')
                    AND (has_schema_privilege(api.oid,'rosago_session','USAGE')
                         OR has_table_privilege(api.oid,c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'))) AS api_access,
                EXISTS(SELECT 1 FROM aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a WHERE a.grantee=0) AS public_access
                FROM pg_roles r CROSS JOIN pg_class c WHERE r.rolname=current_user
                  AND c.oid=to_regclass('rosago_session.payloads')""").fetchone()
            if (not row or row['role']!='rosago_session_app' or row['login']!='rosago_session_app'
                    or row['owner']!='rosago_session_owner'
                    or any(row[k] is not False for k in ('rolsuper','rolbypassrls','rolcreaterole','rolcreatedb',
                        'rolreplication','rolinherit','api_access','public_access','database_create','public_create'))
                    or any(row[k] is not True for k in ('relrowsecurity','relforcerowsecurity','logged','schema_use','rw','can_login','no_memberships'))):
                raise SessionStorageUnavailable('Private session role or ACL verification failed.')


class ProductionRealm(ExternalPgRealm):
    def __init__(self,*args,release,**kwargs):
        self.release=release
        super().__init__(*args,**kwargs)
    def guard(self):
        if not self.release.not_before<=time.time()<self.release.deadline:
            raise SessionStorageUnavailable('Production security release is not current.')
        super().guard()


@dataclass(repr=False)
class ProductionWorker:
    settings: ProductionSettings
    runtime: object
    pool: object
    transports: tuple
    pid: int
    closed: bool=False
    def current(self):
        if self.closed or self.pid!=os.getpid() or not self.settings.not_before<=time.time()<self.settings.deadline:
            raise SessionStorageUnavailable('Production session admission is closed.')
    def readiness(self):
        try:
            self.current()
            return all(r.readiness().get('ready') is True for r in self.runtime.realms.values())
        except Exception:return False
    def close(self):
        if self.pid!=os.getpid():raise SessionStorageUnavailable('Production clients cannot cross worker fork.')
        if self.closed:return
        self.closed=True
        for resource in (*self.transports,self.pool):
            try:resource.close()
            except Exception:pass


def open_worker(settings,*,pool_factory=None,transport_factory=None,base_factory=SupabaseAdapters):
    """Explicit post-fork construction; every failure closes resources without retry."""
    pool=None;transports=[];stage='configuration'
    try:
        if type(settings) is not ProductionSettings or any(v and k.startswith('PG') for k,v in os.environ.items()):raise ValueError()
        if not settings.not_before<=time.time()<settings.deadline:raise ValueError()
        stage='store_connect'
        pool=(pool_factory or _open_pool)(settings)
        stage='store_permissions'
        _verify_pool(pool)
        transport_factory=transport_factory or AuthorityHTTPTransport
        stage='authority_transport'
        for name,path in (('metadata','/v1/authority'),('enroll','/v1/provider/enroll'),('check','/v1/provider/check'),('revoke','/v1/provider/revoke')):
            transports.append(transport_factory(settings.authority_origin+path,settings.tokens[name],expected_path=path))
        authority=ProtectedRevisionAuthority(transports[0],settings.binding)
        stage='authority_readiness'
        realms={r:ProductionRealm(pool,settings.cipher,settings.namespace,r,settings.epochs[r],authority=authority,release=settings) for r in ('user','admin')}
        if not all(r.readiness().get('ready') is True for r in realms.values()):raise ValueError()
        issuer=settings.url+'/auth/v1'
        stage='provider_binding'
        provider=BoundProviderSessions(issuer,authority_id=settings.binding.authority_id,incarnation=settings.binding.incarnation,
            namespace=settings.namespace,transports=dict(zip(('enroll','check','revoke'),transports[1:])))
        # Share only this stateless constructor/configuration adapter, never an SDK
        # client or token. Checks, logout and both realms must use the same scoped
        # provider transport; every operation still owns a fresh HTTP/SDK client.
        adapters=BoundProviderAdapters(base_factory(settings.url,settings.public_key),provider)
        def adapters_factory(url,key):
            if url!=settings.url or key!=settings.public_key:raise SessionStorageUnavailable('Production provider binding mismatch.')
            return adapters
        logout=DurableLogout(realms,issuer=issuer,sign_out=adapters.sign_out_current_session,
            session_check=adapters.provider_session_present,revocation_check=provider.revocation_confirmed)
        runtime=LocalSessionRuntime(realms,ExternalPgModel,RedisChallenges,adapters.provider_session_check,
            logout_handler=logout,adapters_factory=adapters_factory)
        return ProductionWorker(settings,runtime,pool,tuple(transports),os.getpid())
    except Exception:
        if pool is not None:ProductionWorker(settings,None,pool,tuple(transports),os.getpid()).close()
        logging.getLogger(__name__).warning('production_session_startup stage=%s outcome=denied',stage)
    raise SessionStorageUnavailable('Production shared-session startup failed; no fallback is permitted.') from None


def install(app,environment):
    from flask import abort,request
    from werkzeug.middleware.proxy_fix import ProxyFix
    settings=validate_environment(environment)
    if app.config.get('APPLICATION_ROOT','/')!='/' or app.config.get('SESSION_COOKIE_DOMAIN'):
        raise RuntimeError('Production sessions require a root-mounted, host-only application.')
    worker=open_worker(settings)
    try:
        worker.runtime.install(app,secure=True)
        app.config.update(TRUSTED_HOSTS=[urlsplit(settings.origin).hostname],SESSION_COOKIE_DOMAIN=None,
            SESSION_COOKIE_SECURE=True,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax')
        # Evaluation HTTP already installs the same last-hop scheme boundary.
        if 'rosago_evaluation' not in app.extensions:
            app.wsgi_app=ProxyFix(app.wsgi_app,x_for=0,x_proto=1,x_host=0,x_port=0,x_prefix=0)
        app.extensions['rosago_production_sessions']=worker
        @app.before_request
        def production_admission():
            worker.current()
            if request.host_url.rstrip('/')!=settings.origin:abort(400)
            if not request.path.startswith('/static/') and not worker.readiness():
                raise SessionStorageUnavailable('Production session infrastructure is unavailable.')
        @app.after_request
        def production_headers(response):
            response.headers.setdefault('Strict-Transport-Security','max-age=31536000')
            return response
    except Exception:
        worker.close()
        raise
    return worker
