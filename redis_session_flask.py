"""Opaque browser realms over independent per-record authority/cache stores."""
from copy import deepcopy
from dataclasses import asdict
import re
import secrets
from urllib.parse import urlsplit

from flask import current_app, request, session
from flask.sessions import SessionInterface, SecureCookieSession
from session_realms import AdminBrowserSession, SessionStorageUnavailable, is_admin_path
from session_authority import RevisionConflict
from redis_session_store import RedisModel
from normal_auth_store import NormalAuthSession


class UserBrowserSession(SecureCookieSession):
    realm='user'
    def __init__(self,values=None,*,handle=None,version=0,invalid=False):
        super().__init__(values)
        self.handle,self.version,self.invalid=handle,version,invalid
        self.issue_cookie=self.delete_cookie=False


class SharedSessionInterface(SessionInterface):
    def __init__(self,realms,*,secure=False,model_factory=RedisModel):
        self.realms,self.secure=realms,secure
        self.model_factory=model_factory
        self.store=model_factory(realms['admin'],'web')

    def cookie(self,realm):
        if realm=='admin':
            return ('__Secure-rosago_admin_session' if self.secure else 'rosago_admin_session_dev','/admin')
        return ('__Host-rosago_user_session' if self.secure else 'rosago_user_session_dev','/')

    def open_session(self,app,req):
        realm='admin' if is_admin_path(req.path) else 'user'
        cls=AdminBrowserSession if realm=='admin' else UserBrowserSession
        if req.path.startswith('/static/'):
            value=cls()
            value.authority_free=True
            return value
        candidates=req.cookies.getlist(self.cookie(realm)[0])
        if len(candidates)>1 or (candidates and not re.fullmatch(r'[A-Za-z0-9_-]{43}',candidates[0])):
            return cls(invalid=True)
        handle=candidates[0] if candidates else None
        try:
            record=self.model_factory(self.realms[realm],'web').read(handle)
        except SessionStorageUnavailable:
            value=cls(invalid=True)
            value.storage_failed=True
            return value
        value=cls(record[0],handle=handle,version=record[1]) if record else cls()
        value.initial=deepcopy(dict(value))
        return value

    def save_session(self,app,state,response):
        if getattr(state,'authority_free',False):
            return
        response.vary.add('Cookie')
        if state.invalid:
            return
        name,path=self.cookie(state.realm)
        if state.delete_cookie:
            response.delete_cookie(name,path=path,secure=self.secure,httponly=True,samesite='Lax')
            return
        if not state.modified:
            return
        backend=self.realms[state.realm]
        try:
            if state.handle is None:
                if not state:
                    return
                if state.get('auth_session_id'):
                    raise RevisionConflict('Generic session save cannot install authority.')
                challenges=current_app.extensions['rosago_login_challenges']
                if not challenges.allow_attempt(state.realm,request.remote_addr,purpose='browser'):
                    raise SessionStorageUnavailable('Browser session allocation limit exceeded.')
                state.handle=self.model_factory(backend,'web').create(dict(state))
                state.version=0
                state.issue_cookie=True
            else:
                snap=backend.snapshot('web',state.handle)
                if snap.data is None:
                    raise RevisionConflict('Session was superseded.')
                old=snap.data['values']
                initial=getattr(state,'initial',{})
                missing=object()
                changes={k for k in set(initial)|set(state) if initial.get(k,missing)!=state.get(k,missing)}
                if 'auth_session_id' in changes:
                    if state.get('auth_session_id') or self.model_factory(backend,'auth').resolve(initial.get('auth_session_id')):
                        raise RevisionConflict('Generic session save cannot replace authority.')
                conflicts={k for k in changes if old.get(k,missing)!=initial.get(k,missing)}
                if conflicts:
                    if changes<={'_flashes'}:
                        response.headers['X-RosaGo-Session-Notice']='notification-conflict'
                        return
                    raise RevisionConflict('Session state changed.')
                merged=deepcopy(old)
                for key in changes:
                    if key in state:
                        merged[key]=state[key]
                    else:
                        merged.pop(key,None)
                if changes:
                    state.version=snap.data['version']+1
                    backend.write(snap,{'values':merged,'version':state.version},snap.meta['expires'])
        except SessionStorageUnavailable as error:
            response.status_code=409 if isinstance(error,RevisionConflict) else 503
            response.headers.pop('Location',None)
            response.headers['Cache-Control']='private, no-store'
            response.set_data('Session state is unavailable or changed. Verify any submitted action before retrying.')
            return
        if state.issue_cookie:
            response.set_cookie(name,state.handle,path=path,secure=self.secure,httponly=True,samesite='Lax')


def shared_interface():
    interface=current_app.session_interface
    return interface if isinstance(interface,SharedSessionInterface) else None


