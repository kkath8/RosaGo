"""Isolated real-browser form/CSRF check; NEVER loads .env or signs anyone in.

Uses an ephemeral loopback HTTP fixture around Flask's test client, a fresh Edge
profile, and a deny-only proxy for all non-loopback browser traffic. Only EMPTY
forms are submitted; provider methods are forbidden. No cookies/tokens are logged.
"""
from contextlib import ExitStack
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import argparse
import json
import os
from pathlib import Path
import runpy
import secrets
import subprocess
import sys
import tempfile
from threading import Lock,Thread
import time
from unittest.mock import Mock,patch
from urllib.parse import parse_qs,urlsplit

from websockets.sync.client import connect

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

class CDP:
    def __init__(self,url):self.ws=connect(url,max_size=4*1024*1024,open_timeout=5);self.number=0;self.session=None
    def call(self,method,params=None,*,browser=False):
        self.number+=1;number=self.number
        request={'id':number,'method':method,'params':params or {}}
        if self.session and not browser:request['sessionId']=self.session
        self.ws.send(json.dumps(request))
        while True:
            message=json.loads(self.ws.recv(timeout=10))
            if message.get('id')==number:
                if 'error' in message:raise RuntimeError('Offline browser command failed.')
                return message.get('result',{})
    def evaluate(self,expression):
        answer=self.call('Runtime.evaluate',{'expression':expression,'returnByValue':True})
        if 'exceptionDetails' in answer:raise RuntimeError('Offline page script failed.')
        return answer.get('result',{}).get('value')
    def ready(self,selector):
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            try:
                if self.evaluate("document.readyState==='complete' && Boolean(document.querySelector("+json.dumps(selector)+"))"):return
            except RuntimeError:pass
            time.sleep(.05)
        raise RuntimeError('Offline page did not initialize.')

