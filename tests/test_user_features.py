"""New feature boundaries with real auth scopes and forbidden external I/O."""
from dataclasses import replace
from unittest.mock import Mock, patch
from werkzeug.datastructures import MultiDict
import unittest
import test_trip_routes as trips
from test_recommendation_engine import place
from trip_service import TripDetail, TripPlace, TripUnavailableError
from test_public_layout import Document
import test_itinerary_preview_routes as previews


class UserFeatureTests(unittest.TestCase):
    seed = trips.TripRouteTests.seed
    tearDown = trips.TripRouteTests.tearDown

    def setUp(self):
        trips.TripRouteTests.setUp(self)
        self.place = place(4)
        self.catalog = Mock(list_published=Mock(return_value=(self.place,)))
        self.app.extensions['rosago_places'] = self.catalog
        self.form = MultiDict(dict(csrf_token=self.csrf, name='Day trip', visit_date='', selected_place_ids=self.place.id))

    def test_public_utilities_render_and_catalog_hides_internal_records_and_provenance(self):
        self.catalog.list_published.return_value = (self.place,replace(place(5),slug='rosago-test-v1-private'))
        for path in ('/saved','/visited','/budget','/help','/not-a-route'):
            response = self.client.get(path)
            self.assertEqual(response.status_code,404 if path=='/not-a-route' else 200)
            page=Document(response.get_data(as_text=True))
            self.assertEqual(len(page.find('h1')),1)
            self.assertEqual(page.stack,[])
        response=self.client.get('/api/places')
        self.assertEqual(response.status_code,200)
        self.assertEqual([p['id'] for p in response.json['places']],[self.place.id])
        self.assertNotIn('provenance',response.get_data(as_text=True))
        self.assertNotIn('tourism_source',response.get_data(as_text=True))
        self.assertEqual(response.json['places'][0]['exposure'],'unknown')
        self.assertEqual(response.headers['Cache-Control'],'no-store')

    def test_weather_strip_reuses_real_service_and_has_explicit_unavailable_state(self):
        from weather_service import parse_weather
        from test_weather_service import weather_payload, NOW
        service=Mock(get_weather=Mock(return_value=parse_weather(weather_payload(),now=NOW)))
        self.app.extensions['rosago_weather']=service
        with self.client.session_transaction() as session:session.clear()
        response=self.client.get('/api/weather')
        self.assertEqual(response.status_code,200)
        self.assertFalse(response.json['sample'])
        self.assertEqual(response.json['temperature_c'],29.5)
        self.assertEqual(len(response.json['forecast']),3)
        service.get_weather.return_value=None
        response=self.client.get('/api/weather')
        self.assertEqual(response.status_code,503)
        self.assertNotIn('forecast',response.json)

    def test_bag_requires_auth_csrf_exact_form_and_published_unique_ids(self):
        path='/user/bag'
        for fields,code in ((self.form|{'csrf_token':'bad'},403), (self.form|{'extra':'x'},400),
                            (self.form|{'selected_place_ids':'bad'},400),
                            (self.form|{'selected_place_ids':place(99).id},409)):
            self.assertEqual(self.client.post(path,data=fields).status_code,code)
        duplicate=MultiDict(self.form);duplicate.add('selected_place_ids',self.place.id)
        self.assertEqual(self.client.post(path,data=duplicate).status_code,400)
        self.assertEqual(self.client.post(path,data=self.form,headers={'Origin':'https://evil.invalid'}).status_code,403)
        self.services['create_trip'].assert_not_called()
        with self.client.session_transaction() as session:session.clear()
        self.assertEqual(self.client.post(path,data=self.form).status_code,302)
        self.assertEqual(self.client.get('/api/user/trips').status_code,302)

    def test_bag_saves_real_trip_and_reports_partial_write_without_retry(self):
        response=self.client.post('/user/bag',data=self.form)
        self.assertEqual((response.status_code,response.location),(303,trips.DETAIL+'?notice=saved'))
        self.services['create_trip'].assert_called_once()
        self.assertEqual(self.services['add_place'].call_args.args[1:],(trips.TRIP,self.place.id))
        self.services['add_place'].side_effect=TripUnavailableError()
        response=self.client.post('/user/bag',data=self.form)
        self.assertEqual(response.location,trips.DETAIL+'?notice=partial')
        self.assertEqual(self.services['create_trip'].call_count,2)
        self.assertEqual(self.services['add_place'].call_count,2)

    def test_reorder_reads_all_owned_pages_and_calls_existing_rpc_adapter(self):
        other=place(6).id
        members=(TripPlace(trips.TRIP,self.place.id,1,self.trip.created_at,None),TripPlace(trips.TRIP,other,2,self.trip.created_at,None))
        self.services['get_user_trip'].side_effect=[TripDetail(self.trip,members,2),TripDetail(self.trip,(),None)]
        with patch('user_features.reorder_places') as reorder:
            response=self.client.post(trips.DETAIL+'/move-place',data={'csrf_token':self.csrf,'place_id':other,'direction':'up'})
        self.assertEqual(response.status_code,303)
        self.assertEqual(reorder.call_args.args[1:],(trips.TRIP,[other,self.place.id]))
        self.assertEqual([c.kwargs for c in self.services['get_user_trip'].call_args_list],
            [dict(membership_limit=100,after_position=0),dict(membership_limit=100,after_position=2)])

    def test_remove_csrf_before_existing_owned_service(self):
        with patch('user_features.remove_place') as remove:
            path=trips.DETAIL+'/remove-place'
            self.assertEqual(self.client.post(path,data={'csrf_token':'bad','place_id':self.place.id}).status_code,403)
            remove.assert_not_called()
            self.assertEqual(self.client.post(path,data={'csrf_token':self.csrf,'place_id':self.place.id}).status_code,303)
            self.assertEqual(remove.call_args.args[1:],(trips.TRIP,self.place.id))

    def test_duplicate_requires_csrf_owned_published_complete_membership(self):
        path=trips.DETAIL+'/duplicate'
        self.assertEqual(self.client.post(path,data={'csrf_token':'bad'}).status_code,403)
        self.services['get_user_trip'].assert_not_called()
        member=TripPlace(trips.TRIP,self.place.id,1,self.trip.created_at,self.place)
        self.services['get_user_trip'].side_effect=None
        self.services['get_user_trip'].return_value=TripDetail(self.trip,(member,),None)
        response=self.client.post(path,data={'csrf_token':self.csrf})
        self.assertEqual(response.location,trips.DETAIL+'?notice=saved')
        self.assertEqual(self.services['create_trip'].call_args.kwargs['name'],self.trip.name+' copy')
        self.assertEqual(self.services['add_place'].call_args.args[1:],(trips.TRIP,self.place.id))
        self.services['create_trip'].reset_mock()
        self.catalog.list_published.return_value=()
        self.assertEqual(self.client.post(path,data={'csrf_token':self.csrf}).status_code,409)
        self.services['create_trip'].assert_not_called()
        self.services['get_user_trip'].return_value=None
        self.assertEqual(self.client.post(path,data={'csrf_token':self.csrf}).status_code,404)


