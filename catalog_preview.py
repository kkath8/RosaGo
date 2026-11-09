"""Loopback-only catalog readers reused by normal Flask development integration.

No Supabase/auth clients or writes. The standalone create_app factory remains
available for offline tests. install_catalog_preview mounts only public preview
views; it never replaces the authenticated Planner or published-only service.
"""
import hashlib
import os
from pathlib import Path
import re
from types import SimpleNamespace
from urllib.parse import urlsplit

from flask import Flask, abort, g, redirect, render_template, request, send_file, url_for

ROOT=Path(__file__).resolve().parent
LOCAL_HOSTS={'localhost','127.0.0.1','::1'}


def load_preview():
    import json
    def read(name):return json.loads((ROOT/'local_catalog'/name).read_text(encoding='utf-8-sig'))
    plan=read('production-first-publication-batch-v2.review.json')
    images=read('destination-images.final-mapping.review.json')
    original_images=read('destination-images.review.json')
    registry=read('category-registry.merged-resort.review.json')
    if (plan['target_project_ref']!='brnkigrrqdrywahvcbvc' or images['target_project_ref']!=plan['target_project_ref']
            or original_images['target_project_ref']!=plan['target_project_ref'] or registry['project_ref']!=plan['target_project_ref']):
        raise RuntimeError('Preview review target mismatch.')
    if hashlib.sha256((ROOT/'local_catalog/destination-images.review.json').read_bytes()).hexdigest()!=images['source_image_review_sha256']:
        raise RuntimeError('Completed image review changed; review before previewing.')
    # This package binds its baseline and completed image mapping by hash. No
    # image bytes are scanned/decoded/validated or regenerated here.
    for name,digest in plan['input_sha256'].items():
        if hashlib.sha256((ROOT/'local_catalog'/name).read_bytes()).hexdigest()!=digest:
            raise RuntimeError('Preview review inputs changed; review before previewing.')
    baseline=read('production-mapped-publication-v4.review.json')
    if hashlib.sha256((ROOT/'data/imports/rosago_pois_import_source.csv').read_bytes()).hexdigest()!=baseline['source_csv_sha256']:
        raise RuntimeError('Preview CSV source changed.')
    by_image={r['csv_record']:r for r in images['records']}
    by_original={r['csv_record']:r for r in original_images['records']}
    descriptions={r['csv_record']:r['description'] for r in plan['description_proposals']}
    labels={r['key']:r['label'] for r in registry['categories']}
    parents={r['key']:r['parent_key'] or r['key'] for r in registry['categories']}
    places=[];details={};files={}
    for row in plan['records']:
        number=row['csv_record'];photo=by_image[number];values=row['proposed_values']
        if photo['name']!=row['name'] or photo['existing_id']!=row['existing_id']:
            raise RuntimeError('Preview image identity mismatch.')
        candidate=photo['selected_local_candidate']
        # Display an existing prepared local candidate for the three preserved
        # hosted covers; never fetch Supabase or change their stored URL.
        preserved=photo['action']=='preserve_existing_hosted_image'
        if preserved:candidate=by_original[number]['candidate']
        if number in (56,58):candidate=None
        path=preview_image_path(candidate) if candidate else None
        if path and path.is_file():files[number]=path
        category=values['category'] or 'resort-swimming-pool'
        if category not in labels:raise RuntimeError('Preview category missing from proposed registry.')
        data={k:values.get(k) for k in ('name','slug','address','tourism_type','tourism_category','environment',
            'operating_days_raw','tourism_hours_status','tourism_opening_hours_raw','tourism_closing_hours_raw')}
        data.update(id=f'catalog-preview-{number:03}',category=category,
            description=values.get('description') or descriptions.get(number) or 'Description not supplied.',
            latitude=row['accepted_pair'][0] if row['accepted_pair'] else None,
            longitude=row['accepted_pair'][1] if row['accepted_pair'] else None,
            image_url=None,preview_number=number)
        place=SimpleNamespace(**data);places.append(place)
        details[place.slug]=dict(number=number,first_batch=row['first_content_batch_candidate'],
            status='Proposed Published — not applied' if row['first_content_batch_candidate'] else 'Draft — pending decisions',
            issues=row['remaining_record_decisions'],location_accepted=row['research_location_accepted'],
            description_proposed=not values.get('description'),
            photo_note='Local candidate preview; existing hosted cover remains preserved' if preserved else photo['reason'])
    if len(places)!=98 or len(details)!=98 or set(by_image)!=set(range(1,99)):
        raise RuntimeError('Preview requires the exact 98-record review inventory.')
    return tuple(places),details,files,labels,parents


