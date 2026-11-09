"""TEST ONLY metadata service, not protected infrastructure or a network codec.

Can run in a separate Manager process outside tested APP snapshot directories.
Its process/LMDB are deliberately not production durability evidence. Restart
creates a new incarnation and closes old bindings. No real tokens are stored.
"""
from copy import deepcopy
import secrets
from threading import RLock
import time

from session_authority import LocalRevisionAuthority,RevisionConflict
from session_realms import SessionStorageUnavailable


class TestMetadataService:
    __test__=False
    def __init__(self,path,namespace,*,existing=None):
        self.local=existing if existing is not None else LocalRevisionAuthority(path,bootstrap=True)
        if existing is None:
            self.local.configure(namespace,{'user':'test_epoch','admin':'test_epoch'})
        self.namespace=namespace
        self.identity=secrets.token_urlsafe(24)
        self.incarnation=secrets.token_urlsafe(24)
        self.sequence=0
        self.lock=RLock()
        self.closed=False

    def binding(self):
        return {'authority_id':self.identity,'incarnation':self.incarnation,'minimum_sequence':self.sequence}

    def exchange(self,request):
        with self.lock:
            if self.closed:raise OSError('Synthetic metadata service outage')
            status='ok';payload=None
            try:
                if (request['authority_id']!=self.identity or request['incarnation']!=self.incarnation):
                    raise SessionStorageUnavailable('binding')
                args=request['arguments'];op=request['operation']
                if op!='health' and args['namespace']!=self.namespace:
                    raise SessionStorageUnavailable('namespace')
                if op=='descriptor':payload=self.local.descriptor(args['namespace'])
                elif op=='read':
                    desc=self.local.descriptor(args['namespace'])
                    self.local.guard(args['namespace'],args['realm'],args['epoch'],desc['generation'])
                    payload=self.local.read(args['key'],time.time())
                elif op=='commit':
                    self.local.commit(args['namespace'],args['realm'],args['epoch'],args['generation'],
                                      args['expected'],args['changes'],time.time())
                    self.sequence+=1;payload=True
                elif op=='health':self.local.maintain();payload=True
                else:raise SessionStorageUnavailable('operation')
            except RevisionConflict:status='conflict'
            except SessionStorageUnavailable:status='closed'
            return deepcopy({'request_id':request['request_id'],'authority_id':self.identity,
                             'incarnation':self.incarnation,'sequence':self.sequence,'status':status,'payload':payload})

    def block(self):
        self.local.configure(self.namespace,{'user':'test_epoch','admin':'test_epoch'},state='BLOCKED')
        self.sequence+=1

    def stop(self):
        self.closed=True

    def close(self):
        self.local.close()
