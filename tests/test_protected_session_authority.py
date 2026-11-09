import tempfile
import time
import unittest
from unittest.mock import Mock,patch

from protected_session_authority import AuthorityBinding,ProtectedRevisionAuthority
from record_session_store import RedisRealm,local_realms
from session_authority import LocalRevisionAuthority,RevisionConflict
from session_realms import SessionStorageUnavailable,init_session_realms
from flask import Flask
from protected_authority_fixture import TestMetadataService


class ProtectedAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='rosago-phase2j-unit-')
        self.addCleanup(self.temp.cleanup)
        self.service=TestMetadataService(self.temp.name,'fixture')
        self.addCleanup(self.service.close)
        self.binding=AuthorityBinding(**self.service.binding())
        self.authority=ProtectedRevisionAuthority(self.service,self.binding)

    def test_missing_external_authority_closes_factory_before_any_storage(self):
        with patch('record_session_store.redis.Redis.from_url',side_effect=AssertionError('Redis touched')):
            with self.assertRaises(SessionStorageUnavailable):local_realms({})

    def test_raw_local_metadata_no_longer_authorizes_by_default(self):
        backend=RedisRealm(Mock(),Mock(),'fixture','user','test_epoch',authority=self.service.local)
        with self.assertRaises(SessionStorageUnavailable):backend.now()

    def test_production_safeguard_unconditional(self):
        with self.assertRaises(RuntimeError):init_session_realms(Flask('closed'),mode='production')

    def test_binding_validation(self):
        for seq in (-1,True,'1'):
            with self.subTest(sequence=seq),self.assertRaises(ValueError):AuthorityBinding('a'*20,'b'*20,seq)

    def test_descriptor_and_blocked_generation(self):
        self.authority.guard('fixture','user','test_epoch',1)
        self.service.block()
        with self.assertRaises(SessionStorageUnavailable):self.authority.guard('fixture','user','test_epoch',1)

    def test_unavailable_transport_never_falls_back(self):
        self.service.stop()
        with self.assertRaises(SessionStorageUnavailable):self.authority.descriptor('fixture')

    def test_replayed_wrong_nonce_stale_incarnation_and_sequence_are_denied(self):
        original=self.service.exchange
        for field,value in [('request_id','replayed'),('incarnation','stale'),('sequence',-1),('status','closed')]:
            def altered(request,field=field,value=value):
                answer=original(request);answer[field]=value;return answer
            with self.subTest(field=field),patch.object(self.service,'exchange',side_effect=altered):
                with self.assertRaises(SessionStorageUnavailable):self.authority.descriptor('fixture')

    def test_corrupted_descriptor_and_nonfinite_response_are_denied(self):
        original=self.service.exchange
        for payload in ({},{'generation':float('nan')},None):
            def altered(request,payload=payload):
                answer=original(request);answer['payload']=payload;return answer
            with self.subTest(kind=type(payload).__name__),patch.object(self.service,'exchange',side_effect=altered):
                with self.assertRaises(SessionStorageUnavailable):self.authority.descriptor('fixture')

    def test_late_response_is_rejected_without_retry(self):
        original=self.service.exchange;calls=[]
        def slow(request):
            calls.append(True);time.sleep(.01);return original(request)
        authority=ProtectedRevisionAuthority(Mock(exchange=slow),self.binding,response_budget=.001)
        with self.assertRaises(SessionStorageUnavailable):authority.descriptor('fixture')
        self.assertEqual(len(calls),1)

    def test_commit_conflict_and_cross_realm_scope(self):
        key='fixture:sessions:v3:user:test_epoch:auth:'+'a'*64
        meta={'digest':'b'*64,'expires':time.time()+60,'size':10,
              'scope':'fixture:sessions:v3:user:test_epoch:auth','realm_scope':'fixture:sessions:v3:user:test_epoch'}
        self.authority.commit('fixture','user','test_epoch',1,{key:None},{key:meta},time.time())
        self.assertEqual(self.authority.read(key,time.time()),meta)
        with self.assertRaises(RevisionConflict):
            self.authority.commit('fixture','user','test_epoch',1,{key:None},{key:meta},time.time())
        with self.assertRaises(SessionStorageUnavailable):
            self.authority.commit('fixture','admin','test_epoch',1,{key:meta},{key:None},time.time())
