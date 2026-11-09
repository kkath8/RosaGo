"""LOCAL TEST ONLY recovery controller; not independently protected infra."""
from threading import RLock
import time
from postgres_session_recovery import RecoveryBinding,RecoveryProof


class TestRecoveryController:
    __test__=False
    def __init__(self,binding):
        self.binding=binding;self.revision=1;self.state='OPEN';self.freshness='VERIFIED'
        self.available=True;self.lock=RLock()
    def proof(self,namespace,request_id):
        with self.lock:
            if not self.available:raise OSError('Synthetic recovery authority outage')
            return RecoveryProof(request_id,self.binding,self.revision,time.time(),self.state,self.freshness)
    def change(self,binding=None,state='OPEN',freshness='VERIFIED'):
        with self.lock:
            if binding is not None:self.binding=binding
            self.state=state;self.freshness=freshness;self.revision+=1
