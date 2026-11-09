"""Independent, fsynced revision authority for LOCAL, SAME-HOST qualification.

This is not Redis and uses no SQL. Never restore it together with Redis data.
Production/multi-host authority and recovery controls remain a release blocker.
Only metadata/digests live here; credentials remain encrypted in Redis.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import struct
from threading import Lock
import time

import lmdb
from session_realms import SessionStorageUnavailable


class RevisionConflict(SessionStorageUnavailable):
    pass


_environments, _environment_lock = {}, Lock()


def encoded(value):
    return json.dumps(value, separators=(',', ':'), allow_nan=False).encode()


class LocalRevisionAuthority:
    """One LMDB environment shared by processes on a LOCAL filesystem only.

    No network filesystem, async fsync, worker-local positive authority cache,
    auto-bootstrap or rollback of a revision after a failed Redis publish.
    """
    def __init__(self, path, *, bootstrap=False, map_size=64 * 1024 * 1024,
                 lock_timeout=1.0, record_limit=4096, byte_limit=32*1024*1024):
        if os.fspath(path).startswith('\\\\'):
            raise SessionStorageUnavailable('Local revision authority cannot use a network filesystem.')
        self.path = Path(path).resolve()
        if str(self.path).startswith('\\\\') or any(part.casefold().startswith('onedrive') for part in self.path.parts):
            raise SessionStorageUnavailable('Local revision authority requires an unsynchronized local filesystem.')
        if not bootstrap and not (self.path / 'data.mdb').is_file():
            raise SessionStorageUnavailable('Independent session authority is not initialized.')
        self.path.mkdir(parents=True, exist_ok=True)
        self.lock_timeout, self.record_limit, self.byte_limit = lock_timeout, record_limit, byte_limit
        identity = (os.getpid(), str(self.path))
        with _environment_lock:
            if identity not in _environments:
                env = lmdb.open(str(self.path), map_size=map_size, max_dbs=4,
                    sync=True, metasync=True, writemap=False, map_async=False,
                    max_readers=256, create=bootstrap)
                databases = {n:env.open_db(n.encode()) for n in ('records', 'expiry', 'control', 'quotas')}
                _environments[identity] = env, databases
            self.env, self.db = _environments[identity]

    @contextmanager
    def writer(self):
        try:
            with self._writer_transaction() as transaction:
                yield transaction
        except (OSError,lmdb.Error):
            raise SessionStorageUnavailable('Independent session authority unavailable.') from None

    @contextmanager
    def _writer_transaction(self):
        # All writers in this module honor this bounded OS lock before entering
        # LMDB's single-writer transaction. Never held over a provider request.
        with (self.path / 'writer.lock').open('a+b') as handle:
            if handle.tell() == 0:
                handle.write(b'0')
                handle.flush()
            deadline = time.monotonic() + self.lock_timeout
            acquired = False
            try:
                while not acquired:
                    try:
                        handle.seek(0)
                        if os.name == 'nt':
                            import msvcrt
                            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        else:
                            import fcntl
                            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        acquired = True
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise SessionStorageUnavailable('Session authority is busy.') from None
                        time.sleep(.005)
                with self.env.begin(write=True) as transaction:
                    yield transaction
            except lmdb.Error:
                raise SessionStorageUnavailable('Independent session authority unavailable.') from None
            finally:
                if acquired:
                    handle.seek(0)
                    if os.name == 'nt':
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle, fcntl.LOCK_UN)

    def configure(self, namespace, epochs, *, state='OPEN'):
        """Explicit LOCAL operator/test setup, never automatic request fallback."""
        with self.writer() as tx:
            old = self._get(tx, 'control', namespace)
            descriptor = {'generation':old['generation']+1 if old else 1,
                          'epochs':dict(epochs), 'state':state,
                          'limits':{'records':self.record_limit,'bytes':self.byte_limit}}
            tx.put(namespace.encode(), encoded(descriptor), db=self.db['control'])
        return descriptor

    def _get(self, tx, database, key):
        raw = tx.get(key.encode(), db=self.db[database])
        return json.loads(raw) if raw else None

    def descriptor(self, namespace):
        try:
            with self.env.begin() as tx:
                return self._get(tx, 'control', namespace)
        except (lmdb.Error, ValueError):
            raise SessionStorageUnavailable('Independent session authority unavailable.') from None

    def guard(self, namespace, realm, epoch, generation, *, tx=None):
        current = self._get(tx, 'control', namespace) if tx else self.descriptor(namespace)
        if (not isinstance(current,dict) or current.get('state') != 'OPEN' or current.get('generation') != generation
                or current.get('epochs',{}).get(realm) != epoch
                or current.get('limits')!={'records':self.record_limit,'bytes':self.byte_limit}):
            raise SessionStorageUnavailable('Session generation is not approved.')

    def read(self, key, now):
        try:
            with self.env.begin() as tx:
                value = self._get(tx, 'records', key)
                return value if value and value['expires'] > now else None
        except (lmdb.Error, ValueError):
            raise SessionStorageUnavailable('Independent session authority unavailable.') from None

    def _expiry_key(self, key, expiry):
        return struct.pack('>Q', int(expiry * 1000)) + hashlib.sha256(key.encode()).digest()

    def _remove(self, tx, key, old):
        for scope in (old['scope'],old['realm_scope']):
            quota = self._get(tx, 'quotas', scope) or {'count':0, 'bytes':0}
            quota['count'] -= 1
            quota['bytes'] -= old['size']
            tx.put(scope.encode(), encoded(quota), db=self.db['quotas'])
        tx.delete(self._expiry_key(key, old['expires']), db=self.db['expiry'])
        tx.delete(key.encode(), db=self.db['records'])

    def _prune(self, tx, now, limit=256):
        cursor = tx.cursor(db=self.db['expiry'])
        expired = []
        for key, value in cursor:
            if struct.unpack('>Q', key[:8])[0] > now*1000 or len(expired) >= limit:
                break
            expired.append((bytes(key), value.decode()))
        cursor.close()
        for expiry_key, key in expired:
            old = self._get(tx, 'records', key)
            if old and old['expires'] <= now:
                self._remove(tx, key, old)
            else:
                tx.delete(expiry_key, db=self.db['expiry'])

    def commit(self, namespace, realm, epoch, generation, expected, changes, now):
        """Durably fence ALL revisions first. Cache publish may subsequently fail.

        Deletion removes authority, even if an older Redis ciphertext survives.
        Never roll this commit back to 'repair' a failed cache write.
        """
        with self.writer() as tx:
            self.guard(namespace, realm, epoch, generation, tx=tx)
            self._prune(tx, now)
            for key, wanted in expected.items():
                current = self._get(tx, 'records', key)
                if current and current['expires'] <= now:
                    current = None
                if current != wanted:
                    raise RevisionConflict('Session state changed.')
            # Delete/replacement credit is taken before admission; one LMDB
            # transaction rolls back all bookkeeping on any rejection.
            for key in changes:
                old = self._get(tx, 'records', key)
                if old:
                    self._remove(tx, key, old)
            for key, value in changes.items():
                if value is None:
                    continue
                for scope in (value['scope'],value['realm_scope']):
                    quota = self._get(tx, 'quotas', scope) or {'count':0, 'bytes':0}
                    if ((scope==value['scope'] and quota['count'] >= self.record_limit)
                            or quota['bytes'] + value['size'] > self.byte_limit):
                        raise SessionStorageUnavailable('Session admission limit exceeded.')
                    quota['count'] += 1
                    quota['bytes'] += value['size']
                    tx.put(scope.encode(), encoded(quota), db=self.db['quotas'])
                tx.put(key.encode(), encoded(value), db=self.db['records'])
                tx.put(self._expiry_key(key, value['expires']), key.encode(), db=self.db['expiry'])

    def maintain(self, now=None):
        with self.writer() as tx:
            self._prune(tx, time.time() if now is None else now)

    def close(self):
        """Only after all apps/threads in this process stop using this path."""
        identity = (os.getpid(), str(self.path))
        with _environment_lock:
            resource = _environments.pop(identity, None)
            if resource:
                resource[0].close()
