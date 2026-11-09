"""Per-record encrypted Redis cache; protected authority required by default.

LOCAL QUALIFICATION ONLY. Production startup remains blocked. Raw LMDB and
same-host witnesses are permitted only by an explicit Python historical-test
option, never by the default factory or an environment fallback switch.
"""
from dataclasses import dataclass, replace
import base64
import hashlib
import json
import math
import re
import secrets
import time
from urllib.parse import urlsplit

import redis
from redis.backoff import NoBackoff
from redis.retry import Retry

from session_crypto import SessionCipher
from session_authority import LocalRevisionAuthority, RevisionConflict
from protected_session_authority import ProtectedRevisionAuthority
from session_realms import SessionStorageUnavailable
from normal_auth_store import NormalAuthSession, RefreshReservation, _credentials_valid
from recovery_helpers import PendingRecovery, RecoveryGrant
from email_verification import PendingEmail


PUBLISH = """
local t=redis.call('TIME')
local now=tonumber(t[1])+tonumber(t[2])/1000000
if math.abs(now-tonumber(ARGV[1])) > 0.25 then return 0 end
local values={}
for i,key in ipairs(KEYS) do
  local old=redis.call('GET',key)
  if (old or '') ~= ARGV[2+(i-1)*3] then return 0 end
  if not redis.acl_check_cmd('PEXPIREAT',key,ARGV[4+(i-1)*3]) then return 0 end
  table.insert(values,key)
  table.insert(values,ARGV[3+(i-1)*3])
end
redis.call('MSET',unpack(values))
for i,key in ipairs(KEYS) do
  local result=redis.pcall('PEXPIREAT',key,ARGV[4+(i-1)*3])
  if type(result)=='table' and result.err then return 2 end
end
return 1
"""


@dataclass(repr=False)
class Snapshot:
    kind: str
    key: str
    meta: dict | None
    raw: bytes | None
    data: object
    now: float
    revocation_only: bool = False


