"""Fail-closed client boundary for an independently protected metadata service.

No transport, credentials or production backend is supplied here. The service
MUST provide linearizable durable CAS and restore-safe incarnation binding in a
failure/admin domain independent of application backups. A matching response is
not evidence of those infrastructure properties. Test transports are not such
evidence. Redis/LMDB/journals must not bootstrap the binding.
"""
from dataclasses import dataclass
import json
import math
import re
import secrets
from threading import RLock
import time
from typing import Protocol

from session_realms import SessionStorageUnavailable
from session_authority import RevisionConflict


class FreshnessTransport(Protocol):
    def exchange(self, request: dict) -> dict:
        """Authenticated, bounded, non-retrying call to current authority.

        Server enforces binding on EVERY operation. A commit atomically checks
        generation, expected records, quotas/deadlines and replaces <=8 records.
        Unknown commit outcomes must never be retried automatically. Network
        nonce/sequence validation does not make a rolled-back server safe.
        """
        ...


@dataclass(frozen=True)
class AuthorityBinding:
    authority_id: str
    incarnation: str
    minimum_sequence: int

    def __post_init__(self):
        if (not all(type(v) is str and re.fullmatch(r'[A-Za-z0-9_-]{16,128}',v)
                    for v in (self.authority_id,self.incarnation))
                or type(self.minimum_sequence) is not int or self.minimum_sequence<0):
            raise ValueError('Invalid independently supplied authority binding.')


class ProtectedRevisionAuthority:
    """Sole source of metadata; local LMDB is never consulted or restored.

    Binding and authenticated transport must come from a separately reviewed
    control plane, not from a snapshot. Missing/inconsistent proof denies access.
    No positive metadata cache or local failover exists. Method API preserves
    RedisRealm's independent-prepare-before-cache-publication boundary.
    """
    def __init__(self, transport: FreshnessTransport, binding: AuthorityBinding, *, response_budget=1.0):
        if transport is None or not callable(getattr(transport,'exchange',None)) or not isinstance(binding,AuthorityBinding):
            raise SessionStorageUnavailable('Protected freshness authority is not configured.')
        if type(response_budget) not in (int,float) or not 0<response_budget<=2:
            raise ValueError('Invalid authority response budget.')
        self.transport,self.binding,self.response_budget=transport,binding,response_budget
        self._floor=binding.minimum_sequence
        self._lock=RLock()

    def _rpc(self, operation, arguments):
        started=time.monotonic()
        if not self._lock.acquire(timeout=self.response_budget):
            raise SessionStorageUnavailable('Protected freshness authority is busy.')
        try:
            nonce=secrets.token_urlsafe(32)
            request={'version':1,'request_id':nonce,'authority_id':self.binding.authority_id,
                     'incarnation':self.binding.incarnation,'operation':operation,'arguments':arguments}
            try:
                if len(json.dumps(request,allow_nan=False))>65536:
                    raise ValueError('bounds')
                if time.monotonic()-started>=self.response_budget:
                    raise ValueError('deadline')
                response=self.transport.exchange(request)
                if time.monotonic()-started>self.response_budget:
                    raise ValueError('deadline')
                if (type(response) is not dict or len(json.dumps(response,allow_nan=False))>65536
                        or response.get('request_id')!=nonce
                        or response.get('authority_id')!=self.binding.authority_id
                        or response.get('incarnation')!=self.binding.incarnation
                        or type(response.get('sequence')) is not int or response['sequence']<self._floor):
                    raise ValueError('freshness')
                self._floor=response['sequence']
                if response.get('status')=='conflict':
                    raise RevisionConflict('Protected authority revision changed.')
                if response.get('status')!='ok':
                    raise ValueError('closed')
                return response['payload']
            except RevisionConflict:
                raise
            except Exception:
                # No raw transport exceptions, identities, references or payloads.
                raise SessionStorageUnavailable('Protected freshness authority is unavailable or inconsistent.') from None
        finally:
            self._lock.release()

    def descriptor(self, namespace):
        value=self._rpc('descriptor',{'namespace':namespace})
        if (type(value) is not dict or type(value.get('generation')) is not int or value['generation']<1
                or value.get('state') not in ('OPEN','BLOCKED','QUALIFYING')
                or type(value.get('epochs')) is not dict or set(value['epochs'])!={'user','admin'}
                or any(type(v) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',v) for v in value['epochs'].values())
                or type(value.get('limits')) is not dict
                or set(value['limits'])!={'records','bytes'}
                or any(type(v) is not int or v<=0 for v in value['limits'].values())):
            raise SessionStorageUnavailable('Protected authority descriptor is invalid.')
        return value

    def guard(self, namespace, realm, epoch, generation):
        value=self.descriptor(namespace)
        if value['state']!='OPEN' or value['generation']!=generation or value['epochs'].get(realm)!=epoch:
            raise SessionStorageUnavailable('Protected authority generation is closed.')

    def read(self, key, now):
        parts=key.split(':')
        if len(parts)!=7 or parts[1:3]!=['sessions','v3'] or parts[3] not in ('user','admin'):
            raise SessionStorageUnavailable('Invalid protected record scope.')
        value=self._rpc('read',{'namespace':parts[0],'realm':parts[3],'epoch':parts[4],'key':key,'now':now})
        if value is not None:
            required={'digest','expires','size','scope','realm_scope'}
            if (type(value) is not dict or not required<=set(value)
                    or type(value['digest']) is not str or not re.fullmatch(r'[a-f0-9]{64}',value['digest'])
                    or type(value['expires']) not in (int,float) or not math.isfinite(value['expires'])
                    or value['expires']<=now or type(value['size']) is not int or not 0<value['size']<=45000
                    or value['realm_scope']!=':'.join(parts[:5]) or value['scope']!=':'.join(parts[:6])):
                raise SessionStorageUnavailable('Protected authority record is invalid.')
        return value

    def commit(self, namespace, realm, epoch, generation, expected, changes, now):
        prefix=f'{namespace}:sessions:v3:{realm}:{epoch}:'
        if (realm not in ('user','admin') or not 0<len(expected)<=8 or not changes
                or set(changes)-set(expected) or any(not key.startswith(prefix) for key in expected)):
            raise SessionStorageUnavailable('Invalid protected transaction scope.')
        result=self._rpc('commit',{'namespace':namespace,'realm':realm,'epoch':epoch,'generation':generation,
                                  'expected':expected,'changes':changes,'now':now})
        if result is not True:
            raise SessionStorageUnavailable('Protected authority commit was not acknowledged.')

    def maintain(self):
        # Cleanup is service-owned; unrelated app traffic cannot renew metadata.
        if self._rpc('health',{}) is not True:
            raise SessionStorageUnavailable('Protected authority readiness is closed.')
