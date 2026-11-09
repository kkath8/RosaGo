"""Offline Admin UI checks in Edge. Synthetic rendered snapshots; GET only.

No .env, live authentication, provider network, or hosted writes. The browser
gets no session cookies; its server only serves pre-rendered fixture pages and
static assets. External browser traffic goes through a deny-only proxy.
"""
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Thread, Lock
import time
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import urlsplit

import httpx

from check_login_browser import CDP, ROOT, fixture

sys.path.insert(0, str(ROOT / 'tests'))
from test_registration import seed_admin_session
from test_admin_frontend import detail
from test_admin_management import overview
from test_admin_audit import audit_row, ACTOR_ONE
from admin_management_service import BASIC_FIELDS, TOURISM_FIELDS, PHOTO_FIELDS, ENVIRONMENT_FIELDS


def snapshots():
    app, forbidden_calls = fixture()
    app.extensions['rosago_weather'] = Mock(get_weather=Mock(return_value=None))
    def respond(request):
        if request.url.path.endswith('/rosago_is_admin'):
            return httpx.Response(200, json=True)
        if request.url.path.endswith('/rosago_admin_operational_overview'):
            data = overview()
            data['users'][0].update(identifier=ACTOR_ONE, name='Synthetic Administrator', email='admin@example.invalid')
            return httpx.Response(200, json=data)
        if request.url.path.endswith('/admin_destination_audit'):
            return httpx.Response(200, json=[audit_row(1, summary=dict(
                submitted_fields=list(BASIC_FIELDS+TOURISM_FIELDS+PHOTO_FIELDS+ENVIRONMENT_FIELDS), resulting_status='draft')),
                audit_row(2, action='publish', summary=dict(submitted_fields=[], resulting_status='published')),
                audit_row(3, action='archive', summary=dict(submitted_fields=[], resulting_status='archived'))])
        if request.url.path.endswith('/places'):
            record = detail()
            selected = {key: record.get(key) for key in request.url.params.get('select', '').split(',')}
            return httpx.Response(200, json=[] if request.method == 'HEAD' else [selected],
                                  headers={'Content-Range': '0-0/1'})
        if request.url.path.endswith('/profiles'):
            return httpx.Response(200, json=[dict(id='user-123', first_name='Synthetic',
                last_name='Admin', created_at='2026-11-01T00:00:00Z')])
        return httpx.Response(503, json={'message': 'Offline fixture unavailable'})
    deps = app.extensions['rosago_admin_auth']
    deps.adapters._http_factory = lambda **kw: httpx.Client(transport=httpx.MockTransport(respond), **kw)
    deps.coordinator._clients = deps.adapters.database_client
    client = app.test_client()
    pages = {'/admin/login': client.get('/admin/login').data}
    seed_admin_session(SimpleNamespace(app=app, client=client), email='admin@example.invalid')
    slug = '/admin/places/rosago-test-v1-fixture'
    for path in ('/admin', '/admin/places', '/admin/places/new', slug, slug+'/edit',
                 slug+'/publication/archive', '/admin/users', '/admin/trips', '/admin/insights',
                 '/admin/system', '/admin/audit-logs', '/admin/account', '/admin/settings',
                 '/admin/help', '/admin/about'):
        response = client.get(path)
        if response.status_code != 200:
            raise AssertionError('Fixture failed to render '+path+': '+str(response.status_code))
        pages[path] = response.data
    return app, pages, forbidden_calls, client


