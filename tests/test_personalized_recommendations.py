"""Deterministic Local/NULL/Common priority without changing category eligibility."""
import unittest
from dataclasses import replace
from itertools import permutations
from recommendation_engine import rank_candidates,RecommendationInputError
from itinerary_selection_policy import select_destinations
from test_recommendation_engine import place,preferences

class TourismRecommendationTests(unittest.TestCase):
 def test_shopping_local_unknown_common_and_unmatched_local(self):
  local=replace(place(8,'shopping'),tourism_type='Local')
  unknown=place(4,'shopping')
  common=replace(place(1,'shopping'),tourism_type='Common')
  unrelated=replace(place(2,'heritage'),tourism_type='Local')
  prefs=preferences(interests=['shopping'],trip_pace='relaxed',start_date='2026-11-01',end_date='2026-11-01')
  for catalog in permutations((common,unknown,unrelated,local)):
   r=rank_candidates(prefs,catalog)
   self.assertEqual([c.place_id for c in r.matched],[local.id,unknown.id,common.id])
   self.assertEqual(r.unmatched[0].place_id,unrelated.id)
   self.assertTrue(all(c.deterministic_score==1 for c in r.matched))
   self.assertEqual([c.place_id for c in select_destinations(prefs,r.matched,place_count=1)],[local.id])
   self.assertEqual([c.place_id for c in select_destinations(prefs,r.matched,place_count=3)],[local.id,unknown.id,common.id])
  self.assertIsNone(unknown.tourism_type)
 def test_mixed_interests_keep_variety_and_requested_count(self):
  places=(replace(place(9,'shopping'),tourism_type='Local'),replace(place(8,'shopping'),tourism_type='Local'),replace(place(1,'dining'),tourism_type='Common'),replace(place(3,'nature'),tourism_type='Local'))
  prefs=preferences(interests=['shopping','dining'],start_date='2026-11-01',end_date='2026-11-01',trip_pace='balanced')
  r=rank_candidates(prefs,places)
  self.assertEqual([c.place_id for c in select_destinations(prefs,r.matched,place_count=1)],[places[1].id])
  selected=select_destinations(prefs,r.matched,place_count=2)
  self.assertEqual(len(selected),2)
  self.assertEqual({c.category for c in selected},{'shopping','dining'})
  self.assertNotIn(places[3].id,[c.place_id for c in selected])
 def test_invalid_classification_is_not_inferred(self):
  for value in ('local','Common-ish',[],False):
   with self.assertRaises(RecommendationInputError):rank_candidates(preferences(),[replace(place(),tourism_type=value)])
 def test_legacy_preview_policy_is_still_readable(self):
  import test_itinerary_preview as fixtures
  import itinerary_preview as preview
  old=preview.build_personalized_preview(**fixtures.arguments(count=1,days=1),recommendation_policy_version='category-interest-v1')
  self.assertEqual(preview.validate_preview(old.to_document()).source.recommendation_policy_version,'category-interest-v1')

 def test_ranking_revision_preserves_deployed_preview_wire_contract(self):
  import test_itinerary_preview as fixtures
  import itinerary_preview as preview
  from recommendation_engine import POLICY_VERSION
  document=preview.build_personalized_preview(**fixtures.arguments(count=1,days=1)).to_document()
  self.assertEqual(POLICY_VERSION,'category-interest-tourism-v2')
  self.assertEqual(document['source']['recommendation_policy_version'],'category-interest-v1')
