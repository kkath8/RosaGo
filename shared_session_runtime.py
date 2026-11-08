"""Explicit local composition for backend-neutral shared authentication.

No environment factory, production activation or infrastructure qualification.
Production startup remains unconditionally refused in session_realms. Each
worker must construct its own backend clients after fork.
"""
from dataclasses import dataclass, field
import os
from types import MappingProxyType

from session_realms import SessionStorageUnavailable


@dataclass(frozen=True, repr=False)
class LocalSessionRuntime:
    realms: dict
    model_factory: object
    challenges_factory: object
    provider_session_check: object
    logout_handler: object = None
    adapters_factory: object = None
    creator_pid: int = field(default_factory=os.getpid, init=False)

    def __post_init__(self):
        if self.logout_handler is not None and not callable(self.logout_handler):
            raise ValueError('Invalid durable logout dependency.')
        if self.adapters_factory is not None and not callable(self.adapters_factory):
            raise ValueError('Invalid provider adapter dependency.')
        if (set(self.realms) != {'user','admin'}
                or self.realms['user'] is self.realms['admin']
                or not all(callable(value) for value in
                           (self.model_factory,self.challenges_factory,self.provider_session_check))):
            raise ValueError('Invalid local shared authentication dependencies.')
        for name, backend in self.realms.items():
            if (getattr(backend,'realm',None) != name
                    or not all(callable(getattr(backend,method,None))
                               for method in ('readiness','snapshot','atomic','write','now'))):
                raise ValueError('Invalid local shared realm backend.')
        object.__setattr__(self,'realms',MappingProxyType(dict(self.realms)))

    def install(self, app, *, secure=False):
        if self.creator_pid != os.getpid():
            raise SessionStorageUnavailable('Shared backend clients must be constructed after worker fork.')
        if 'rosago_shared_sessions' in app.extensions or 'rosago_local_session_runtime' in app.extensions:
            raise RuntimeError('Shared authentication is already installed.')
        # Validate every dependency before publishing an interface or extension.
        for backend in self.realms.values():
            status=backend.readiness()
            if not isinstance(status,dict) or status.get('ready') is not True:
                raise SessionStorageUnavailable('Shared authentication readiness is closed.')
        from redis_session_flask import SharedSessionInterface
        realms=dict(self.realms)
        challenges=self.challenges_factory(realms)
        interface=SharedSessionInterface(realms,secure=secure,model_factory=self.model_factory)
        app.extensions['rosago_shared_sessions']=realms
        app.extensions['rosago_login_challenges']=challenges
        app.extensions['rosago_local_session_runtime']=self
        app.session_interface=interface


def session_model(app, realm, kind):
    runtime=app.extensions.get('rosago_local_session_runtime')
    if runtime is not None:
        return runtime.model_factory(runtime.realms[realm],kind)
    from redis_session_store import RedisModel
    return RedisModel(app.extensions['rosago_shared_sessions'][realm],kind)


def provider_checker(app):
    runtime=app.extensions.get('rosago_local_session_runtime')
    return runtime.provider_session_check if runtime is not None else None


def auth_adapters(app, url, public_key):
    from normal_auth_coordinator import SupabaseAdapters
    runtime=app.extensions.get('rosago_local_session_runtime')
    if runtime is not None and runtime.adapters_factory is not None:
        return runtime.adapters_factory(url,public_key)
    return SupabaseAdapters(url,public_key)
