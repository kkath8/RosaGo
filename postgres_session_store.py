"""INACTIVE local PostgreSQL adapter. No application/environment activation.

Encrypted state, CAS and terminal tombstones share one PostgreSQL transaction.
Independent recovery fencing is mandatory; no production provider is supplied.
Legacy transition/codec code is reused without contacting Redis or LMDB.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import math
import os
import re
import time

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from record_session_store import RedisModel,RedisChallenges
from session_authority import RevisionConflict
from session_realms import SessionStorageUnavailable
from postgres_session_recovery import RecoveryFence


@dataclass(repr=False)
class PgSnapshot:
    kind: str
    key: str
    meta: dict | None
    raw: bytes | None
    data: object
    now: float
    revocation_only: bool=False


def isolated_pool(conninfo,*,max_size=2):
    """Explicit numeric-loopback only. No production/Supabase factory exists."""
    info=psycopg.conninfo.conninfo_to_dict(conninfo)
    if (info.get('host') not in ('127.0.0.1','::1') or info.get('hostaddr')
            or info.get('service') or not info.get('dbname','').startswith('rosago_lab')):
        raise ValueError('Isolated PostgreSQL requires explicit loopback lab database.')
    if type(max_size) is not int or not 1<=max_size<=8:
        raise ValueError('Invalid isolated pool bound.')
    return ConnectionPool(conninfo,min_size=0,max_size=max_size,max_waiting=8,timeout=1,
        kwargs={'autocommit':True,'prepare_threshold':None,'connect_timeout':2,'row_factory':dict_row},
        check=ConnectionPool.check_connection,open=True)


class PgRealm:
    def __init__(self,pool,cipher,namespace,realm,*,recovery=None,record_limit=4096,byte_limit=32*1024*1024):
        if (realm not in ('user','admin') or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',namespace)
                or not isinstance(recovery,RecoveryFence)):
            raise SessionStorageUnavailable('A scoped independent recovery fence is required.')
        if type(record_limit) is not int or not 0<record_limit<=16384 or type(byte_limit) is not int or not 0<byte_limit<=64*1024*1024:
            raise ValueError('Invalid PostgreSQL admission limits.')
        self.pool,self.cipher,self.namespace,self.realm,self.recovery=pool,cipher,namespace,realm,recovery
        self.epoch=getattr(recovery.binding,realm+'_epoch')
        self.prefix=f'{namespace}:sessions:pg1:{realm}:{self.epoch}'
        self.record_limit,self.byte_limit=record_limit,byte_limit
        self.pid=os.getpid()

    def key(self,kind,handle):
        if type(handle) is not str or not 1<=len(handle)<=512 or not re.fullmatch(r'[a-z_]{1,20}',kind):
            raise ValueError('Invalid PostgreSQL record reference.')
        return self.prefix+':'+kind+':'+hashlib.sha256(handle.encode()).hexdigest()

    @contextmanager
    def transaction(self,*,write=False):
        if os.getpid()!=self.pid:
            raise SessionStorageUnavailable('PostgreSQL pools must be created after worker fork.')
        self.recovery.check(self.namespace)
        began=time.monotonic()
        try:
            with self.pool.connection() as connection:
                with connection.transaction():
                    connection.execute("SET LOCAL lock_timeout='750ms'")
                    connection.execute("SET LOCAL statement_timeout='1500ms'")
                    connection.execute("SET LOCAL idle_in_transaction_session_timeout='2500ms'")
                    connection.execute('SET LOCAL synchronous_commit=on')
                    gate=connection.execute("SELECT g.*,current_setting('fsync') AS fsync,pg_is_in_recovery() AS standby FROM rosago_session_m.lock_gate(%s) g",(self.namespace,)).fetchone()
                    binding=self.recovery.binding
                    if (not gate or gate['state']!='OPEN' or gate['protocol']!=1 or gate['fsync']!='on' or gate['standby']
                            or any(gate[field]!=getattr(binding,field) for field in ('authority_id','incarnation','user_epoch','admin_epoch'))):
                        raise SessionStorageUnavailable('PostgreSQL recovery gate is closed or stale.')
                    if write:
                        # A short transaction-scoped per-realm admission lock.
                        # No provider HTTP or external-control IO while held.
                        identity=int.from_bytes(hashlib.sha256((self.namespace+':'+self.realm).encode()).digest()[:8],'big',signed=True)
                        connection.execute('SELECT pg_advisory_xact_lock(%s)',(identity,))
                    now=connection.execute('SELECT extract(epoch FROM clock_timestamp())::float8 AS now').fetchone()['now']
                    if abs(now-time.time())>5:
                        raise SessionStorageUnavailable('PostgreSQL clock validation failed.')
                    yield connection,now
                    if time.monotonic()-began>2:
                        raise SessionStorageUnavailable('PostgreSQL operation exceeded its deadline.')
            # A closure here may follow an already committed session mutation.
            # Report unavailable; do not retry it or replay a provider request.
            self.recovery.check(self.namespace)
        except (psycopg.Error,TimeoutError):
            raise SessionStorageUnavailable('PostgreSQL session operation unavailable or outcome uncertain.') from None

    def now(self):
        with self.transaction() as (_,now):return now

    def _row(self,connection,key,now,*,lock=False):
        row=connection.execute('''SELECT r.*,v.revision AS fence_revision,
            EXISTS(SELECT 1 FROM rosago_session_m.revoked d WHERE d.key=r.key AND d.retain_until>%s) AS dead
            FROM rosago_session_m.records r LEFT JOIN rosago_session_m.versions v ON v.key=r.key
            WHERE r.namespace=%s AND r.realm=%s AND r.epoch=%s AND r.key=%s'''+(' FOR UPDATE OF r' if lock else ''),
                               (now,self.namespace,self.realm,self.epoch,key)).fetchone()
        if not row or row['expires']<=now or row['dead']:return None
        if row['fence_revision']!=row['revision']:
            raise SessionStorageUnavailable('PostgreSQL record revision is inconsistent or restored.')
        return row

    @staticmethod
    def _meta(row):
        return {**row['metadata'],'revision':row['revision'],'expires':row['expires'],'size':len(row['ciphertext'])}

    def snapshot(self,kind,handle,*,revocation_only=False):
        key=self.key(kind,handle)
        with self.transaction() as (connection,now):
            row=self._row(connection,key,now)
            if not row:return PgSnapshot(kind,key,None,None,None,now,revocation_only)
            raw=bytes(row['ciphertext']);meta=self._meta(row)
            data=None
            if not revocation_only:
                envelope=self.cipher.decrypt(raw,key.encode())
                if envelope['expires']<=now:raise SessionStorageUnavailable('PostgreSQL encrypted authority expired.')
                data=envelope['data']
            return PgSnapshot(kind,key,meta,raw,data,now,revocation_only)

    def atomic(self,snapshots,updates):
        if not 0<len(snapshots)<=8 or not updates or set(updates)-set(snapshots):
            raise ValueError('Invalid bounded PostgreSQL transition.')
        if any(not key.startswith(self.prefix+':') or snap.key!=key for key,snap in snapshots.items()):
            raise SessionStorageUnavailable('Cross-realm PostgreSQL transaction denied.')
        if any(snap.revocation_only and (key not in updates or updates[key][0] is not None) for key,snap in snapshots.items()):
            raise ValueError('Revocation-only state cannot install authority.')
        with self.transaction(write=True) as (connection,now):
            if any(abs(now-snap.now)>2 for snap in snapshots.values()):raise RevisionConflict('PostgreSQL snapshot is stale.')
            for key,snap in sorted(snapshots.items()):
                row=self._row(connection,key,now,lock=True)
                if (self._meta(row) if row else None)!=snap.meta:
                    raise RevisionConflict('PostgreSQL session revision changed.')
            # Reclaim a bounded batch; no request extends unrelated retention.
            connection.execute('DELETE FROM rosago_session_m.records WHERE key IN (SELECT key FROM rosago_session_m.records WHERE namespace=%s AND realm=%s AND expires<=%s LIMIT 128)',
                               (self.namespace,self.realm,now))
            encoded={}
            for key,(data,expires,extra) in updates.items():
                if data is None:
                    if snapshots[key].meta:
                        connection.execute('INSERT INTO rosago_session_m.revoked(namespace,realm,epoch,key,retain_until) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(key) DO NOTHING',
                                           (self.namespace,self.realm,self.epoch,key,now+28802))
                    connection.execute('DELETE FROM rosago_session_m.records WHERE key=%s',(key,))
                    continue
                if (type(expires) not in (int,float) or not math.isfinite(expires) or not now<expires<=now+28801
                        or any(k not in ('absolute','activity','generation','busy') for k in extra)):
                    raise ValueError('Invalid PostgreSQL lifetime/metadata.')
                if connection.execute('SELECT 1 FROM rosago_session_m.revoked WHERE key=%s AND retain_until>%s',(key,now)).fetchone():
                    raise RevisionConflict('Revoked PostgreSQL references cannot be recreated.')
                absolute=extra.get('absolute',expires)
                if type(absolute) not in (int,float) or not math.isfinite(absolute) or absolute<expires:
                    raise ValueError('Invalid PostgreSQL absolute deadline.')
                raw=self.cipher.encrypt({'data':data,'expires':absolute},key.encode())
                encoded[key]=(raw,expires,extra)
            # Replacement credit before admission, one transaction rolls back all.
            for key in encoded:connection.execute('DELETE FROM rosago_session_m.records WHERE key=%s',(key,))
            for key,(raw,expires,extra) in encoded.items():
                kind=snapshots[key].kind
                counts=connection.execute('SELECT count(*) AS n,coalesce(sum(octet_length(ciphertext)),0) AS bytes FROM rosago_session_m.records WHERE namespace=%s AND realm=%s',
                                          (self.namespace,self.realm)).fetchone()
                floor=connection.execute('SELECT revision,retain_until FROM rosago_session_m.versions WHERE key=%s',(key,)).fetchone()
                history=connection.execute('SELECT count(*) AS n FROM rosago_session_m.versions WHERE namespace=%s AND realm=%s',
                                           (self.namespace,self.realm)).fetchone()['n']
                if (not floor and history>=self.record_limit) or counts['bytes']+len(raw)>self.byte_limit:
                    raise SessionStorageUnavailable('PostgreSQL session admission limit reached.')
                revision=floor['revision']+1 if floor else 1
                retain=max(extra.get('absolute',expires)+2,floor['retain_until'] if floor else 0)
                connection.execute('INSERT INTO rosago_session_m.versions(namespace,realm,epoch,key,revision,retain_until) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(key) DO UPDATE SET revision=excluded.revision,retain_until=excluded.retain_until',
                                   (self.namespace,self.realm,self.epoch,key,revision,retain))
                connection.execute('INSERT INTO rosago_session_m.records(namespace,realm,epoch,family,key,revision,expires,metadata,ciphertext) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (self.namespace,self.realm,self.epoch,kind,key,revision,expires,Jsonb(extra),raw))

    def write(self,snapshot,data,expires,**extra):
        self.atomic({snapshot.key:snapshot},{snapshot.key:(data,expires,extra)})

    def touch(self,handle,expected_generation=None):
        snap=self.snapshot('auth',handle)
        if not snap.meta or snap.meta['busy'] or (expected_generation is not None and snap.meta['generation']!=expected_generation):return False
        with self.transaction(write=True) as (connection,now):
            row=self._row(connection,snap.key,now,lock=True)
            if not row or self._meta(row)!=snap.meta:raise RevisionConflict('PostgreSQL activity revision changed.')
            if abs(now-snap.now)>2:raise RevisionConflict('PostgreSQL activity snapshot is stale.')
            expiry=min(now+1800,snap.meta['absolute'])
            meta={**row['metadata'],'activity':now}
            connection.execute('UPDATE rosago_session_m.records SET expires=%s,metadata=%s,revision=revision+1 WHERE key=%s',
                               (expiry,Jsonb(meta),snap.key))
            connection.execute('UPDATE rosago_session_m.versions SET revision=revision+1 WHERE key=%s',(snap.key,))
        return True

    def readiness(self):
        self.now()
        return {'ready':True,'protocol':1,'realm':self.realm,'production_approved':False}


class PgModel(RedisModel):
    """Reuse existing provider-independent transition rules; no Redis IO."""
    def touch(self,handle,*,expected_generation=None):
        return self.backend.touch(handle,expected_generation)


class PgChallenges(RedisChallenges):
    """Existing purpose/realm/rate transitions over PostgreSQL operations."""
