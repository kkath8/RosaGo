"""Reusable real Redis v3 contract cases, isolated metadata and synthetic users."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import json
import multiprocessing
import os
import secrets
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

import redis
from redis_session_store import RedisRealm,RedisModel,RedisChallenges,SessionCipher
from session_authority import LocalRevisionAuthority,RevisionConflict
from session_realms import SessionStorageUnavailable
from normal_auth_coordinator import VerifiedLoginCredentials

URL=os.environ.get('ROSAGO_TEST_REDIS_URL')
A='11111111-1111-4111-8111-111111111111'
B='22222222-2222-4222-8222-222222222222'


def process_probe(url,key,namespace,handle,path,output):
    client=redis.Redis.from_url(url,socket_timeout=1)
    authority=LocalRevisionAuthority(path)
    try:
        realm=RedisRealm(client,SessionCipher({'test':key},'test'),namespace,'user','test_epoch',authority=authority,unprotected_local_testing=True)
        record=RedisModel(realm,'auth').resolve(handle)
        output.put(record.user_id if record else None)
    finally:
        client.close()
        authority.close()


def process_reserve(url,key,namespace,handle,path,output):
    client=redis.Redis.from_url(url,socket_timeout=1)
    authority=LocalRevisionAuthority(path)
    try:
        realm=RedisRealm(client,SessionCipher({'test':key},'test'),namespace,'user','test_epoch',authority=authority,unprotected_local_testing=True)
        output.put(RedisModel(realm,'auth').reserve_refresh(handle) is not None)
    finally:
        client.close()
        authority.close()


@unittest.skipUnless(URL,'Explicit loopback Redis URL required.')
class RedisTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(urlsplit(URL).hostname,'127.0.0.1')
        self.client=redis.Redis.from_url(URL,socket_timeout=1,socket_connect_timeout=1,
            retry=redis.retry.Retry(redis.backoff.NoBackoff(),0))
        self.client.ping()
        self.namespace='phase2f_test_'+secrets.token_hex(12)
        self.temp=tempfile.TemporaryDirectory(prefix='rosago-phase2f-authority-')
        self.addCleanup(self.temp.cleanup)
        self.authority=LocalRevisionAuthority(self.temp.name,bootstrap=True)
        self.addCleanup(self.authority.close)
        self.authority.configure(self.namespace,{'user':'test_epoch','admin':'test_epoch'})
        self.key_material=secrets.token_bytes(32)
        self.cipher=SessionCipher({'test':self.key_material},'test')
        # Historical local-storage mechanics only, not rollback-safe authority.
        self.realms={r:RedisRealm(self.client,self.cipher,self.namespace,r,'test_epoch',authority=self.authority,unprotected_local_testing=True) for r in ('user','admin')}
        self.addCleanup(self.client.close)
        self.addCleanup(self.cleanup_keys)

    def cleanup_keys(self):
        keys=list(self.client.scan_iter(self.namespace+':sessions:v3:*'))
        if keys:
            self.client.delete(*keys)

    def credentials(self,realm='user'):
        return VerifiedLoginCredentials(A if realm=='user' else B,realm+'@example.invalid',
            realm+'-access',realm+'-refresh',time.time()+3600,realm+'-provider-session')

    def store(self,realm='user',kind='auth'):
        return RedisModel(self.realms[realm],kind)

    def short_expiry(self,kind,handle,seconds=.15,realm='user'):
        backend=self.realms[realm]
        snap=backend.snapshot(kind,handle)
        extra={k:v for k,v in snap.meta.items() if k in ('absolute','activity','generation','busy')}
        backend.write(snap,snap.data,snap.now+seconds,**extra)

    def test_encryption_and_realm_aad(self):
        handle=self.store().create(**asdict(self.credentials()))
        key=self.realms['user'].key('auth',handle)
        raw=self.client.get(key)
        for value in (handle,A,'user-access','user-refresh'):
            self.assertNotIn(value.encode(),raw)
        self.assertEqual(self.store().resolve(handle).user_id,A)
        self.assertIsNone(self.store('admin').resolve(handle))
        with self.assertRaises(SessionStorageUnavailable):
            self.cipher.decrypt(raw,self.realms['admin'].key('auth',handle).encode())

    def test_actual_second_process_reads_authority(self):
        handle=self.store().create(**asdict(self.credentials()))
        context=multiprocessing.get_context('spawn')
        output=context.Queue()
        worker=context.Process(target=process_probe,args=(URL,self.key_material,self.namespace,handle,self.temp.name,output))
        worker.start()
        worker.join(15)
        if worker.is_alive():
            worker.terminate();worker.join()
        self.assertEqual(worker.exitcode,0)
        self.assertEqual(output.get(timeout=2),A)
        output.close()

    def test_rollback_after_acknowledged_logout_does_not_restore_authority(self):
        handle=self.store().create(**asdict(self.credentials()))
        key=self.realms['user'].key('auth',handle)
        before=self.client.get(key)
        self.assertTrue(self.store().revoke(handle))
        self.client.set(key,before,ex=1800)
        self.assertIsNone(self.store().resolve(handle))
        restarted=RedisRealm(self.client,self.cipher,self.namespace,'user','test_epoch',authority=LocalRevisionAuthority(self.temp.name),unprotected_local_testing=True)
        self.assertIsNone(RedisModel(restarted,'auth').resolve(handle))

    def test_separate_process_refresh_has_single_owner(self):
        handle=self.store().create(**asdict(self.credentials()))
        context=multiprocessing.get_context('spawn')
        output=context.Queue()
        workers=[context.Process(target=process_reserve,args=(URL,self.key_material,self.namespace,handle,self.temp.name,output)) for _ in range(3)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(15)
            if worker.is_alive():
                worker.terminate();worker.join()
            self.assertEqual(worker.exitcode,0)
        self.assertEqual(sum(output.get(timeout=2) for _ in workers),1)
        output.close()

    def test_acl_rejects_other_realm_and_nested_script_access(self):
        identity=self.namespace+'_acl'
        password=secrets.token_urlsafe(32)
        self.client.acl_setuser(identity,enabled=True,reset=True,passwords=['+'+password],
            keys=[self.realms['user'].prefix+':*'],commands=['+get','+pttl','+pexpireat','+mget','+mset','+eval','+time','+info','+role','+del'])
        limited=redis.Redis(host='127.0.0.1',port=self.client.connection_pool.connection_kwargs['port'],
                            username=identity,password=password,socket_timeout=1)
        try:
            user=RedisRealm(limited,self.cipher,self.namespace,'user','test_epoch',authority=self.authority,unprotected_local_testing=True)
            handle=RedisModel(user,'auth').create(**asdict(self.credentials()))
            self.assertEqual(RedisModel(user,'auth').resolve(handle).user_id,A)
            forbidden=self.realms['admin'].key('auth',handle)
            with self.assertRaises(redis.ResponseError):
                limited.eval("return redis.call('GET',ARGV[1])",0,forbidden)
            with self.assertRaises(redis.ResponseError):
                limited.get(forbidden)
        finally:
            limited.close()
            self.client.acl_deluser(identity)

    def test_rollback_to_pre_refresh_or_pre_reservation_is_denied(self):
        handle=self.store().create(**asdict(self.credentials()))
        key=self.realms['user'].key('auth',handle)
        before=self.client.get(key)
        lease,_=self.store().reserve_refresh(handle)
        self.client.set(key,before,ex=1800)
        with self.assertRaises(SessionStorageUnavailable):
            self.store().resolve(handle)

    def test_refresh_one_owner_then_late_commit_rejected(self):
        for _ in range(10):
            handle=self.store().create(**asdict(self.credentials()))
            with ThreadPoolExecutor(max_workers=4) as pool:
                results=list(pool.map(lambda _:self.store().reserve_refresh(handle),range(4)))
            self.assertEqual(sum(r is not None for r in results),1)
            lease,_=next(r for r in results if r)
            self.store().revoke(handle)
            self.assertFalse(self.store().replace_credentials(handle,lease,**asdict(self.credentials())))

    def test_expired_refresh_is_terminal(self):
        handle=self.store().create(**asdict(self.credentials()))
        self.store().reserve_refresh(handle)
        self.short_expiry('auth',handle)
        time.sleep(.2)
        self.assertIsNone(self.store().resolve(handle))
        self.assertIsNone(self.store().reserve_refresh(handle))

    def test_refresh_commit_rotates_generation(self):
        handle=self.store().create(**asdict(self.credentials()))
        lease,_=self.store().reserve_refresh(handle)
        self.assertTrue(self.store().replace_credentials(handle,lease,**asdict(self.credentials())))
        self.assertEqual(self.store().resolve(handle).generation,1)

    def test_reads_do_not_rewrite_and_touch_only_updates_ttl(self):
        handle=self.store().create(**asdict(self.credentials()))
        key=self.realms['user'].key('auth',handle)
        raw=self.client.get(key)
        with patch.object(self.client,'eval',wraps=self.client.eval) as writes:
            for _ in range(4):
                self.assertIsNotNone(self.store().resolve(handle))
            self.assertTrue(self.store().touch(handle,expected_generation=0))
        self.assertEqual(writes.call_count,0)
        self.assertEqual(self.client.get(key),raw)

    def test_web_cas_and_deleted_record_not_recreated(self):
        store=self.store(kind='web')
        handle=store.create({'setting':'old'})
        values,version=store.read(handle)
        self.assertTrue(store.save(handle,version,{'setting':'new'}))
        self.assertFalse(store.save(handle,version,values))
        store.revoke(handle)
        self.assertFalse(store.save(handle,version,values))

    def test_independent_family_ttls_and_cleanup(self):
        email=self.store(kind='email').create('fixture@example.invalid')
        pending=self.store(kind='pending').create()
        self.short_expiry('email',email)
        self.short_expiry('pending',pending)
        time.sleep(.2)
        self.store().create(**asdict(self.credentials()))
        self.assertIsNone(self.store(kind='email').get(email))
        self.assertIsNone(self.store(kind='pending').lookup(pending))
        for kind,handle in (('email',email),('pending',pending)):
            self.assertFalse(self.client.exists(self.realms['user'].key(kind,handle)))
            self.assertIsNone(self.authority.read(self.realms['user'].key(kind,handle),time.time()))

    def test_challenge_purpose_consumption_and_rate(self):
        challenge=RedisChallenges(self.realms)
        token=challenge.issue('user')
        self.assertFalse(challenge.valid('admin',token))
        self.assertTrue(challenge.valid('user',token,consume=True))
        self.assertFalse(challenge.valid('user',token,consume=True))
        for _ in range(20):
            self.assertTrue(challenge.allow_attempt('user','fixture'))
        self.assertFalse(challenge.allow_attempt('user','fixture'))
        self.assertTrue(challenge.allow_attempt('admin','fixture'))

    def test_recovery_and_verification_single_use(self):
        pending=self.store(kind='pending')
        handle=pending.create()
        lease,record=pending.reserve(handle)
        self.assertTrue(record.verifier)
        self.assertIsNone(pending.reserve(handle))
        pending.release(handle,lease)
        self.assertIsNone(pending.lookup(handle))
        grants=self.store(kind='grants')
        grant=grants.issue(A,'synthetic-provider',time.time()+60,'synthetic-recovery')
        self.assertIsNone(grants.issue(A,'synthetic-provider',time.time()+60,'synthetic-recovery'))
        lease,record=grants.reserve(grant)
        grants.release(grant,lease)
        self.assertFalse(grants.valid(grant))
        email=self.store(kind='email')
        handle=email.create('fixture@example.invalid')
        self.assertIsNotNone(email.reserve(handle,'verify')[0])
        self.assertIsNone(email.reserve(handle,'verify')[0])
        email.finish(handle,verified=True)
        self.assertTrue(email.get(handle).verified)

    def test_generation_gate_and_missing_authority_fail_closed(self):
        handle=self.store().create(**asdict(self.credentials()))
        self.authority.configure(self.namespace,{'user':'new','admin':'new'},state='BLOCKED')
        with self.assertRaises(SessionStorageUnavailable):
            self.store().resolve(handle)
        missing=RedisRealm(self.client,self.cipher,self.namespace,'user','test_epoch')
        with self.assertRaises(SessionStorageUnavailable):
            missing.snapshot('auth',handle)

    def test_capacity_credit_and_revocation_at_limit(self):
        self.authority.record_limit=1
        self.authority.configure(self.namespace,{'user':'test_epoch','admin':'test_epoch'})
        self.realms={r:RedisRealm(self.client,self.cipher,self.namespace,r,'test_epoch',authority=self.authority,unprotected_local_testing=True) for r in self.realms}
        handle=self.store().create(**asdict(self.credentials()))
        with self.assertRaises(SessionStorageUnavailable):
            self.store().create(**asdict(self.credentials()))
        self.assertTrue(self.store().touch(handle,expected_generation=0))
        self.assertTrue(self.store().revoke(handle))
        self.assertIsNotNone(self.store().create(**asdict(self.credentials())))

    def test_oversize_rejected_before_authority_change(self):
        handle=self.store(kind='web').create({'safe':'yes'})
        with self.assertRaises(SessionStorageUnavailable):
            self.store(kind='web').save(handle,0,{'oversize':'x'*40000})
        self.assertEqual(self.store(kind='web').read(handle)[0],{'safe':'yes'})

    def test_dropped_publish_ack_reconciles_without_provider_retry(self):
        original=self.client.eval
        def lost(*args,**kwargs):
            original(*args,**kwargs)
            raise redis.ConnectionError('Synthetic lost acknowledgment.')
        with patch.object(self.client,'eval',side_effect=lost):
            handle=self.store().create(**asdict(self.credentials()))
        self.assertIsNotNone(self.store().resolve(handle))

    def test_publish_failure_never_rolls_authority_back(self):
        handle=self.store().create(**asdict(self.credentials()))
        with patch.object(self.client,'eval',side_effect=redis.ConnectionError('Synthetic outage.')):
            with self.assertRaises(SessionStorageUnavailable):
                self.store().reserve_refresh(handle)
        with self.assertRaises(SessionStorageUnavailable):
            self.store().resolve(handle)

    def test_uncertain_revision_can_be_revoked_but_not_reinstalled(self):
        handle=self.store().create(**asdict(self.credentials()))
        with patch.object(self.client,'eval',side_effect=redis.ConnectionError('Synthetic outage.')):
            with self.assertRaises(SessionStorageUnavailable):
                self.store().reserve_refresh(handle)
        snap=self.realms['user'].snapshot('auth',handle,revocation_only=True)
        with self.assertRaises(ValueError):
            self.realms['user'].write(snap,{'forbidden':'replacement'},snap.now+60)
        self.assertTrue(self.store().revoke(handle))
        self.assertIsNone(self.store().resolve(handle))

    def test_clock_fault_and_cache_loss_denied(self):
        handle=self.store().create(**asdict(self.credentials()))
        with patch('record_session_store.time.time',return_value=time.time()+10):
            with self.assertRaises(SessionStorageUnavailable):
                self.store().resolve(handle)
        self.client.delete(self.realms['user'].key('auth',handle))
        with self.assertRaises(SessionStorageUnavailable):
            self.store().resolve(handle)

    def test_key_rotation_and_tamper(self):
        old=secrets.token_bytes(32)
        new=secrets.token_bytes(32)
        source=SessionCipher({'old':old},'old')
        target=SessionCipher({'old':old,'new':new},'new')
        raw=source.encrypt({'synthetic':'value'},b'context')
        self.assertEqual(target.decrypt(raw,b'context'),{'synthetic':'value'})
        with self.assertRaises(SessionStorageUnavailable):
            target.decrypt(raw,b'other')

    def test_connection_pool_exhaustion_is_unavailable(self):
        handle=self.store().create(**asdict(self.credentials()))
        pool=self.client.connection_pool
        old_limit=pool.max_connections
        pool.max_connections=2
        held=[]
        try:
            held=[pool.get_connection() for _ in range(2)]
            with self.assertRaises(SessionStorageUnavailable):
                self.store().resolve(handle)
        finally:
            for connection in held:
                pool.release(connection)
            pool.max_connections=old_limit
        self.assertIsNotNone(self.store().resolve(handle))

    def test_authority_lock_wait_is_bounded(self):
        with self.authority.writer():
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(self.store().create,**asdict(self.credentials()))
                with self.assertRaises(SessionStorageUnavailable):
                    future.result(timeout=3)
