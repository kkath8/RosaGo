"""Dialog transport uses existing protected trip operations; no external I/O."""
from dataclasses import replace
import unittest
from unittest.mock import Mock
from werkzeug.datastructures import MultiDict
import test_trip_routes as trips
from trip_service import TripNotFoundError, TripOperationRejectedError, TripUnavailableError
from test_public_layout import Document

JSON = {'Accept': 'application/json', 'Origin': 'http://localhost'}


class TripChooserTests(unittest.TestCase):
    tearDown = trips.TripRouteTests.tearDown
    seed = trips.TripRouteTests.seed
    setup_add_place = trips.TripRouteTests.setup_add_place

    def setUp(self):
        trips.TripRouteTests.setUp(self)
        self.data = self.setup_add_place()

    def test_json_choices_owned_sanitized_and_no_default_or_mutation(self):
        response = self.client.get(self.add_path, headers=JSON)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['trips'], [dict(id=trips.TRIP, name=self.trip.name, date_label='Jan 02, 2020')])
        self.assertEqual(response.json['csrf_token'], self.csrf)
        self.assertEqual(response.json['place']['name'], self.place.name)
        self.assertEqual(response.json['new_url'], '/user/trips/new?add_place=synthetic-place')
        self.assertIsNone(response.json['next_url'])
        self.assertNotIn('selected_trip', response.json)
        self.assertIn('no-store', response.headers['Cache-Control'])
        self.services['list_user_trips'].assert_called_once()
        self.services['add_place'].assert_not_called()
        for secret in (trips.OWNER, self.handle, 'private-access', 'private-refresh'):
            self.assertNotIn(secret, response.get_data(as_text=True))

    def test_separate_trip_name_date_and_no_initial_selection_in_fallback(self):
        page = Document(self.client.get(self.add_path).get_data(as_text=True))
        row = page.find('label', **{'class': 'trip-choice'})[0]
        name = [node for node in page.find('strong') if row in node.ancestors][0]
        date = [node for node in page.find('span', **{'class':'trip-choice-date'}) if row in node.ancestors][0]
        self.assertNotEqual(name, date)
        self.assertEqual(name.text, self.trip.name)
        self.assertEqual(date.text, 'Jan 02, 2020')
        self.assertNotIn('checked', page.find('input', name='trip_id')[0].attrs)

    def test_selection_required_before_place_or_trip_access(self):
        for data in ({'csrf_token':self.csrf}, self.data | {'trip_id':''}):
            self.assertEqual(self.client.post(self.add_path, headers=JSON, data=data).status_code, 400)
        self.catalog.get_published_by_slug.assert_not_called()
        self.services['get_user_trip'].assert_not_called()
        self.services['add_place'].assert_not_called()

    def test_selected_owned_trip_success_uses_existing_rpc_adapter_once(self):
        other = 'aaaaaaaa-0000-0000-0000-000000000005'
        self.services['get_user_trip'].side_effect = None
        self.services['get_user_trip'].return_value = replace(self.detail, trip=replace(self.trip, id=other, name='My second trip'))
        response = self.client.post(self.add_path, headers=JSON, data=self.data | {'trip_id':other})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['message'], 'Added <script>Place</script> to My second trip.')
        self.assertEqual(response.json['trip_id'], other)
        self.services['add_place'].assert_called_once()
        self.assertEqual(self.services['add_place'].call_args.args[1:], (other,self.place.id))
        self.assertNotIn('Location', response.headers)

    def test_duplicate_is_confirmed_from_owned_memberships_without_retry(self):
        self.services['add_place'].side_effect = TripOperationRejectedError()
        duplicate = replace(self.detail, memberships=(replace(self.detail.memberships[0], place_id=self.place.id),), next_after_position=None)
        self.services['get_user_trip'].side_effect = [replace(self.detail, next_after_position=3), duplicate]
        response = self.client.post(self.add_path, headers=JSON, data=self.data)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json['message'], 'This destination is already in My <trip>.')
        self.services['add_place'].assert_called_once()
        self.assertEqual(self.services['get_user_trip'].call_args.kwargs, {'after_position':3})

    def test_foreign_trip_and_unpublished_place_prevent_write(self):
        self.services['get_user_trip'].side_effect = None
        self.services['get_user_trip'].return_value = None
        self.assertEqual(self.client.post(self.add_path, headers=JSON, data=self.data).status_code,404)
        self.services['add_place'].assert_not_called()
        self.services['get_user_trip'].reset_mock()
        self.catalog.get_published_by_slug.return_value = None
        self.assertEqual(self.client.get(self.add_path,headers=JSON).status_code,404)
        self.assertEqual(self.client.post(self.add_path,headers=JSON,data=self.data).status_code,404)
        self.services['get_user_trip'].assert_not_called()

    def test_csrf_origin_exact_fields_and_login_continuation_preserved(self):
        for data,headers,status in [(self.data|{'csrf_token':'wrong'},JSON,403),
                (self.data,JSON|{'Origin':'https://foreign.invalid'},403),
                (self.data|{'place_id':self.place.id},JSON,400),
                (MultiDict(list(self.data.items())+[('trip_id',trips.TRIP)]),JSON,400)]:
            self.assertEqual(self.client.post(self.add_path,headers=headers,data=data).status_code,status)
        self.services['add_place'].assert_not_called()
        with self.client.session_transaction() as session:
            session.clear()
        response = self.client.get(self.add_path,headers=JSON)
        self.assertEqual(response.status_code,302)
        self.assertEqual(response.location,'/login?login_required=1&add_place=synthetic-place')

    def test_trip_creation_json_and_fallback_destination_continuation(self):
        response = self.client.get('/user/trips/new?add_place=synthetic-place')
        self.assertIn(b'action="/user/trips?add_place=synthetic-place"',response.data)
        data = dict(csrf_token=self.csrf,name='Real trip',visit_date='')
        response = self.client.post('/user/trips',headers=JSON,data=data)
        self.assertEqual(response.status_code,201)
        self.assertEqual(response.json['trip']['id'],trips.TRIP)
        response = self.client.post('/user/trips?add_place=synthetic-place',data=data)
        self.assertEqual((response.status_code,response.location),(303,self.add_path))
        response = self.client.post('/user/trips?add_place=https://evil.invalid',data=data)
        self.assertEqual(response.location,trips.DETAIL)

    def test_create_validation_retains_context_and_mutation_failure_not_retried(self):
        data = dict(csrf_token=self.csrf,name='Real trip',visit_date='bad')
        response = self.client.post('/user/trips?add_place=synthetic-place',data=data)
        self.assertEqual(response.status_code,400)
        self.assertIn(b'action="/user/trips?add_place=synthetic-place"',response.data)
        self.services['create_trip'].assert_not_called()
        self.services['add_place'].side_effect = TripUnavailableError()
        self.assertEqual(self.client.post(self.add_path,headers=JSON,data=self.data).status_code,503)
        self.services['add_place'].assert_called_once()

    def test_paginated_choices_keep_date_unset_and_dont_mutate(self):
        self.services['list_user_trips'].side_effect = None
        self.services['list_user_trips'].return_value = (replace(self.trip,visit_date=None),)*50
        response = self.client.get(self.add_path,headers=JSON)
        self.assertEqual(response.json['next_url'],self.add_path+'?offset=50')
        self.assertEqual(response.json['trips'][0]['date_label'],'Date not set')
        self.services['add_place'].assert_not_called()
