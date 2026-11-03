"""Regression for the live stale-controller/current-template JSON failure."""
import json
import unittest
from dataclasses import replace
from types import SimpleNamespace
from flask import before_render_template
import test_alerts_routes as alerts
from test_public_layout import Document
from alerts_service import Alert
from user_features import notification_cards
from weather_service import WeatherService
import httpx

class AlertsLiveRegressionTests(unittest.TestCase):
    setUp=alerts.AlertsRouteTests.setUp
    tearDown=alerts.AlertsRouteTests.tearDown
    seed=alerts.AlertsRouteTests.seed

    def test_old_running_controller_omits_bootstrap_context_as_in_live_trace(self):
        def old_controller(sender,template,context,**extra):
            context.pop('notifications',None)
        with before_render_template.connected_to(old_controller,self.app):
            response=self.client.get('/user/alerts')
        self.assertEqual(response.status_code,200)
        page=Document(response.get_data(as_text=True))
        self.assertEqual(json.loads(page.find('script',id='notifications-data')[0].text),[])
        self.assertTrue(page.find('h2',id='notifications-title'))
        self.assertTrue(page.find('section',id='weather'))

    def test_null_and_empty_notifications_have_valid_json(self):
        for value in (None,[]):
            def null_controller(sender,template,context,**extra):context['notifications']=value
            with before_render_template.connected_to(null_controller,self.app):
                response=self.client.get('/user/alerts')
            self.assertEqual(response.status_code,200)
            page=Document(response.get_data(as_text=True))
            self.assertEqual(json.loads(page.find('script',id='notifications-data')[0].text),[])

    def test_one_malformed_notice_and_missing_destination_do_not_break_others(self):
        good=Alert('trip','info','Upcoming saved trip','',self.today_trip.visit_date,self.trip.id)
        bad_id=replace(good,trip_id='not-a-uuid')
        bad_trip=SimpleNamespace(id='not-a-uuid',name='Bad optional destination')
        with self.app.test_request_context('/user/alerts'):
            rows=notification_cards([None,SimpleNamespace(kind='trip',day=None),bad_id,good], [None,bad_trip,self.trip])
        self.assertEqual(len(rows),2)
        self.assertIsNone(rows[0]['url'])
        self.assertIsNone(rows[0]['action_label'])
        self.assertEqual(rows[1]['url'],'/user/trips/'+self.trip.id)
        json.dumps(rows)

    def test_notification_without_optional_action_renders_no_dead_button(self):
        def no_action(sender,template,context,**extra):
            context['notifications']=[dict(id='no-action',kind='trip',title='Trip reminder',name='Visit',day='2026-11-01',date_label='November 1',message='Review your trip.')]
        with before_render_template.connected_to(no_action,self.app):
            response=self.client.get('/user/alerts')
        self.assertEqual(response.status_code,200)
        page=Document(response.get_data(as_text=True))
        row=page.find('li',**{'data-notice-id':'no-action'})[0]
        self.assertFalse([n for n in page.find('a') if row in n.ancestors])

    def test_real_weather_provider_boundary_timeout_renders_trip_and_unavailable(self):
        service=WeatherService(http_factory=lambda **kwargs:httpx.Client(transport=httpx.MockTransport(lambda request: (_ for _ in ()).throw(httpx.ReadTimeout('fixture timeout'))),**kwargs))
        self.app.extensions['rosago_weather']=service
        response=self.client.get('/user/alerts')
        self.assertEqual(response.status_code,200)
        self.assertIn(b'Weather information is temporarily unavailable.',response.data)
        self.assertIn(b'Your trip is today',response.data)

    def test_no_trips_or_undated_trip_produces_no_trip_notification(self):
        self.upcoming.return_value=()
        self.assertEqual(self.client.get('/user/alerts').status_code,200)
        from alerts_service import trip_alerts
        self.assertEqual(trip_alerts((replace(self.trip,visit_date=None),),today=self.today_trip.visit_date),())
