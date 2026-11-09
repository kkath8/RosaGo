"""Real separate-process Flask/session qualification with synthetic providers.

No listening application ports, hosted projects or actual Auth credentials.
Each worker creates its own pool and app after process start. Pipe inputs/outputs
contain throwaway fixture state; only sanitized outcomes are saved or printed.
Recovery controllers remain TEST fixtures, not independent protected authority.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from dataclasses import asdict
import base64
import importlib.util
import io
import json
import os
from pathlib import Path
import runpy
import secrets
import socket
import subprocess
import sys
import time
from unittest.mock import Mock,patch
import traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT/'tools')]


def worker(config):
    import httpx
    from normal_auth_coordinator import VerifiedLoginCredentials
    from postgres_session_store import PgModel,PgChallenges
    from shared_session_runtime import LocalSessionRuntime
    from session_realms import init_session_realms,SessionStorageUnavailable
    from test_public_layout import Document
    from qualify_evaluation_readiness import stores
    pool,models=stores(config)
    try:
        realms={r:model.backend for r,model in models.items()}
        for backend in realms.values():
            backend.recovery.provider.available=config.get('recovery_available',True)
        provider_state=config.get('provider_state',{'user':True,'admin':True})
        runtime=LocalSessionRuntime(realms,PgModel,PgChallenges,
            lambda record,issuer,realm:provider_state[realm])
        origin='https://fixture.example.invalid'
        environment={key:os.environ[key] for key in ('PATH','SystemRoot','TEMP','TMP','PATHEXT') if key in os.environ}
        environment.update({'ROSAGO_AUTH_MODE':'redis-local','FLASK_SECRET_KEY':config['flask_secret'],
            'ROSAGO_PUBLIC_ORIGIN':origin,'SUPABASE_URL':'https://provider.example.invalid',
            'SUPABASE_KEY':'sb_publishable_synthetic_fixture','ROUTING_PROVIDER':'disabled',
            'ROSAGO_LOCAL_HTTPS_QUALIFICATION':'true','ROSAGO_TRUSTED_HOSTS':'["fixture.example.invalid"]',
            'ROSAGO_PROXY_HOPS':'0'})
        try:
            with patch.dict(os.environ,environment,clear=True),patch('dotenv.load_dotenv'),\
                 patch('supabase.create_client',return_value=Mock()),\
                 patch('session_realms.init_session_realms',side_effect=lambda app,mode:init_session_realms(app,mode=mode,local_runtime=runtime)),\
                 redirect_stdout(io.StringIO()):
                app=runpy.run_path(str(ROOT/'app.py'))['app']
        except SessionStorageUnavailable:
            if config.get('operation')=='startup_outage':
                return {'startup_refused':True}
            raise
        app.testing=True
        def response(request):
            if request.url.path.endswith('/rosago_is_admin'):
                return httpx.Response(200,json=request.headers.get('authorization')=='Bearer admin-access')
            if request.url.path.endswith('/profiles'):
                return httpx.Response(200,json=[])
            raise AssertionError('Unexpected synthetic provider request')
        for realm,name in (('user','rosago_normal_auth'),('admin','rosago_admin_auth')):
            dependencies=app.extensions[name]
            dependencies.adapters._http_factory=lambda **kw:httpx.Client(transport=httpx.MockTransport(response),**kw)
            dependencies.adapters.password_login=lambda email,password,r=realm:VerifiedLoginCredentials(
                '11111111-1111-4111-8111-111111111111' if r=='user' else '22222222-2222-4222-8222-222222222222',
                r+'@example.invalid',r+'-access',r+'-refresh',time.time()+3600,r+'-provider-session')
        browser=app.test_client()
        names={'user':('__Host-rosago_user_session','/'),
               'admin':('__Secure-rosago_admin_session','/admin')}
        for realm,value in config.get('cookies',{}).items():
            name,path=names[realm]
            browser.set_cookie(name,value,domain='fixture.example.invalid',path=path,secure=True)
        def request(method,path,**kwargs):
            return getattr(browser,method)(path,base_url=origin,**kwargs)
        operation=config.get('operation','status')
        if operation=='login':
            for realm in config.get('order',('user','admin')):
                path='/login' if realm=='user' else '/admin/login'
                page=request('get',path)
                assert page.status_code==200
                token=Document(page.text).find('input',name='csrf_token')[0].attrs['value']
                reply=request('post',path,data={'email':realm+'@example.invalid','password':'fixture-only',
                    'csrf_token':token},headers={'Origin':origin})
                assert reply.status_code==303
        if operation=='logout_user':
            token=request('get','/auth/logout-token').json['csrf_token']
            reply=request('post','/logout',data={'csrf_token':token},headers={'Origin':origin})
            assert reply.status_code in (302,303)
        if operation=='logout_admin':
            page=request('get','/admin/account')
            token=Document(page.text).find('input',name='csrf_token')[0].attrs['value']
            reply=request('post','/admin/logout',data={'csrf_token':token},headers={'Origin':origin})
            assert reply.status_code in (302,303)
        user=request('get','/auth/status')
        admin=request('get','/admin/account')
        cookies={}
        for realm,(name,path) in names.items():
            cookie=browser.get_cookie(name,domain='fixture.example.invalid',path=path)
            if cookie:cookies[realm]=cookie.value
        return {'user_authenticated':bool(user.json and user.json.get('authenticated')),
                'user_status':user.status_code,'admin_status':admin.status_code,
                'cookies':cookies,'user_set_cookie':bool(user.headers.getlist('Set-Cookie'))}
    finally:
        pool.close()


def probe(config,operation='status',**changes):
    environment={key:os.environ[key] for key in ('PATH','SystemRoot','TEMP','TMP','PATHEXT') if key in os.environ}
    run=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker'],
        input=json.dumps(dict(config,operation=operation,**changes)),capture_output=True,text=True,
        cwd=ROOT,env=environment,timeout=60)
    if run.returncode:
        try:
            failure=json.loads(run.stdout)
            if set(failure)=={'error_class','locations'}:
                print(json.dumps({'sanitized_worker_failure':failure}))
        except (ValueError,TypeError):
            pass
        raise RuntimeError('Synthetic worker qualification failed')
    return json.loads(run.stdout)


def main():
    from postgres_session_recovery import RecoveryBinding
    result={'hosted_requests':0,'live_sign_ins':0,'application_listener_started':False,
        'scope':'Real Flask app/routes, separate Python processes, disposable PostgreSQL, synthetic providers and per-process test recovery controller.',
        'production_qualified':False,'protected_recovery_authority_qualified':False}
    stage='fixture'
    try:
        spec=importlib.util.spec_from_file_location('runtime_worker_lab',ROOT/'docs/admin-finalization/phase2m-postgresql-session-implementation/local_lab.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        module.NAME='rosago-runtime-workers-'+secrets.token_hex(6);module.IMAGE='postgres:17'
        with socket.socket() as reserve:
            reserve.bind(('127.0.0.1',0));module.PORT=reserve.getsockname()[1]
        original=module.docker
        def cached(*args,**kwargs):
            if args and args[0]=='run':args=(args[0],'--pull=never',*args[1:])
            return original(*args,**kwargs)
        module.docker=cached
        checks=[]
        with module.Lab() as lab:
            binding=RecoveryBinding(*(secrets.token_hex(16) for _ in range(4)))
            config={'dsn':lab.app_dsn,'namespace':'workers_'+secrets.token_hex(8),
                'key':base64.b64encode(secrets.token_bytes(32)).decode(),'binding':asdict(binding),
                'flask_secret':secrets.token_hex(32)}
            lab.operator.execute('INSERT INTO rosago_session_m.gate VALUES(%s,1,%s,%s,%s,%s,%s)',
                (config['namespace'],binding.authority_id,binding.incarnation,binding.user_epoch,binding.admin_epoch,'OPEN'))
            def both(answer):
                if not (answer['user_authenticated'] and answer['user_status']==200 and answer['admin_status']==200):
                    result['unexpected_status']={k:answer[k] for k in ('user_authenticated','user_status','admin_status')}
                    raise AssertionError('Expected both synthetic realms active')
            stage='login_and_worker_handoff'
            answer=probe(config,'login');both(answer);config['cookies']=answer['cookies']
            original_cookies=dict(config['cookies'])
            with ThreadPoolExecutor(max_workers=2) as workers:
                concurrent=list(workers.map(lambda _:probe(config),range(2)))
            result['concurrent_statuses']=[{k:answer[k] for k in ('user_status','admin_status')} for answer in concurrent]
            for answer in concurrent:
                assert answer['user_status'] in (200,503) and answer['admin_status'] in (200,503)
                if answer['user_status']==200:assert answer['user_authenticated']
                else:assert not answer['user_set_cookie']
            both(probe(config))
            checks.append('two_concurrent_processes_share_User_Admin_sessions')
            swapped=probe(config,cookies={'user':original_cookies['admin'],'admin':original_cookies['user']})
            assert not swapped['user_authenticated'] and swapped['admin_status']==302
            checks.append('cross_realm_cookie_substitution_denied')
            stage='restart'
            value=json.loads(module.docker('inspect',module.NAME))[0]
            assert value['Id']==lab.identity and value['Config']['Labels']['rosago.phase']=='2m'
            assert value['HostConfig']['PortBindings']['5432/tcp']==[{'HostIp':'127.0.0.1','HostPort':str(module.PORT)}]
            module.docker('restart',module.NAME)
            both(probe(config))
            checks.append('fresh_application_process_after_clean_database_restart')
            stage='outages'
            assert probe(config,'startup_outage',recovery_available=False)=={'startup_refused':True}
            both(probe(config))
            checks.append('unavailable_test_recovery_authority_refuses_startup_without_state_loss')
            outage=probe(config,provider_state={'user':None,'admin':True})
            assert outage['user_status']==503 and not outage['user_set_cookie'] and outage['admin_status']==200
            both(probe(config))
            checks.append('provider_unknown_fails_closed_and_preserves_other_realm')
            stage='logout_and_replay'
            answer=probe(config,'logout_user')
            assert not answer['user_authenticated'] and answer['admin_status']==200
            replay=probe(config,cookies=original_cookies)
            assert not replay['user_authenticated'] and replay['admin_status']==200
            config['cookies']=answer['cookies']
            answer=probe(config,'logout_admin')
            assert not answer['user_authenticated'] and answer['admin_status']==302
            replay=probe(config,cookies=original_cookies)
            assert not replay['user_authenticated'] and replay['admin_status']==302
            checks.append('selected_realm_logout_and_old_cookie_replay_denied_across_processes')
            stage='provider_revocation'
            config.pop('cookies',None)
            answer=probe(config,'login',order=('admin','user'));both(answer)
            config['cookies']=answer['cookies']
            denied=probe(config,provider_state={'user':False,'admin':True})
            assert not denied['user_authenticated'] and denied['user_status']==200 and denied['admin_status']==200
            replay=probe(config)
            assert not replay['user_authenticated'] and replay['admin_status']==200
            checks.append('confirmed_provider_denial_terminally_revokes_local_reference')
            stage='post_revocation_database_restart'
            value=json.loads(module.docker('inspect',module.NAME))[0]
            assert value['Id']==lab.identity and value['Config']['Labels']['rosago.phase']=='2m'
            assert value['HostConfig']['PortBindings']['5432/tcp']==[{'HostIp':'127.0.0.1','HostPort':str(module.PORT)}]
            module.docker('restart',module.NAME)
            replay=probe(config)
            assert not replay['user_authenticated'] and replay['admin_status']==200
            checks.append('terminal_provider_revocation_survives_clean_database_restart')
            result['checks']=checks
        result.update(status='passed',checks_passed=len(checks),owned_fixture_removed=True)
    except Exception as error:
        result.update(status='failed',stage=stage,error_class=type(error).__name__)
    output=ROOT/'docs/production-readiness/remote-evaluation/runtime-worker-qualification.json'
    output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))
    return 0 if result['status']=='passed' else 1


if __name__=='__main__':
    if '--worker' in sys.argv:
        try:
            answer=worker(json.load(sys.stdin));print(json.dumps(answer))
        except Exception as error:
            print(json.dumps({'error_class':type(error).__name__,
                'locations':[{'file':Path(frame.filename).name,'line':frame.lineno,'function':frame.name}
                    for frame in traceback.extract_tb(error.__traceback__)[-5:]]}))
            raise SystemExit(1) from None
    else:
        raise SystemExit(main())
