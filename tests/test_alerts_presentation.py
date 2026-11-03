"""UX contracts over authenticated route fixtures and real weather data shapes."""
import json
import unittest
from dataclasses import replace
from datetime import timedelta
import test_alerts_routes as alerts
from test_public_layout import Document

class AlertsPresentationTests(unittest.TestCase):
    setUp = alerts.AlertsRouteTests.setUp
    tearDown = alerts.AlertsRouteTests.tearDown
    seed = alerts.AlertsRouteTests.seed
    def test_clear_destinations_shared_by_api_and_page_and_no_duplicates(self):
        weather=self.weather.get_weather.return_value
        self.weather.get_weather.return_value=replace(weather,precipitation_mm=2,
            forecast=(replace(weather.forecast[0],precipitation_probability=100),)+weather.forecast[1:])
        page=Document(self.client.get('/user/alerts').get_data(as_text=True))
        data=json.loads(page.find('script',id='notifications-data')[0].text)
        rows=self.client.get('/api/user/notices').json['notices']
        self.assertEqual(data,rows)
        trips=[n for n in rows if n['kind']=='trip']
        self.assertEqual(trips[0]['url'],'/user/trips/'+self.trip.id)
        self.assertEqual(trips[0]['action_label'],'View Trip')
        weather=[n for n in rows if n['kind']=='weather']
        self.assertEqual(len({n['day'] for n in weather}),len(weather))
        self.assertTrue(all(n['url']=='/user/alerts#weather' for n in weather))
        self.assertEqual(len(page.find('section',id='weather')),1)
        self.assertEqual(weather,[])  # Ordinary city weather does not notify.
        self.assertEqual(page.find('a',**{'class':'site-button'})[0].text,'View Trip')
        self.assertFalse(any(n.text=='Open' for n in page.find('a')))
        details=page.find('details',**{'class':'weather-about'})[0]
        self.assertNotIn('open',details.attrs)
        self.assertIn('Forecast retrieved',details.text)

    def test_future_outside_forecast_has_short_trip_message(self):
        self.upcoming.return_value=(replace(self.today_trip,visit_date=self.today_trip.visit_date+timedelta(days=6)),)
        page=Document(self.client.get('/user/alerts').get_data(as_text=True))
        card=page.find('article',**{'class':'trip-weather-card'})[0]
        self.assertIn('Forecast not available yet',card.text)
        self.assertNotIn('Forecast retrieved',card.text)
        self.assertEqual([n.attrs['href'] for n in page.find('a') if card in n.ancestors],['/user/trips/'+self.trip.id])

    def test_forecast_concern_notifies_only_for_a_saved_future_trip(self):
        self.upcoming.return_value=()
        self.assertEqual(self.client.get('/api/user/notices').json['notices'],[])
        tomorrow=self.today_trip.visit_date+timedelta(days=1)
        self.upcoming.return_value=(replace(self.today_trip,visit_date=tomorrow),)
        rows=self.client.get('/api/user/notices').json['notices']
        weather=[n for n in rows if n['kind']=='weather']
        self.assertEqual(len(weather),1)
        self.assertEqual(weather[0]['url'],'/user/trips/'+self.trip.id)
        self.assertEqual(weather[0]['action_label'],'View Trip')
        self.upcoming.return_value=(replace(self.today_trip,visit_date=tomorrow+timedelta(days=4)),)
        self.assertFalse([n for n in self.client.get('/api/user/notices').json['notices'] if n['kind']=='weather'])