class RedisRealm:
    def __init__(self, client, cipher, namespace, realm, epoch, *, authority=None, unprotected_local_testing=False):
        if realm not in ('user','admin') or any(not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', v) for v in (namespace,epoch)):
            raise ValueError('Invalid session namespace.')
        self.client, self.cipher, self.namespace, self.realm, self.epoch = client, cipher, namespace, realm, epoch
        self.prefix = f'{namespace}:sessions:v3:{realm}:{epoch}'
        self.authority = authority
        # Python-only historical qualification option; never an environment
        # switch or production backend. Raw snapshots are not freshness proof.
        self.unprotected_local_testing = unprotected_local_testing is True
        descriptor = authority.descriptor(namespace) if authority else None
        self.generation = descriptor['generation'] if descriptor else None

    def guard(self):
        if not isinstance(self.authority,ProtectedRevisionAuthority) and not self.unprotected_local_testing:
            raise SessionStorageUnavailable('Protected freshness authority is required; local snapshots cannot authorize sessions.')
        if not self.authority or self.generation is None:
            raise SessionStorageUnavailable('Independent session authority is required.')
        self.authority.guard(self.namespace,self.realm,self.epoch,self.generation)

    def now(self):
        self.guard()
        try:
            pipe=self.client.pipeline(transaction=False)
            seconds,stats,role=pipe.time().info('stats').role().execute()
            now=seconds[0]+seconds[1]/1_000_000
            if abs(now-time.time())>5 or stats.get('evicted_keys',0) or role[0] not in (b'master','master'):
                raise SessionStorageUnavailable('Session backend clock, eviction or writer validation failed.')
            self.guard()
            return now
        except redis.RedisError:
            raise SessionStorageUnavailable('Session backend unavailable.') from None

    def key(self,kind,handle):
        if type(handle) is not str or not 1<=len(handle)<=512 or not re.fullmatch(r'[a-z_]{1,20}',kind):
            raise ValueError('Invalid session record reference.')
        return self.prefix+':'+kind+':'+hashlib.sha256(handle.encode()).hexdigest()

    def snapshot(self,kind,handle,*,revocation_only=False):
        key=self.key(kind,handle)
        now=self.now()
        meta=self.authority.read(key,now)
        try:
            raw,ttl=self.client.pipeline(transaction=False).get(key).pttl(key).execute()
        except redis.RedisError:
            raise SessionStorageUnavailable('Session backend unavailable.') from None
        self.guard()
        if self.authority.read(key,now)!=meta:
            raise RevisionConflict('Session revision changed.')
        if revocation_only:
            return Snapshot(kind,key,meta,raw,None,now,True)
        if meta is None:
            return Snapshot(kind,key,None,raw,None,now)
        if (not raw or ttl<=0 or ttl>(meta['expires']-now)*1000+2000
                or hashlib.sha256(raw).hexdigest()!=meta['digest']):
            # This also covers the short independent-commit/cache-publish
            # window. It NEVER supplies authority or replays a refresh.
            raise RevisionConflict('Session revision is unavailable or publication is busy.')
        envelope=self.cipher.decrypt(raw,key.encode())
        if envelope['expires']<=now:
            raise SessionStorageUnavailable('Session envelope has expired.')
        return Snapshot(kind,key,meta,raw,envelope['data'],now)

    def atomic(self, snapshots, updates):
        """updates: key -> (payload, logical expiry, authoritative metadata).

        None payload removes independent authority first. Redis is NOT allowed
        to restore the previous revision when publishing fails.
        """
        if len(snapshots)>8 or not updates or set(updates)-set(snapshots):
            raise ValueError('Invalid bounded session transition.')
        if any(s.revocation_only and (key not in updates or updates[key][0] is not None) for key,s in snapshots.items()):
            raise ValueError('Revocation-only snapshots cannot install authority.')
        now=self.now()
        if any(abs(now-s.now)>2 for s in snapshots.values()):
            raise RevisionConflict('Session snapshot exceeded its deadline.')
        changes,encrypted={},{}
        operation=secrets.token_urlsafe(24)
        for key,(data,expires,extra) in updates.items():
            if data is None:
                changes[key]=None
                continue
            if not now<expires<=now+28801:
                raise ValueError('Invalid session lifetime.')
            absolute=extra.get('absolute',expires)
            raw=self.cipher.encrypt({'data':data,'expires':absolute,'operation':operation},key.encode())
            changes[key]={'digest':hashlib.sha256(raw).hexdigest(),'expires':expires,
                'size':len(raw),'scope':self.prefix+':'+snapshots[key].kind,'realm_scope':self.prefix,**extra}
            encrypted[key]=raw
        if encrypted:
            try:
                memory=self.client.info('memory')
                ceiling=memory.get('maxmemory',0)
                reserve=max(65536,2*sum(len(raw) for raw in encrypted.values()))
                if ceiling and memory['used_memory']+reserve>ceiling:
                    raise SessionStorageUnavailable('Session cache admission is closed under memory pressure.')
            except redis.RedisError:
                raise SessionStorageUnavailable('Session admission could not be verified.') from None
        # Durable local transaction is the authority commit, independent of Redis.
        self.authority.commit(self.namespace,self.realm,self.epoch,self.generation,
            {k:s.meta for k,s in snapshots.items()},changes,now)
        if not encrypted:
            try:
                self.client.delete(*updates)
            except redis.RedisError:
                pass  # Revocation was durably acknowledged by independent authority.
            return
        args=[str(time.time())]
        for key,raw in encrypted.items():
            args.extend([snapshots[key].raw or b'',raw,str(math.ceil(changes[key]['expires']*1000))])
        try:
            result=self.client.eval(PUBLISH,len(encrypted),*encrypted,*args)
        except (redis.ConnectionError,redis.TimeoutError):
            # Reconcile exact prepared bytes; NEVER repeat a provider operation.
            try:
                values=self.client.mget(list(encrypted))
                ttl_ok=all(0<self.client.pttl(key)<=(changes[key]['expires']-time.time())*1000+2000 for key in encrypted)
                result=1 if values==list(encrypted.values()) and ttl_ok else 0
            except redis.RedisError:
                result=0
        except redis.RedisError:
            result=0
        if result!=1:
            raise SessionStorageUnavailable('Session publish outcome is uncertain; reload or sign in again.')
        self.guard()
        try:
            deleted=[k for k,v in changes.items() if v is None]
            if deleted:
                self.client.delete(*deleted)
        except redis.RedisError:
            pass  # Deleted independent revisions remain inaccessible.

    def write(self,snapshot,data,expires,**extra):
        self.atomic({snapshot.key:snapshot},{snapshot.key:(data,expires,extra)})

    def readiness(self):
        self.now()
        try:
            if self.client.config_get('maxmemory-policy').get('maxmemory-policy')!='noeviction':
                raise SessionStorageUnavailable('Session backend requires noeviction.')
        except redis.RedisError:
            raise SessionStorageUnavailable('Session configuration could not be verified.') from None
        self.authority.maintain()
        return {'ready':True,'protocol':3,'realm':self.realm,'production_approved':False}


class RedisModel:
    def __init__(self,realm,kind):
        self.backend,self.kind=realm,kind

    def _read(self,handle):
        if type(handle) is not str or not handle:
            return None
        return self.backend.snapshot(self.kind,handle)

    def create(self,*args,**kwargs):
        if self.kind=='email':
            return self.create_email(*args,**kwargs)
        handle=secrets.token_urlsafe(32)
        snap=self._read(handle)
        now=snap.now
        if self.kind=='auth':
            if not _credentials_valid(**kwargs):
                raise ValueError('Invalid credentials.')
            record=NormalAuthSession(**kwargs,created_at=now,last_activity_at=now,
                generation=0,revoked=False,csrf=secrets.token_urlsafe(32))
            self.backend.write(snap,{'record':record,'lease':None},now+1800,
                absolute=now+28800,activity=now,generation=0,busy=False)
        elif self.kind=='pending':
            self.backend.write(snap,{'record':PendingRecovery(secrets.token_urlsafe(32),now,now+600),'lease':None},now+600)
        elif self.kind=='web':
            values=dict(args[0])
            self.backend.write(snap,{'values':values,'version':0},now+(28800 if values.get('auth_session_id') else 1800))
        else:
            raise ValueError('Use the family-specific allocation method.')
        return handle

    def read(self,handle):
        snap=self._read(handle)
        return (snap.data['values'],snap.data['version']) if snap and snap.data else None

    def save(self,handle,version,values):
        snap=self._read(handle)
        if not snap or not snap.data or snap.data['version']!=version:
            return False
        try:
            self.backend.write(snap,{'values':dict(values),'version':version+1},snap.meta['expires'])
        except RevisionConflict:
            return False
        return True

    def resolve(self,handle):
        snap=self._read(handle)
        if not snap or snap.data is None:
            return None
        record=snap.data['record']
        return replace(record,last_activity_at=snap.meta['activity'])

    def touch(self,handle,*,expected_generation=None):
        snap=self._read(handle)
        if not snap or not snap.data or snap.meta['busy'] or (expected_generation is not None and snap.meta['generation']!=expected_generation):
            return False
        now=self.backend.now()
        meta={**snap.meta,'activity':now,'expires':min(now+1800,snap.meta['absolute'])}
        self.backend.authority.commit(self.backend.namespace,self.backend.realm,self.backend.epoch,self.backend.generation,
                                     {snap.key:snap.meta},{snap.key:meta},now)
        try:
            if not self.backend.client.pexpireat(snap.key,math.ceil(meta['expires']*1000)):
                raise SessionStorageUnavailable('Session cache expired during activity update.')
        except redis.RedisError:
            raise SessionStorageUnavailable('Session activity outcome is uncertain.') from None
        self.backend.guard()
        return True

    def reserve_refresh(self,handle):
        try:
            snap=self._read(handle)
        except RevisionConflict:
            return None
        if not snap or not snap.data or snap.data['lease']:
            return None
        record=replace(snap.data['record'],last_activity_at=snap.meta['activity'])
        lease=RefreshReservation(secrets.token_urlsafe(32),record.generation)
        try:
            self.backend.write(snap,{'record':record,'lease':lease},min(snap.now+30,snap.meta['expires']),
                absolute=min(snap.now+30,snap.meta['absolute']),activity=record.last_activity_at,generation=record.generation,busy=True)
        except RevisionConflict:
            return None
        return lease,record

    def replace_credentials(self,handle,lease,**credentials):
        snap=self._read(handle)
        if not snap or not snap.data or snap.data['lease']!=lease:
            return False
        old=snap.data['record']
        if (not _credentials_valid(**credentials) or credentials['user_id']!=old.user_id or credentials['session_id']!=old.session_id):
            return False
        record=replace(old,**credentials,generation=old.generation+1)
        absolute=old.created_at+28800
        self.backend.write(snap,{'record':record,'lease':None},min(old.last_activity_at+1800,absolute),
            absolute=absolute,activity=old.last_activity_at,generation=record.generation,busy=False)
        return True

    def release_refresh(self,handle,lease):
        snap=self._read(handle)
        if not snap or not snap.data or snap.data['lease']!=lease:
            return False
        # Only a still-fresh, unconsumed reservation is released by the
        # coordinator's early-fresh branch. Other failures call revoke_refresh.
        old=snap.data['record']
        self.backend.write(snap,{'record':old,'lease':None},min(old.last_activity_at+1800,old.created_at+28800),
            absolute=old.created_at+28800,activity=old.last_activity_at,generation=old.generation,busy=False)
        return True

    def revoke_refresh(self,handle,lease):
        snap=self._read(handle)
        if not snap or not snap.data or snap.data['lease']!=lease:
            return False
        self.backend.write(snap,None,snap.now)
        return True

    def revoke(self,handle):
        if type(handle) is not str or not handle:
            return False
        # Retry only a known stale-CAS conflict, with a fresh authoritative read.
        # Transport/uncertain-commit failures must propagate without replay.
        for _ in range(3):
            try:
                snap=self.backend.snapshot(self.kind,handle,revocation_only=True)
                if not snap or not snap.meta:
                    return False
                self.backend.write(snap,None,snap.now)
                return True
            except RevisionConflict:
                continue
        raise RevisionConflict('Session revocation could not be confirmed.')

    def lookup(self,handle):
        snap=self._read(handle)
        return snap.data['record'] if snap and snap.data else None

    def reserve(self,handle,*args):
        if self.kind=='email':
            return self._reserve_email(handle,*args)
        snap=self._read(handle)
        if not snap or not snap.data or snap.data['lease']:
            return None
        lease=secrets.token_urlsafe(32)
        self.backend.write(snap,{**snap.data,'lease':lease},min(snap.now+30,snap.meta['expires']))
        return lease,snap.data['record']

    def finalize(self,handle,lease):
        snap=self._read(handle)
        if not snap or not snap.data or snap.data['lease']!=lease:
            return None
        self.backend.write(snap,None,snap.now)
        return snap.data['record']

    def release(self,handle,lease):
        return self.finalize(handle,lease)  # Burn ambiguous provider outcomes.

    def consume(self,handle):
        snap=self._read(handle)
        if not snap or not snap.data:
            return None
        self.backend.write(snap,None,snap.now)
        return snap.data['record']

    def issue(self,user,provider,expires,token):
        now=self.backend.now()
        if expires<=now:
            return None
        replay=self.backend.snapshot('used',hashlib.sha256(provider.encode()).hexdigest())
        if replay.data:
            return None
        handle=secrets.token_urlsafe(32)
        snap=self._read(handle)
        record=RecoveryGrant(user,min(expires,now+600),token,secrets.token_urlsafe(32))
        self.backend.atomic({snap.key:snap,replay.key:replay},{
            snap.key:({'record':record,'lease':None},record.expires,{}),replay.key:(True,now+630,{})})
        return handle

    def valid(self,handle):
        return self.lookup(handle) is not None

    def csrf(self,handle):
        record=self.lookup(handle)
        return record.csrf if record else None

    def get(self,handle):
        return self.lookup(handle)

    def seconds(self,record):
        return max(0,math.ceil(record.resend_at-self.backend.now()))

    def create_email(self,email):
        handle=secrets.token_urlsafe(32)
        snap=self._read(handle)
        rate=self.backend.snapshot('email_rate',email.casefold())
        now=snap.now
        due=max(now+60,rate.data or 0)
        record=PendingEmail(email,secrets.token_urlsafe(32),now+1800,due)
        self.backend.atomic({snap.key:snap,rate.key:rate},{snap.key:({'record':record},now+1800,{}),rate.key:(due,due,{})})
        return handle

    def _reserve_email(self,handle,action):
        snap=self._read(handle)
        if not snap or not snap.data:
            return None,0
        old=snap.data['record']
        rate=self.backend.snapshot('email_rate',old.email.casefold())
        due=max(old.resend_at,rate.data or 0) if action=='resend' else old.verify_at
        if old.verified or old.busy or due>snap.now:
            return None,max(1,math.ceil(due-snap.now))
        changes={'busy':True,'resend_at' if action=='resend' else 'verify_at':snap.now+(60 if action=='resend' else 5)}
        updates={snap.key:({'record':replace(old,**changes)},old.expires,{})}
        if action=='resend':
            updates[rate.key]=(snap.now+60,snap.now+60,{})
        self.backend.atomic({snap.key:snap,rate.key:rate},updates)
        return old,0

    def finish(self,handle,*,verified=False,resent=False,limited=False,uncertain=False):
        snap=self._read(handle)
        if not snap or not snap.data:
            return
        old=snap.data['record']
        changes={'busy':bool(uncertain),'verified':old.verified or verified}
        updates={}
        reads={snap.key:snap}
        if resent or limited:
            rate=self.backend.snapshot('email_rate',old.email.casefold())
            reads[rate.key]=rate
            changes['resend_at']=snap.now+60
            updates[rate.key]=(snap.now+60,snap.now+60,{})
        if limited:
            changes['verify_at']=snap.now+60
        updates[snap.key]=({'record':replace(old,**changes)},old.expires,{})
        self.backend.atomic(reads,updates)


class RedisChallenges:
    def __init__(self,realms):
        self.realms=realms

    def issue(self,realm):
        from flask import has_request_context,request
        if has_request_context() and not self.allow_attempt(realm,request.remote_addr,purpose='allocation'):
            raise SessionStorageUnavailable('Login allocation limit exceeded.')
        token=secrets.token_urlsafe(32)
        snap=self.realms[realm].snapshot('login',token)
        self.realms[realm].write(snap,{'purpose':realm},snap.now+1800)
        return token

    def valid(self,realm,token,*,consume=False):
        if type(token) is not str or not token:
            return False
        snap=self.realms[realm].snapshot('login',token)
        if not snap.data or snap.data.get('purpose')!=realm:
            return False
        if consume:
            self.realms[realm].write(snap,None,snap.now)
        return True

    def allow_attempt(self,realm,address,*,purpose='login'):
        backend=self.realms[realm]
        for _ in range(4):
            snap=backend.snapshot('rate',purpose+':'+str(address))
            count=snap.data or 0
            if count>=20:
                return False
            try:
                backend.write(snap,count+1,snap.meta['expires'] if snap.meta else snap.now+60)
                return True
            except RevisionConflict:
                continue
        raise SessionStorageUnavailable('Login rate state is busy.')


def local_realms(environ, *, authority=None, unprotected_local_testing=False):
    if not isinstance(authority,ProtectedRevisionAuthority) and unprotected_local_testing is not True:
        # No real service/transport is provisioned. Refuse before touching Redis,
        # LMDB, keys or old cookies. There is deliberately no environment bypass.
        raise SessionStorageUnavailable('Protected freshness authority is not configured; shared authentication is closed.')
    try:
        ring=json.loads(environ['ROSAGO_SESSION_KEYRING'])
        cipher=SessionCipher({k:base64.b64decode(v,validate=True) for k,v in ring['keys'].items()},ring['current'])
        if authority is None:
            authority=LocalRevisionAuthority(environ['ROSAGO_SESSION_AUTHORITY_PATH'])
        result={}
        for realm in ('user','admin'):
            url=environ[f'ROSAGO_SESSION_REDIS_{realm.upper()}_URL']
            parsed=urlsplit(url)
            if parsed.scheme!='redis' or parsed.hostname not in ('127.0.0.1','::1') or parsed.query:
                raise ValueError('Local Redis requires numeric loopback and no URL overrides.')
            client=redis.Redis.from_url(url,socket_timeout=1,socket_connect_timeout=1,
                retry=Retry(NoBackoff(),0),retry_on_timeout=False,max_connections=16)
            result[realm]=RedisRealm(client,cipher,environ['ROSAGO_SESSION_NAMESPACE'],realm,
                environ[f'ROSAGO_{realm.upper()}_SESSION_EPOCH'],authority=authority,unprotected_local_testing=unprotected_local_testing)
            result[realm].readiness()
        return result
    except (KeyError,ValueError,TypeError):
        raise RuntimeError('Invalid local independent session configuration.') from None
