"""Inactive PostgreSQL recovery-control contract, NOT a protected service.

The provider must independently verify current recovery state outside database
and deployment rollback. No environment/database bootstrap or local provider is
implemented. Local test providers establish only conditional protocol evidence.
"""
from dataclasses import dataclass
import re
import secrets
from threading import RLock
import time
from typing import Protocol

from session_realms import SessionStorageUnavailable


@dataclass(frozen=True)
class RecoveryBinding:
    authority_id: str
    incarnation: str
    user_epoch: str
    admin_epoch: str

    def __post_init__(self):
        if any(type(v) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{16,64}',v)
               for v in (self.authority_id,self.incarnation,self.user_epoch,self.admin_epoch)):
            raise ValueError('Invalid independent recovery binding.')


@dataclass(frozen=True)
class RecoveryProof:
    request_id: str
    binding: RecoveryBinding
    revision: int
    issued_at: float
    state: str
    freshness: str


class RecoveryAuthority(Protocol):
    def proof(self, namespace: str, request_id: str) -> RecoveryProof:
        """Authenticated, bounded fresh read; never infer VERIFIED from a DB.

        Must fence restores/promotions before stale data is served, drain old
        workers/leases, and enforce never-reused epochs after uncertain recovery.
        A lying/restored provider cannot be repaired by client nonce checks.
        """
        ...


class RecoveryFence:
    def __init__(self, provider: RecoveryAuthority, binding: RecoveryBinding, *, minimum_revision=0,
                 response_budget=1.0):
        if provider is None or not callable(getattr(provider,'proof',None)) or not isinstance(binding,RecoveryBinding):
            raise SessionStorageUnavailable('Independent recovery authority is not configured.')
        if type(minimum_revision) is not int or minimum_revision<0:
            raise ValueError('Invalid recovery revision floor.')
        if type(response_budget) not in (int,float) or not 0<response_budget<=2:
            raise ValueError('Invalid recovery response budget.')
        self.provider,self.binding=provider,binding
        self.response_budget=response_budget
        self._floor=minimum_revision;self._lock=RLock()

    def check(self,namespace):
        started=time.monotonic()
        if not self._lock.acquire(timeout=self.response_budget):
            raise SessionStorageUnavailable('Independent recovery freshness is busy.')
        try:
            nonce=secrets.token_urlsafe(32)
            try:
                if time.monotonic()-started>=self.response_budget:
                    raise ValueError('Recovery response budget exhausted')
                proof=self.provider.proof(namespace,nonce)
                if (time.monotonic()-started>self.response_budget or not isinstance(proof,RecoveryProof)
                        or proof.request_id!=nonce or proof.binding!=self.binding
                        or type(proof.revision) is not int or proof.revision<self._floor
                        or type(proof.issued_at) not in (int,float) or not abs(time.time()-proof.issued_at)<=2
                        or proof.state!='OPEN' or proof.freshness!='VERIFIED'):
                    raise ValueError('Recovery freshness denied')
                self._floor=proof.revision
                return proof
            except Exception:
                raise SessionStorageUnavailable('Independent recovery freshness is unavailable or untrusted.') from None
        finally:
            self._lock.release()