def fixture():
    sdk=Mock()
    with patch.dict(os.environ,{'ROSAGO_AUTH_MODE':'development','SUPABASE_URL':'https://offline.invalid',
        'SUPABASE_KEY':'sb_publishable_synthetic_fixture','FLASK_SECRET_KEY':secrets.token_hex(32)},clear=True),\
        patch('dotenv.load_dotenv'),patch('supabase.create_client',return_value=sdk):
        app=runpy.run_path(str(ROOT/'app.py'))['app']
    app.testing=True
    denied=[]
    def forbidden(*args,**kwargs):denied.append(True);raise RuntimeError('Offline provider calls forbidden.')
    for name in ('rosago_normal_auth','rosago_admin_auth'):
        app.extensions[name].adapters.password_login=Mock(side_effect=forbidden)
        app.extensions[name].adapters._http_factory=forbidden
        app.extensions[name].coordinator._clients=forbidden
    return app,denied

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--expect',choices=('broken','fixed'),required=True)
    args=parser.parse_args();app,provider_calls=fixture();requests=[];lock=Lock()
    client=app.test_client(use_cookies=False)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def dispatch(self):
            path=urlsplit(self.path).path
            size=int(self.headers.get('Content-Length','0'))
            if size>32768:self.send_error(413);return
            body=self.rfile.read(size) if size else None
            headers={key:value for key,value in self.headers.items() if key.lower() not in ('host','connection','content-length')}
            with lock:
                # Assertions/data output retain booleans only, never form/cookie values.
                fields=parse_qs(body.decode()) if body else {}
                token_matches=False
                if path=='/login' and body:
                    cookie=SimpleCookie();cookie.load(self.headers.get('Cookie',''))
                    item=cookie.get(app.config['SESSION_COOKIE_NAME'])
                    if item:
                        try:
                            state=app.session_interface.get_signing_serializer(app).loads(item.value)
                            token_matches=fields.get('csrf_token')==[state.get('user_login_csrf')]
                        except Exception:pass
                try:response=client.open(self.path,method=self.command,base_url=origin,headers=headers,data=body)
                except Exception:
                    self.send_error(500);return
                requests.append({'method':self.command,'path':path,'status':response.status_code,
                    'same_origin':self.headers.get('Origin')==origin,'null_origin':self.headers.get('Origin')=='null',
                    'matching_csrf_cookie':token_matches,'policy':response.headers.get('Referrer-Policy')})
                self.send_response(response.status_code)
                for key,value in response.headers:
                    if key.lower() not in ('connection','transfer-encoding'):self.send_header(key,value)
                self.end_headers();self.wfile.write(response.data)
        do_GET=dispatch
        do_POST=dispatch
    class DenyProxy(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reject(self):self.send_response(403);self.end_headers()
        do_CONNECT=reject
        do_GET=reject
        do_POST=reject
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);origin='http://127.0.0.1:'+str(server.server_port)
    proxy=ThreadingHTTPServer(('127.0.0.1',0),DenyProxy)
    threads=[Thread(target=s.serve_forever,daemon=True) for s in (server,proxy)]
    for thread in threads:thread.start()
    result={'scope':'Real Edge, synthetic loopback Flask fixture, empty forms only; no live authentication.',
        'expectation':args.expect}
    try:
        edge=Path(os.environ.get('PROGRAMFILES(X86)','C:/Program Files (x86)'))/'Microsoft/Edge/Application/msedge.exe'
        if not edge.is_file():raise RuntimeError('Installed Edge browser not found.')
        with tempfile.TemporaryDirectory(prefix='rosago-login-browser-') as temp:
            process=subprocess.Popen([str(edge),'--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check',
                '--disable-background-networking','--disable-component-update','--disable-sync','--disable-extensions',
                '--remote-debugging-address=127.0.0.1','--remote-debugging-port=0','--user-data-dir='+temp,
                '--proxy-server=http://127.0.0.1:'+str(proxy.server_port),
                '--proxy-bypass-list=127.0.0.1;localhost;[::1]','about:blank'],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            cdp=None
            try:
                deadline=time.monotonic()+15;active=Path(temp)/'DevToolsActivePort'
                while not active.is_file() and time.monotonic()<deadline:time.sleep(.05)
                if not active.is_file():raise RuntimeError('Isolated browser did not start.')
                port,path=active.read_text().splitlines()[:2]
                cdp=CDP('ws://127.0.0.1:'+port+path)
                target=cdp.call('Target.createTarget',{'url':'about:blank'},browser=True)['targetId']
                cdp.session=cdp.call('Target.attachToTarget',{'targetId':target,'flatten':True},browser=True)['sessionId']
                cdp.call('Page.enable');cdp.call('Runtime.enable')
                cdp.call('Page.navigate',{'url':origin+'/login'});cdp.ready('#login-form')
                result['user_get_initialized']=cdp.evaluate("document.getElementById('login-status').textContent.trim()===''")
                before=sum(r['method']=='POST' for r in requests)
                cdp.evaluate("document.getElementById('login-submit').click()")
                result['login_js_validation_works']=cdp.evaluate("document.getElementById('login-status').textContent.includes('highlighted fields')")
                result['invalid_ui_submit_makes_no_post']=sum(r['method']=='POST' for r in requests)==before
                # Deliberately EMPTY native form navigation bypasses JS only to
                # test browser-generated Origin + cookie CSRF admission. Empty
                # credentials cannot reach the provider password-login branch.
                cdp.evaluate("document.getElementById('login-form').submit()")
                deadline=time.monotonic()+10
                while not any(r['method']=='POST' and r['path']=='/login' for r in requests) and time.monotonic()<deadline:time.sleep(.05)
                cdp.ready('#login-form')
                post=next(r for r in requests if r['method']=='POST' and r['path']=='/login')
                result['user_native_post']=post
                result['reported_error_reproduced']=cdp.evaluate("document.getElementById('login-status').textContent.includes('Please reload this page and try again.')")
                cdp.call('Page.navigate',{'url':origin+'/admin/login'});cdp.ready('.admin-login-form')
                cdp.evaluate("document.querySelector('.admin-login-form').submit()")
                deadline=time.monotonic()+10
                while not any(r['method']=='POST' and r['path']=='/admin/login' for r in requests) and time.monotonic()<deadline:time.sleep(.05)
                result['admin_native_post']=next(r for r in requests if r['method']=='POST' and r['path']=='/admin/login')
            finally:
                if cdp:
                    try:cdp.call('Browser.close',browser=True)
                    except Exception:pass
                    cdp.ws.close()
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=5)
        result['provider_calls']=len(provider_calls)
        expected_status=403 if args.expect=='broken' else 400
        checks=[result['user_get_initialized'],result['login_js_validation_works'],result['invalid_ui_submit_makes_no_post'],
            result['user_native_post']['matching_csrf_cookie'],result['user_native_post']['status']==expected_status,
            result['user_native_post']['null_origin']==(args.expect=='broken'),result['user_native_post']['same_origin']==(args.expect=='fixed'),
            result['reported_error_reproduced']==(args.expect=='broken'),result['admin_native_post']['status']==400,
            result['admin_native_post']['same_origin'],not provider_calls]
        result['passed']=all(checks)
    finally:
        for s in (server,proxy):s.shutdown();s.server_close()
        for t in threads:t.join(timeout=2)
    output=ROOT/'docs/local-login-diagnosis';output.mkdir(parents=True,exist_ok=True)
    (output/(args.expect+'-browser-results.json')).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2));return 0 if result['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
