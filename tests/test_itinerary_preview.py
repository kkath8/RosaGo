"""Offline preview contract and frozen cross-language canonical/hash vectors."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta, timezone
import hashlib
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from place_model import Place
from itinerary_builder import build_itinerary, ItineraryBuildRequest
import itinerary_preview as preview


DRAFT_ID = 'aaaaaaaa-0000-0000-0000-000000000001'
# These are literal interoperability vectors, not outputs derived at test time.
CANONICAL_VECTOR = (
    '{"ascii":"RosaGo","booleans":[true,false],"date":"2026-10-19",'
    '"integer_budget":12500,"null_budget":null,"ordered":["b","a"],'
    '"time":"08:00:00","unicode":"Caf\u00e9 \u2014 \u6771\u4eac",'
    '"uuid":"00000000-0000-0000-0000-000000000001"}'
)
VECTOR_HASHES = {
    b'rosago:catalog:v1:': '101a836ec89878dd20e34ad2dbcac4f47ec488f8c6468ea129764dc05c71c363',
    b'rosago:source:v1:': '301a4896815976ad4945339f7cbac330b2e33703e50a5240b98dfd9ac36825ee',
    b'rosago:preview:v1:': '6e302874fc47bf1fd27407794d6c937ee530f7072559cb848953a46add32cc16',
}
CATALOG_VECTOR = (
    '[{"address":"Fixture address","category":"nature",'
    '"id":"00000000-0000-0000-0000-000000000001","is_test_record":false,'
    '"name":"Place 1","status":"published"}]'
)
CATALOG_VECTOR_HASH = '4bf99dffda4cae5ed902027fec541879c9664f25f3add88db977ae30b559c68e'
SOURCE_VECTOR = (
    '{"catalog_fingerprint":"4bf99dffda4cae5ed902027fec541879c9664f25f3add88db977ae30b559c68e",'
    '"draft_id":"aaaaaaaa-0000-0000-0000-000000000001","draft_revision":2,'
    '"recommendation_policy_version":"category-interest-v1",'
    '"selected_place_ids":["00000000-0000-0000-0000-000000000001"],"source_schema_version":1}'
)
SOURCE_VECTOR_HASH = '7f63a0d428d84de5e86a0f340d85fa0a109c5683cbe631d583507ce5e09f0a17'


def place(number=1):
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return Place(f'00000000-0000-0000-0000-{number:012x}', f'Place {number}', f'place-{number}',
                 'Untrusted description', 'nature', 'Fixture address', 14.0, 121.0, None, stamp, stamp)


def preferences(days=1, budget=None):
    start = date(2026, 10, 19)
    return dict(start_date=start.isoformat(), end_date=(start + timedelta(days=days - 1)).isoformat(),
                daily_start_time='08:00:00', daily_end_time='18:00:00', transportation='walking',
                trip_pace='balanced', timezone='Asia/Manila', budget_centavos=budget,
                interests=['nature'], companion_type='solo', other_interests='Unused',
                activity_preferences=['sightseeing'], environment_preference='mixed', additional_preferences=None)


def arguments(count=3, days=2, budget=None):
    places = tuple(place(n) for n in range(1, count + 1))
    return dict(preferences=preferences(days, budget), selected_places=places,
                selected_place_ids=tuple(p.id for p in places), draft_id=DRAFT_ID,
                draft_revision=2, publication_confirmed=True)


def fixture(**kwargs):
    return preview.build_personalized_preview(**arguments(**kwargs))


class ItineraryPreviewTests(unittest.TestCase):
    def invalid_document(self, document):
        with self.assertRaisesRegex(preview.PreviewContractError, '^Invalid itinerary preview contract.$'):
            preview.validate_preview(document)
        with self.assertRaises(preview.PreviewContractError):
            preview.compute_preview_digest(document)

    def test_one_multi_and_empty_day_roundtrips(self):
        for count, days, sizes in ((1, 1, [1]), (5, 2, [3, 2]), (2, 4, [1, 1, 0, 0])):
            value = fixture(count=count, days=days)
            doc = value.to_document()
            self.assertEqual(preview.validate_preview(doc), value)
            self.assertEqual(doc['preview_schema_version'], 1)
            self.assertEqual(doc['builder_policy_version'], 'preserve-order-equal-count-v1')
            self.assertEqual(doc['planning_mode'], 'personalized')
            self.assertEqual([len(day['stops']) for day in doc['days']], sizes)
            stops = [stop for day in doc['days'] for stop in day['stops']]
            self.assertEqual([s['place_id'] for s in stops], doc['source']['selected_place_ids'])
            self.assertEqual([s['order'] for s in stops], list(range(1, count + 1)))
            self.assertTrue(all(s['source'] == 'recommended' and s['keep_place'] is True for s in stops))
            self.assertTrue(all(set(s) == {'place_id', 'order', 'source', 'keep_place'} for s in stops))

    def test_adapter_maps_only_constraints_and_uses_builder(self):
        args = arguments(budget=12345)
        args['preferences'].update(transportation='ride_hailing', trip_pace='packed')
        with patch.object(preview, 'build_itinerary', wraps=build_itinerary) as builder:
            result = preview.build_personalized_preview(**args)
        supplied = builder.call_args_list[0].args[0]
        self.assertIsInstance(supplied, ItineraryBuildRequest)
        self.assertEqual(supplied.destinations[0].place, args['selected_places'][0])
        self.assertEqual(supplied.source_version, result.plan.source_version)
        self.assertEqual(supplied.constraints.start_date, date(2026, 10, 19))
        constraints = result.to_document()['constraints']
        self.assertEqual(constraints, {k: args['preferences'][k] for k in (
            'start_date', 'end_date', 'daily_start_time', 'daily_end_time', 'transportation',
            'trip_pace', 'timezone', 'budget_centavos')})
        opaque = dict(args['preferences'])
        for key in set(opaque) - set(constraints):
            opaque[key] = object()
        self.assertEqual(preview.build_personalized_preview(**(args | {'preferences': opaque})), result)
        self.assertIn('budget_feasibility', result.plan.unresolved_constraints)
        self.assertIsNone(fixture(budget=None).to_document()['constraints']['budget_centavos'])
        self.assertNotIn('budget_feasibility', fixture(budget=None).plan.unresolved_constraints)

    def test_explicit_selection_order_and_catalog_permutation(self):
        args = arguments()
        original = preview.build_personalized_preview(**args)
        permuted = preview.build_personalized_preview(**(args | {'selected_places': tuple(reversed(args['selected_places']))}))
        self.assertEqual(original, permuted)
        reversed_order = tuple(reversed(args['selected_place_ids']))
        changed = preview.build_personalized_preview(**(args | {'selected_place_ids': reversed_order}))
        self.assertEqual(changed.source.catalog_fingerprint, original.source.catalog_fingerprint)
        self.assertNotEqual(changed.plan.source_version, original.plan.source_version)
        self.assertEqual([s.place_id for d in changed.plan.days for s in d.stops], list(reversed_order))

    def test_catalog_relevant_changes_and_exact_test_rule(self):
        original = place()
        def fingerprint(p):
            return preview.compute_catalog_fingerprint((p,), publication_confirmed=True)
        baseline = fingerprint(original)
        for changed in (replace(original, name='Changed'), replace(original, address='Changed'),
                        replace(original, category='heritage'), replace(original, slug='rosago-test-v1-nature-01')):
            self.assertNotEqual(fingerprint(changed), baseline)
        for slug in ('rosago-test-v2-nature-01', 'not-rosago-test-v1-nature-01', 'other-slug'):
            self.assertEqual(fingerprint(replace(original, slug=slug)), baseline)
        test = replace(original, slug='rosago-test-v1-a')
        self.assertEqual(fingerprint(test), fingerprint(replace(test, slug='rosago-test-v1-b')))
        irrelevant = replace(original, description='Completely changed', image_url='https://example.invalid/new.png',
                             latitude=-45.0, longitude=-90.0, created_at=original.created_at + timedelta(days=1),
                             updated_at=original.updated_at + timedelta(days=1))
        self.assertEqual(fingerprint(irrelevant), baseline)

    def test_explicit_publication_fact_and_exact_selected_collection(self):
        args = arguments()
        for flag in (False, None, 1, 'published'):
            with self.assertRaises(preview.PreviewContractError):
                preview.build_personalized_preview(**(args | {'publication_confirmed': flag}))
        for places in ((), list(args['selected_places']), (place(), place()), (None,),
                       args['selected_places'] + (place(99),)):
            with self.assertRaises(preview.PreviewContractError):
                preview.build_personalized_preview(**(args | {'selected_places': places}))
        for ids in ((), list(args['selected_place_ids']), (place().id,) * 2, (place(99).id,)):
            with self.assertRaises(preview.PreviewContractError):
                preview.build_personalized_preview(**(args | {'selected_place_ids': ids}))

    def test_catalog_field_boundaries(self):
        for field, values in (('id', ('bad', place(15).id.upper())), ('category', ('bad', None)),
                              ('name', ('', ' padded ', 'a' * 151, '\ud800')),
                              ('address', ('', 'a' * 501)), ('slug', ('', 'Bad Slug', None))):
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(preview.PreviewContractError):
                    preview.compute_catalog_fingerprint((replace(place(), **{field: value}),), publication_confirmed=True)

    def test_source_bindings_change_independently(self):
        source = fixture().source
        original = preview.compute_source_version(source)
        self.assertEqual(original.kind, 'draft')
        self.assertRegex(original.version, r'^v1:[0-9a-f]{64}$')
        for change in ({'draft_id': place(99).id}, {'draft_revision': 3},
                       {'selected_place_ids': tuple(reversed(source.selected_place_ids))},
                       {'recommendation_policy_version': 'category-interest-v2'}, {'catalog_fingerprint': 'f' * 64}):
            self.assertNotEqual(preview.compute_source_version(replace(source, **change)), original)
        self.assertEqual(preview.compute_source_version(source), original)

    def test_source_manifest_is_strict_and_immutable(self):
        source = fixture().source
        for field, values in (('source_schema_version', (True, 2, '1')), ('draft_id', ('bad', DRAFT_ID.upper())),
                              ('draft_revision', (0, -1, True, 1.0, '2', 2 ** 63)),
                              ('selected_place_ids', ((), list(source.selected_place_ids), (place().id,) * 2)),
                              ('recommendation_policy_version', ('', 'Bad policy', 'a' * 65, None)),
                              ('catalog_fingerprint', ('a' * 63, 'A' * 64, 'g' * 64, None))):
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(preview.PreviewContractError):
                    replace(source, **{field: value})
        with self.assertRaises(FrozenInstanceError):
            source.draft_revision = 3

    def test_missing_and_unknown_fields_at_every_level(self):
        base = fixture().to_document()
        paths = ((), ('source',), ('source_version',), ('constraints',), ('days', 0), ('days', 0, 'stops', 0))
        for path in paths:
            original = base
            for key in path:
                original = original[key]
            for field in list(original) + ['invented']:
                doc = deepcopy(base)
                target = doc
                for key in path:
                    target = target[key]
                if field == 'invented':
                    target[field] = 'unsafe'
                else:
                    del target[field]
                self.invalid_document(doc)

    def test_wrong_versions_modes_source_and_primitive_types(self):
        for key, values in (('preview_schema_version', (True, 2, '1', None)),
                            ('builder_policy_version', ('unsupported', None)), ('planning_mode', ('manual', None)),
                            ('source_version', ({'kind': 'draft', 'version': 'v1:' + '0' * 64}, None)),
                            ('days', ([], {}, None)), ('unresolved_constraints', ([], ['weather'], None))):
            for value in values:
                doc = fixture().to_document(); doc[key] = value
                self.invalid_document(doc)

    def test_invalid_constraints_and_no_silent_date_normalization(self):
        for key, values in (('start_date', ('20261019', '2026-W43-1', 'bad', None)),
                            ('end_date', ('2026-10-18', '2026-10-26')),
                            ('daily_start_time', ('08:00', '18:00:00', '24:00:00', None)),
                            ('daily_end_time', ('08:00:00', '25:00:00')),
                            ('transportation', ('car', None)), ('trip_pace', ('fast', None)),
                            ('timezone', ('UTC', None)), ('budget_centavos', (True, 1.0, -1, 10000001))):
            for value in values:
                doc = fixture().to_document(); doc['constraints'][key] = value
                self.invalid_document(doc)

    def test_wrong_day_dates_counts_distribution_and_order(self):
        base = fixture(count=5, days=2).to_document()
        mutations = []
        doc = deepcopy(base); doc['days'].reverse(); mutations.append(doc)
        doc = deepcopy(base); doc['days'].pop(); mutations.append(doc)
        doc = deepcopy(base); doc['days'][1]['date'] = '2026-10-21'; mutations.append(doc)
        doc = deepcopy(base); doc['days'][1]['stops'].insert(0, doc['days'][0]['stops'].pop()); mutations.append(doc)
        doc = deepcopy(base); doc['days'][0]['stops'].reverse(); mutations.append(doc)
        for doc in mutations:
            self.invalid_document(doc)

    def test_invalid_stop_ids_flags_order_and_invented_fields(self):
        for key, values in (('place_id', ('bad', place(15).id.upper(), place(99).id)),
                            ('order', (0, 2, True, '1')), ('source', ('manual', 'unknown')),
                            ('keep_place', (False, 1, 'true'))):
            for value in values:
                doc = fixture().to_document(); doc['days'][0]['stops'][0][key] = value
                self.invalid_document(doc)
        doc = fixture().to_document()
        doc['days'][0]['stops'][1]['place_id'] = doc['days'][0]['stops'][0]['place_id']
        self.invalid_document(doc)
        for key in ('arrival_time', 'departure_time', 'visit_duration', 'travel_time', 'estimated_cost',
                    'route_distance', 'opening_status', 'weather'):
            doc = fixture().to_document(); doc['days'][0]['stops'][0][key] = None
            self.invalid_document(doc)

    def test_unresolved_exact_order_and_budget_dependency(self):
        for budget in (None, 0):
            base = fixture(budget=budget).to_document()
            for codes in (list(reversed(base['unresolved_constraints'])),
                          base['unresolved_constraints'] + ['weather'], base['unresolved_constraints'][:-1],
                          base['unresolved_constraints'] + [base['unresolved_constraints'][0]]):
                self.invalid_document(base | {'unresolved_constraints': codes})

    def test_arbitrary_plan_type_is_not_trusted(self):
        valid = fixture()
        plan = valid.plan
        changed_day = replace(plan.days[0], stops=plan.days[0].stops[:-1])
        for bad in (replace(plan, policy_version='wrong'), replace(plan, source_version=replace(plan.source_version, version='bad')),
                    replace(plan, days=(changed_day,) + plan.days[1:]), replace(plan, unresolved_constraints=()),
                    replace(plan, constraints=replace(plan.constraints, trip_pace='invalid')), None):
            with self.assertRaises(preview.PreviewContractError):
                preview.preview_from_plan(valid.source, bad)
        # A valid but changed builder constraint must not replace the adapter's input.
        def wrong_builder(request):
            return build_itinerary(replace(request, constraints=replace(request.constraints, trip_pace='packed')))
        with patch.object(preview, 'build_itinerary', side_effect=wrong_builder), self.assertRaises(preview.PreviewContractError):
            preview.build_personalized_preview(**arguments())

    def test_digest_complete_document_and_no_embedded_digest(self):
        value = fixture()
        document = value.to_document()
        digest = preview.compute_preview_digest(value)
        self.assertRegex(digest, r'^[0-9a-f]{64}$')
        self.assertEqual(digest, preview.compute_preview_digest(document))
        self.assertEqual(digest, hashlib.sha256(preview.PREVIEW_DOMAIN + preview.canonical_json(document)).hexdigest())
        self.assertNotIn('digest', document)
        self.assertNotIn('accepted_preview_digest', document)
        changed = fixture(budget=0)
        self.assertNotEqual(digest, preview.compute_preview_digest(changed))
        doc = deepcopy(document); doc['constraints']['budget_centavos'] = 0
        self.invalid_document(doc)  # unresolved codes must change too

    def test_canonical_cross_language_vectors(self):
        value = dict(uuid=place().id, unicode='Caf\u00e9 \u2014 \u6771\u4eac', time='08:00:00',
                     ordered=['b', 'a'], null_budget=None, integer_budget=12500,
                     date='2026-10-19', booleans=[True, False], ascii='RosaGo')
        actual = preview.canonical_json(value)
        self.assertEqual(actual, CANONICAL_VECTOR.encode('utf-8'))
        self.assertEqual((preview.CATALOG_DOMAIN, preview.SOURCE_DOMAIN, preview.PREVIEW_DOMAIN), tuple(VECTOR_HASHES))
        for prefix, expected in VECTOR_HASHES.items():
            self.assertEqual(hashlib.sha256(prefix + actual).hexdigest(), expected)
        self.assertEqual(preview.canonical_json({'z': {'z': 1, 'a': 2}, 'a': [2, 1]}), b'{"a":[2,1],"z":{"a":2,"z":1}}')
        self.assertEqual(preview.canonical_json({'escape': '"\\\n\t/'}), b'{"escape":"\\"\\\\\\n\\t/"}')

    def test_concrete_catalog_source_and_preview_golden_vectors(self):
        value = fixture(count=1, days=1)
        self.assertEqual(hashlib.sha256(preview.CATALOG_DOMAIN + CATALOG_VECTOR.encode('utf-8')).hexdigest(),
                         CATALOG_VECTOR_HASH)
        self.assertEqual(value.source.catalog_fingerprint, CATALOG_VECTOR_HASH)
        self.assertEqual(preview.canonical_json(value.to_document()['source']), SOURCE_VECTOR.encode('utf-8'))
        self.assertEqual(hashlib.sha256(preview.SOURCE_DOMAIN + SOURCE_VECTOR.encode('utf-8')).hexdigest(),
                         SOURCE_VECTOR_HASH)
        self.assertEqual(value.plan.source_version.version, 'v1:' + SOURCE_VECTOR_HASH)
        self.assertEqual(preview.compute_preview_digest(value),
                         '9d7c461b7c182a6789fd27d4bd9d8a3413b324bc5e74750833ed2b49bb09b8a2')

    def test_destination_limits_and_adapter_constraint_errors(self):
        value = fixture(count=100, days=7)
        self.assertEqual(sum(len(day.stops) for day in value.plan.days), 100)
        for count in (0, 101):
            with self.assertRaises(preview.PreviewContractError):
                fixture(count=count)
        for prefs in (None, {}, preferences() | {'trip_pace': 'wrong'},
                      preferences() | {'budget_centavos': True}):
            with self.assertRaises(preview.PreviewContractError):
                preview.build_personalized_preview(**(arguments() | {'preferences': prefs}))
        doc = fixture().to_document()
        doc['source']['selected_place_ids'][1] = doc['source']['selected_place_ids'][0]
        self.invalid_document(doc)

    def test_canonical_rejects_non_json_and_oversized_cyclic_input(self):
        cycle = []; cycle.append(cycle)
        for invalid in (1.0, float('nan'), float('inf'), {1: 'bad'}, ('tuple',), object(),
                        '\x00', '\ud800', 'a' * (preview.MAX_DOCUMENT_BYTES + 1), 2 ** 63, cycle):
            with self.assertRaises(preview.PreviewContractError):
                preview.canonical_json(invalid)

    def test_repeated_calls_permuted_keys_and_no_mutation(self):
        args = arguments(); before = deepcopy(args)
        value = preview.build_personalized_preview(**args)
        for _ in range(3):
            self.assertEqual(preview.build_personalized_preview(**args), value)
        self.assertEqual(args, before)
        doc = value.to_document(); original = deepcopy(doc)
        self.assertEqual(preview.validate_preview(dict(reversed(list(doc.items())))), value)
        self.assertEqual(doc, original)
        doc['days'].clear()
        self.assertNotEqual(doc, value.to_document())
        with self.assertRaises(FrozenInstanceError):
            value.source = None

    def test_isolated_import_and_execution_without_application_or_network(self):
        script = '''
import sys
class Guard:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'flask', 'supabase', 'postgrest', 'httpx', 'requests',
            'app', 'itinerary_draft_service', 'places_service', 'normal_auth_coordinator', 'google'}:
            raise AssertionError('Forbidden dependency')
sys.meta_path.insert(0, Guard())
def audit(event, args):
    if event.startswith('socket.'):
        raise AssertionError('Network forbidden')
sys.addaudithook(audit)
sys.path.insert(0, 'tests')
from test_itinerary_preview import fixture
from itinerary_preview import compute_preview_digest
assert len(compute_preview_digest(fixture())) == 64
'''
        result = subprocess.run([sys.executable, '-S', '-c', script],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