def main():
    app, pages, forbidden_calls, fixture_client = snapshots()
    fixture_lock = Lock()
    posts = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            posts.append(True)
            self.send_error(405)
        def do_GET(self):
            path = urlsplit(self.path).path
            if path == '/admin/places' and urlsplit(self.path).query:
                with fixture_lock:
                    response = fixture_client.get(self.path)
                body, mime = response.data, response.content_type
            elif path in pages:
                body, mime = pages[path], 'text/html; charset=utf-8'
            elif path.startswith('/static/'):
                response = app.test_client().get(path)
                body, mime = response.data, response.content_type
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.end_headers()
            self.wfile.write(body)
    class DenyProxy(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def reject(self): self.send_response(403); self.end_headers()
        do_CONNECT = do_GET = do_POST = reject
    servers = [ThreadingHTTPServer(('127.0.0.1', 0), handler) for handler in (Handler, DenyProxy)]
    for server in servers: Thread(target=server.serve_forever, daemon=True).start()
    origin = 'http://127.0.0.1:'+str(servers[0].server_port)
    output = ROOT / 'docs/admin-settings'
    output.mkdir(parents=True, exist_ok=True)
    results = {'scope': 'Offline synthetic GET-only snapshots, real Edge; no live sign-in.', 'layouts': []}
    def check(name, value):
        results[name] = value
        if not value: raise AssertionError(name)
    try:
        with tempfile.TemporaryDirectory(prefix='rosago-admin-ui-') as temp:
            edge = Path(os.environ.get('PROGRAMFILES(X86)', 'C:/Program Files (x86)'))/'Microsoft/Edge/Application/msedge.exe'
            process = subprocess.Popen([str(edge), '--headless=new', '--disable-gpu', '--no-first-run',
                '--no-default-browser-check', '--disable-background-networking', '--disable-component-update',
                '--disable-sync', '--disable-extensions', '--remote-debugging-address=127.0.0.1',
                '--remote-debugging-port=0', '--user-data-dir='+temp,
                '--proxy-server=http://127.0.0.1:'+str(servers[1].server_port),
                '--proxy-bypass-list=127.0.0.1;localhost;[::1]', 'about:blank'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            cdp = None
            try:
                active = Path(temp)/'DevToolsActivePort'
                deadline = time.monotonic()+15
                while not active.is_file() and time.monotonic()<deadline: time.sleep(.05)
                port, path = active.read_text().splitlines()[:2]
                cdp = CDP('ws://127.0.0.1:'+port+path)
                target = cdp.call('Target.createTarget', {'url': 'about:blank'}, browser=True)['targetId']
                cdp.session = cdp.call('Target.attachToTarget', {'targetId': target, 'flatten': True}, browser=True)['sessionId']
                cdp.call('Page.enable'); cdp.call('Runtime.enable')
                cdp.call('Page.addScriptToEvaluateOnNewDocument', {'source': "window.__uiErrors=[];addEventListener('error',e=>{if(e.target===window)__uiErrors.push(true)});addEventListener('unhandledrejection',()=>__uiErrors.push(true))"})
                def visit(path):
                    cdp.evaluate("document.documentElement.setAttribute('data-ui-check-leaving','')")
                    cdp.call('Page.navigate', {'url': origin+path})
                    cdp.ready('html:not([data-ui-check-leaving]) #main-content')
                def key(name, code, virtual):
                    for kind in ('keyDown', 'keyUp'):
                        params = {'type': kind, 'key': name, 'code': code, 'windowsVirtualKeyCode': virtual}
                        if kind == 'keyDown': params['text'] = '\r' if name == 'Enter' else ' ' if name == ' ' else ''
                        cdp.call('Input.dispatchKeyEvent', params)
                visit('/admin')
                cdp.evaluate("document.querySelector('[data-toggle-theme]').focus()")
                key(' ', 'Space', 32)
                check('space_toggles_dark', cdp.evaluate("document.documentElement.dataset.theme==='dark' && document.querySelector('[data-toggle-theme]').getAttribute('aria-pressed')==='true'"))
                visit('/admin/settings')
                check('navigation_persists', cdp.evaluate("document.documentElement.dataset.theme==='dark' && document.querySelector('[data-set-theme=dark]').getAttribute('aria-pressed')==='true'"))
                cdp.evaluate("document.documentElement.setAttribute('data-ui-check-leaving','')")
                cdp.call('Page.reload'); cdp.ready('html:not([data-ui-check-leaving]) [data-toggle-theme]')
                check('reload_persists', cdp.evaluate("document.documentElement.dataset.theme==='dark'"))
                cdp.evaluate("document.querySelector('[data-set-theme=light]').click();document.querySelector('[data-toggle-theme]').focus()")
                key('Enter', 'Enter', 13)
                check('enter_toggles_and_settings_sync', cdp.evaluate("document.documentElement.dataset.theme==='dark' && document.querySelector('[data-set-theme=dark]').getAttribute('aria-pressed')==='true'"))
                cdp.evaluate("document.querySelector('.admin-account summary').focus()")
                key('Enter', 'Enter', 13)
                check('profile_dropdown_opens', cdp.evaluate("document.querySelector('.admin-account').open"))
                key('Escape', 'Escape', 27)
                check('escape_closes_and_restores_focus', cdp.evaluate("!document.querySelector('.admin-account').open && document.activeElement.matches('.admin-account summary')"))
                for width in (360, 768, 1440):
                    cdp.call('Emulation.setDeviceMetricsOverride', {'width': width, 'height': 1000, 'deviceScaleFactor': 1, 'mobile': False})
                    for theme in ('light', 'dark'):
                        cdp.evaluate("localStorage.setItem('rosago.theme.v1',"+json.dumps(theme)+")")
                        for route in pages:
                            visit(route)
                            item = cdp.evaluate("({theme:document.documentElement.dataset.theme,overflow:document.documentElement.scrollWidth>innerWidth+1,jsErrors:window.__uiErrors.length})")
                            item.update(width=width, route=route)
                            results['layouts'].append(item)
                            if item['overflow'] or item['theme']!=theme or item['jsErrors']: raise AssertionError(str(item))
                            tables = cdp.evaluate("""[...document.querySelectorAll('table')].every(table=>
                                table.classList.contains('admin-table') && table.closest('.admin-table-scroll')?.tabIndex===0 &&
                                [...table.querySelectorAll('thead th')].every(th=>th.scope==='col') &&
                                parseFloat(getComputedStyle(table).fontSize)>=14)""")
                            if not tables: raise AssertionError('Table semantics/containment: '+route)
                            if route == '/admin/audit-logs':
                                check(str(width)+'_'+theme+'_audit_summary_and_closed_details', cdp.evaluate("document.querySelector('.admin-audit-summary').textContent.trim()==='13 fields submitted' && [...document.querySelectorAll('.admin-audit-details')].every(d=>!d.open)"))
                                cdp.evaluate("document.querySelector('.admin-audit-details summary').focus()")
                                key('Enter', 'Enter', 13)
                                time.sleep(.05)  # Native toggle notification also aligns the scroll region.
                                check(str(width)+'_'+theme+'_audit_full_details_accessible', cdp.evaluate("""(() => {
                                    const d=document.querySelector('.admin-audit-details');
                                    const body=d.querySelector('.admin-audit-detail-body');
                                    return d.open && body.querySelectorAll('li').length===13 &&
                                        body.textContent.includes('11111111-1111-4111-8111-000000000001') &&
                                        body.textContent.includes('22222222-2222-4222-8222-222222222222') &&
                                        body.textContent.includes('33333333-3333-4333-8333-333333333333') &&
                                        body.textContent.includes('2026-11-03T12:05:06+08:00') &&
                                        body.getBoundingClientRect().width<=innerWidth-24 &&
                                        body.getBoundingClientRect().right<=d.closest('.admin-table-scroll').getBoundingClientRect().right &&
                                        body.getBoundingClientRect().left>=d.closest('.admin-table-scroll').getBoundingClientRect().left &&
                                        document.documentElement.scrollWidth<=innerWidth+1;
                                })()"""))
                                if width in (360,1440):
                                    screenshot = cdp.call('Page.captureScreenshot', {'format':'png'})['data']
                                    (output/('audit-'+str(width)+'-'+theme+'-expanded.png')).write_bytes(base64.b64decode(screenshot))
                                key('Enter', 'Enter', 13)
                                check(str(width)+'_'+theme+'_audit_details_close', cdp.evaluate("!document.querySelector('.admin-audit-details').open"))
                                cdp.evaluate("scrollTo(0,0);document.querySelector('.admin-table-scroll').scrollLeft=0")
                                if width==1440:
                                    screenshot = cdp.call('Page.captureScreenshot', {'format':'png'})['data']
                                    (output/('audit-'+theme+'.png')).write_bytes(base64.b64decode(screenshot))
                            if route == '/admin/settings' and width in (360,1440):
                                time.sleep(.2)  # Let initial enabled/selected control transitions settle.
                                screenshot=cdp.call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':True})['data']
                                (output/('settings-'+str(width)+'-'+theme+'.png')).write_bytes(base64.b64decode(screenshot))
                            if route == '/admin':
                                expected_columns = 1 if width <= 600 else 2 if width <= 1024 else 3
                                quick = cdp.evaluate("""(() => {
                                    const dashboard=document.querySelector('.admin-dashboard');
                                    const panel=dashboard.querySelector('.admin-actions-panel');
                                    return {single:dashboard.querySelectorAll('.admin-actions-panel').length===1,
                                        afterHeading:dashboard.children[1]===panel,
                                        beforeStats:panel.nextElementSibling.matches('.admin-kpi-grid'),
                                        columns:getComputedStyle(panel.querySelector('.admin-action-grid')).gridTemplateColumns.split(' ').length,
                                        links:[...panel.querySelectorAll('.admin-action-card')].map(a=>a.getAttribute('href'))};
                                })()""")
                                check(str(width)+'_'+theme+'_quick_management_order_and_grid',
                                    quick['single'] and quick['afterHeading'] and quick['beforeStats']
                                    and quick['columns']==expected_columns and quick['links']==[
                                        '/admin/places/new', '/admin/places', '/admin/users',
                                        '/admin/insights', '/admin/system', '/admin/places?status=draft'])
                        visit('/admin')
                        if width == 1440:
                            # Real computed colors, not token/string assertions.
                            contrast = cdp.evaluate("""(() => {
                                const canvas=document.createElement('canvas');canvas.width=canvas.height=1;
                                const context=canvas.getContext('2d',{willReadFrequently:true});
                                const luminance=color=>{
                                    context.clearRect(0,0,1,1);context.fillStyle=color;context.fillRect(0,0,1,1);
                                    const rgb=[...context.getImageData(0,0,1,1).data].slice(0,3).map(v=>{
                                        v=Number(v)/255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;
                                    });return rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722;
                                };
                                return [...document.querySelectorAll('.admin-ui-button,.admin-appearance,.admin-kpi h2,.admin-inline-stat h2,.admin-review-value')].map(el=>{
                                    const card=el.matches('h2,.admin-review-value')?el.closest('.admin-kpi,.admin-inline-stat,.admin-review-panel'):el;
                                    const s=getComputedStyle(el),a=luminance(s.color),b=luminance(getComputedStyle(card).backgroundColor);
                                    return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);
                                });
                            })()""")
                            check(theme+'_button_and_stat_label_contrast_aa', bool(contrast) and min(contrast)>=4.5)
                            check(theme+'_appearance_icon_only', cdp.evaluate("document.querySelector('[data-toggle-theme]').textContent.trim()==='' && document.querySelector('[data-toggle-theme]').getBoundingClientRect().width>=44 && document.querySelector('[data-toggle-theme]').getBoundingClientRect().height>=44"))
                            check(theme+'_pill_buttons', cdp.evaluate("getComputedStyle(document.querySelector('.admin-ui-primary')).borderRadius==='999px'"))
                            check(theme+'_inter_configured', cdp.evaluate("[...document.querySelectorAll('.admin-site,.admin-kpi h2,.metric-value,.admin-ui-button,.admin-desktop-nav a,.wordmark')].every(el=>getComputedStyle(el).fontFamily.startsWith('Inter'))"))
                            # Force hover on a genuinely disabled form control.
                            visit('/admin/places/new')
                            cdp.evaluate("document.querySelector('button[type=submit]').disabled=true")
                            time.sleep(.2)
                            style = "(() => {const s=getComputedStyle(document.querySelector('button[type=submit]'));return [s.color,s.backgroundColor,s.borderColor,s.boxShadow,s.transform]})()"
                            idle = cdp.evaluate(style)
                            root = cdp.call('DOM.getDocument')['root']['nodeId']
                            node = cdp.call('DOM.querySelector', {'nodeId': root, 'selector': 'button[type=submit]'})['nodeId']
                            cdp.call('CSS.enable')
                            cdp.call('CSS.forcePseudoState', {'nodeId': node, 'forcedPseudoClasses': ['hover', 'active']})
                            time.sleep(.2)
                            check(theme+'_disabled_has_no_hover_or_active_effect', cdp.evaluate(style)==idle)
                            visit('/admin')
                        if width in (360, 1440):
                            screenshot = cdp.call('Page.captureScreenshot', {'format': 'png'})['data']
                            (output/(str(width)+'-'+theme+'.png')).write_bytes(base64.b64decode(screenshot))
                visit('/admin/settings')
                check('preferences_save_enabled', cdp.evaluate("!document.querySelector('[data-save-preferences]').disabled"))
                cdp.evaluate("""(() => {
                    const f=document.querySelector('[data-admin-preferences-form]');
                    for(const [name,value] of Object.entries({density:'compact',reduceMotion:true,reviewAlerts:false,successNotices:false,
                        sort:'newest',pageSize:'10',status:'draft',timeFormat:'24',dateFormat:'iso'})) {
                        const c=f.elements.namedItem(name);if(typeof value==='boolean')c.checked=value;else c.value=value;
                    }
                    f.dispatchEvent(new Event('change',{bubbles:true}));
                })()""")
                check('preferences_unsaved_feedback', cdp.evaluate("document.querySelector('[data-preferences-status]').dataset.state==='pending' && document.documentElement.dataset.adminDensity==='comfortable'"))
                cdp.evaluate("document.querySelector('[data-admin-preferences-form]').requestSubmit()")
                check('preferences_confirmed_save', cdp.evaluate("document.querySelector('[data-preferences-status]').dataset.state==='success' && JSON.parse(localStorage.getItem('rosago.admin.preferences.v1')).density==='compact' && document.documentElement.dataset.adminReduceMotion==='true'"))
                visit('/admin')
                check('saved_review_visibility_and_motion', cdp.evaluate("getComputedStyle(document.querySelector('[data-catalog-review-alert]')).display==='none' && getComputedStyle(document.querySelector('[data-toggle-theme]')).transitionDuration==='0s'"))
                cdp.evaluate("document.querySelector('main').insertAdjacentHTML('afterbegin','<p data-admin-success-notice>Offline success fixture</p><p role=alert data-offline-error>Offline error fixture</p>')")
                check('success_preference_cannot_hide_errors', cdp.evaluate("getComputedStyle(document.querySelector('[data-admin-success-notice]')).display==='none' && getComputedStyle(document.querySelector('[data-offline-error]')).display!=='none'"))
                visit('/admin/places')
                cdp.ready('#catalog-sort option[value=newest][selected]')
                check('saved_defaults_affect_actual_catalog', cdp.evaluate("new URL(location.href).searchParams.get('status')==='draft' && document.querySelector('#catalog-page-size').value==='10' && document.querySelector('#catalog-sort').value==='newest' && document.querySelector('#catalog-status').value==='draft'"))
                visit('/admin/places?sort=name&page_size=50&status=')
                check('explicit_catalog_filters_override_defaults', cdp.evaluate("document.querySelector('#catalog-sort').value==='name' && document.querySelector('#catalog-page-size').value==='50' && document.querySelector('#catalog-status').value===''"))
                visit('/admin/audit-logs')
                check('saved_density_and_dates_across_pages', cdp.evaluate("getComputedStyle(document.querySelector('td')).paddingTop==='8px' && document.querySelector('[data-admin-date]').textContent.includes('2026-11-03') && !document.querySelector('[data-admin-date]').textContent.includes('PM') && document.querySelector('[data-admin-date]').getAttribute('datetime')==='2026-11-03T12:05:06+08:00'"))
                visit('/admin/settings')
                check('preferences_persist_and_controls_reflect', cdp.evaluate("document.querySelector('[name=density]:checked').value==='compact' && document.querySelector('[name=pageSize]').value==='10' && document.querySelector('[name=reduceMotion]').checked"))
                for failure in ('throw','ignore'):
                    cdp.evaluate("""window.__originalSetItem=Storage.prototype.setItem;
                        Storage.prototype.setItem=function(key,value){
                            if(key==='rosago.admin.preferences.v1'){FAILURE}
                            return window.__originalSetItem.call(this,key,value);
                        };
                        document.querySelector('[data-admin-preferences-form]').elements.namedItem('density').value='comfortable';
                        document.querySelector('[data-admin-preferences-form]').requestSubmit();
                    """.replace('FAILURE',"throw new Error('Offline write blocked');" if failure=='throw' else 'return;'))
                    check('preferences_'+failure+'_save_failure_is_honest', cdp.evaluate("document.querySelector('[data-preferences-status]').dataset.state==='error' && document.documentElement.dataset.adminDensity==='compact' && JSON.parse(localStorage.getItem('rosago.admin.preferences.v1')).density==='compact'"))
                    cdp.evaluate('Storage.prototype.setItem=window.__originalSetItem')
                cdp.evaluate("localStorage.removeItem('rosago.admin.preferences.v1')")
                visit('/admin/places/new')
                check('hidden_photo_reset_stays_hidden', cdp.evaluate("getComputedStyle(document.querySelector('[data-photo-reset]')).display==='none'"))
                cdp.evaluate("const input=document.querySelector('[data-photo-input]');const files=new DataTransfer();files.items.add(new File(['fixture'],'synthetic.png',{type:'image/png'}));input.files=files.files;input.dispatchEvent(new Event('change'))")
                check('photo_selection_shows_cancel', cdp.evaluate("!document.querySelector('[data-photo-reset]').hidden"))
                cdp.evaluate("document.querySelector('[data-photo-reset]').click()")
                check('photo_cancel_preserved', cdp.evaluate("document.querySelector('[data-photo-reset]').hidden && document.querySelector('[data-photo-input]').files.length===0"))
                cdp.call('Emulation.setEmulatedMedia', {'features': [{'name': 'prefers-reduced-motion', 'value': 'reduce'}]})
                check('reduced_motion', cdp.evaluate("getComputedStyle(document.querySelector('[data-toggle-theme]')).transitionDuration==='0s'"))
                cdp.evaluate("document.querySelector('[data-toggle-theme]').focus()")
                check('visible_keyboard_focus', cdp.evaluate("getComputedStyle(document.querySelector('[data-toggle-theme]')).outlineStyle==='solid' && parseFloat(getComputedStyle(document.querySelector('[data-toggle-theme]')).outlineWidth)>=2"))
                check('no_form_posts_or_live_auth', not posts and not forbidden_calls)
            finally:
                if cdp:
                    try: cdp.call('Browser.close', browser=True)
                    except Exception: pass
                    cdp.ws.close()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired: process.terminate(); process.wait(timeout=5)
    finally:
        for server in servers: server.shutdown(); server.server_close()
        (output/'browser-results.json').write_text(json.dumps(results, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k: len(v) if k=='layouts' else v for k,v in results.items()}, indent=2))


if __name__ == '__main__': main()