def begin_login(realm,token):
    interface=shared_interface()
    if not interface:
        return current_app.extensions['rosago_login_challenges'].valid(realm,token,consume=True)
    if session.realm!=realm or not session.handle:
        return False
    backend=interface.realms[realm]
    parent=backend.snapshot('web',session.handle)
    challenge=backend.snapshot('login',token)
    if (not parent.data or parent.data['version']!=session.version or not challenge.data
            or challenge.data['purpose']!=realm or parent.data['values'].get(realm+'_login_csrf')!=token):
        return False
    operation=secrets.token_urlsafe(32)
    values={**parent.data['values'],'_login_operation':operation,'_login_deadline':parent.now+30}
    try:
        backend.atomic({parent.key:parent,challenge.key:challenge},{
            parent.key:({'values':values,'version':session.version+1},parent.meta['expires'],{}),
            challenge.key:(None,parent.now,{})})
    except RevisionConflict:
        return False
    session.update(values)
    session.version+=1
    session.initial=deepcopy(dict(session))
    session.modified=False
    session.login_operation=operation
    return True


def finish_login(credentials):
    interface=shared_interface()
    backend=interface.realms[session.realm]
    operation=getattr(session,'login_operation',None)
    if not session.handle or not operation:
        raise SessionStorageUnavailable('Login state expired. Reload and sign in again.')
    parent=backend.snapshot('web',session.handle)
    if (not parent.data or parent.data['version']!=session.version
            or parent.data['values'].get('_login_operation')!=operation
            or parent.data['values'].get('_login_deadline',0)<=parent.now
            or credentials.access_expires_at<=parent.now):
        raise SessionStorageUnavailable('Login was superseded. Sign in again.')
    old_auth=parent.data['values'].get('auth_session_id')
    reads={parent.key:parent}
    updates={parent.key:(None,parent.now,{})}
    if old_auth:
        old=backend.snapshot('auth',old_auth,revocation_only=True)
        reads[old.key]=old
        updates[old.key]=(None,parent.now,{})
    auth_handle,web_handle=secrets.token_urlsafe(32),secrets.token_urlsafe(32)
    auth,web=backend.snapshot('auth',auth_handle),backend.snapshot('web',web_handle)
    reads.update({auth.key:auth,web.key:web})
    now=backend.now()
    record=NormalAuthSession(**asdict(credentials),created_at=now,last_activity_at=now,
        generation=0,revoked=False,csrf=secrets.token_urlsafe(32))
    values={k:v for k,v in parent.data['values'].items() if k not in (
        'auth_session_id','user_id','user_email','_login_operation','_login_deadline',
        'user_login_csrf','user_logout_csrf','admin_login_csrf','admin_login_csrf_at')}
    values['auth_session_id']=auth_handle
    updates[auth.key]=({'record':record,'lease':None},now+1800,
                       {'absolute':now+28800,'activity':now,'generation':0,'busy':False})
    updates[web.key]=({'values':values,'version':0},now+28800,{})
    backend.atomic(reads,updates)
    session.clear()
    session.update(values)
    session.handle,session.version=web_handle,0
    session.initial=deepcopy(dict(session))
    session.issue_cookie=True
    return auth_handle


def shared_logout():
    runtime=current_app.extensions.get('rosago_local_session_runtime')
    handler=getattr(runtime,'logout_handler',None)
    if handler is not None:
        confirmed=handler(session.realm,session.handle)
        session.clear()
        session.delete_cookie=True
        return confirmed is True
    backend=shared_interface().realms[session.realm]
    if session.handle:
        for _ in range(3):
            try:
                # Rebuild the entire selected-realm transition after a conflict.
                # No stale snapshots, provider calls, or uncertain commits replay.
                parent=backend.snapshot('web',session.handle)
                reads={parent.key:parent}
                updates={parent.key:(None,parent.now,{})}
                if parent.data and parent.data['values'].get('auth_session_id'):
                    auth=backend.snapshot('auth',parent.data['values']['auth_session_id'],revocation_only=True)
                    reads[auth.key]=auth
                    updates[auth.key]=(None,parent.now,{})
                backend.atomic(reads,updates)
                break
            except RevisionConflict:
                continue
        else:
            raise RevisionConflict('Logout revocation could not be confirmed.')
    session.clear()
    session.delete_cookie=True


def validate_https_configuration(app,origin,proxy_hops=0):
    parsed=urlsplit(origin)
    if parsed.port is not None and not 1<=parsed.port<=65535:
        raise ValueError('Invalid HTTPS port.')
    if (parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in ('','/') or parsed.query or parsed.fragment
            or app.config.get('APPLICATION_ROOT','/')!='/' or app.config.get('SESSION_COOKIE_DOMAIN')
            or parsed.hostname not in (app.config.get('TRUSTED_HOSTS') or ())
            or type(proxy_hops) is not int or not 0<=proxy_hops<=3):
        raise ValueError('Unreviewed HTTPS/root/proxy configuration.')
    return parsed.hostname
