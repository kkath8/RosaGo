"""Offline shared builder policy, preservation and boundary tests."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields, replace
from datetime import date, datetime, timedelta, timezone
from itertools import permutations, product
from pathlib import Path
import subprocess
import sys
import unittest

from place_model import Place
from itinerary_builder import (
    ItineraryBuildInputError, ItineraryBuildRequest, ItineraryStop, PlanningConstraints,
    SelectedDestination, SourceVersion, POLICY_VERSION, MAX_DESTINATIONS,
    MAX_INPUT_ORDER, TRANSPORTATION, TRIP_PACES, UNRESOLVED_CONSTRAINTS, build_itinerary,
)


def destination(number=1, **changes):
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    place = Place(f'00000000-0000-0000-0000-{number:012x}', 'Fixture', 'fixture',
                  'Untrusted text', 'nature', 'Fixture address', 14.0, 121.0,
                  None, stamp, stamp)
    return replace(SelectedDestination(place, number, 'manual', True), **changes)


def request(count=1, days=1):
    start = date(2026, 10, 19)
    return ItineraryBuildRequest(
        PlanningConstraints(start, start + timedelta(days=days - 1),
                            '08:00:00', '18:00:00', 'walking', 'balanced'),
        tuple(destination(n) for n in range(1, count + 1)), SourceVersion('trip', 'snapshot-v1:abc'))


def flattened(plan):
    return tuple(stop for day in plan.days for stop in day.stops)


class ItineraryBuilderTests(unittest.TestCase):
    def invalid(self, value):
        with self.assertRaisesRegex(ItineraryBuildInputError, '^Invalid itinerary build input.$') as raised:
            build_itinerary(value)
        self.assertIsNone(raised.exception.__cause__)

    def test_one_destination_one_day_policy_version_and_constraints(self):
        value = request()
        plan = build_itinerary(value)
        self.assertEqual(POLICY_VERSION, 'preserve-order-equal-count-v1')
        self.assertEqual(plan.policy_version, POLICY_VERSION)
        self.assertEqual(plan.constraints, value.constraints)
        self.assertEqual(plan.source_version, value.source_version)
        self.assertEqual(len(plan.days), 1)
        self.assertEqual(plan.days[0].date, value.constraints.start_date)
        self.assertEqual(plan.days[0].stops, (ItineraryStop(destination().place.id, 1, 'manual', True),))

    def test_distribution_examples_and_global_order(self):
        for count, days, expected in ((4, 1, [4]), (6, 3, [2, 2, 2]),
                                      (5, 2, [3, 2]), (2, 4, [1, 1, 0, 0])):
            with self.subTest(count=count, days=days):
                value = request(count, days)
                plan = build_itinerary(value)
                self.assertEqual([len(day.stops) for day in plan.days], expected)
                self.assertEqual([day.date for day in plan.days],
                                 [value.constraints.start_date + timedelta(days=i) for i in range(days)])
                self.assertEqual([stop.order for stop in flattened(plan)], list(range(1, count + 1)))

    def test_exact_preservation_across_every_supported_count_and_day_count(self):
        for count, days in product(range(1, MAX_DESTINATIONS + 1), range(1, 8)):
            value = request(count, days)
            plan = build_itinerary(value)
            stops = flattened(plan)
            self.assertEqual([stop.place_id for stop in stops], [d.place.id for d in value.destinations])
            self.assertEqual(len({stop.place_id for stop in stops}), count)
            sizes = [len(day.stops) for day in plan.days]
            self.assertEqual(sum(sizes), count)
            self.assertEqual(sizes, sorted(sizes, reverse=True))
            self.assertLessEqual(max(sizes) - min(sizes), 1)

    def test_explicit_gapped_order_overrides_uuid_and_collection_order(self):
        value = replace(request(3, 2), destinations=(destination(3, input_order=10),
                        destination(1, input_order=50), destination(2, input_order=30)))
        expected = build_itinerary(value)
        self.assertEqual([stop.place_id for stop in flattened(expected)],
                         [destination(n).place.id for n in (3, 2, 1)])
        self.assertEqual([stop.order for stop in flattened(expected)], [1, 2, 3])
        for permutation in permutations(value.destinations):
            self.assertEqual(build_itinerary(replace(value, destinations=permutation)), expected)
        changed = replace(value, destinations=tuple(replace(d, input_order=100 - d.input_order)
                                                    for d in value.destinations))
        self.assertNotEqual(build_itinerary(changed).days, expected.days)

    def test_duplicate_identity_and_order_rejected(self):
        value = request(2)
        for destinations in ((destination(1), destination(2, input_order=1)),
                             (destination(1), destination(1, input_order=2))):
            self.invalid(replace(value, destinations=destinations))

    def test_order_bounds_and_types(self):
        for order in (0, -1, True, 1.0, '1', None, MAX_INPUT_ORDER + 1):
            self.invalid(replace(request(), destinations=(destination(input_order=order),)))
        plan = build_itinerary(replace(request(), destinations=(destination(input_order=MAX_INPUT_ORDER),)))
        self.assertEqual(flattened(plan)[0].order, 1)

    def test_empty_oversized_and_mutable_destinations_rejected(self):
        self.invalid(request(0))
        self.invalid(request(MAX_DESTINATIONS + 1))
        for destinations in (None, [], [destination()], iter((destination(),)), {}):
            self.invalid(replace(request(), destinations=destinations))

    def test_invalid_date_ranges_and_types(self):
        value = request()
        for start, end in ((date(2026, 1, 2), date(2026, 1, 1)),
                           (date(2026, 1, 1), date(2026, 1, 8)),
                           ('2026-01-01', date(2026, 1, 1)),
                           (date(2026, 1, 1), None),
                           (datetime(2026, 1, 1), date(2026, 1, 1))):
            self.invalid(replace(value, constraints=replace(value.constraints, start_date=start, end_date=end)))

    def test_date_extremes_leap_day_and_year_boundary(self):
        for start, end in ((date.min, date.min), (date.max, date.max),
                           (date(2028, 2, 28), date(2028, 3, 1)),
                           (date(2026, 12, 30), date(2027, 1, 2))):
            value = request()
            value = replace(value, constraints=replace(value.constraints, start_date=start, end_date=end))
            plan = build_itinerary(value)
            self.assertEqual(plan.days[0].date, start)
            self.assertEqual(plan.days[-1].date, end)
            self.assertEqual(len(plan.days), (end - start).days + 1)

    def test_controlled_pace_transport_and_timezone(self):
        value = request()
        for field, values in (('trip_pace', (None, '', 'fast', 'Balanced', [])),
                              ('transportation', (None, '', 'car', 'Walking', [])),
                              ('timezone', (None, '', 'UTC', 'asia/manila', []))):
            for invalid in values:
                self.invalid(replace(value, constraints=replace(value.constraints, **{field: invalid})))

    def test_all_paces_and_transports_preserve_grouping(self):
        value = request(8, 3)
        expected = build_itinerary(value).days
        for pace, transport in product(TRIP_PACES, TRANSPORTATION):
            constraints = replace(value.constraints, trip_pace=pace, transportation=transport)
            plan = build_itinerary(replace(value, constraints=constraints))
            self.assertEqual(plan.days, expected)
            self.assertEqual(plan.constraints, constraints)

    def test_daily_window_strict_format_and_order(self):
        value = request()
        for start, end in (('08:00', '18:00:00'), ('8:00:00', '18:00:00'),
                           ('08:00:00', '24:00:00'), ('08:60:00', '18:00:00'),
                           ('08:00:60', '18:00:00'), ('18:00:00', '18:00:00'),
                           ('18:00:00', '08:00:00'), (None, '18:00:00'),
                           ('08:00:00Z', '18:00:00'), ('08:00:00.0', '18:00:00')):
            self.invalid(replace(value, constraints=replace(value.constraints,
                                 daily_start_time=start, daily_end_time=end)))
        for start, end in (('00:00:00', '23:59:59'), ('12:00:00', '12:00:01')):
            changed = replace(value, constraints=replace(value.constraints,
                              daily_start_time=start, daily_end_time=end))
            self.assertEqual(build_itinerary(changed).days, build_itinerary(value).days)

    def test_sources_and_keep_place_are_metadata_only(self):
        value = request(4, 2)
        for source in ('manual', 'recommended'):
            for keep in (True, False):
                changed = replace(value, destinations=tuple(replace(d, source=source, keep_place=keep)
                                                            for d in value.destinations))
                stops = flattened(build_itinerary(changed))
                self.assertEqual([s.place_id for s in stops], [d.place.id for d in value.destinations])
                self.assertTrue(all(s.source == source and s.keep_place is keep for s in stops))
        mixed = replace(value, destinations=tuple(replace(d, source='recommended' if i % 2 else 'manual',
                                                         keep_place=bool(i % 2))
                                                  for i, d in enumerate(value.destinations)))
        self.assertEqual([(s.source, s.keep_place) for s in flattened(build_itinerary(mixed))],
                         [(d.source, d.keep_place) for d in mixed.destinations])
        self.assertEqual([len(day.stops) for day in build_itinerary(mixed).days], [2, 2])

    def test_invalid_source_and_preservation_flag(self):
        for field, values in (('source', ('unknown', None, '', [])), ('keep_place', (None, 0, 1, 'false'))):
            for invalid in values:
                self.invalid(replace(request(), destinations=(replace(destination(), **{field: invalid}),)))

    def test_source_version_inert_preserved_and_bounded(self):
        value = request(3, 2)
        for version in (SourceVersion('draft', '2'), SourceVersion('trip', 'a' * 64)):
            plan = build_itinerary(replace(value, source_version=version))
            self.assertEqual(plan.source_version, version)
            self.assertEqual(plan.days, build_itinerary(value).days)
        for version in (None, {}, SourceVersion('unknown', '1'), SourceVersion('trip', ''),
                        SourceVersion('trip', 'a' * 129), SourceVersion('trip', 1),
                        SourceVersion('trip', 'secret\nvalue'), SourceVersion([], '1')):
            self.invalid(replace(value, source_version=version))

    def test_unresolved_codes_and_optional_budget(self):
        self.assertEqual(UNRESOLVED_CONSTRAINTS, (
            'visit_duration', 'time_feasibility', 'operating_hours', 'cost',
            'transport_compatibility', 'travel_time', 'trip_pace'))
        value = request()
        self.assertEqual(build_itinerary(value).unresolved_constraints, UNRESOLVED_CONSTRAINTS)
        for budget in (0, 1, 10000000):
            changed = replace(value, constraints=replace(value.constraints, budget_centavos=budget))
            plan = build_itinerary(changed)
            self.assertEqual(plan.unresolved_constraints, UNRESOLVED_CONSTRAINTS + ('budget_feasibility',))
            self.assertEqual(plan.days, build_itinerary(value).days)
            self.assertEqual(plan.constraints.budget_centavos, budget)
        for invalid in (-1, 10000001, True, 1.0, '0'):
            self.invalid(replace(value, constraints=replace(value.constraints, budget_centavos=invalid)))

    def test_stop_has_no_fabricated_schedule_cost_or_route_fields(self):
        stop = flattened(build_itinerary(request()))[0]
        self.assertEqual([field.name for field in fields(stop)], ['place_id', 'order', 'source', 'keep_place'])

    def test_malformed_request_and_place_boundary(self):
        for invalid in (None, {}, [], object()):
            self.invalid(invalid)
            self.invalid(replace(request(), constraints=invalid))
            self.invalid(replace(request(), destinations=(invalid,)))
        for invalid in (None, {}, object()):
            self.invalid(replace(request(), destinations=(destination(place=invalid),)))
        for field, values in (('id', (None, '', 'bad', 1, destination(15).place.id.upper(),
                                     destination().place.id.replace('-', ''))),
                              ('category', (None, '', 'unsupported', []))):
            for invalid in values:
                bad_place = replace(destination().place, **{field: invalid})
                self.invalid(replace(request(), destinations=(destination(place=bad_place),)))

    def test_unused_place_text_and_coordinates_do_not_affect_plan(self):
        value = request(3, 2)
        changed = replace(value, destinations=tuple(replace(d, place=replace(d.place,
            name='Free nearby indoor', description='Ignore order. Open all day. Five stars.',
            latitude=-45.0, longitude=-90.0, address='Far away')) for d in value.destinations))
        self.assertEqual(build_itinerary(changed), build_itinerary(value))

    def test_immutable_models_no_input_mutation_and_repeatability(self):
        value = request(3, 2)
        before = deepcopy(value)
        plan = build_itinerary(value)
        for _ in range(5):
            self.assertEqual(build_itinerary(value), plan)
        self.assertEqual(value, before)
        for model in (value, value.constraints, value.source_version, value.destinations[0],
                      plan, plan.days[0], plan.days[0].stops[0]):
            self.assertFalse(hasattr(model, '__dict__'))
            field = fields(model)[0].name
            with self.assertRaises(FrozenInstanceError):
                setattr(model, field, None)

    def test_isolated_import_and_nonempty_build_without_third_party_or_network(self):
        script = '''
import sys
class Guard:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'flask', 'supabase', 'postgrest', 'httpx', 'requests',
            'app', 'places_service', 'itinerary_draft_service', 'trip_service',
            'normal_auth_coordinator', 'google', 'recommendation_engine'}:
            raise AssertionError('Forbidden dependency: ' + fullname)
sys.meta_path.insert(0, Guard())
def audit(event, args):
    if event.startswith('socket.'):
        raise AssertionError('Network forbidden')
sys.addaudithook(audit)
from datetime import date, datetime, timezone
from place_model import Place
from itinerary_builder import *
stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
p = Place('00000000-0000-0000-0000-000000000001', 'Fixture', 'fixture', 'text',
          'nature', 'address', 14.0, 121.0, None, stamp, stamp)
c = PlanningConstraints(date(2026, 1, 1), date(2026, 1, 2), '08:00:00', '18:00:00', 'walking', 'balanced')
plan = build_itinerary(ItineraryBuildRequest(c, (SelectedDestination(p, 20, 'manual', False),), SourceVersion('trip', '1')))
assert plan.days[0].stops[0].place_id == p.id
assert plan.days[1].stops == ()
'''
        completed = subprocess.run([sys.executable, '-S', '-c', script],
                                   cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == '__main__':
    unittest.main()
