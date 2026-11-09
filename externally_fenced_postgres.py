"""Inactive evaluation candidate: PostgreSQL is ciphertext cache, never authority.

All models use the independent ledger, including recovery/rates/browser state.
No hosted DSN factory or production startup switch is provided here.
"""
from contextlib import contextmanager
import hashlib
import os
import secrets
import time

import psycopg
from record_session_store import RedisRealm, RedisModel, Snapshot
from protected_session_authority import ProtectedRevisionAuthority
from session_authority import RevisionConflict
from session_realms import SessionStorageUnavailable


class ExternalPgRealm(RedisRealm):
    def __init__(self, pool, cipher, namespace, realm, epoch, *, authority):
        if not isinstance(authority, ProtectedRevisionAuthority):
            raise SessionStorageUnavailable('Independent authority is required.')
        super().__init__(None,cipher,namespace,realm,epoch,authority=authority)
        self.pool, self.pid = pool, os.getpid()
        self.guard()

    @contextmanager
    def transaction(self):
        if self.pid != os.getpid():
            raise SessionStorageUnavailable('Session pools must be created after fork.')
        try:
            with self.pool.connection(timeout=1) as connection:
                with connection.transaction():
                    connection.execute("SET LOCAL lock_timeout='400ms'")
                    connection.execute("SET LOCAL statement_timeout='700ms'")
                    connection.execute("SET LOCAL idle_in_transaction_session_timeout='1500ms'")
                    connection.execute('SET LOCAL synchronous_commit=on')
                    state=connection.execute("SELECT current_setting('fsync') fsync, pg_is_in_recovery() standby").fetchone()
                    if state['fsync']!='on' or state['standby']:
                        raise SessionStorageUnavailable('Session database durability is unavailable.')
                    yield connection
        except (psycopg.Error, TimeoutError):
            raise SessionStorageUnavailable('Session database operation is unavailable or unconfirmed.') from None

    def now(self):
        self.guard()
        with self.transaction() as connection:
            now=connection.execute('SELECT extract(epoch FROM clock_timestamp())::float8 t').fetchone()['t']
        if abs(now-time.time())>2:
            raise SessionStorageUnavailable('Session database clock is inconsistent.')
        self.guard()
        return now

    def snapshot(self,kind,handle,*,revocation_only=False):
        key=self.key(kind,handle); now=self.now()
        meta=self.authority.read(key,now)
        with self.transaction() as connection:
            row=connection.execute('SELECT ciphertext,expires FROM rosago_session.payloads WHERE key=%s',(key,)).fetchone()
        raw=bytes(row['ciphertext']) if row else None
        self.guard()
        if self.authority.read(key,now)!=meta:
            raise RevisionConflict('Independent session revision changed.')
        if revocation_only or meta is None:
            return Snapshot(kind,key,meta,raw,None,now,revocation_only)
        if (not row or row['expires']<=now or row['expires']>meta['expires']+.001
                or not raw or hashlib.sha256(raw).hexdigest()!=meta['digest']):
            raise RevisionConflict('Session publication is unavailable or stale.')
        value=self.cipher.decrypt(raw,key.encode())
        if value['expires']<=now:
            raise SessionStorageUnavailable('Session envelope expired.')
        return Snapshot(kind,key,meta,raw,value['data'],now)

    def atomic(self,snapshots,updates):
        if not 0<len(snapshots)<=8 or not updates or set(updates)-set(snapshots):
            raise ValueError('Invalid bounded session transition.')
        now=self.now()
        if any(s.key!=k or not k.startswith(self.prefix+':') or abs(now-s.now)>2
               or (s.revocation_only and (k not in updates or updates[k][0] is not None))
               for k,s in snapshots.items()):
            raise RevisionConflict('Session transition is stale or outside its scope.')
        changes={}; encrypted={}; operation=secrets.token_urlsafe(24)
        for key,(data,expires,extra) in updates.items():
            if data is None:
                changes[key]=None;continue
            if not now<expires<=now+28801 or not now<extra.get('absolute',expires)<=now+28801:
                raise ValueError('Invalid session lifetime.')
            raw=self.cipher.encrypt({'data':data,'expires':extra.get('absolute',expires),'operation':operation},key.encode())
            # Derived security metadata cannot be overridden by caller extras.
            changes[key]={**extra,'digest':hashlib.sha256(raw).hexdigest(),'expires':expires,
                'size':len(raw),'scope':self.prefix+':'+snapshots[key].kind,'realm_scope':self.prefix}
            encrypted[key]=raw
        self.authority.commit(self.namespace,self.realm,self.epoch,self.generation,
                              {k:s.meta for k,s in snapshots.items()},changes,now)
        # Never roll back the independent commit, nor retry publication/provider
        # operations, when the following database transaction is uncertain.
        if encrypted:
            with self.transaction() as connection:
                for key in sorted(updates):
                    lock=int.from_bytes(hashlib.sha256(key.encode()).digest()[:8],'big',signed=True)
                    connection.execute('SELECT pg_advisory_xact_lock(%s)',(lock,))
                for key,raw in encrypted.items():
                    row=connection.execute('SELECT ciphertext FROM rosago_session.payloads WHERE key=%s',(key,)).fetchone()
                    old=bytes(row['ciphertext']) if row else None
                    if old!=snapshots[key].raw:
                        raise RevisionConflict('Session cache publication changed.')
                    connection.execute('INSERT INTO rosago_session.payloads VALUES(%s,%s,%s) '
                        'ON CONFLICT(key) DO UPDATE SET ciphertext=excluded.ciphertext, expires=excluded.expires',
                        (key,raw,changes[key]['expires']))
        # Deletion of cache bytes is best effort after authoritative revocation.
        try:
            with self.transaction() as connection:
                for key,value in changes.items():
                    if value is None:
                        connection.execute('DELETE FROM rosago_session.payloads WHERE key=%s AND ciphertext IS NOT DISTINCT FROM %s',
                                           (key,snapshots[key].raw))
                connection.execute('DELETE FROM rosago_session.payloads WHERE key IN '
                    '(SELECT key FROM rosago_session.payloads WHERE expires<%s LIMIT 64)',(now,))
        except SessionStorageUnavailable:
            pass
        self.guard()

    def readiness(self):
        self.now();self.authority.maintain()
        return {'ready':True,'protocol':3,'realm':self.realm,'production_approved':False}

    def logout_receipts(self,*,cursor='',limit=8):
        if type(limit) is not int or not 1<=limit<=16 or type(cursor) is not str or (cursor and not cursor.startswith(self.prefix+':logout:')):
            raise ValueError('Invalid bounded logout scan.')
        now=self.now()
        with self.transaction() as connection:
            rows=connection.execute('SELECT key,ciphertext,expires FROM rosago_session.payloads '
                'WHERE starts_with(key,%s) AND key>%s AND expires>%s ORDER BY key LIMIT %s',
                (self.prefix+':logout:',cursor,now,limit)).fetchall()
        found=[]
        for row in rows:
            key=row['key'];meta=self.authority.read(key,now)
            if meta is None:continue
            raw=bytes(row['ciphertext'])
            if hashlib.sha256(raw).hexdigest()!=meta['digest'] or row['expires']>meta['expires']+.001:
                raise RevisionConflict('Logout receipt publication changed.')
            data=self.cipher.decrypt(raw,key.encode())['data']
            if data.get('state') not in ('attempted','prepared'):continue
            handle=data.get('web_handle')
            if self.key('logout',handle)!=key:
                raise SessionStorageUnavailable('Logout receipt binding is inconsistent.')
            snap=self.snapshot('logout',handle)
            if snap.data:found.append(snap)
        self.guard()
        return found,rows[-1]['key'] if len(rows)==limit else ''


class ExternalPgModel(RedisModel):
    def touch(self,handle,*,expected_generation=None):
        snap=self._read(handle)
        if (not snap or not snap.data or snap.meta['busy']
                or expected_generation is not None and snap.meta['generation']!=expected_generation):
            return False
        now=self.backend.now()
        extra={k:v for k,v in snap.meta.items() if k not in ('digest','expires','size','scope','realm_scope')}
        self.backend.write(snap,snap.data,min(now+1800,snap.meta['absolute']),**{**extra,'activity':now})
        return True
