"""Real Edge preview check. Fresh profile, loopback HTTP, deny-only outbound proxy."""
import base64
import argparse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import tempfile
import runpy
from threading import Thread
import time
from unittest.mock import Mock,patch

from werkzeug.serving import make_server,WSGIRequestHandler
from catalog_preview import create_app
from tools.check_login_browser import CDP
from tools.local_destination_catalog import write_new

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='preview-browser')
    parser.add_argument('--integrated',action='store_true')
    args=parser.parse_args()
    if not args.output.startswith('preview-browser') or Path(args.output).name!=args.output:raise RuntimeError('Use a new preview-browser folder name only.')
    output=ROOT/'local_catalog'/args.output;output.mkdir(exist_ok=False)
    sdk=None
    if args.integrated:
        sdk=Mock()
        with patch.dict(os.environ,{'ROSAGO_CATALOG_PREVIEW':'true','ROSAGO_AUTH_MODE':'development',
                'SUPABASE_URL':'https://fixture.invalid','SUPABASE_KEY':'sb_publishable_synthetic_browser',
                'FLASK_SECRET_KEY':'synthetic-preview-browser-only'},clear=True),patch('dotenv.load_dotenv'),patch('supabase.create_client',return_value=sdk):
            app=runpy.run_path(str(ROOT/'app.py'))['app']
        simulation_path='/preview/planner'
    else:
        app=create_app({'ROSAGO_CATALOG_PREVIEW':'true'})
        simulation_path='/user/planner'
    class Quiet(WSGIRequestHandler):
        def log_request(self,*args,**kwargs):pass
    class Deny(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def deny(self):
            try:self.send_error(403)
            except (ConnectionAbortedError,ConnectionResetError,BrokenPipeError):pass
        do_CONNECT=do_GET=do_POST=deny
    server=make_server('127.0.0.1',0,app,request_handler=Quiet,threaded=True)
    proxy=ThreadingHTTPServer(('127.0.0.1',0),Deny)
    threads=[Thread(target=s.serve_forever,daemon=True) for s in (server,proxy)]
    for thread in threads:thread.start()
    origin='http://127.0.0.1:'+str(server.server_port)
    checks={};process=None;cdp=None
    try:
        edge=Path(os.environ.get('ProgramFiles(x86)',r'C:\Program Files (x86)'))/'Microsoft/Edge/Application/msedge.exe'
        if not edge.is_file():raise RuntimeError('Installed Edge unavailable; no browser download allowed.')
        with tempfile.TemporaryDirectory(prefix='rosago-catalog-browser-') as temp:
            process=subprocess.Popen([str(edge),'--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check',
                '--disable-background-networking','--disable-component-update','--disable-sync','--disable-extensions',
                '--remote-debugging-address=127.0.0.1','--remote-debugging-port=0','--user-data-dir='+temp,
                '--proxy-server=http://127.0.0.1:'+str(proxy.server_port),'--proxy-bypass-list=127.0.0.1;localhost;[::1]',
                'about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                deadline=time.monotonic()+20;active=Path(temp)/'DevToolsActivePort'
                while not active.is_file() and time.monotonic()<deadline:time.sleep(.1)
                if not active.is_file():raise RuntimeError('Owned browser did not start.')
                port,path=active.read_text().splitlines()[:2];cdp=CDP('ws://127.0.0.1:'+port+path)
                target=cdp.call('Target.createTarget',{'url':'about:blank'},browser=True)['targetId']
                cdp.session=cdp.call('Target.attachToTarget',{'targetId':target,'flatten':True},browser=True)['sessionId']
                cdp.call('Page.enable');cdp.call('Runtime.enable')
                for width,height,label in [(1440,1000,'desktop'),(390,844,'mobile')]:
                    cdp.call('Emulation.setDeviceMetricsOverride',{'width':width,'height':height,'deviceScaleFactor':1,'mobile':width<500})
                    cdp.call('Page.navigate',{'url':origin+'/places'});cdp.ready('.place-card')
                    checks[label+'_98_cards']=cdp.evaluate("document.querySelectorAll('.place-card').length===98")
                    checks[label+'_no_overflow']=cdp.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    checks[label+'_navigation_visible']=cdp.evaluate("getComputedStyle(document.querySelector('.site-nav')).display!=='none'")
                    time.sleep(.4)
                    checks[label+'_visible_images_loaded']=cdp.evaluate("[...document.querySelectorAll('img[data-destination-image]')].filter(i=>i.getBoundingClientRect().top<innerHeight&&i.getBoundingClientRect().bottom>0).every(i=>i.complete&&i.naturalWidth>0)")
                    data=cdp.call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False})
                    (output/(label+'.png')).write_bytes(base64.b64decode(data['data']))
                cdp.evaluate("document.querySelector('[data-toggle-theme]').click()")
                checks['theme_toggle']=cdp.evaluate("document.documentElement.dataset.theme==='dark'")
                cdp.call('Page.navigate',{'url':origin+'/places/nuvali-sand-courts'});cdp.ready('.place-detail')
                checks['theme_persists']=cdp.evaluate("document.documentElement.dataset.theme==='dark'")
                checks['held_court_uses_placeholder']=cdp.evaluate("document.querySelector('.place-detail img').getAttribute('src').endsWith('/static/img/destination-placeholder.svg')")
                cdp.call('Page.navigate',{'url':origin+simulation_path+'?interest=dining&stops=3'});cdp.ready('.preview-simulation-form')
                checks['simulation_three_cards']=cdp.evaluate("document.querySelectorAll('.place-card').length===3 && document.querySelector('h1').textContent.includes('simulation')")
                checks['no_external_page_resources']=cdp.evaluate("performance.getEntriesByType('resource').every(r=>new URL(r.name).origin===location.origin)")
                if sdk is not None:checks['no_sdk_operations']=not sdk.mock_calls
            finally:
                if cdp:
                    try:cdp.call('Browser.close',browser=True)
                    except Exception:pass
                    cdp.ws.close()
                if process:
                    try:process.wait(timeout=10)
                    except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=5)
    finally:
        for service in (server,proxy):service.shutdown();service.server_close()
        for thread in threads:thread.join(timeout=2)
    result=dict(checks=checks,passed=all(checks.values()),live_signins=0,hosted_changes=0,
        scope='Owned loopback preview, outbound browser proxy denies non-loopback; '+('normal Flask app with synthetic SDK and no sign-ins.' if args.integrated else 'standalone preview app.'),
        browser_and_servers_stopped=True,remote_deployment='NO-GO')
    write_new(output/'results.json',result);print(json.dumps(result,indent=2))
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
