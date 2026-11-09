"""Real Edge, offline GET-only User/Admin snapshots. No live app or sign-in."""
import base64
import argparse
from dataclasses import replace
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Thread
import time
from types import SimpleNamespace
from urllib.parse import urlsplit
from unittest.mock import Mock, patch
import httpx

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tools'),str(ROOT/'tests')]
from check_admin_appearance import snapshots as admin_snapshots
from check_login_browser import CDP
from test_recommendation_engine import place


def snapshots():
    app,pages,forbidden,client=admin_snapshots()
    with client.session_transaction(path='/admin') as state:
        state['_flashes']=[('success','Synthetic successful action'),
                           ('error','Synthetic security error'),('warning','Synthetic important warning')]
    response=client.get('/admin/settings')
    assert response.status_code==200
    pages['/admin/settings']=response.data
    # Exercise the actual attention-list template with synthetic rows of varying
    # lengths; the generic provider fixture can render the unavailable state.
    from admin_insights_service import summarize_catalog
    from test_admin_insights import place as insight_place
    attention=summarize_catalog((insight_place(1,'heritage'),insight_place(2,'dining')),
        tourism_metadata_enabled=False,scope='published',issue=None,page=1)
    with patch('admin_routes.catalog_insights',return_value=attention):
        response=client.get('/admin/insights')
        assert response.status_code==200
        pages['/admin/insights']=response.data
    public=replace(place(1),name='Santa Rosa Riverside Garden',latitude=14.25,longitude=121.05)
    app.extensions['rosago_places']=Mock(list_published=Mock(return_value=(public,)),
        get_published_by_slug=Mock(return_value=public))
    deps=app.extensions['rosago_normal_auth']
    def respond(request):
        if request.url.path.endswith('/profiles'):
            row=dict(id='11111111-1111-4111-8111-111111111111',first_name='Synthetic',last_name='Traveller',created_at='2026-11-01T00:00:00Z')
            fields=request.url.params.get('select','').split(',')
            return httpx.Response(200,json=[{k:row.get(k) for k in fields}])
        return httpx.Response(200,json=[],headers={'Content-Range':'*/0'})
    deps.adapters._http_factory=lambda **kw:httpx.Client(transport=httpx.MockTransport(respond),**kw)
    deps.coordinator._clients=deps.adapters.database_client
    # Render public authentication screens before adding a synthetic local session.
    endpoints=['index','login','register','forgot_password','places_list','map_index','terms','privacy']
    from flask import url_for
    with app.test_request_context():
        paths=[url_for(e) for e in endpoints]+[url_for('places_detail',slug=public.slug),url_for('register',workspace='admin')]
    for path in paths:
        response=client.get(path,follow_redirects=True)
        assert response.status_code==200,(path,response.status_code)
        pages[path]=response.data
    handle=deps.store.create(user_id='11111111-1111-4111-8111-111111111111',user_email='traveller@example.invalid',
        access_token='synthetic-access',refresh_token='synthetic-refresh',access_expires_at=time.time()+3600,session_id='synthetic-provider-session')
    with client.session_transaction() as current:current['auth_session_id']=handle
    with app.test_request_context():
        paths=[url_for(e) for e in ['user_index','settings','planner','trips_list','assistant','features.saved',
            'features.visited','features.budget','features.help_page','alerts']]
    for path in paths:
        response=client.get(path,follow_redirects=True)
        assert response.status_code==200,(path,response.status_code)
        pages[path]=response.data
    assert not forbidden
    return app,pages,forbidden


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--matrix-pages',nargs='+',help='Limit the layout matrix; interaction checks still run.')
    args=parser.parse_args()
    app,pages,forbidden=snapshots();posts=[];results={'layouts':[],'checks':{}}
    matrix_pages=args.matrix_pages or list(pages)
    if any(path not in pages for path in matrix_pages):raise ValueError('Unknown synthetic matrix page.')
    results['matrix_pages']=matrix_pages
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):posts.append(True);self.send_error(405)
        def do_GET(self):
            path=self.path if self.path in pages else urlsplit(self.path).path
            if path in pages:body,mime=pages[path],'text/html; charset=utf-8'
            elif path.startswith('/static/'):
                response=app.test_client().get(path);body,mime=response.data,response.content_type
            else:self.send_error(404);return
            self.send_response(200);self.send_header('Content-Type',mime);self.end_headers();self.wfile.write(body)
    class Deny(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reject(self):self.send_response(403);self.end_headers()
        do_GET=do_POST=do_CONNECT=reject
    servers=[ThreadingHTTPServer(('127.0.0.1',0),handler) for handler in (Handler,Deny)]
    for server in servers:Thread(target=server.serve_forever,daemon=True).start()
    origin='http://127.0.0.1:'+str(servers[0].server_port)
    output=ROOT/'docs/unified-workspace-ui';output.mkdir(exist_ok=True)
    def check(name,value):
        results['checks'][name]=bool(value)
        if not value:raise AssertionError(name)
    try:
        with tempfile.TemporaryDirectory(prefix='rosago-unified-ui-') as temporary:
            edge=Path(os.environ.get('PROGRAMFILES(X86)','C:/Program Files (x86)'))/'Microsoft/Edge/Application/msedge.exe'
            process=subprocess.Popen([str(edge),'--headless=new','--disable-gpu','--no-first-run',
                '--no-default-browser-check','--disable-background-networking','--disable-component-update','--disable-sync',
                '--disable-extensions','--remote-debugging-address=127.0.0.1','--remote-debugging-port=0','--user-data-dir='+temporary,
                '--proxy-server=http://127.0.0.1:'+str(servers[1].server_port),'--proxy-bypass-list=127.0.0.1;localhost;[::1]',
                'about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            cdp=None
            try:
                active=Path(temporary)/'DevToolsActivePort';deadline=time.monotonic()+20
                while not active.exists() and time.monotonic()<deadline:time.sleep(.05)
                port,path=active.read_text().splitlines()[:2];cdp=CDP('ws://127.0.0.1:'+port+path)
                target=cdp.call('Target.createTarget',{'url':'about:blank'},browser=True)['targetId']
                cdp.session=cdp.call('Target.attachToTarget',{'targetId':target,'flatten':True},browser=True)['sessionId']
                cdp.call('Page.enable')
                def visit(path):
                    cdp.call('Page.navigate',{'url':origin+path});deadline=time.monotonic()+8
                    while time.monotonic()<deadline:
                        if cdp.evaluate("document.readyState==='complete' && location.pathname+location.search==="+json.dumps(path)):return
                        time.sleep(.025)
                    raise RuntimeError('Offline snapshot navigation timed out: '+path)
                visit('/admin/login');cdp.evaluate("localStorage.setItem('rosago.theme.v1','dark')")
                visit('/admin/login')
                check('admin_login_white_without_theme_control_and_preserves_preference',cdp.evaluate("!document.querySelector('[data-set-theme],[data-toggle-theme]') && getComputedStyle(document.body).backgroundColor==='rgb(255, 255, 255)' && localStorage.getItem('rosago.theme.v1')==='dark'"))
                check('admin_login_security_fields_preserved',cdp.evaluate("document.querySelector('[name=csrf_token]').type==='hidden' && document.querySelector('#password').required && document.querySelector('.admin-login-form').method==='post'"))
                check('admin_registration_uses_existing_account_flow',cdp.evaluate("document.querySelector('.login-prompt a').getAttribute('href')==='/register?workspace=admin' && !!document.querySelector('.admin-account-approval-note') && !document.querySelector('[name=role],[name=is_admin]') && !!document.querySelector('.registration-layout>.welcome') && !!document.querySelector('.form-panel>.registration-card')"))
                check('login_brand_has_no_badge_or_background',cdp.evaluate("!document.querySelector('.admin-badge,.admin-login-card .eyebrow') && getComputedStyle(document.querySelector('.admin-login-wordmark')).backgroundColor==='rgba(0, 0, 0, 0)'"))
                cdp.evaluate("document.querySelector('[data-admin-password-toggle]').click()")
                check('password_show_handler_preserved',cdp.evaluate("document.querySelector('#password').type==='text'"))
                cdp.evaluate("document.querySelector('[data-admin-password-toggle]').click()")
                for theme in ('light','dark'):
                    cdp.evaluate("localStorage.setItem('rosago.theme.v1',"+json.dumps(theme)+")")
                    for width in (320,393,768,1024,1366,1440,1920):
                        cdp.call('Emulation.setDeviceMetricsOverride',{'width':width,'height':900,'deviceScaleFactor':1,'mobile':False})
                        for path in matrix_pages:
                            visit(path)
                            state=cdp.evaluate("JSON.stringify({width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth,css:!!document.querySelector('link[href*=\"workspace-ui.css\"]'),theme:document.documentElement.dataset.theme||'light'})")
                            state=json.loads(state);state.update(path=path,viewport=width,selected_theme=theme)
                            results['layouts'].append(state)
                            check('shared_css_'+str(len(results['layouts'])),state['css'])
                            check('no_page_overflow_'+str(len(results['layouts'])),state['scroll']<=state['width']+1)
                            if path in ('/login','/admin/login'):
                                check('matching_login_brand_and_toggle_'+path+'_'+theme+'_'+str(width),cdp.evaluate("(()=>{const brand=getComputedStyle(document.querySelector('.welcome .brand')),toggle=getComputedStyle(document.querySelector('.password-toggle'));return brand.backgroundColor==='rgba(0, 0, 0, 0)' && brand.color==='rgb(255, 255, 255)' && brand.padding==='0px' && toggle.borderTopWidth==='0px' && toggle.boxShadow==='none'})()"))
                            if path=='/':
                                check('dashboard_centered_arch_'+theme+'_'+str(width),cdp.evaluate("(()=>{const hero=document.querySelector('.wl-hero'),r=hero.getBoundingClientRect(),s=getComputedStyle(hero);return !hero.querySelector('form,input[type=search],.wl-chips,a') && s.backgroundSize.split(',').every(size=>size.trim()==='cover') && s.textAlign==='center' && [...hero.children].every(el=>{const b=el.getBoundingClientRect();return Math.abs((b.left+b.width/2)-(r.left+r.width/2))<2})})()"))
                            if width>=1024 and path in ('/admin/login','/login','/register','/register?workspace=admin'):
                                photo_state=cdp.evaluate("JSON.stringify({inner:innerHeight,scroll:document.documentElement.scrollHeight,photo:document.querySelector('.welcome').getBoundingClientRect().height,panel:document.querySelector('.form-panel').getBoundingClientRect().height,overflow:getComputedStyle(document.querySelector('.form-panel')).overflowY,bodyHeight:document.body.getBoundingClientRect().height,bodyTop:document.body.getBoundingClientRect().top,bodyOverflow:getComputedStyle(document.body).overflow,layoutTop:document.querySelector('.registration-layout').getBoundingClientRect().top,layoutHeight:document.querySelector('.registration-layout').getBoundingClientRect().height,panelTop:document.querySelector('.form-panel').getBoundingClientRect().top,htmlOverflow:getComputedStyle(document.documentElement).overflow})")
                                results.setdefault('photo_states',{})[path+'_'+theme+'_'+str(width)]=json.loads(photo_state)
                                check('fixed_auth_photo_'+path+'_'+theme+'_'+str(width),cdp.evaluate("(()=>{const panel=document.querySelector('.registration-layout>.form-panel'),photo=document.querySelector('.registration-layout>.welcome');if(!panel||!photo)return false;const before=photo.getBoundingClientRect();panel.scrollTop=panel.scrollHeight;const after=photo.getBoundingClientRect();return getComputedStyle(panel).overflowY==='auto' && document.documentElement.scrollHeight<=innerHeight+1 && Math.abs(before.top-after.top)<1 && Math.abs(after.height-innerHeight)<1})()"))
                            if path=='/register?workspace=admin':
                                check('admin_registration_navigation_'+theme+'_'+str(width),cdp.evaluate("document.querySelector('.login-prompt a').getAttribute('href')==='/admin/login' && document.querySelector('#registration-form').getAttribute('action')==='/register?workspace=admin' && document.querySelector('#register-title').textContent==='Create an Admin account'"))
                            if path=='/places':
                                check('compact_explore_search_'+theme+'_'+str(width),cdp.evaluate("(()=>{const a=document.querySelector('#explore-query').getBoundingClientRect(),b=document.querySelector('.explore-controls button').getBoundingClientRect();return Math.abs(a.top-b.top)<5 && a.right<=b.left && a.top<200})()"))
                            if path=='/admin/users':
                                check('compact_user_search_'+theme+'_'+str(width),cdp.evaluate("(()=>{const form=document.querySelector('.admin-list-toolbar'),s=getComputedStyle(form),a=form.getBoundingClientRect();return s.boxShadow==='none' && a.top<230 && [...form.querySelectorAll('input,button,a')].every(el=>{const r=el.getBoundingClientRect();return r.left>=a.left-1 && r.right<=a.right+1})})()"))
                            if path=='/admin':
                                check('admin_header_alignment_'+theme+'_'+str(width),cdp.evaluate("(()=>{const a=document.querySelector('.admin-header .admin-brand').getBoundingClientRect(),b=document.querySelector('.admin-header-actions').getBoundingClientRect();return a.right<=b.left && Math.abs((a.top+a.height/2)-(b.top+b.height/2))<2})()"))
                            if path=='/admin/insights':
                                check('attention_actions_aligned_'+theme+'_'+str(width),cdp.evaluate("(()=>{const list=document.querySelector('.attention-list'),row=list?.querySelector('li');if(!row)return false;const copy=row.cloneNode(true);copy.querySelector('strong').textContent='Short name';list.append(copy);const a=[...row.querySelectorAll(':scope>a')].map(el=>el.getBoundingClientRect()),b=[...copy.querySelectorAll(':scope>a')].map(el=>el.getBoundingClientRect());const ok=a.length===2 && a.every((r,i)=>Math.abs(r.left-b[i].left)<1 && Math.abs(r.width-b[i].width)<1 && r.height>=44) && Math.abs(a[0].top-a[1].top)<1 && a[0].right<=a[1].left;copy.remove();return ok})()"))
                    visit('/admin/settings')
                    check('settings_theme_controls_'+theme,cdp.evaluate("!!document.querySelector('[data-set-theme=light]') && !!document.querySelector('[data-set-theme=dark]')"))
                    visit('/admin')
                    check('red_admin_shell_'+theme,cdp.evaluate("[...document.querySelectorAll('.admin-header,.admin-workspace footer')].every(el=>getComputedStyle(el).backgroundColor==='rgb(142, 59, 44)')"))
                    check('status_contrast_'+theme,cdp.evaluate("""(()=>{
                        const luminance=s=>{const c=s.match(/[0-9.]+/g).slice(0,3).map(v=>{v=Number(v)/255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4});return c[0]*.2126+c[1]*.7152+c[2]*.0722};
                        return [...document.querySelectorAll('.admin-pill-published,.admin-pill-draft,.admin-pill-archived')].every(el=>{
                            const s=getComputedStyle(el),a=luminance(s.color),b=luminance(s.backgroundColor);return (Math.max(a,b)+.05)/(Math.min(a,b)+.05)>=4.5});
                    })()"""))
                cdp.evaluate("localStorage.setItem('rosago.theme.v1','light')")
                visit('/admin')
                check('admin_header_minimal_branding',cdp.evaluate("!document.querySelector('.admin-badge,.admin-topbar-title') && !!document.querySelector('.admin-header .wordmark')"))
                cdp.evaluate("document.querySelector('.admin-account>summary').click()")
                check('admin_profile_dropdown_opens',cdp.evaluate("document.querySelector('.admin-account').open && !!document.querySelector('.admin-account [name=csrf_token]')"))
                cdp.evaluate("document.querySelector('.admin-account>summary').click()")
                check('dashboard_cards_use_white_surfaces',cdp.evaluate("[...document.querySelectorAll('.admin-kpi,.admin-inline-stat,.admin-review-panel')].every(el=>getComputedStyle(el).backgroundColor==='rgb(255, 255, 255)')"))
                check('dashboard_status_labels_are_distinct',cdp.evaluate("new Set([...document.querySelectorAll('.admin-pill-published,.admin-pill-draft,.admin-pill-archived')].map(el=>getComputedStyle(el).backgroundColor)).size===3"))
                cdp.evaluate("document.querySelector('[data-toggle-theme]').click()")
                check('header_toggle_persists',cdp.evaluate("document.documentElement.dataset.theme==='dark' && localStorage.getItem('rosago.theme.v1')==='dark'"))
                cdp.evaluate("document.querySelector('[data-toggle-theme]').click()")
                visit('/admin/places')
                check('catalog_words_wrap_naturally',cdp.evaluate("[...document.querySelectorAll('.catalog-table th,.catalog-table td')].every(el=>{const s=getComputedStyle(el);return s.overflowWrap==='normal' && s.wordBreak==='normal'})"))
                check('catalog_scroll_and_columns',cdp.evaluate("getComputedStyle(document.querySelector('.catalog-table')).tableLayout==='auto' && document.querySelector('.catalog-table').getBoundingClientRect().width>=1240"))
                check('table_has_scrolling_region_and_wrapping',cdp.evaluate("getComputedStyle(document.querySelector('.admin-table-scroll')).overflowX==='auto' && getComputedStyle(document.querySelector('tbody td')).whiteSpace==='normal'"))
                check('status_labels_are_distinct_and_textual',cdp.evaluate("(()=>{const colors=['published','draft','archived'].map(s=>{let el=document.createElement('span');el.className='status-badge status-'+s;el.textContent=s;document.body.append(el);let c=getComputedStyle(el).backgroundColor;el.remove();return c});return new Set(colors).size===3})()"))
                cdp.call('Emulation.setDeviceMetricsOverride',{'width':390,'height':844,'deviceScaleFactor':1,'mobile':False})
                check('mobile_buttons_keep_touch_targets',cdp.evaluate("[...document.querySelectorAll('.admin-table .secondary-button')].every(el=>el.getBoundingClientRect().height>=44)"))
                cdp.evaluate("document.querySelector('button,.secondary-button').focus()")
                cdp.call('Input.dispatchKeyEvent',{'type':'keyDown','key':'Tab','code':'Tab','windowsVirtualKeyCode':9})
                cdp.call('Input.dispatchKeyEvent',{'type':'keyUp','key':'Tab','code':'Tab','windowsVirtualKeyCode':9})
                check('keyboard_focus_is_visible',cdp.evaluate("(()=>{const s=getComputedStyle(document.activeElement);return s.outlineStyle!=='none' && parseFloat(s.outlineWidth)>=2})()"))
                cdp.call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':900,'deviceScaleFactor':1,'mobile':False})
                def hover(selector):
                    rect=json.loads(cdp.evaluate("(()=>{const el=document.querySelector("+json.dumps(selector)+");el.scrollIntoView({block:'center'});const r=el.getBoundingClientRect();return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2})})()"))
                    cdp.call('Input.dispatchMouseEvent',{'type':'mouseMoved',**rect});time.sleep(.25)
                    return json.loads(cdp.evaluate("(()=>{const s=getComputedStyle(document.querySelector("+json.dumps(selector)+"));return JSON.stringify({background:s.backgroundColor,color:s.color})})()"))
                visit('/')
                reference=hover('.landmark-copy .site-button')
                check('heritage_hover_is_dark_red_white',reference==dict(background='rgb(110, 42, 30)',color='rgb(255, 255, 255)'))
                check('red_user_header_footer',cdp.evaluate("[...document.querySelectorAll('.site-header,.site-footer')].every(el=>getComputedStyle(el).backgroundColor==='rgb(142, 59, 44)')"))
                visit('/places')
                check('explore_accessible_labels_retained_without_clutter',cdp.evaluate("document.querySelector('label[for=explore-query]').classList.contains('visually-hidden') && document.querySelector('.category-nav').getAttribute('aria-label')==='Place categories'"))
                check('secondary_hover_matches_heritage',hover('.secondary-button')==reference)
                visit('/admin')
                check('admin_hover_matches_heritage',hover('.admin-ui-button:not(.admin-ui-primary)')==reference)
                check('quick_management_hover_matches_heritage',hover('.admin-action-card:not(.admin-action-primary)')==reference)
                cdp.evaluate("localStorage.setItem('rosago.theme.v1','dark')")
                visit('/admin/settings')
                check('dark_selected_theme_button_hover_matches_heritage',hover('[data-set-theme=dark]')==reference)
                cdp.evaluate("localStorage.setItem('rosago.theme.v1','light')")
                visit('/admin/places')
                comfortable_padding=cdp.evaluate("parseFloat(getComputedStyle(document.querySelector('.admin-table td')).paddingTop)")
                visit('/admin/settings')
                def save_preferences(values):
                    cdp.evaluate("(()=>{const form=document.querySelector('[data-admin-preferences-form]');for(const [key,value] of Object.entries("+json.dumps(values)+")){const control=form.elements.namedItem(key);if(typeof value==='boolean')control.checked=value;else control.value=value;control.dispatchEvent?.(new Event('change',{bubbles:true}));}form.requestSubmit();})()")
                saved=dict(density='compact',reduceMotion=True,reviewAlerts=False,successNotices=False,
                           sort='oldest',pageSize='10',status='draft',timeFormat='24',dateFormat='iso')
                save_preferences(saved)
                check('settings_save_confirmed',cdp.evaluate("document.querySelector('[data-preferences-status]').dataset.state==='success' && JSON.parse(localStorage.getItem('rosago.admin.preferences.v1')).pageSize==='10'"))
                visit('/admin/settings')
                check('settings_values_restore',cdp.evaluate("(()=>{const f=document.querySelector('[data-admin-preferences-form]');return f.elements.namedItem('density').value==='compact' && f.elements.namedItem('reduceMotion').checked && !f.elements.namedItem('reviewAlerts').checked && f.elements.namedItem('pageSize').value==='10' && f.elements.namedItem('timeFormat').value==='24'})()"))
                check('optional_success_hidden_but_errors_and_warnings_visible',cdp.evaluate("(()=>{const notes=[...document.querySelectorAll('.notice')];return notes.some(el=>el.textContent==='Synthetic successful action' && getComputedStyle(el).display==='none') && ['Synthetic security error','Synthetic important warning'].every(text=>notes.some(el=>el.textContent===text && getComputedStyle(el).display!=='none')) && getComputedStyle(document.querySelector('[data-preferences-status]')).display!=='none'})()"))
                check('saved_reduce_motion_changes_controls',cdp.evaluate("getComputedStyle(document.querySelector('[data-save-preferences]')).transitionDuration==='0s'"))
                for path in ('/admin/places?sort=slug&page_size=25&status=', '/admin/users','/admin/trips','/admin/audit-logs'):
                    visit(path)
                    check('compact_density_actual_table_'+path,cdp.evaluate("parseFloat(getComputedStyle(document.querySelector('.admin-table td')).paddingTop)")<comfortable_padding)
                    if path in ('/admin/users','/admin/audit-logs'):
                        check('saved_datetime_display_'+path,cdp.evaluate("[...document.querySelectorAll('[data-admin-date]')].some(el=>/^\\d{4}-\\d{2}-\\d{2}/.test(el.textContent) && el.title.startsWith('Asia/Manila') && /T/.test(el.getAttribute('datetime')))"))
                visit('/admin')
                check('optional_catalog_review_hidden',cdp.evaluate("getComputedStyle(document.querySelector('[data-catalog-review-alert]')).display==='none'"))
                # Default navigation changes the real URL; synthetic GET-only pages
                # do not claim to qualify database row counts (route tests do).
                cdp.call('Page.navigate',{'url':origin+'/admin/places'})
                deadline=time.monotonic()+8
                while time.monotonic()<deadline:
                    if cdp.evaluate("document.readyState==='complete' && new URLSearchParams(location.search).get('page_size')==='10'"):break
                    time.sleep(.05)
                check('destination_defaults_reach_catalog_url',cdp.evaluate("(()=>{const p=new URLSearchParams(location.search);return p.get('sort')==='oldest' && p.get('page_size')==='10' && p.get('status')==='draft'})()"))
                visit('/admin/settings')
                save_preferences(dict(density='comfortable',reduceMotion=False,reviewAlerts=True,successNotices=True,
                                      sort='slug',pageSize='25',status='all',timeFormat='12',dateFormat='dmy'))
                check('success_notices_can_be_restored',cdp.evaluate("getComputedStyle(document.querySelector('[data-admin-success-notice]')).display!=='none'"))
                visit('/admin')
                check('review_alerts_can_be_restored',cdp.evaluate("getComputedStyle(document.querySelector('[data-catalog-review-alert]')).display!=='none'"))
                for path,name,width in [('/','user-dashboard',1440),('/','user-dashboard-mobile',393),('/admin','admin-dashboard',1440),('/places','user-explore',1440),('/admin/login','admin-login',390),('/places','user-explore-mobile',390),('/admin/account','admin-account',1440),('/admin/settings','admin-settings',1440),('/admin/account','admin-account-mobile',393),('/admin/settings','admin-settings-mobile',393)]:
                    cdp.call('Emulation.setDeviceMetricsOverride',{'width':width,'height':900,'deviceScaleFactor':1,'mobile':False});visit(path)
                    # Notice behavior was checked above; keep design screenshots
                    # representative of the ordinary workspace with no flashes.
                    if path=='/admin/settings':cdp.evaluate("document.querySelectorAll('.notice').forEach(el=>{if(el.textContent.startsWith('Synthetic '))el.remove()})")
                    results.setdefault('font_samples',{})[path]=json.loads(cdp.evaluate("JSON.stringify([...document.querySelectorAll('body,h1,h2,p,button')].slice(0,15).map(el=>({tag:el.tagName,family:getComputedStyle(el).fontFamily})))"))
                    (output/(name+'.png')).write_bytes(base64.b64decode(cdp.call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False})['data']))
                cdp.evaluate("localStorage.setItem('rosago.theme.v1','dark')")
                cdp.call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':900,'deviceScaleFactor':1,'mobile':False})
                visit('/admin/settings')
                cdp.evaluate("document.querySelectorAll('.notice').forEach(el=>{if(el.textContent.startsWith('Synthetic '))el.remove()})")
                (output/'admin-settings-dark.png').write_bytes(base64.b64decode(cdp.call('Page.captureScreenshot',{'format':'png'})['data']))
                visit('/admin/account')
                (output/'admin-account-dark.png').write_bytes(base64.b64decode(cdp.call('Page.captureScreenshot',{'format':'png'})['data']))
                cdp.call('Emulation.setEmulatedMedia',{'features':[{'name':'prefers-reduced-motion','value':'reduce'}]})
                check('reduced_motion',cdp.evaluate("[...document.querySelectorAll('button,.site-button')].every(el=>getComputedStyle(el).transitionDuration==='0s')"))
                check('no_posts_or_live_auth',not posts and not forbidden)
            finally:
                if cdp:
                    try:cdp.call('Browser.close',browser=True)
                    except Exception:pass
                    cdp.ws.close()
                try:process.wait(timeout=8)
                except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=5)
    finally:
        for server in servers:server.shutdown();server.server_close()
        results.update(scope='Offline synthetic GET-only snapshots, installed Edge, deny-only external proxy.',pages=len(pages),hosted_requests=0,live_signins=0,posts=len(posts))
        (output/'browser-results.json').write_text(json.dumps(results,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(pages=results['pages'],layouts=len(results['layouts']),checks=len(results['checks']),failed=[k for k,v in results['checks'].items() if not v],hosted_requests=0)))

if __name__=='__main__':main()