class SavePreviewTests(unittest.TestCase):
    seed = trips.TripRouteTests.seed
    protected = trips.TripRouteTests.protected
    assert_context = previews.PreviewRouteTests.assert_context
    read_current = previews.PreviewRouteTests.read_current
    store_preview = previews.PreviewRouteTests.store_preview
    edit_preview = previews.PreviewRouteTests.edit_preview

    def setUp(self):
        previews.PreviewRouteTests.setUp(self)
        previews.PreviewRouteTests.ready(self)
        self.path='/user/itinerary/'+trips.TRIP+'/save-trip'
        self.form={'csrf_token':self.csrf,'expected_revision':'3','name':'My preview trip'}

    def tearDown(self):
        trips.TripRouteTests.tearDown(self)

    def test_preview_saves_current_owned_published_manifest_through_trip_services(self):
        response=self.client.post(self.path,data=self.form)
        self.assertEqual((response.status_code,response.location),(303,trips.DETAIL+'?notice=saved'))
        self.assertEqual(self.services['add_place'].call_args.args[1:],(trips.TRIP,self.match.id))
        self.store.assert_not_called()
        self.edit.assert_not_called()

    def test_changed_revision_catalog_or_unpublished_place_never_creates_trip(self):
        self.assertEqual(self.client.post(self.path,data=self.form|{'expected_revision':'2'}).status_code,409)
        self.catalog.list_published.return_value=(replace(self.match,name='Changed'),)
        self.assertEqual(self.client.post(self.path,data=self.form).status_code,409)
        self.catalog.list_published.return_value=()
        self.assertEqual(self.client.post(self.path,data=self.form).status_code,409)
        self.services['create_trip'].assert_not_called()

    def test_csrf_foreign_origin_and_missing_owned_preview_block_writes(self):
        self.assertEqual(self.client.post(self.path,data=self.form|{'csrf_token':'bad'}).status_code,403)
        self.assertEqual(self.client.post(self.path,data=self.form,headers={'Origin':'https://evil.invalid'}).status_code,403)
        self.current=None
        self.assertEqual(self.client.post(self.path,data=self.form).status_code,404)
        self.services['create_trip'].assert_not_called()
