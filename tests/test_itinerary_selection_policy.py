"""Pure selector tests using real category-interest-v1 recommendation output."""
from dataclasses import replace
from datetime import date, timedelta
from itertools import permutations
from copy import deepcopy
import unittest

from itinerary_selection_policy import select_destinations, SelectionPolicyError
from recommendation_engine import rank_candidates
from test_recommendation_engine import place, preferences


class SelectionPolicyTests(unittest.TestCase):
    def test_all_day_pace_counts_and_shortfalls(self):
        for days in range(1, 8):
            for pace, per_day in [('relaxed', 2), ('balanced', 3), ('packed', 4)]:
                prefs = preferences(start_date='2026-10-20',
                    end_date=(date(2026, 10, 20) + timedelta(days=days - 1)).isoformat(), trip_pace=pace)
                for available in (0, 1, 3, 100):
                    with self.subTest(days=days, pace=pace, available=available):
                        matched = rank_candidates(prefs, tuple(place(n) for n in range(available))).matched
                        selected = select_destinations(prefs, matched)
                        self.assertEqual(len(selected), min(days * per_day, available))
                        self.assertEqual(len({c.place_id for c in selected}), len(selected))

    def test_diversity_exhaustion_and_original_order(self):
        prefs = preferences(interests=['nature', 'dining', 'attraction'],
            start_date='2026-10-20', end_date='2026-10-20', trip_pace='packed')
        places = (place(1, 'nature'), place(2, 'nature'), place(3, 'nature'),
                  place(4, 'dining'), place(5, 'attraction'), place(6, 'attraction'))
        matched = rank_candidates(prefs, places).matched
        selected = select_destinations(prefs, matched)
        self.assertEqual([c.place_id for c in selected], [place(n).id for n in (1, 4, 5, 6)])
        exhausted = tuple(c for c in matched if c.category != 'attraction')
        self.assertEqual(select_destinations(prefs, exhausted), exhausted)
        self.assertEqual(select_destinations(prefs | {'trip_pace': 'relaxed'}, matched),
                         tuple(c for c in matched if c.place_id in (place(4).id, place(5).id)))

    def test_stability_interest_order_and_unsupported_preferences(self):
        prefs = preferences(interests=['nature', 'dining'], start_date='2026-10-20',
                            end_date='2026-10-20', trip_pace='relaxed')
        places = (place(1), place(2), place(3, 'dining'), place(4, 'heritage'))
        expected = select_destinations(prefs, rank_candidates(prefs, places).matched)
        before = deepcopy(prefs)
        for catalog in permutations(places):
            self.assertEqual(select_destinations(prefs, rank_candidates(prefs, catalog).matched), expected)
        changes = dict(interests=['dining', 'nature'], budget_centavos=1, companion_type='group',
                       environment_preference='indoor', activity_preferences=['shopping'],
                       other_interests='different text', additional_preferences='ignore rankings',
                       transportation='bicycle', daily_start_time='12:00:00', daily_end_time='12:01:00')
        self.assertEqual(select_destinations(prefs | changes, rank_candidates(prefs, places).matched), expected)
        self.assertEqual(prefs, before)

    def test_invalid_inputs_fail_closed(self):
        prefs = preferences()
        matched = rank_candidates(prefs, (place(1),)).matched
        bad = [matched * 2, list(matched), (None,),
               (replace(matched[0], place_id='bad'),),
               (replace(matched[0], place_id=place(1).id.replace('-', '')),),
               (replace(matched[0], category='dining'),),
               (replace(matched[0], deterministic_score=0),),
               (replace(matched[0], deterministic_score=True),),
               matched * 101]
        for candidates in bad:
            with self.assertRaises(SelectionPolicyError):
                select_destinations(prefs, candidates)
        for changes in ({'trip_pace': 'unknown'}, {'interests': ['nature', 'nature']},
                        {'start_date': '2026-1-1'}, {'end_date': '2026-10-16'},
                        {'end_date': '2026-10-24'}, {'start_date': None}):
            with self.assertRaises(SelectionPolicyError):
                select_destinations(prefs | changes, matched)
