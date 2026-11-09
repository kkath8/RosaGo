"""Offline Admin management integration through real auth and PostgREST clients.

The transport is an isolated database double, never a production CRUD probe.
SQL deployment and database execution are explicitly separate verification steps.
"""
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import httpx
from werkzeug.datastructures import MultiDict
from admin_management_service import (validate_destination, DestinationValidationError,
    operational_overview, mutate_destination)
from admin_places_service import AdminPlacesError
from normal_auth_coordinator import AuthenticatedContext
from places_service import PlacesService
import test_admin_authorization as foundation
import test_registration
from test_public_layout import Document

ORIGIN = {'Origin':'http://localhost'}
BASE = dict(name='RosaGo Admin Verification Test',category='nature',description='Isolated fixture only.',
    address='Fixture address',latitude='',longitude='',tourism_type='',tourism_category='',
    tourism_opening_hours_raw='',tourism_closing_hours_raw='',tourism_hours_status='')


def overview():
    return dict(users_total=1,users_matching=1,users=[dict(identifier='account-fixture',
        email='fixture@example.invalid',name='Fixture <Admin>',created_at='2026-11-01T00:00:00Z')],
        trips_total=2,upcoming_trips=1,destinations_in_trips=1,
        popular=[dict(name='Fixture destination',slug='fixture-destination',trips=2)],
        categories=[dict(category='nature',trips=2)])


class ManagementServiceTests(unittest.TestCase):
    def test_validation_nulls_raw_hours_and_trimmed_required_text(self):
        result=validate_destination(BASE | dict(name=' Test ',tourism_opening_hours_raw=' 10:00 AM* '),tourism_enabled=True)
        self.assertEqual(result['name'],'Test')
        self.assertIsNone(result['tourism_type'])
        self.assertIsNone(result['latitude'])
        self.assertEqual(result['tourism_opening_hours_raw'],' 10:00 AM* ')
        for value in ('Local','Common',''):
            self.assertEqual(validate_destination(BASE | dict(tourism_type=value),tourism_enabled=True)['tourism_type'],value or None)

    def test_all_invalid_values_rejected(self):
        cases=[dict(name=' '),dict(name='a'*151),dict(description=''),dict(description='a'*3001),
            dict(address=''),dict(address='a'*501),dict(category='invented'),dict(tourism_type='local'),
            dict(tourism_type='Outdoor'),dict(tourism_hours_status='verified'),dict(latitude='14'),
            dict(longitude='121'),dict(latitude='nan',longitude='121'),dict(latitude='91',longitude='121'),
            dict(latitude='0',longitude='181'),dict(latitude='true',longitude='0'),dict(tourism_category='x'*251),
            dict(status='published'),dict(tourism_source='forged')]
        for change in cases:
            with self.subTest(change=change), self.assertRaises(DestinationValidationError):
                validate_destination(BASE | change,tourism_enabled=True)
        for lat,lon in (('-90','-180'),('90','180'),('0','0')):
            self.assertEqual(validate_destination(BASE|dict(latitude=lat,longitude=lon),tourism_enabled=True)['latitude'],float(lat))

    def test_operational_projection_rejects_extra_secrets_and_malformed_counts(self):
        client=Mock(); query=client.rpc.return_value; query.retry.return_value=query
        context=AuthenticatedContext('handle','actor','email',client, realm='admin')
        query.execute.return_value=SimpleNamespace(data=overview())
        self.assertEqual(operational_overview(context)['trips_total'],2)
        for bad in (overview()|dict(password='secret'),overview()|dict(users_total=True),
                    overview()|dict(users=[overview()['users'][0]|dict(access_token='secret')]),
                    overview()|dict(popular=[dict(name='X',slug='bad/slug',trips=1)])):
            query.execute.return_value=SimpleNamespace(data=bad)
            with self.assertRaises(AdminPlacesError): operational_overview(context)

    def test_mutation_result_and_action_are_strict(self):
        client=Mock(); query=client.rpc.return_value; query.retry.return_value=query
        context=AuthenticatedContext('handle','actor','email',client, realm='admin')
        for action in ('delete','published','disable'):
            with self.assertRaises(DestinationValidationError): mutate_destination(context,action=action)
        query.execute.return_value=SimpleNamespace(data=dict(slug='valid',status='draft',token='secret'))
        with self.assertRaises(AdminPlacesError):
            mutate_destination(context,action='create',values=BASE,tourism_enabled=True)