def preview_image_path(candidate):
    path=(ROOT/candidate['staged_file'].replace('\\','/')).resolve()
    staging=(ROOT/'local_catalog/image-staging').resolve()
    if path.parent!=staging or not re.fullmatch(r'[a-f0-9]{64}\.(?:jpg|png|webp)',path.name):
        raise RuntimeError('Preview image path is outside the prepared staging inventory.')
    return path


def validate_preview_environment(environment):
    if (environment.get('ROSAGO_CATALOG_PREVIEW')!='true'
            or environment.get('ROSAGO_AUTH_MODE','development')!='development'
            or environment.get('FLASK_ENV')=='production'
            or any(environment.get(k) for k in ('RENDER','RENDER_SERVICE_ID','DYNO','WEBSITE_INSTANCE_ID'))
            or environment.get('FLASK_RUN_HOST','127.0.0.1') not in LOCAL_HOSTS):
        raise RuntimeError('Catalog preview requires explicit local development mode and loopback hosting.')


def validate_local_request():
    host=urlsplit('http://'+request.host).hostname
    if (host not in LOCAL_HOSTS or request.remote_addr not in ('127.0.0.1','::1')
            or any(k in request.headers for k in ('Forwarded','X-Forwarded-For','X-Forwarded-Host','X-Forwarded-Proto'))):
        abort(403)


def preview_response_headers(response):
    response.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
        'X-Frame-Options':'DENY','Referrer-Policy':'no-referrer',
        'Content-Security-Policy':"default-src 'self'; img-src 'self' data:; connect-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"})
    return response


def create_app(environment=None):
    environment=os.environ if environment is None else environment
    validate_preview_environment(environment)
    app=Flask(__name__,static_folder=None,template_folder=str(ROOT/'templates'))
    app.config.update(SESSION_COOKIE_NAME='rosago_catalog_preview_unused',MAX_CONTENT_LENGTH=4096)
    places,details,files,labels,parents=load_preview()
    app.extensions['rosago_catalog_preview']=dict(places=places,details=details)

    @app.before_request
    def local_read_only():
        validate_local_request()
        if request.method not in ('GET','HEAD'):abort(405)

    @app.after_request
    def private_preview(response):
        return preview_response_headers(response)

    @app.context_processor
    def preview_context():
        return dict(catalog_preview=True,preview_records=details,category_labels=labels,preview_planner_endpoint='planner',
            website_settings=SimpleNamespace(personalized=False,location_enabled=False))

    @app.get('/static/<path:filename>',endpoint='static')
    def static_asset(filename):
        path=(ROOT/'static'/filename).resolve()
        if (not path.is_relative_to((ROOT/'static').resolve()) or Path(filename).parts[0] not in ('css','js','img','fonts')
                or path.suffix.lower() not in ('.css','.js','.svg','.png','.jpg','.webp','.woff','.woff2','.ttf') or not path.is_file()):abort(404)
        return send_file(path)

    @app.get('/preview/images/<int:number>')
    def preview_image(number):
        if number not in files:abort(404)
        return send_file(files[number],conditional=False,max_age=0)

    def display_rows():
        return tuple(SimpleNamespace(**(vars(p)|dict(image_url=url_for('preview_image',number=p.preview_number)
            if p.preview_number in files else None))) for p in places)

    @app.get('/',endpoint='index')
    def index():return redirect(url_for('places_list'))

    @app.get('/places',endpoint='places_list')
    def explore():
        query=request.args.get('q','').strip()
        category=request.args.get('category')
        if len(query)>200 or (category and category not in labels):abort(400)
        words=query.casefold().split()
        selected=[p for p in display_rows() if (not category or p.category==category) and
            all(w in f'{p.name} {p.address} {labels[p.category]} {p.tourism_type or ""}'.casefold() for w in words)]
        return render_template('places/list.html',places=selected,categories=tuple(labels),selected_category=category)

    @app.get('/places/<slug>',endpoint='places_detail')
    def detail(slug):
        place=next((p for p in display_rows() if p.slug==slug),None)
        if place is None:abort(404)
        return render_template('places/detail.html',place=place,destination_weather=SimpleNamespace(exposure=None))

    @app.get('/user/planner',endpoint='planner')
    def planner():
        interest=request.args.get('interest','attraction');count=request.args.get('stops','6')
        if interest not in ('attraction','nature','heritage','industrial','shopping','dining','accommodation') or count not in ('3','6','9','12'):abort(400)
        eligible=[p for p in display_rows() if details[p.slug]['first_batch'] and parents[p.category]==interest]
        eligible.sort(key=lambda p:({'Local':0,None:1,'Common':2}.get(p.tourism_type,1),p.name.casefold()))
        return render_template('places/list.html',places=eligible[:int(count)],categories=(),selected_category=None,
            preview_simulation=True,preview_interest=interest,preview_stops=count,
            preview_interests=('attraction','nature','heritage','industrial','shopping','dining','accommodation'))

    return app


