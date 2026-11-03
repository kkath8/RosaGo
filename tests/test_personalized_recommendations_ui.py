"""New recommendation screen uses real protected route fixtures, no live writes."""
import unittest
from dataclasses import replace
import test_itinerary_recommendations as rec
from test_recommendation_engine import place
from test_public_layout import Document,assert_shared_scripts

class PersonalizedRecommendationsUiTests(unittest.TestCase):
 setUp=rec.RecommendationRouteTests.setUp
 tearDown=rec.RecommendationRouteTests.tearDown
 seed=rec.RecommendationRouteTests.seed
 def choices(self):
  self.read.side_effect=None
  prefs=self.draft.preferences|dict(interests=['shopping'],start_date='2026-11-01',end_date='2026-11-01',trip_pace='balanced')
  self.read.return_value=replace(self.draft,preferences=prefs)
  self.catalog.list_published.return_value=(replace(place(1,'shopping'),tourism_type='Common'),place(2,'shopping'),replace(place(5,'shopping'),tourism_type='Local'),replace(place(9,'heritage'),tourism_type='Local'))
 def test_default_selected_order_reasons_and_direct_preview_contract(self):
  self.choices();response=self.client.get(rec.ROUTE+'?stops=2');self.assertEqual(response.status_code,200)
  page=Document(response.get_data(as_text=True));form=page.find('form',id='personalized-recommendations')[0]
  self.assertTrue(form.attrs['action'].endswith('/preview'))
  inputs=page.find('input',name='selected_place_ids')
  self.assertEqual([n.attrs['value'] for n in inputs if 'checked' in n.attrs],[place(5).id,place(2).id])
  self.assertEqual([n.attrs['value'] for n in inputs if 'checked' not in n.attrs],[place(1).id])
  self.assertIn('identified as a Local destination',page.find('main')[0].text)
  self.assertIn('provides another shopping option',page.find('main')[0].text)
  self.assertEqual(len(page.find('button',type='submit')),3) # two primary actions and explicit count refinement
  self.assertEqual([n.text for n in page.find('strong',**{'data-selection-count':None})],['2 destinations selected']*2)
  self.assertEqual(len(page.find('li',**{'aria-current':'step'})),1)
  self.assertEqual(page.find('li',**{'aria-current':'step'})[0].text.strip(),'3 Recommendations')
  self.assertNotIn('Why recommended:',page.find('main')[0].text)
  self.assertNotIn('Explain with AI',page.find('main')[0].text)
  self.assertEqual(page.stack,[]);assert_shared_scripts(self,page)
 def test_count_validation_and_common_retained(self):
  self.choices()
  page=Document(self.client.get(rec.ROUTE+'?stops=3').get_data(as_text=True))
  self.assertEqual(len([n for n in page.find('input',name='selected_place_ids') if 'checked' in n.attrs]),3)
  for query in ('?stops=101','?stops=-1','?stops=01','?stops=2&stops=3','?stops=2.5','?stops='+'1'*5000):
   self.assertEqual(self.client.get(rec.ROUTE+query).status_code,400)
 def test_alternatives_are_bounded_and_never_outside_interests(self):
  self.choices();self.catalog.list_published.return_value=tuple(place(n,'shopping') for n in range(20))+(place(90,'heritage'),)
  page=Document(self.client.get(rec.ROUTE+'?stops=2').get_data(as_text=True))
  self.assertEqual(len(page.find('input',name='selected_place_ids')),8)
