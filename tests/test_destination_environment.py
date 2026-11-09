"""Phase 1A offline contracts: no production SQL, Storage, or destination writes."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx
from werkzeug.datastructures import MultiDict

from admin_management_service import BASIC_FIELDS, validate_destination, DestinationValidationError
from place_model import CATEGORIES, ENVIRONMENTS
from places_client import PublicPlacesClient
from places_service import PlacesService, parse_place_row, PlacesConsistencyError
from recommendation_engine import rank_candidates
import test_admin_management as management
import test_places_service as public_tests
from test_public_layout import Document
from test_recommendation_engine import place, preferences
from test_admin_photo_sql import function_body, parse_sql_json, parse_plpgsql_json
BASE, ORIGIN = management.BASE, management.ORIGIN

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / 'migrations/0014_destination_environment.sql'
OMITTED = object()


class EnvironmentValidationTests(unittest.TestCase):
    def test_read_model_supports_legacy_null_and_rejects_unknown_classifications(self):
        row = public_tests.PlacesServiceTests.row()
        self.assertIsNone(parse_place_row(row).environment)
        for value in (None, *ENVIRONMENTS):
            self.assertEqual(parse_place_row(row | {'environment': value}).environment, value)
        for value in ('covered', 'indoor', '', 'Not recorded', False, {}):
            with self.subTest(value=value), self.assertRaises(PlacesConsistencyError):
                parse_place_row(row | {'environment': value})

    def test_optional_null_and_exact_three_values(self):
        self.assertEqual(ENVIRONMENTS, ('Indoor', 'Outdoor', 'Mix of Both'))
        self.assertNotIn('environment', validate_destination(BASE, tourism_enabled=True))
        for value in (None, *ENVIRONMENTS):
            result = validate_destination(BASE | {'environment': value}, tourism_enabled=True)
            self.assertEqual(result['environment'], value)
        for value in ('', 'indoor', 'covered', 'Unknown', 'Indoor ', 'Not recorded', True, 1, [], {}):
            with self.subTest(value=value), self.assertRaises(DestinationValidationError):
                validate_destination(BASE | {'environment': value}, tourism_enabled=True)

    def test_seven_categories_and_rankings_remain_independent_of_environment(self):
        self.assertEqual(CATEGORIES, frozenset(('attraction','dining','shopping','accommodation','nature','heritage','industrial')))
        places = [place(i + 1, category) for i, category in enumerate(sorted(CATEGORIES))]
        baseline = rank_candidates(preferences(), places)
        for value in ENVIRONMENTS:
            self.assertEqual(rank_candidates(preferences(), [replace(p, environment=value) for p in places]), baseline)


class EnvironmentRouteTests(unittest.TestCase):
    setUp = management.ManagementRouteTests.setUp
    tearDown = management.ManagementRouteTests.tearDown
    protected = management.ManagementRouteTests.protected
    version = management.ManagementRouteTests.version
    transition = management.ManagementRouteTests.transition

    def install(self):
        management.ManagementRouteTests.install(self)
        patch.dict(os.environ, ROSAGO_DESTINATION_ENVIRONMENT_ENABLED='true').start()
        def factory(**kwargs):
            client = httpx.Client(transport=httpx.MockTransport(self.respond), **kwargs)
            self.clients.append(client)
            return client
        public = PublicPlacesClient('https://example.supabase.co', 'sb_publishable_fixture', http_factory=factory)
        self.app.extensions['rosago_places'] = PlacesService(public.database_client,
            tourism_metadata_enabled=True, environment_enabled=True)

    def save(self, value=OMITTED, *, edit=False, **changes):
        data = BASE | {'csrf_token': self.csrf} | changes
        if value is not OMITTED:
            data['environment'] = '' if value is None else value
        if edit:
            data.setdefault('expected_updated_at', self.version())
        return self.client.post('/admin/places/fixture-destination/edit' if edit else '/admin/places/new',
            data=data, headers=ORIGIN, content_type='multipart/form-data')

    def test_create_each_value_and_omitted_creation_defaults_to_null(self):
        self.install()
        for value in (*ENVIRONMENTS, None, OMITTED):
            self.protected(self.save(value), 303)
            self.assertEqual(self.records[-1]['environment'], None if value is OMITTED else value)
            self.assertEqual(self.records[-1]['status'], 'draft')
            self.assertIsNone(self.records[-1]['image_url'])
            if value is OMITTED:
                self.assertNotIn('environment', self.operations[-1]['p_values'])

    def test_form_choices_saved_value_and_null_placeholder(self):
        self.install()
        page = Document(self.client.get('/admin/places/new').get_data(as_text=True))
        select = page.find('select', id='environment')[0]
        self.assertNotIn('disabled', select.attrs)
        options = [n for n in page.find('option') if select in n.ancestors]
        self.assertEqual([(n.attrs['value'], n.text) for n in options],
            [('', 'Not recorded')] + [(v, v) for v in ENVIRONMENTS])
        self.protected(self.save('Mix of Both'), 303)
        response = self.client.get('/admin/places/fixture-destination/edit')
        self.protected(response, 200)
        selected = Document(response.get_data(as_text=True)).find('option', value='Mix of Both')[0]
        self.assertIn('selected', selected.attrs)
        self.assertIn(b'Environment', self.client.get('/admin/places/fixture-destination').data)

    def test_edit_clear_and_user_synchronization_preserve_other_fields_and_photo(self):
        self.install(); self.protected(self.save('Indoor'), 303)
        self.protected(self.transition('publish'), 303)
        photo = 'https://example.supabase.co/storage/v1/object/public/destination-images/destinations/' + 'a' * 32 + '.png'
        self.records[0]['image_url'] = photo
        original = deepcopy(self.records[0])
        with patch('admin_routes.upload_photo', side_effect=AssertionError('Environment edit must not upload')):
            for value in ('Outdoor', 'Mix of Both', None):
                self.protected(self.save(value, edit=True), 303)
                self.assertEqual(self.operations[-1]['p_values']['environment'], value)
                self.assertNotIn('image_url', self.operations[-1]['p_values'])
                for key, before in original.items():
                    if key not in ('environment', 'updated_at'):
                        self.assertEqual(self.records[0][key], before, key)
                public = self.client.get('/api/places')
                self.assertEqual(public.status_code, 200)
                self.assertEqual(public.json['places'][0]['environment'], value)
                self.assertEqual(public.json['places'][0]['image_url'], photo)
                self.assertEqual(public.json['places'][0]['exposure'], 'unknown')
                detail = self.client.get('/places/fixture-destination')
                self.assertEqual(detail.status_code, 200)
                self.assertIn(('<th scope="row">Environment</th><td>' + (value or 'Not recorded') + '</td>').encode(), detail.data)
                self.assertIn(photo.encode(), detail.data)
        self.protected(self.transition('archive'), 303)
        self.assertEqual(self.client.get('/places/fixture-destination').status_code, 404)
        self.assertEqual(self.client.get('/api/places').json['places'], [])

    def test_omitted_edit_preserves_saved_environment(self):
        self.install(); self.protected(self.save('Mix of Both'), 303)
        self.protected(self.save(edit=True, name='Renamed fixture'), 303)
        self.assertEqual(self.records[0]['environment'], 'Mix of Both')
        self.assertNotIn('environment', self.operations[-1]['p_values'])

    def test_environment_does_not_depend_on_tourism_rollout(self):
        self.install()
        with patch.dict(os.environ, ROSAGO_TOURISM_METADATA_ENABLED='false'):
            data = {key: BASE[key] for key in BASIC_FIELDS}
            data.update(csrf_token=self.csrf, environment='Outdoor')
            self.protected(self.client.post('/admin/places/new', data=data, headers=ORIGIN), 303)
            self.protected(self.client.get('/admin/places/fixture-destination/edit'), 200)
            self.assertEqual(self.records[0]['environment'], 'Outdoor')
            self.assertNotIn('tourism_type', self.operations[-1]['p_values'])

    def test_invalid_values_are_rejected_without_mutations(self):
        self.install()
        for value in ('indoor', 'covered', 'Not recorded', 'Outdoor ', '<script>'):
            self.protected(self.save(value), 400)
        self.assertEqual(self.records, [])
        self.assertEqual(self.operations, [])

    def test_admin_csrf_origin_exact_fields_and_concurrency_remain_enforced(self):
        self.install(); self.protected(self.save('Indoor'), 303)
        self.protected(self.save('Outdoor', edit=True, csrf_token='invalid'), 403)
        self.value = False
        self.protected(self.save('Outdoor', edit=True), 403)
        self.value = True
        data = MultiDict(BASE | {'csrf_token': self.csrf, 'environment': 'Indoor'})
        data.add('environment', 'Outdoor')
        self.protected(self.client.post('/admin/places/new', data=data, headers=ORIGIN), 403)
        self.protected(self.client.post('/admin/places/new', data=BASE | {'csrf_token': self.csrf,
            'environment': 'Outdoor'}, headers={'Origin': 'https://foreign.invalid'}), 403)
        self.protected(self.save('Outdoor', edit=True, status='published'), 403)
        original = deepcopy(self.records[0])
        self.protected(self.save('Outdoor', edit=True, expected_updated_at='2020-01-01T00:00:00+00:00'), 503)
        self.assertEqual(self.records[0], original)
        with self.client.session_transaction(path='/admin') as session:
            session.clear()
        self.protected(self.save('Outdoor', edit=True), 302)

    def test_disabled_rollout_preserves_legacy_contract_and_does_not_read_new_column(self):
        self.install()
        with patch.dict(os.environ, ROSAGO_DESTINATION_ENVIRONMENT_ENABLED='false'):
            page = Document(self.client.get('/admin/places/new').get_data(as_text=True))
            self.assertIn('disabled', page.find('select', id='environment')[0].attrs)
            self.protected(self.save('Indoor'), 403)
            self.protected(self.save(), 303)
            self.assertNotIn('environment', self.operations[-1]['p_values'])
            self.protected(self.client.get('/admin/places/fixture-destination/edit'), 200)
            # Simulate the actual pre-migration table: the column is absent.
            self.records[0].pop('environment')
            self.records[0]['status'] = 'published'
            legacy = self.app.extensions['rosago_places']
            self.app.extensions['rosago_places'] = PlacesService(legacy._clients, tourism_metadata_enabled=True)
            response = self.client.get('/api/places')
            self.assertEqual(response.status_code, 200)
            self.assertIsNone(response.json['places'][0]['environment'])
            self.assertTrue(all('environment' not in r.url.params.get('select', '').split(',')
                for r in self.requests if r.method == 'GET'))

    def test_environment_write_uses_each_authenticated_admin_context_not_client_actor_fields(self):
        self.install()
        import admin_routes
        with patch('admin_routes.mutate_destination', wraps=admin_routes.mutate_destination) as mutation:
            self.protected(self.save('Indoor'), 303)
            self.assertEqual(mutation.call_args.args[0].user_id, 'user-123')
            other = self.dependencies.store.create(user_id='22222222-2222-4222-8222-222222222222',
                user_email='other@example.invalid', access_token='fixture-second-admin',
                refresh_token='fixture-second-refresh', access_expires_at=2000000000,
                session_id='fixture-second-session')
            with self.client.session_transaction(path='/admin') as session:
                session['auth_session_id'] = other
            self.csrf = self.dependencies.store.resolve(other).csrf
            self.protected(self.save('Outdoor', edit=True), 303)
            self.assertEqual(mutation.call_args.args[0].user_id, '22222222-2222-4222-8222-222222222222')
        rpc = [r for r in self.requests if r.url.path.endswith('/rosago_admin_mutate_destination')]
        self.assertEqual([r.headers['authorization'] for r in rpc], ['Bearer fixture-access', 'Bearer fixture-second-admin'])
        self.assertTrue(all(set(args) == {'p_action','p_slug','p_expected_updated_at','p_values'} for args in self.operations))


class EnvironmentSQLTests(unittest.TestCase):
    def test_guarded_additive_migration_keeps_photo_body_except_environment(self):
        sql = MIGRATION.read_text(encoding='utf-8')
        original = function_body((ROOT / 'tools/admin_destination_photo_contract.sql').read_text(encoding='utf-8'))
        updated = function_body(sql)
        restored = updated.replace("'image_url','environment',", "'image_url',", 1)
        start = restored.index('        -- Optional Environment')
        end = restored.index('        tourism_fields :=', start)
        restored = restored[:start] + restored[end:]
        start = restored.index("        IF p_values ? 'environment' THEN")
        end = restored.index('        IF tourism_fields THEN\n            UPDATE', start)
        restored = restored[:start] + restored[end:]
        self.assertEqual(restored, original)
        self.assertIn(hashlib.md5(original.encode()).hexdigest(), sql)
        self.assertIn(hashlib.md5(updated.encode()).hexdigest(), sql)
        self.assertIn('4cab3fdc6baf75133fd19b8f1dde6345', sql)
        self.assertIn('ADD COLUMN environment text', sql)
        self.assertIn("environment IN ('Indoor','Outdoor','Mix of Both')", sql)
        self.assertEqual(sql.count('CREATE OR REPLACE FUNCTION'), 1)
        function_start = sql.index('CREATE OR REPLACE FUNCTION')
        function_end = sql.index('$$;', sql.index('AS $$', function_start)) + 3
        outside_function = sql[:function_start] + sql[function_end:]
        self.assertNotRegex(outside_function, r'(?im)^\s*(GRANT|REVOKE|DROP|DELETE|INSERT|UPDATE|CREATE TABLE)\b')
        self.assertNotIn('SET NOT NULL', sql)
        self.assertNotIn('ADD COLUMN IF NOT EXISTS', sql)
        # Wrapper remains untouched; actor comes from authenticated auth.uid().
        wrapper = (ROOT / 'migrations/0013_admin_destination_audit.sql').read_text()
        self.assertIn('VALUES ((SELECT auth.uid()),p_action,target_id,', wrapper)

    @unittest.skipIf(parse_sql_json is None, 'pglast is not installed')
    def test_prepared_sql_and_plpgsql_parse_offline(self):
        sql = MIGRATION.read_text(encoding='utf-8')
        parse_sql_json(sql)
        parse_plpgsql_json(sql)


if __name__ == '__main__':
    unittest.main()