class ManagementRouteTests(unittest.TestCase):
    setUp=foundation.AdminBoundaryTests.setUp
    tearDown=foundation.AdminBoundaryTests.tearDown
    protected=foundation.AdminBoundaryTests.protected

    def install(self):
        self.value=True
        self.records=[]
        self.operations=[]
        self.directory=overview()
        self.failure=False
        self.tick=0
        self.addCleanup(patch.stopall)
        patch.dict(os.environ,ROSAGO_TOURISM_METADATA_ENABLED='true').start()

        def respond(request):
            self.requests.append(request)
            if request.url.path.endswith('/rosago_is_admin'):
                return httpx.Response(200,json=self.value)
            if request.url.path == '/rest/v1/profiles':
                return httpx.Response(200,json=[])
            if request.url.path.endswith('/rosago_admin_operational_overview'):
                args=json.loads(request.content)
                result=json.loads(json.dumps(self.directory))
                result['users']=[u for u in result['users'] if args['p_query'].casefold() in
                    ((u['name'] or '')+' '+(u['email'] or '')).casefold()]
                result['users_matching']=len(result['users'])
                result['users']=result['users'][args['p_offset']:args['p_offset']+25]
                return httpx.Response(503,json={'message':'private-provider-detail'}) if self.failure else httpx.Response(200,json=result)
            if request.url.path.endswith('/rosago_admin_mutate_destination'):
                args=json.loads(request.content); self.operations.append(args)
                if self.failure: return httpx.Response(503,json={'message':'private-provider-detail'})
                action=args['p_action']; values=args['p_values']
                record=next((p for p in self.records if p['slug']==args['p_slug']),None)
                self.tick+=1
                stamp=(datetime(2026,11,1,tzinfo=timezone.utc)+timedelta(seconds=self.tick)).isoformat()
                if action=='create':
                    index=len(self.records)+1
                    record=dict(id=f'11111111-1111-4111-8111-{index:012}',
                        slug='fixture-destination' if index==1 else f'fixture-destination-{index}',
                        status='draft',image_url=None,environment=None,created_at=stamp,updated_at=stamp,
                        tourism_source=None,tourism_source_row=None)|values
                    self.records.append(record)
                elif not record or datetime.fromisoformat(args['p_expected_updated_at'])!=datetime.fromisoformat(record['updated_at']):
                    return httpx.Response(409,json={'message':'stale','code':'40001'})
                elif action=='edit': record.update(values)
                else: record['status']={'publish':'published','draft':'draft','archive':'archived','restore':'draft'}[action]
                record['updated_at']=stamp
                return httpx.Response(200,json=dict(slug=record['slug'],status=record['status']))
            self.assertEqual(request.url.path,'/rest/v1/places')
            params=request.url.params
            rows=self.records
            if 'status' in params: rows=[p for p in rows if 'eq.'+p['status']==params['status']]
            if 'slug' in params: rows=[p for p in rows if 'eq.'+p['slug']==params['slug']]
            if request.method=='HEAD': return httpx.Response(200,headers={'Content-Range':f'*/{len(rows)}'})
            projection=params['select'].split(',')
            return httpx.Response(200,json=[{k:p[k] for k in projection} for p in rows],headers={'Content-Range':f'*/{len(rows)}'})

        self.respond=respond
        def factory(**kwargs):
            client=httpx.Client(transport=httpx.MockTransport(respond),**kwargs); self.clients.append(client); return client
        self.dependencies.adapters._http_factory=factory
        handle=test_registration.seed_admin_session(self)
        self.csrf=self.dependencies.store.resolve(handle).csrf
        return handle

    def create(self,**changes):
        return self.client.post('/admin/places/new',data=BASE|dict(csrf_token=self.csrf)|changes,headers=ORIGIN)

    def version(self): return self.records[0]['updated_at']

    def transition(self,action):
        return self.client.post('/admin/places/fixture-destination/publication/'+action,
            data=dict(csrf_token=self.csrf,expected_updated_at=self.version()),headers=ORIGIN)

    def test_create_edit_and_full_publication_lifecycle(self):
        self.install()
        self.protected(self.create(),303)
        self.assertEqual(self.records[0]['status'],'draft')
        self.assertIsNone(self.records[0]['tourism_type'])
        data=BASE|dict(csrf_token=self.csrf,expected_updated_at=self.version(),name='Edited fixture',latitude='14.3',longitude='121.1',tourism_type='Local')
        self.protected(self.client.post('/admin/places/fixture-destination/edit',data=data,headers=ORIGIN),303)
        self.assertEqual(self.records[0]['name'],'Edited fixture')
        self.assertEqual(self.records[0]['tourism_type'],'Local')
        for action,status in (('publish','published'),('draft','draft'),('archive','archived'),('restore','draft')):
            self.protected(self.client.get('/admin/places/fixture-destination/publication/'+action),200)
            self.protected(self.transition(action),303)
            self.assertEqual(self.records[0]['status'],status)
        self.assertEqual([o['p_action'] for o in self.operations],['create','edit','publish','draft','archive','restore'])

    def test_direct_mutations_require_auth_membership_csrf_and_exact_origin(self):
        # Every mutation family must be denied before any destination read/write.
        paths=['/admin/places/new','/admin/places/fixture-destination/edit']+[
            '/admin/places/fixture-destination/publication/'+a for a in ('publish','draft','archive','restore')]
        for path in paths: self.protected(self.client.post(path,data={}),302)
        self.install(); self.value=False
        for path in paths: self.protected(self.client.post(path,data={}),403)
        self.value=True
        for path in paths:
            for headers in ({}, {'Origin':'null'}, {'Origin':'https://foreign.invalid'},ORIGIN):
                self.protected(self.client.post(path,data={'csrf_token':'wrong'},headers=headers),403)
        self.assertEqual(self.operations,[])
        self.assertFalse(any(r.url.path.endswith('/places') for r in self.requests))
        invalid=MultiDict(BASE|dict(csrf_token=self.csrf)); invalid.add('name','duplicate')
        self.protected(self.client.post('/admin/places/new',data=invalid,headers=ORIGIN),403)

    def test_invalid_creation_retains_values_and_never_calls_mutation(self):
        self.install()
        for changes in (dict(category='fake'),dict(latitude='14'),dict(tourism_type='local'),dict(name='')):
            response=self.create(**changes)
            self.protected(response,400)
            self.assertIn(b'role="alert"',response.data)
        self.assertEqual(self.operations,[])
        self.protected(self.create(status='published'),403)

    def test_stale_edit_does_not_refresh_submitted_version(self):
        self.install(); self.create(); old=self.version()
        self.transition('publish')
        response=self.client.post('/admin/places/fixture-destination/edit',data=BASE|dict(
            csrf_token=self.csrf,expected_updated_at=old),headers=ORIGIN)
        self.protected(response,503)
        self.assertEqual(Document(response.get_data(as_text=True)).find('input',name='expected_updated_at')[0].attrs['value'],old)
        self.assertEqual(self.records[0]['status'],'published')

    def test_confirmation_transitions_and_safe_failure(self):
        self.install(); self.create()
        response=self.client.get('/admin/places/fixture-destination/publication/publish')
        self.assertIn(b'This destination will become available to RosaGo users.',response.data)
        self.assertEqual(self.records[0]['status'],'draft')

        self.protected(self.transition('restore'),409)
        self.failure=True
        self.protected(self.transition('publish'),503)
        self.assertEqual(self.records[0]['status'],'draft')

    def test_same_record_propagates_to_public_catalog_map_and_recommendation_inputs(self):
        from places_client import PublicPlacesClient
        from recommendation_engine import rank_candidates
        from itinerary_selection_policy import select_destinations
        from test_recommendation_engine import preferences
        self.install(); self.create(latitude='14.3',longitude='121.1',tourism_type='Local')
        def factory(**kwargs):
            client=httpx.Client(transport=httpx.MockTransport(self.respond),**kwargs)
            self.clients.append(client)
            return client
        adapter=PublicPlacesClient('https://example.supabase.co','sb_publishable_fixture',http_factory=factory)
        service=PlacesService(adapter.database_client,tourism_metadata_enabled=True)
        self.app.extensions['rosago_places']=service
        for action,visible in ((None,False),('publish',True),('draft',False),('archive',False),('restore',False),('publish',True)):
            if action: self.protected(self.transition(action),303)
            # These are the shared read contracts used by Explore, details, maps,
            # Planner and recommendation candidate construction; no second store.
            rows=service.list_published(limit=100)
            ranked=rank_candidates(preferences(),rows)
            selected=select_destinations(preferences(),ranked.matched)
            place=service.get_published_by_slug('fixture-destination')
            self.assertEqual(bool(rows),visible)
            self.assertEqual(bool(selected),visible)
            self.assertEqual(place is not None,visible)
            explore=self.client.get('/places')
            self.assertEqual(explore.status_code,200)
            self.assertEqual(b'RosaGo Admin Verification Test' in explore.data,visible)
            detail=self.client.get('/places/fixture-destination')
            self.assertEqual(detail.status_code,200 if visible else 404)
            with self.app.test_request_context('/map'):
                markers=self.app.view_functions['map_index'].__globals__['_map_markers']()
            self.assertEqual(bool(markers),visible)
            if visible:
                self.assertEqual((place.id,place.latitude,place.longitude,place.tourism_type),
                    (self.records[0]['id'],14.3,121.1,'Local'))
                self.assertEqual(rows[0],place)

    def test_system_renders_existing_weather_snapshot_and_all_exposure_buckets(self):
        from weather_service import WeatherSnapshot, ForecastDay
        from datetime import date
        self.install(); self.create()
        stamp=datetime(2026,11,3,tzinfo=timezone(timedelta(hours=8)))
        snapshot=WeatherSnapshot(stamp,stamp,900,28.0,30.0,0,8.0,1,
            (ForecastDay(date(2026,11,3),1,24,31,20),))
        with patch.object(self.app.extensions['rosago_weather'],'get_weather',return_value=snapshot):
            response=self.client.get('/admin/system')
        self.protected(response,200)
        for phrase in (b'28.0',b'Indoor',b'Covered',b'Mixed',b'Outdoor',b'Unknown',b'20%'):
            self.assertIn(phrase,response.data)

    def test_users_search_pagination_privacy_and_no_account_actions(self):
        self.install()
        for path in ('/admin/users','/admin/trips','/admin/system'):
            self.value=False; self.protected(self.client.get(path),403)
        self.value=True
        response=self.client.get('/admin/users?q=FIXTURE')
        self.protected(response,200)
        self.assertIn(b'Fixture &lt;Admin&gt;',response.data)
        self.assertNotIn(b'No users found',response.data)
        self.assertIn(b'No users found',self.client.get('/admin/users?q=missing').data)
        self.directory['users_total']=self.directory['users_matching']=30
        self.directory['users']=[dict(overview()['users'][0],identifier=f'account-{i}') for i in range(30)]
        response=self.client.get('/admin/users?q=fixture')
        self.assertIn(b'q=fixture&amp;page=2',response.data)
        for field in (b'password_hash',b'access_token',b'recovery_token',b'Disable Account',b'Login As User'):
            self.assertNotIn(field,response.data)
        self.protected(self.client.post('/admin/users',data={}),405)
        self.protected(self.client.get('/admin/users?q=x&q=y'),400)

    def test_trip_aggregates_only_and_no_editing(self):
        self.install()
        response=self.client.get('/admin/trips'); self.protected(response,200)
        for phrase in (b'Popular Destinations',b'Based on saved trips',b'Upcoming trips'):
            self.assertIn(phrase,response.data)
        for private in (b'fixture@example.invalid',b'account-fixture',b'Fixture &lt;Admin&gt;',b'<textarea'):
            self.assertNotIn(private,response.data)
        self.protected(self.client.post('/admin/trips'),405)
        self.directory.update(trips_total=0,upcoming_trips=0,destinations_in_trips=0,popular=[],categories=[])
        self.assertIn(b'No saved trips are available',self.client.get('/admin/trips').data)

    def test_system_provider_failure_unknown_counts_and_safe_pages(self):
        self.install(); self.create()
        with patch.object(self.app.extensions['rosago_weather'],'get_weather',return_value=None):
            response=self.client.get('/admin/system')
        self.protected(response,200)
        for phrase in (b'Current weather is temporarily unavailable',b'Unknown',b'Weather exposure has not been verified',b'Open-Meteo',b'Gemini'):
            self.assertIn(phrase,response.data)
        self.assertIn(b'RosaGo Admin Verification Test',response.data)
        self.failure=True
        for path in ('/admin/users','/admin/trips'):
            response=self.client.get(path); self.protected(response,503)
            self.assertNotIn(b'private-provider-detail',response.data)


class ManagementMigrationTests(unittest.TestCase):
    def test_sql_authorization_privacy_lifecycle_and_audit_contract(self):
        root=Path(__file__).resolve().parents[1]
        sql=(root/'migrations/0012_admin_management.sql').read_text()
        self.assertEqual(sql.count('SECURITY DEFINER SET search_path'),2)
        self.assertEqual(sql.count('WHERE m.user_id = (SELECT auth.uid()) FOR SHARE'),2)
        self.assertIn('FOR UPDATE',sql)
        self.assertIn("ELSE 'draft' END",sql)
        self.assertNotIn('DELETE FROM',sql)
        self.assertNotIn('GRANT UPDATE',sql)
        self.assertNotIn('encrypted_password',sql)
        audit=(root/'migrations/0013_admin_destination_audit.sql').read_text()
        self.assertIn('REVOKE ALL ON FUNCTION public.rosago_admin_mutate_destination_unlogged',audit)
        self.assertIn('INSERT INTO public.admin_destination_audit',audit)
        self.assertIn("'submitted_fields'",audit)
        self.assertNotIn("'values',p_values",audit)
