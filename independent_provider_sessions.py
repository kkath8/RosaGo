"""Explicitly injected evaluation candidate; never activates from environment.

Transport credentials are separately scoped. Admission is only from the trusted
password-login result, never from refresh, browser claims, or a database row.
"""
import math
import re
import secrets
import time
from normal_auth_coordinator import VerifiedLoginCredentials, ClientUnavailable, PasswordLoginError
from session_realms import SessionStorageUnavailable

ISSUER='https://jfaufpfzfhysqkhcdsrs.supabase.co/auth/v1'
UUID=re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z')
IDENTITY=re.compile(r'[A-Za-z0-9_-]{16,128}\Z')


class IndependentProviderSessions:
    def __init__(self, *, authority_id, incarnation, namespace, transports, clock=time.time):
        if (not all(type(v) is str and IDENTITY.fullmatch(v) for v in (authority_id,incarnation))
                or type(namespace) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',namespace)
                or set(transports)!={'enroll','check','revoke'}
                or not all(callable(getattr(t,'exchange',None)) for t in transports.values())):
            raise ValueError('Invalid independent provider dependencies.')
        self.binding=dict(authority_id=authority_id,incarnation=incarnation,namespace=namespace,issuer=ISSUER)
        self.transports=dict(transports); self.clock=clock

    def _exchange(self, operation, record, *, deadline=None):
        try:
            uid,sid=record.user_id,record.session_id
            if not all(type(v) is str and UUID.fullmatch(v) for v in (uid,sid)): raise ValueError()
            now=self.clock()
            request=dict(version=1,nonce=secrets.token_hex(24),now=now,uid=uid,sid=sid,**self.binding)
            if deadline is not None: request['deadline']=deadline
            response=self.transports[operation].exchange(request)
            if (type(response) is not dict or type(response.get('version')) is not int or response['version']!=1
                    or any(response.get(k)!=request[k] for k in (*self.binding,'nonce','uid','sid'))
                    or type(response.get('now')) not in (int,float) or not math.isfinite(response['now'])
                    or abs(self.clock()-response['now'])>5
                    or not all(type(response.get(k)) is bool for k in ('active','revoked','known','expired'))
                    or (response['active'] and (response['revoked'] or response['expired'] or not response['known']))): raise ValueError()
            return response
        except Exception:
            raise SessionStorageUnavailable('Independent provider authority is unavailable.') from None

    def enroll_verified_login(self, credentials):
        if (type(credentials) is not VerifiedLoginCredentials
                or not math.isfinite(credentials.access_expires_at)
                or credentials.access_expires_at<=self.clock()):
            raise ClientUnavailable()
        # Absolute eight-hour admission cap, never extended by refresh or a retry.
        result=self._exchange('enroll',credentials,deadline=self.clock()+28795)
        if not result['active']: raise ClientUnavailable()

    def current(self, record, issuer, realm):
        if issuer!=ISSUER or realm not in ('user','admin'): return None
        try: return self._exchange('check',record)['active']
        except SessionStorageUnavailable: return None

    def revoke(self, record, issuer, realm):
        if issuer!=ISSUER or realm not in ('user','admin'): return None
        try:
            result=self._exchange('revoke',record)
            return True if result['revoked'] and not result['active'] else None
        except SessionStorageUnavailable: return None


class IndependentProviderAdapters:
    """Wrap existing verified SDK and bounded logout transports, without retries."""
    def __init__(self, adapters, authority):
        if adapters.issuer!=ISSUER or not isinstance(authority,IndependentProviderSessions):
            raise ValueError('Evaluation provider target mismatch.')
        self.base,self.authority=adapters,authority

    def __getattr__(self,name): return getattr(self.base,name)

    def password_login(self,email,password):
        credentials=self.base.password_login(email,password)
        # Must run before Admin membership lookup, which also uses guarded RLS.
        try:
            self.authority.enroll_verified_login(credentials)
        except (SessionStorageUnavailable,ClientUnavailable):
            raise PasswordLoginError('service_failure') from None
        return credentials

    def provider_session_check(self,record,issuer,realm):
        state=self.authority.current(record,issuer,realm)
        if state is not True: return state
        return self.base.provider_session_check(record,issuer,realm)

    def provider_session_present(self,record,issuer,realm):
        # A denied independent session is NOT evidence of provider-row deletion.
        return self.base.provider_session_present(record,issuer,realm)

    def sign_out_current_session(self,record,issuer,realm):
        if self.authority.revoke(record,issuer,realm) is not True: return None
        return self.base.sign_out_current_session(record,issuer,realm)


def evaluation_runtime(*, realms, model_factory, challenges_factory, authority, url, public_key,
                       base_factory=None):
    """Reviewable, post-fork composition. No env loader or production activation."""
    from normal_auth_coordinator import SupabaseAdapters
    from durable_session_logout import DurableLogout
    from shared_session_runtime import LocalSessionRuntime
    if url!=ISSUER.removesuffix('/auth/v1'): raise ValueError('Evaluation target mismatch.')
    base_factory=base_factory or SupabaseAdapters
    def adapters_factory(selected_url, selected_key):
        if selected_url!=url or selected_key!=public_key:
            raise ValueError('Evaluation provider configuration mismatch.')
        return IndependentProviderAdapters(base_factory(selected_url,selected_key),authority)
    adapters=adapters_factory(url,public_key)
    logout=DurableLogout(realms,issuer=ISSUER,sign_out=adapters.sign_out_current_session,
                         session_check=adapters.provider_session_present)
    return LocalSessionRuntime(realms=realms,model_factory=model_factory,
        challenges_factory=challenges_factory,provider_session_check=adapters.provider_session_check,
        logout_handler=logout,adapters_factory=adapters_factory)
