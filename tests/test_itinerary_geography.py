"""Geographic set selection, coverage, missing data and visit sequencing."""
from dataclasses import replace
from itertools import permutations
import unittest

from itinerary_geography import coordinates, distance_km, order_places
from itinerary_selection_policy import select_destinations
from recommendation_engine import rank_candidates
from test_recommendation_engine import place, preferences


def located(n, lat, category='shopping', tourism_type=None):
    return replace(place(n, category), latitude=lat, longitude=121.0, tourism_type=tourism_type)


class GeographicSelectionTests(unittest.TestCase):
    def select(self, catalog, count=3, interests=None):
        prefs = preferences(interests=interests or ['shopping'])
        return select_destinations(prefs, rank_candidates(prefs, catalog).matched,
                                   places=catalog, place_count=count)

    def test_set_favors_nearby_alternatives_over_earlier_uuid(self):
        # A anchor, C earlier in UUID order, B/D close to A.
        catalog = (located(1, 14.3), located(2, 14.1), located(3, 14.301), located(4, 14.302))
        for shuffled in permutations(catalog):
            self.assertEqual([c.place_id for c in self.select(shuffled)],
                             [catalog[n].id for n in (0, 2, 3)])

    def test_mixed_interests_cover_categories_before_geography(self):
        catalog = (located(1, 14.3), located(2, 14.301), located(3, 14.302),
                   located(4, 14.1, 'heritage'), located(5, 14.11, 'dining'),
                   located(6, 14.12, 'nature'))
        selected = self.select(catalog, interests=['shopping', 'heritage', 'dining'])
        self.assertEqual({c.category for c in selected}, {'shopping', 'heritage', 'dining'})

    def test_tourism_priority_precedes_proximity(self):
        catalog = (located(1, 14.3, tourism_type='Local'),
                   located(2, 14.1, tourism_type='Local'),
                   located(3, 14.301), located(4, 14.302, tourism_type='Common'))
        selected = self.select(catalog, 2)
        self.assertEqual({c.place_id for c in selected}, {catalog[0].id, catalog[1].id})

    def test_missing_coordinates_keep_baseline_turn_and_eligibility(self):
        catalog = (located(1, 14.3), replace(located(2, 14.1), latitude=None, longitude=None),
                   located(3, 14.5), located(4, 14.301))
        self.assertEqual({c.place_id for c in self.select(catalog)},
                         {catalog[n].id for n in (0, 1, 3)})
        self.assertEqual(len(self.select(catalog, 4)), 4)
        missing = tuple(replace(p, latitude=None, longitude=None) for p in catalog)
        prefs = preferences(interests=['shopping'])
        ranked = rank_candidates(prefs, missing).matched
        self.assertEqual(select_destinations(prefs, ranked, places=missing, place_count=3), ranked[:3])

    def test_one_known_coordinate_falls_back_exactly(self):
        catalog = (located(1, 14.3), replace(located(2, 14.1), latitude=None, longitude=None))
        prefs = preferences(interests=['shopping'])
        ranked = rank_candidates(prefs, catalog).matched
        self.assertEqual(select_destinations(prefs, ranked, places=catalog, place_count=2),
                         select_destinations(prefs, ranked, place_count=2))

    def test_similar_branches_are_not_banned(self):
        catalog = tuple(replace(located(n, 14.3+n/10000), name=f'Same chain branch {n}')
                        for n in (1, 2, 3))
        self.assertEqual(len(self.select(catalog)), 3)

    def test_sequence_reduces_obvious_backtracking_and_keeps_unknown_slot(self):
        catalog = (located(1, 14.3), replace(located(2, 14.4), latitude=None, longitude=None),
                   located(3, 14.1), located(4, 14.299))
        self.assertEqual([p.id for p in order_places(catalog)],
                         [catalog[n].id for n in (0, 1, 3, 2)])

    def test_bad_pairs_are_never_used_as_locations(self):
        for lat, lon in ((None, 121), (14, None), (float('nan'), 121),
                         (91, 121), (14, 181), (True, 121), ('14', 121)):
            self.assertIsNone(coordinates(replace(place(), latitude=lat, longitude=lon)))
        self.assertAlmostEqual(distance_km((0, 0), (0, 1)), 111.19508, places=4)