def install_catalog_preview(app, environment=None):
    """Mount the existing renderers in the normal app without replacing services.

    Realm/session before-request safeguards run before preview dispatch. No
    protected view is intercepted: the public simulation has its own endpoint.
    """
    environment=os.environ if environment is None else environment
    if environment.get('ROSAGO_CATALOG_PREVIEW')!='true':return
    if 'rosago_catalog_preview' in app.extensions:raise RuntimeError('Preview already installed.')
    preview=create_app(environment)
    app.extensions['rosago_catalog_preview']=preview.extensions['rosago_catalog_preview']
    preview_endpoints={'places_list','places_detail','preview_image','catalog_preview_simulation'}

    def development_boundary():
        validate_local_request()
        # No simulated/catalog/account writes can enter the real services.
        # Logout must retain its existing CSRF, realm and revocation behavior.
        if request.method not in ('GET','HEAD') and request.endpoint not in ('logout','admin.logout'):
            return 'Local catalog preview is read-only. Disable ROSAGO_CATALOG_PREVIEW to change data or sign in.',403
        if request.path in ('/auth/reset-callback','/verify-email'):
            return 'Account completion is unavailable during local catalog preview.',403

    # Apply loopback/write restrictions even before an auth redirect. This
    # never admits a request; normal realm/auth gates remain in their order.
    app.before_request_funcs.setdefault(None,[]).insert(0,development_boundary)

    @app.before_request
    def preview_dispatch():
        if request.endpoint not in preview_endpoints:return
        g.rosago_catalog_preview_page=True
        endpoint={'catalog_preview_simulation':'planner'}.get(request.endpoint,request.endpoint)
        return preview.view_functions[endpoint](**(request.view_args or {}))

    # New public simulation/image routes; original User/Admin views are retained.
    app.add_url_rule('/preview/planner','catalog_preview_simulation',lambda:abort(404),methods=['GET'])
    app.add_url_rule('/preview/images/<int:number>','preview_image',lambda number:abort(404),methods=['GET'])

    @app.context_processor
    def integrated_preview_context():
        context=dict(catalog_preview_enabled=True)
        if getattr(g,'rosago_catalog_preview_page',False):
            context.update(preview.template_context_processors[None][-1]())
            context.update(catalog_preview_integrated=True,preview_planner_endpoint='catalog_preview_simulation')
        return context

    @app.after_request
    def integrated_preview_response(response):
        if getattr(g,'rosago_catalog_preview_page',False):return preview_response_headers(response)
        response.headers['Cache-Control']='private, no-store'
        return response
